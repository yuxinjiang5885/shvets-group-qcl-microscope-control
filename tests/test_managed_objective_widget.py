"""Actual legacy widget class compiled with inert PI/stage/NI dependencies."""
import ast
from contextlib import ExitStack
import os
from pathlib import Path
import sys
from threading import Thread
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import numpy as np
from PyQt6 import QtWidgets
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction, QTextCursor

from test_operational_localization_bridge import FakePrior, FakeMotion
from test_objective_daq_lifecycle import ObjectiveNI
from ui.managed_objective_widget import create_managed_objective
from ui.localization_orchestration import RunSettings, CleanupOutcome, OwnershipError
from ui.hardware_ownership_diagnostics import hardware_ownership_snapshot
from qcl_scanning_imaging_autorelocation_ui import operational_window_class


ROOT = Path(__file__).resolve().parents[1]


def inert_legacy_widget():
    path = ROOT / 'instruments/pi_scanner.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'piScanner_widget')
    namespace = {name: getattr(QtWidgets, name) for name in (
        'QWidget', 'QVBoxLayout', 'QPushButton', 'QTextEdit', 'QApplication',
        'QHBoxLayout', 'QLabel', 'QLineEdit', 'QCheckBox')}
    namespace.update(np=np, pyqtSignal=pyqtSignal, QTextCursor=QTextCursor,
                     pitools=SimpleNamespace(waitontarget=lambda device, axes: device.qPOS(axes)))
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace['piScanner_widget']


class InertStage(FakePrior):
    def get_position(self):
        self.calls.append('stage_position')
        return self.position

    def goto(self, x, y):
        self.calls.append('stage_move')
        self.position = (x, y)

    def wait_until_ready(self, timeout):
        self.calls.append('stage_wait')

    def busy(self):
        return '0'


class InertPI:
    def __init__(self):
        self.position, self.calls = 100., []
        self.on_move = lambda: None
        self.fail = False

    def MOV(self, axis, position):
        self.on_move()
        self.calls.append('move')
        if self.fail:
            raise RuntimeError('fake PI motion failure')
        self.position = position

    def qPOS(self, axis):
        self.calls.append('position')
        return {1: self.position}


class ManagedObjectiveWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.legacy = inert_legacy_widget()

    def setUp(self):
        self.ni = ObjectiveNI()
        class InertMain(QtWidgets.QMainWindow):
            def __init__(self):
                super().__init__()
                self.tabs = QtWidgets.QTabWidget()
                self.setCentralWidget(self.tabs)
                self.stage = InertStage()
                self.stageMotionWindow = FakeMotion(self.stage)
                self.pi_scanner = SimpleNamespace(pidevice=InertPI(), RANGE_MIN=0, RANGE_MAX=400,
                    af_min=-1., af_max=1., af_step=1., autofocus_on_imaging=False,
                    target_x=None, target_y=None)
                self.action = QAction('Objective Scanner', self)
                self.action.triggered.connect(self.show_pi_scanner_widget)
                self.snake_calls = 0

            def show_pi_scanner_widget(self):
                raise AssertionError('unmanaged callback must never execute')

            def run_snake_scan(self):
                self.snake_calls += 1

        factory = lambda window: create_managed_objective(
            window, base_class=self.legacy, backend=self.ni)
        self.window = operational_window_class(InertMain, objective_widget_factory=factory)()
        self.bridge = self.window.localization_bridge
        self.bridge.execution_contract_reviewed = True
        self.bridge.joystick_disabled = lambda: True
        self.addCleanup(self.cleanup)
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.errors = []
        stack.enter_context(patch.object(sys, 'excepthook', side_effect=lambda *e: self.errors.append(e)))

    def cleanup(self):
        widget = getattr(self.window, 'pi_scanner_widget', None)
        if widget is None and self.bridge.objective_owner is not None:
            widget = self.bridge.objective_owner.widget
        if widget:
            if hasattr(widget, 'ownership_timer'):
                widget.ownership_timer.stop()
            widget.deleteLater()
        self.window.localization_display_timer.stop()
        self.window.deleteLater()
        self.app.processEvents()

    def open(self):
        self.window.action.trigger()
        self.assertEqual(self.errors, [])
        self.assertTrue(hasattr(self.window, 'pi_scanner_widget'),
                        self.window.auto_relocation.failures_label.text())
        return self.window.pi_scanner_widget

    def acquire(self):
        state = self.window.auto_relocation.state
        return self.bridge.acquire(RunSettings(state.context, state.context_generation, 'fake'))

    def finish(self, handle, clean=True):
        self.bridge.controller.finish(handle, succeeded=False, cleanup=CleanupOutcome(clean, clean))

    def test_open_real_constructor_without_native_task_and_localize_visible(self):
        widget = self.open()
        self.assertIsNone(widget.daq)
        self.assertEqual(self.ni.calls, [])
        self.assertEqual(self.bridge.legacy_daq_evidence.records, {})
        self.assertTrue(widget.isVisible())
        self.assertTrue(widget.objective_owner.released())
        self.finish(self.acquire())

    def test_visible_hidden_reopen_and_boolean_signals_reuse_without_evidence(self):
        widget = self.open()
        for checked in (False, True, False, True):
            widget.close()
            self.assertFalse(widget.isVisible())
            self.window.action.triggered.emit(checked)
            self.assertIs(self.window.pi_scanner_widget, widget)
            self.assertTrue(widget.isVisible())
            self.window.action.trigger()
        self.assertEqual(self.errors, [])
        self.assertEqual(self.ni.calls, [])
        self.assertEqual(self.bridge.legacy_daq_evidence.records, {})
        self.finish(self.acquire())

    def test_acquire_button_creates_clears_and_localization_follows(self):
        widget = self.open()
        widget.button.click()
        self.assertEqual(self.errors, [])
        self.assertEqual(self.ni.calls.count('create'), 1)
        self.assertEqual(self.ni.calls.count('clear'), 1)
        self.assertTrue(widget.objective_owner.released())
        self.finish(self.acquire())

    def test_move_to_reserves_before_pi_then_acquires(self):
        widget = self.open()
        states = []
        self.window.pi_scanner.pidevice.on_move = lambda: states.append(widget.objective_owner.state)
        widget.setpoint_textbox.setText('101')
        widget.move_button.click()
        self.assertEqual(states, ['ACTIVE'])
        self.assertEqual(self.ni.calls.count('read'), 1)
        self.assertEqual(self.ni.calls.count('clear'), 1)
        self.assertTrue(widget.objective_owner.released())
        self.finish(self.acquire())

    def test_autofocus_active_rejects_localization_then_releases(self):
        widget = self.open()
        def check():
            self.assertEqual(widget.objective_owner.state, 'ACTIVE')
            with self.assertRaisesRegex(OwnershipError, 'active'):
                self.acquire()
        self.window.pi_scanner.pidevice.on_move = check
        widget.autofocus_button.click()
        self.assertEqual(self.errors, [])
        self.assertEqual(self.ni.calls.count('create'), 1)
        self.assertEqual(self.ni.calls.count('read'), 3)
        self.assertEqual(self.ni.calls.count('clear'), 1)
        self.assertTrue(widget.objective_owner.released())
        self.finish(self.acquire())

    def test_all_hardware_methods_denied_during_lease_and_handback(self):
        widget = self.open()
        handle = self.acquire()
        widget.refresh_ownership()
        before = (list(self.ni.calls), list(self.window.stage.calls),
                  list(self.window.pi_scanner.pidevice.calls))
        for method in ('acquire_data', 'move_to_position', 'autofocus', 'acquire_position',
                       'acquire_stage_position', 'move_stage_to_target'):
            self.assertIs(getattr(widget, method)(), False)
        self.window.action.trigger()  # Cached reopen allowed, no initialization.
        self.assertEqual(before, (self.ni.calls, self.window.stage.calls, self.window.pi_scanner.pidevice.calls))
        self.assertFalse(widget.button.isEnabled())
        self.finish(handle)
        widget.refresh_ownership()
        self.assertTrue(widget.button.isEnabled())
        self.assertEqual(self.ni.calls, [])
        widget.acquire_data()
        self.assertEqual(self.ni.calls.count('create'), 1)

    def test_first_open_denied_during_lease_does_not_poison_session(self):
        handle = self.acquire()
        self.window.action.trigger()
        self.assertFalse(hasattr(self.window, 'pi_scanner_widget'))
        self.assertIsNone(self.bridge.objective_owner)
        self.assertEqual(self.ni.calls, [])
        self.assertEqual(self.window.stage.calls, [])
        self.assertEqual(self.window.pi_scanner.pidevice.calls, [])
        self.finish(handle)
        self.open()

    def test_partial_construction_failure_retains_owner_without_daq(self):
        self.window.pi_scanner.pidevice.qPOS = lambda axis: (_ for _ in ()).throw(RuntimeError('fake PI failure'))
        self.window.action.trigger()
        self.assertEqual(self.errors, [])
        self.assertFalse(hasattr(self.window, 'pi_scanner_widget'))
        self.assertEqual(self.bridge.objective_owner.state, 'UNCERTAIN')
        self.assertEqual(self.ni.calls, [])
        with self.assertRaises(OwnershipError):
            self.acquire()

    def test_autofocus_cleanup_failure_latches_uncertain(self):
        widget = self.open()
        self.ni.clear_fail = True
        widget.autofocus()
        self.assertEqual(widget.objective_owner.state, 'UNCERTAIN')
        self.assertFalse(widget.button.isEnabled())
        self.assertEqual(hardware_ownership_snapshot(self.window)['autofocus_state'], 'unknown')
        with self.assertRaises(OwnershipError):
            self.acquire()

    def test_legacy_caught_pi_error_still_latches_uncertainty(self):
        widget = self.open()
        self.window.pi_scanner.pidevice.fail = True
        widget.move_to_position()
        self.assertEqual(widget.objective_owner.state, 'UNCERTAIN')
        self.assertEqual(self.ni.calls, [])
        with self.assertRaises(OwnershipError):
            self.acquire()

    def test_legacy_caught_pi_wait_timeout_still_latches_uncertainty(self):
        widget = self.open()
        pitools = self.legacy.move_to_position.__globals__['pitools']
        with patch.object(pitools, 'waitontarget', side_effect=TimeoutError('fake PI timeout')):
            widget.move_to_position()
        self.assertEqual(widget.objective_owner.state, 'UNCERTAIN')
        self.assertEqual(self.ni.calls, [])
        with self.assertRaises(OwnershipError):
            self.acquire()

    def test_stage_wait_return_is_not_idle_evidence(self):
        widget = self.open()
        self.window.stage.busy = lambda: '1'
        widget.move_stage_to_target()
        self.assertEqual(widget.objective_owner.state, 'UNCERTAIN')
        with self.assertRaises(OwnershipError):
            self.acquire()

    def test_position_queries_use_no_ni(self):
        widget = self.open()
        widget.acquire_position()
        widget.acquire_stage_position()
        self.assertEqual(self.ni.calls, [])
        self.assertTrue(widget.objective_owner.released())

    def test_localization_quarantine_keeps_controls_and_methods_blocked(self):
        widget = self.open()
        self.finish(self.acquire(), clean=False)
        widget.refresh_ownership()
        self.assertFalse(widget.autofocus_button.isEnabled())
        self.assertIs(widget.acquire_data(), False)
        self.assertEqual(self.ni.calls, [])

    def test_worker_origin_direct_call_rejected_before_hardware(self):
        widget = self.open()
        errors = []
        def worker():
            try:
                widget.autofocus()
            except OwnershipError as error:
                errors.append(str(error))
        thread = Thread(target=worker)
        before = list(self.window.stage.calls)
        thread.start()
        thread.join(3)
        self.assertEqual(errors, ['worker_origin_objective_unsupported_in_V1'])
        self.assertEqual(self.ni.calls, [])
        self.assertEqual(self.window.stage.calls, before)

    def test_snake_autofocus_launch_denied_before_callback(self):
        self.window.pi_scanner.autofocus_on_imaging = True
        self.assertIs(self.window.run_snake_scan(), False)
        self.assertEqual(self.window.snake_calls, 0)
        self.assertEqual(self.bridge.legacy_daq_evidence.records, {})
        self.assertIn('unsupported_in_V1', self.window.auto_relocation.failures_label.text())

    def test_diagnostics_separate_window_and_verified_release(self):
        widget = self.open()
        data = hardware_ownership_snapshot(self.window)['objective_owner_state']
        self.assertEqual(data['window'], 'OPEN')
        self.assertEqual(data['state'], 'RELEASED')
        self.assertTrue(data['verified_released'])
        widget.close()
        data = hardware_ownership_snapshot(self.window)['objective_owner_state']
        self.assertEqual(data['window'], 'CLOSED')
        self.assertEqual(data['state'], 'RELEASED')


if __name__ == '__main__':
    unittest.main()
