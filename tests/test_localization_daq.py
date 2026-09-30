"""Run-owned provider with actual bounded read method and fake DAQmx bindings."""
import ast
import ctypes
from pathlib import Path
from types import SimpleNamespace
import unittest
import warnings
import numpy as np
from test_h_only_validation import setup_environment
from test_reflection_scan import FakeClock
from ui.localization_daq import LocalizationDAQProvider
from ui.localization_pipeline import DaqSettings
from ui.localization_orchestration import RunSettings,OwnershipStatus
from experiment.scan_adapters import NIReflectionReader


class FakeNI:
    DAQmx_Val_Cfg_Default=0
    DAQmx_Val_Volts=1
    DAQmx_Val_Rising=2
    DAQmx_Val_FiniteSamps=3
    byref=staticmethod(lambda v:v)

    def __init__(self,stage=None):
        self.stage=stage;self.calls=[];self.fail=None;self.clock=FakeClock()
        self.short=False;self.clip=False;self.timeout=False;self.clear_fail=False
        self.reset=None;self.channels=None;self.channel_count=0

    def MultiChannelAnalogInput(self,channels,limit,reset):
        self.reset=reset;self.channels=channels
        source=Path(__file__).resolve().parents[1]/'instruments'/'ni_daq.py'
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',DeprecationWarning)
            tree=ast.parse(source.read_text(encoding='utf-8'))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='MultiChannelAnalogInput')
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='acquire_bounded')
        namespace=dict(np=np,isfinite=np.isfinite,monotonic=self.clock.monotonic,int32=ctypes.c_int32,
            byref=ctypes.byref,DAQmx_Val_GroupByChannel=0,DAQmxStartTask=self.start,
            DAQmxReadAnalogF64=self.read,DAQmxStopTask=self.stop)
        exec(compile(ast.Module(body=[method],type_ignores=[]),str(source),'exec'),namespace)
        typ=type('InertNI',(),{'acquire_bounded':namespace['acquire_bounded']})
        result=typ();result.numberOfChannel=2;result.taskHandle=SimpleNamespace(value=0)
        return result

    def status(self,name):
        self.calls.append(name)
        return -1 if self.fail==name else 0
    def DAQmxCreateTask(self,name,handle):
        handle.value=123
        return self.status('create')
    def DAQmxCreateAIVoltageChan(self,*args):
        self.channel_count+=1
        assert args[1] in (b'Dev1/ai0',b'Dev1/ai1') and args[4:6]==(-10.,10.)
        return self.status('channel'+str(self.channel_count))
    def DAQmxCfgSampClkTiming(self,*args):
        assert args[2:]==(100000,2,3,32)
        return self.status('timing')
    def DAQmxClearTask(self,handle):
        self.calls.append('clear');return -1 if self.clear_fail else 0
    def start(self,handle):return self.status('start')
    def stop(self,handle):return self.status('stop')
    def read(self,handle,count,timeout,group,data,size,read_pointer,reserved):
        from math import tanh
        self.received_timeout=timeout
        status=self.status('read')
        if self.timeout:raise TimeoutError('fake read timeout')
        value=1.
        if self.stage:
            x,y=self.stage.position
            value=1+3*(tanh((x-750)/3)-tanh((x-1250)/3))/2
        data[0,:]=10. if self.clip else value;data[1,:]=0.
        ctypes.cast(read_pointer,ctypes.POINTER(ctypes.c_int32))[0]=count-1 if self.short else count
        return status


