"""Test Module 6 adapters using fake controllers and DAQ functions exclusively.

Author: Yuxin Jiang
Email: yj546@cornell.edu

The new legacy-driver method is extracted as AST and run with fake DAQ bindings;
the instrument module, vendor libraries, UI, and physical devices are not loaded.
"""

import ast
import ctypes
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
import warnings
from unittest.mock import patch

import numpy as np

from experiment.scan_1d import ScanSettings, StageBounds, ScanStatus, load_scan, scan_1d
from experiment.scan_adapters import NIReflectionReader, PriorStageAdapter


class Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def time(self):
        return 1700000000 + self.now

    def sleep(self, duration):
        self.now += duration


class Controller:
    def __init__(self):
        self.commands = []
        self.position = (100, -100)
        self.busy = '0'
        self.status = 0

    def message(self, command):
        self.commands.append(command)
        if self.status:
            return self.status, 'fake error'
        if command == 'controller.stage.position.get':
            return 0, ','.join(map(str, self.position))
        if command == 'controller.stage.busy.get':
            return 0, self.busy
        if command.startswith('controller.stage.goto-position '):
            self.position = tuple(map(int, command.split()[-2:]))
        return 0, ''


class AnalogInput:
    def __init__(self):
        self.calls = []
        self.data = [[3, -3], [4, -4]]

    def acquire_bounded(self, count, *, timeout_s):
        self.calls.append((count, timeout_s))
        return self.data


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.controller = Controller()
        self.bounds = StageBounds(90, 110, -110, -90, 'unchanged-test-frame')
        self.stage = PriorStageAdapter(self.controller, bounds=self.bounds, clock=self.clock)
        self.analog = AnalogInput()
        self.reader = NIReflectionReader(self.analog, sample_number=2,
                                         channel_limits=((-10, 10), (-10, 10)), clock=self.clock)

    def test_construction_is_inert(self):
        self.assertEqual(self.controller.commands, [])
        self.assertEqual(self.analog.calls, [])

    def test_stage_mapping_and_coordinates(self):
        self.assertEqual(self.stage.get_position(timeout_s=1), (100, -100))
        for reply in ('0', '1', '2', '3'):
            self.controller.busy = reply
            self.assertEqual(self.stage.is_busy(timeout_s=1), reply != '0')
        self.controller.busy = '0'
        self.stage.move_to(101, -99, timeout_s=1)
        self.assertEqual(self.controller.commands[-1], 'controller.stage.goto-position 101 -99')

    def test_reject_fractional_and_out_of_bounds_before_commands(self):
        for x in (100.2, 111, float('nan')):
            with self.assertRaises(ValueError):
                self.stage.move_to(x, -100, timeout_s=1)
        self.assertEqual(self.controller.commands, [])

    def test_reject_unsafe_approach_and_busy(self):
        self.controller.position = (89, -100)
        with self.assertRaises(ValueError):
            self.stage.move_to(100, -100, timeout_s=1)
        self.controller.busy = '1'
        with self.assertRaises(RuntimeError):
            self.stage.move_to(100, -100, timeout_s=1)
        self.assertFalse(any('goto-position' in c for c in self.controller.commands))

    def test_sdk_failure_latches_movement_but_stop_remains_available(self):
        self.controller.status = -7
        with self.assertRaisesRegex(RuntimeError, 'status=-7'):
            self.stage.get_position(timeout_s=1)
        self.controller.status = 0
        with self.assertRaisesRegex(RuntimeError, 'faulted'):
            self.stage.move_to(100, -100, timeout_s=1)
        self.stage.stop(timeout_s=1)
        self.assertEqual(self.controller.commands[-2:], ['controller.stop.smoothly', 'controller.stage.busy.get'])

    def test_malformed_busy_position_and_status(self):
        for reply, operation in (((0, '4'), 'is_busy'), ((0, 'nan,0'), 'get_position'),
                                 ((0, '1,2,3'), 'get_position'), (('0', '0'), 'is_busy')):
            with self.subTest(reply=reply):
                with patch.object(self.controller, 'message', return_value=reply):
                    with self.assertRaises(RuntimeError):
                        getattr(self.stage, operation)(timeout_s=1)

    def test_late_native_call_detected_without_background_commands(self):
        def late(command):
            self.clock.sleep(2)
            return 0, '0'

        with patch.object(self.controller, 'message', side_effect=late):
            with self.assertRaises(TimeoutError):
                self.stage.is_busy(timeout_s=1)
        with self.assertRaisesRegex(RuntimeError, 'faulted'):
            self.stage.move_to(100, -100, timeout_s=1)

    def test_stop_polls_until_idle(self):
        with patch.object(self.controller, 'message', side_effect=[(0, ''), (0, '3'), (0, '1'), (0, '0')]) as message:
            self.stage.stop(timeout_s=1)
        self.assertEqual(message.call_count, 4)
        self.assertAlmostEqual(self.clock.now, 0.02)

    def test_stop_timeout(self):
        self.controller.busy = '1'
        with self.assertRaises(TimeoutError):
            self.stage.stop(timeout_s=0.03)
        self.assertAlmostEqual(self.clock.now, 0.03)

    def test_stop_command_error(self):
        self.controller.status = -1
        with self.assertRaises(RuntimeError):
            self.stage.stop(timeout_s=1)

    def test_reflection_reduction_is_mean_magnitude_not_magnitude_of_mean(self):
        self.assertEqual(self.reader.read(timeout_s=0.5), 5)
        self.assertEqual(self.analog.calls, [(2, 0.5)])
        self.assertEqual(self.reader.last_samples, ((3, -3), (4, -4)))

    def test_reject_counts_nonfinite_and_raw_clipping(self):
        for data in ([[3], [4]], [[3, 3]], [[float('nan'), 0], [0, 0]],
                     [[10, -10], [0, 0]], [[11, 0], [0, 0]]):
            with self.subTest(data=data):
                reader = NIReflectionReader(self.analog, sample_number=2,
                                            channel_limits=((-10, 10), (-10, 10)))
                self.analog.data = data
                with self.assertRaises((ValueError, RuntimeError)):
                    reader.read(timeout_s=1)
                self.assertIsNotNone(reader.last_samples)
                with self.assertRaisesRegex(RuntimeError, 'faulted'):
                    reader.read(timeout_s=1)

    def test_reader_timeout(self):
        def late(count, *, timeout_s):
            self.clock.sleep(timeout_s)
            return [[3, 3], [4, 4]]

        with patch.object(self.analog, 'acquire_bounded', side_effect=late):
            with self.assertRaises(TimeoutError):
                self.reader.read(timeout_s=0.1)
        self.assertIsNotNone(self.reader.last_samples)

    def test_invalid_timeout_never_calls_devices(self):
        for timeout in (0, -1, float('nan'), float('inf'), True):
            with self.assertRaises(ValueError):
                self.stage.stop(timeout_s=timeout)
            with self.assertRaises(ValueError):
                self.reader.read(timeout_s=timeout)
        self.assertEqual(self.controller.commands, [])
        self.assertEqual(self.analog.calls, [])

    def test_scan_integration_both_axes_directions_and_cancellation(self):
        with TemporaryDirectory() as directory:
            for axis in ('x', 'y'):
                for reverse in (False, True):
                    origin, fixed = (100, -100) if axis == 'x' else (-100, 100)
                    start, end = (origin + 2, origin) if reverse else (origin, origin + 2)
                    settings = ScanSettings(axis, start, end, 1, fixed, self.bounds, settling_s=0)
                    path = Path(directory) / f'{axis}-{reverse}.jsonl'
                    result = scan_1d(settings, self.stage, self.reader, output_path=path, clock=self.clock)
                    self.assertEqual(result.status, ScanStatus.COMPLETED, result.reasons)
                    self.assertEqual([p.signal for p in result.points], [5] * 3)
                    self.assertEqual(load_scan(path).points, result.points)
            baseline = len(self.analog.calls)
            path = Path(directory) / 'cancel.jsonl'
            result = scan_1d(settings, self.stage, self.reader, output_path=path, clock=self.clock,
                             cancelled=lambda: len(self.analog.calls) > baseline)
            self.assertEqual(result.status, ScanStatus.CANCELLED)
            self.assertEqual(len(result.points), 1)
            self.assertIn('controller.stop.smoothly', self.controller.commands)