class DAQProviderTests(unittest.TestCase):
    def setUp(self):
        self.window,self.state,self.controller,self.bridge=setup_environment()
        self.handle=self.bridge.acquire(RunSettings(self.state.context,self.state.context_generation,'fixture',purpose='h_only'))
        self.backend=FakeNI()
        self.provider=LocalizationDAQProvider(self.bridge,self.handle,self.backend)

    def task(self):return self.provider(DaqSettings())

    def test_reset_false_exact_channels_finite_timing(self):
        task=self.task()
        self.assertIs(self.backend.reset,False)
        self.assertEqual(self.backend.channels,[b'Dev1/ai0',b'Dev1/ai1'])
        self.assertEqual(self.backend.calls,['create','channel1','channel2','timing'])
        self.assertEqual(task.run_id,self.handle.run_id)
        self.assertIs(self.bridge.daq.task,task)

    def test_second_owner_rejected(self):
        self.task()
        with self.assertRaisesRegex(RuntimeError,'owner_conflict'):self.task()
        self.assertEqual(self.backend.calls.count('create'),1)

    def test_stale_run_rejected_before_creation(self):
        self.controller.active=None
        with self.assertRaises(Exception):self.task()
        self.assertEqual(self.backend.calls,[])

    def test_partial_construction_all_phases_clean_once(self):
        for phase in ('create','channel1','channel2','timing'):
            with self.subTest(phase=phase):
                self.setUp();self.backend.fail=phase
                with self.assertRaises(RuntimeError):self.task()
                self.assertEqual(self.backend.calls.count('clear'),1)
                self.assertIsNone(self.bridge.daq.run_id)

    def test_partial_cleanup_failure_quarantines(self):
        self.backend.fail='channel1';self.backend.clear_fail=True
        with self.assertRaises(RuntimeError):self.task()
        self.assertTrue(self.bridge.daq.uncertain)
        self.assertEqual(self.controller.ownership.status,OwnershipStatus.QUARANTINED)
        self.assertEqual(self.backend.calls.count('clear'),1)

    def test_read_timeout_stops_then_clear(self):
        task=self.task();self.backend.timeout=True
        with self.assertRaises(TimeoutError):task.acquire_bounded(32,timeout_s=2.)
        task.clear()
        self.assertEqual(self.backend.calls[-3:],['read','stop','clear'])
        self.assertLessEqual(self.backend.received_timeout,2.)

    def test_short_read_stops(self):
        task=self.task();self.backend.short=True
        with self.assertRaisesRegex(RuntimeError,'Short DAQ'):task.acquire_bounded(32,timeout_s=2.)
        task.clear();self.assertEqual(self.backend.calls[-2:],['stop','clear'])

    def test_clipping_uses_existing_reader(self):
        task=self.task();self.backend.clip=True
        reader=NIReflectionReader(task,sample_number=32,channel_limits=((-9.9,9.9),)*2)
        with self.assertRaises(Exception):reader.read(timeout_s=2.)
        task.clear();self.assertEqual(self.backend.calls.count('clear'),1)

    def test_start_read_stop_status_failures(self):
        for phase in ('start','read','stop'):
            with self.subTest(phase=phase):
                self.setUp();task=self.task();self.backend.fail=phase
                with self.assertRaises(RuntimeError):task.acquire_bounded(32,timeout_s=2.)
                task.clear();self.assertEqual(self.backend.calls.count('clear'),1)

    def test_clear_idempotent_without_second_native_call(self):
        task=self.task();task.clear();task.clear()
        self.assertEqual(self.backend.calls.count('clear'),1)

    def test_clear_failure_not_retried(self):
        task=self.task();self.backend.clear_fail=True
        with self.assertRaises(RuntimeError):task.clear()
        with self.assertRaisesRegex(RuntimeError,'previously_failed'):task.clear()
        self.assertEqual(self.backend.calls.count('clear'),1)

    def test_exact_count_and_timeout_validation(self):
        task=self.task()
        with self.assertRaises(ValueError):task.acquire_bounded(31,timeout_s=2.)
        with self.assertRaises(ValueError):task.acquire_bounded(32,timeout_s=0.)
        self.assertNotIn('start',self.backend.calls)

    def test_no_read_after_cleanup(self):
        task=self.task();task.clear()
        with self.assertRaises(ValueError):task.acquire_bounded(32,timeout_s=2.)


if __name__=='__main__':unittest.main()