class BoundedDAQTests(unittest.TestCase):
    """Execute the actual method body with fake DAQmx bindings, never import it."""

    def setUp(self):
        self.clock = Clock()
        self.calls = []
        self.count = 2
        self.start_status = self.read_status = self.stop_status = 0
        self.read_exception = None
        self.read_delay = 0
        self.received_timeout = None
        source = Path(__file__).resolve().parents[1] / 'instruments' / 'ni_daq.py'
        with warnings.catch_warnings():
            # Unrelated legacy Windows path literal contains an invalid escape.
            warnings.filterwarnings('ignore', message='invalid escape sequence', category=DeprecationWarning)
            tree = ast.parse(source.read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MultiChannelAnalogInput')
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'acquire_bounded')
        namespace = {'np': np, 'isfinite': np.isfinite, 'monotonic': self.clock.monotonic,
                     'int32': ctypes.c_int32, 'byref': ctypes.byref,
                     'DAQmx_Val_GroupByChannel': 0, 'DAQmxStartTask': self.start,
                     'DAQmxReadAnalogF64': self.read, 'DAQmxStopTask': self.stop}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), namespace)
        fake_type = type('FakeConfiguredDAQ', (), {'acquire_bounded': namespace['acquire_bounded']})
        self.device = fake_type()
        self.device.numberOfChannel = 2
        self.device.taskHandle = object()

    def start(self, task):
        self.calls.append('start')
        self.clock.sleep(0.01)
        return self.start_status

    def read(self, task, count, timeout, grouping, data, size, read_pointer, reserved):
        self.calls.append('read')
        self.received_timeout = timeout
        if self.read_exception:
            raise self.read_exception
        data[:] = [[3, -3], [4, -4]]
        ctypes.cast(read_pointer, ctypes.POINTER(ctypes.c_int32))[0] = self.count
        self.clock.sleep(self.read_delay)
        return self.read_status

    def stop(self, task):
        self.calls.append('stop')
        return self.stop_status

    def test_actual_driver_method_uses_remaining_timeout_and_count(self):
        data = self.device.acquire_bounded(2, timeout_s=0.5)
        self.assertAlmostEqual(self.received_timeout, 0.49)
        self.assertEqual(data.tolist(), [[3, -3], [4, -4]])
        self.assertEqual(self.calls, ['start', 'read', 'stop'])

    def test_short_read_stops_task(self):
        self.count = 1
        with self.assertRaisesRegex(RuntimeError, 'Short DAQ read'):
            self.device.acquire_bounded(2, timeout_s=1)
        self.assertEqual(self.calls[-1], 'stop')

    def test_read_exception_stops_task(self):
        self.read_exception = TimeoutError('fake read timeout')
        with self.assertRaises(TimeoutError):
            self.device.acquire_bounded(2, timeout_s=1)
        self.assertEqual(self.calls[-1], 'stop')

    def test_sdk_statuses_and_warnings_rejected(self):
        for name, status in (('start_status', -1), ('read_status', -2), ('read_status', 1), ('stop_status', -3)):
            with self.subTest(name=name, status=status):
                self.start_status = self.read_status = self.stop_status = 0
                setattr(self, name, status)
                with self.assertRaises(RuntimeError):
                    self.device.acquire_bounded(2, timeout_s=1)
                self.assertEqual(self.calls[-1], 'stop')

    def test_cleanup_error_preserves_acquisition_error(self):
        self.read_exception = TimeoutError('read failed')
        self.stop_status = -3
        with self.assertRaisesRegex(RuntimeError, 'read failed.*stop also failed'):
            self.device.acquire_bounded(2, timeout_s=1)

    def test_expired_start_prevents_read(self):
        with self.assertRaises(TimeoutError):
            self.device.acquire_bounded(2, timeout_s=0.005)
        self.assertEqual(self.calls, ['start', 'stop'])

    def test_late_read_rejected(self):
        self.read_delay = 2
        with self.assertRaises(TimeoutError):
            self.device.acquire_bounded(2, timeout_s=1)
        self.assertEqual(self.calls[-1], 'stop')

    def test_invalid_arguments_do_not_start_task(self):
        for count, timeout in ((0, 1), (True, 1), (2, 0), (2, True), (2, float('nan'))):
            with self.assertRaises(ValueError):
                self.device.acquire_bounded(count, timeout_s=timeout)
        self.assertEqual(self.calls, [])

    def test_reader_wraps_actual_driver_method_with_fake_bindings(self):
        reader = NIReflectionReader(self.device, sample_number=2,
                                    channel_limits=((-10, 10), (-10, 10)), clock=self.clock)
        self.assertEqual(reader.read(timeout_s=1), 5)


class IsolationTests(unittest.TestCase):
    def test_guarded_suite(self):
        code = '''
import importlib.abc, sys, unittest
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'instruments', 'PyDAQmx', 'PIPython', 'serial', 'PyQt6',
                                     'ui', 'qcl_scanning_imaging_ui', 'qcl_spectral_scan_ui'}:
            raise AssertionError('Forbidden import: ' + fullname)
sys.meta_path.insert(0, Guard())
sys.path.insert(0, 'tests')
import test_scan_adapters as t
suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(c)
                           for c in (t.AdapterTests, t.BoundedDAQTests))
sys.exit(not unittest.TextTestRunner(verbosity=0).run(suite).wasSuccessful())
'''
        result = subprocess.run([sys.executable, '-B', '-c', code],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
