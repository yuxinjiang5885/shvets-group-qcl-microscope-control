"""Inert native devices and extracted scan code; never import hardware modules."""
import ast
import ctypes
from dataclasses import replace, FrozenInstanceError
from pathlib import Path
from threading import Thread, Barrier
from types import SimpleNamespace
from time import monotonic, sleep
import unittest
import numpy as np
from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication
from test_operational_localization_bridge import environment, FakePrior
from test_objective_daq_lifecycle import ObjectiveNI
from test_checked_snake_daq import make_factory
from ui.objective_daq_lifecycle import ObjectiveDaqLifecycle
from ui.snake_autofocus_service import SnakeAutofocusSettings, SnakeAutofocusService, AutofocusFailure
from ui.snake_workflow import SnakeWorkflow, WorkerStage, WorkerPI, WorkerLaser
from ui.snake_daq_lifecycle import snake_worker_factory, SnakeDaqLifecycle
from ui.localization_orchestration import OwnershipError, RunSettings, CleanupOutcome, Command

ROOT=Path(__file__).resolve().parents[1]


class PI:
    def __init__(self): self.position=100.;self.timeout=1000;self.calls=[];self.fail=None
    def MOV(self,axis,value):
        self.calls.append(('move',value))
        if self.fail=='move':raise RuntimeError('PI movement failed')
        self.position=value
    def qPOS(self,axis):
        if self.fail=='read':raise RuntimeError('PI read failed')
        return {1:self.position}
    def qONT(self,axis):
        if self.fail=='wait':raise RuntimeError('PI wait failed')
        return {1:True}


class Stage(FakePrior):
    def __init__(self): super().__init__((10.,20.));self.moves=[];self.fault=None;self.mismatch=False
    def goto(self,x,y):
        self.moves.append((x,y))
        if self.fault=='move' or (self.fault=='restore' and len(self.moves)>1):raise RuntimeError('stage failure')
        self.message(f'controller.stage.goto-position {x} {y}')
    def busy(self):return self.message('controller.stage.busy.get')[1]
    def get_position(self):
        point=tuple(map(float,self.message('controller.stage.position.get')[1].split(',')))
        return (point[0]+5,point[1]) if self.mismatch and len(self.moves)>1 else point
    def set_position(self,x,y):self.position=(x,y)
    def set_speed(self,*a):pass
    def arm_trigger(self,**k):pass


def install_laser(bridge,window):
    # The real disable method body, compiled without its module initialization.
    tree=ast.parse((ROOT/'instruments/mircat.py').read_bytes())
    method=next(n for cls in tree.body if isinstance(cls,ast.ClassDef)
                for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='disable')
    def emission(pointer):pointer._obj.value=False;return 0
    ns={'SDK':SimpleNamespace(MIRcatSDK_IsEmissionOn=emission,
                             MIRcatSDK_TurnEmissionOff=lambda:0),'byref':ctypes.byref,
        'print':lambda *a:None}
    exec(compile(ast.Module(body=[method],type_ignores=[]),'<inert laser>', 'exec'),ns)
    class Laser:
        disable=ns['disable']
        def __init__(self):self.isEmitting=ctypes.c_bool(False);self.wavelengths=[]
        def tune(self,**kwargs):self.wavelengths.append(kwargs['wl'])
        def get_current(self,*a):return 1
        get_pulse_rate=get_current
        get_pulse_width=get_current
    window.laser=Laser();bridge.snake_laser_disable=window.laser.disable


def setup():
    window,state,controller,bridge=environment()
    stage=Stage();window.stage=bridge.stage=window.stageMotionWindow.stage=stage
    bridge.guards_installed=False;bridge.install_guards()
    install_laser(bridge,window)
    window.pi_scanner=SimpleNamespace(pidevice=PI(),autofocus_on_imaging=True)
    ni=ObjectiveNI();owner=ObjectiveDaqLifecycle(bridge,ni)
    return window,state,controller,bridge,owner,ni


SETTINGS=SnakeAutofocusSettings(30.,40.,-1.,1.,1.)


class ServiceTests(unittest.TestCase):
    def test_point_telemetry_and_best_signal(self):
        points=[]
        samples=iter([np.array([[3.],[4.]]), np.array([[6.],[8.]]), np.array([[0.],[2.]])])
        service=self.service(acquire=lambda:next(samples));service.progress=points.append
        result=service.run((30.,40.))
        self.assertEqual([(p.sequence,p.position,p.signal) for p in points],
                         [(1,99.,5.),(2,100.,10.),(3,101.,2.)])
        self.assertEqual((result.best_position,result.best_signal),(100.,10.))
        with self.assertRaises(FrozenInstanceError):points[0].signal=0

    def test_broken_telemetry_does_not_change_service_result(self):
        service=self.service()
        service.progress=lambda point:(_ for _ in ()).throw(RuntimeError('display unavailable'))
        with self.assertLogs('ui.snake_autofocus_service',level='ERROR'):
            result=service.run((30.,40.))
        self.assertEqual(result.outcome,'SUCCESS')
        self.assertTrue(result.stage_restored)

    def service(self,stage=None,pi=None,acquire=None,check=None):
        return SnakeAutofocusService(SETTINGS,stage or Stage(),pi or PI(),
            acquire or (lambda:np.ones((2,10))),check or (lambda:None),lambda:True)
    def test_success_restores_stage_and_keeps_best_pi(self):
        stage=Stage();pi=PI();result=self.service(stage,pi).run((30.,40.))
        self.assertEqual(result.outcome,'SUCCESS');self.assertEqual(stage.position,(10.,20.))
        self.assertEqual(pi.position,99.);self.assertTrue(result.stage_restored)
    def test_invalid_settings(self):
        for change in ({'sweep_step':0},{'absolute_target_x':float('nan')},
                       {'pi_min':500},{'movement_timeout':-1}):
            with self.assertRaises(AutofocusFailure):replace(SETTINGS,**change)
    def test_frozen_settings(self):
        with self.assertRaises(FrozenInstanceError):SETTINGS.sweep_step=2
    def test_no_valid_result(self):
        with self.assertRaisesRegex(AutofocusFailure,'NO_VALID_FOCUS_RESULT'):
            self.service(acquire=lambda:np.full((2,10),np.nan)).run((30.,40.))
    def test_pi_faults(self):
        for failure in ('move','read','wait'):
            pi=PI();pi.fail=failure
            with self.assertRaisesRegex(AutofocusFailure,'PI_'):self.service(pi=pi).run((30.,40.))
    def test_stage_restore_failure(self):
        stage=Stage();stage.fault='restore'
        with self.assertRaisesRegex(AutofocusFailure,'STAGE_RESTORE_FAILURE'):
            self.service(stage).run((30.,40.))
    def test_stage_restore_mismatch(self):
        stage=Stage();stage.mismatch=True
        with self.assertRaisesRegex(AutofocusFailure,'STAGE_READBACK_MISMATCH'):
            self.service(stage).run((30.,40.))
    def test_cancellation_restores(self):
        stage=Stage();count=[0]
        def check():
            count[0]+=1
            if count[0]>=3:raise AutofocusFailure('CANCELLED')
        with self.assertRaisesRegex(AutofocusFailure,'CANCELLED'):
            self.service(stage,check=check).run((30.,40.))
        self.assertEqual(stage.position,(10.,20.))


class ParentTests(unittest.TestCase):
    def test_final_telemetry_follows_verified_cleanup(self):
        events=[]
        def receive(event):
            events.append(event)
            if event.kind=='result':
                self.assertEqual(self.ni.calls.count('clear'),1)
                self.assertTrue(self.owner.released())
                self.assertTrue(self.bridge.legacy_daq_evidence.records[event.child_token]['released'])
        self.parent.telemetry=receive
        WorkerLaser(self.window.laser,self.parent).tune(qcl=1,wl=1658,wlUnits='invcm')
        result=self.focus()
        self.assertEqual([e.kind for e in events],['start','point','point','point','result'])
        self.assertTrue(all(e.requested_wavelength==1658 and e.units=='invcm' for e in events))
        self.assertEqual(events[-1].result,result)

    def test_failure_telemetry_is_not_success(self):
        events=[];self.parent.telemetry=events.append;self.ni.clear_fail=True
        with self.assertRaises(AutofocusFailure):self.focus()
        self.assertEqual(events[-1].result.outcome,'DAQ_CLEAR_FAILURE')
        self.assertFalse(events[-1].result.cleanup_verified)
        self.assertTrue(self.parent.uncertain)

    def test_broken_subscriber_cannot_change_attestation(self):
        self.parent.telemetry=lambda event:(_ for _ in ()).throw(RuntimeError('subscriber failed'))
        with self.assertLogs('ui.snake_autofocus_service',level='ERROR'):result=self.focus()
        self.assertTrue(result.cleanup_verified)
        self.assertTrue(self.owner.released())
        self.assertFalse(self.parent.uncertain)

    def setUp(self):
        self.window,self.state,self.controller,self.bridge,self.owner,self.ni=setup()
        self.parent=SnakeWorkflow(self.bridge,'test',SETTINGS)
        self.scope=SnakeDaqLifecycle(self.bridge,'test');self.scope.parent=self.parent
        self.parent.scope=self.scope;self.parent.bind()
    def focus(self):return self.parent.autofocus((30.,40.),WorkerStage(self.window.stage,self.parent),
                                               WorkerPI(self.window.pi_scanner.pidevice,self.parent))
    def test_child_success_keeps_parent_reserved(self):
        result=self.focus()
        self.assertTrue(result.cleanup_verified);self.assertTrue(self.owner.released())
        self.assertIs(self.bridge.snake_parent,self.parent)
        self.assertEqual(self.ni.calls.count('create'),1);self.assertEqual(self.ni.calls.count('clear'),1)
        self.assertTrue(self.bridge.legacy_daq_evidence.records[self.parent.child.token]['released'])
        self.assertFalse(self.bridge.legacy_daq_evidence.records[self.parent.token]['released'])
        with self.assertRaises(OwnershipError):self.owner.run('manual',lambda:None)
        with self.assertRaises(OwnershipError):self.bridge.acquire(RunSettings(self.state.context,0,'test'))
    def test_imaging_requires_success_and_clear(self):
        factory=make_factory()
        with self.assertRaises(OwnershipError):self.scope.task_factory(factory,[b'a',b'b'])
        self.focus()
        task=self.scope.task_factory(factory,[b'a',b'b']);task.configure_triggered(b'x',2,100000)
        with self.assertRaises(OwnershipError):self.focus()
        task.clear_task();self.focus()
        self.assertEqual(self.ni.calls.count('clear'),2)
    def test_daq_failure_matrix(self):
        for failure in ('create','timing','start','read','stop','clear'):
            self.setUp()
            if failure=='clear':self.ni.clear_fail=True
            else:self.ni.fail=failure
            with self.assertRaises(AutofocusFailure):self.focus()
            self.assertEqual(self.ni.calls.count('clear'),1)
            self.assertTrue(self.bridge.legacy_daq_evidence.ever_acquired)
            self.assertEqual(self.parent.result.cleanup_verified,failure!='clear')
            self.assertNotEqual(self.parent.result.outcome,'SUCCESS')
            with self.assertRaises(OwnershipError):self.scope.task_factory(make_factory(),[b'a',b'b'])
    def test_cancel_before_focus(self):
        self.parent.cancellation.request_cancel()
        with self.assertRaisesRegex(AutofocusFailure,'CANCELLED'):self.focus()
        self.assertEqual(self.ni.calls,[])
    def test_cancel_after_focus_blocks_imaging(self):
        self.focus();self.parent.cancellation.request_cancel()
        with self.assertRaisesRegex(AutofocusFailure,'CANCELLED'):
            self.scope.task_factory(make_factory(),[b'a',b'b'])
    def test_cancel_during_read_restores_and_releases_child(self):
        read=self.ni.read
        def cancel(*args):
            result=read(*args);self.parent.cancellation.request_cancel();return result
        self.ni.read=cancel
        with self.assertRaisesRegex(AutofocusFailure,'CANCELLED'):self.focus()
        self.assertTrue(self.parent.result.stage_restored)
        self.assertTrue(self.parent.result.cleanup_verified)
        self.assertEqual(self.ni.calls.count('read'),1)
        self.assertEqual(self.window.stage.position,(10.,20.))
    def test_child_tokens_generation_phase_and_active_state(self):
        read=self.ni.read
        def inspect(*args):
            op=self.parent.child
            self.assertEqual(self.owner.state,'ACTIVE')
            self.parent.authorize_child(op,self.parent.token,self.parent.generation)
            for token,generation in (('foreign',self.parent.generation),(self.parent.token,'stale')):
                with self.assertRaises(OwnershipError):self.parent.authorize_child(op,token,generation)
            with self.assertRaises(OwnershipError):
                self.parent.authorize_child(object(),self.parent.token,self.parent.generation)
            self.parent.phase='IMAGING'
            with self.assertRaises(OwnershipError):
                self.parent.authorize_child(op,self.parent.token,self.parent.generation)
            self.parent.phase='AUTOFOCUS'
            return read(*args)
        self.ni.read=inspect;self.focus()
        with self.assertRaises(OwnershipError):
            self.parent.authorize_child(self.parent.child,self.parent.token,self.parent.generation)
    def test_stale_completion_does_not_overwrite_new_operation(self):
        read=self.ni.read
        replacement=SimpleNamespace(sentinel=True)
        def stale(*args):
            result=read(*args);self.owner.current=replacement;return result
        self.ni.read=stale
        with self.assertRaisesRegex(OwnershipError,'stale_child_completion'):self.focus()
        self.assertIs(self.owner.current,replacement)
        self.assertFalse(self.bridge.legacy_daq_evidence.records[self.parent.child.token]['released'])
    def test_stage_move_and_pi_failure_never_authorize_imaging(self):
        for failure in ('stage','pi'):
            self.setUp()
            if failure=='stage':self.window.stage.fault='move'
            else:self.window.pi_scanner.pidevice.fail='move'
            with self.assertRaises(AutofocusFailure):self.focus()
            self.assertTrue(self.parent.uncertain)
            with self.assertRaises(OwnershipError):self.scope.task_factory(make_factory(),[b'a',b'b'])
    def test_laser_unknown_status_cannot_complete_parent(self):
        original=self.bridge.snake_laser_disable.__func__.__globals__['SDK'].MIRcatSDK_IsEmissionOn
        sdk=self.bridge.snake_laser_disable.__func__.__globals__['SDK']
        sdk.MIRcatSDK_IsEmissionOn=lambda *a:None
        parameters=SimpleNamespace(stage=WorkerStage(self.window.stage,self.parent),
                                   laser=WorkerLaser(self.window.laser,self.parent))
        self.scope.finish_worker();self.parent.finish_worker(parameters);self.parent.finish_thread()
        self.assertEqual(self.parent.phase,'UNCERTAIN');self.assertFalse(self.parent.laser_verified)
        sdk.MIRcatSDK_IsEmissionOn=original
    def test_foreign_worker_and_stale_parent(self):
        errors=[]
        def call():
            try:self.focus()
            except OwnershipError as error:errors.append(error)
        thread=Thread(target=call);thread.start();thread.join()
        self.assertEqual(len(errors),1)
        self.bridge.snake_parent=object()
        with self.assertRaises(OwnershipError):self.focus()
    def test_completion_requires_thread_and_cleanup(self):
        self.focus();self.scope.finish_worker()
        parameters=SimpleNamespace(stage=WorkerStage(self.window.stage,self.parent),
                                   laser=WorkerLaser(self.window.laser,self.parent))
        self.parent.finish_worker(parameters)
        self.assertIs(self.bridge.snake_parent,self.parent)
        self.parent.finish_thread()
        self.assertEqual(self.parent.phase,'COMPLETE');self.assertIsNone(self.bridge.snake_parent)
        self.owner.run('manual',lambda:None)
    def test_clear_uncertainty_retains_parent(self):
        self.ni.clear_fail=True
        with self.assertRaises(AutofocusFailure):self.focus()
        self.scope.finish_worker();self.parent.finish_thread()
        self.assertIs(self.bridge.snake_parent,self.parent);self.assertEqual(self.parent.phase,'UNCERTAIN')
    def test_child_attestation_failure_retains_parent(self):
        self.bridge.legacy_daq_evidence.confirm_release=lambda token:(_ for _ in ()).throw(OwnershipError('unverified attestation'))
        with self.assertRaisesRegex(AutofocusFailure,'UNCERTAIN'):self.focus()
        self.assertEqual(self.owner.state,'UNCERTAIN')
        self.assertTrue(self.parent.uncertain)
        self.assertFalse(self.parent.result.cleanup_verified)


class RaceTests(unittest.TestCase):
    def test_exactly_one_parent_or_localization_wins(self):
        for _ in range(10):
            window,state,controller,bridge,_,_=setup();gate=Barrier(2);wins=[]
            def snake():
                gate.wait()
                try:SnakeWorkflow(bridge,'race');wins.append('snake')
                except OwnershipError:pass
            def locate():
                gate.wait()
                try:bridge.acquire(RunSettings(state.context,state.context_generation,'race'));wins.append('locate')
                except OwnershipError:pass
            a=Thread(target=snake);b=Thread(target=locate);a.start();b.start();a.join();b.join()
            self.assertEqual(len(wins),1)


def scan_class(name, outputs):
    class Base(QObject):
        finished=pyqtSignal()
        outData=pyqtSignal(object)
        outParams=pyqtSignal(object)
        def run(self):
            self.parameters.data=self.scan()
            self.outData.emit(self.parameters.data)
            self.outParams.emit(self.parameters)
            self.finished.emit()
    tree=ast.parse((ROOT/'experiment/routines.py').read_bytes())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==name)
    defaults=SimpleNamespace(DEF_SNAKE_SCAN_SUBFOLDER='inert',IMAG_SCAN_STEP_BUSY_WAIT=0,
        PCI_CH_X=b'Dev1/ai0',PCI_CH_Y=b'Dev1/ai1',PCI_SNAKE_TRIG=b'/Dev1/PFI0',
        SNAKE_TRIG_INDENT=0,HLD117_MAX_SPEED=10)
    ns=dict(imagingScan=Base,pyqtSignal=pyqtSignal,np=np,defaults=defaults,
        os=SimpleNamespace(getcwd=lambda:'inert',path=SimpleNamespace(join=lambda *a:'/'.join(a)),
                           mkdir=lambda *a:None,chdir=lambda *a:None),
        time=SimpleNamespace(sleep=lambda *a:None,time=lambda:123),timer=lambda:1,
        whichQCL=lambda *a:1,MultiAI=make_factory(),print=lambda *a,**k:None,
        hld117=SimpleNamespace(HLD117_TRIG_RES=1),
        piScanner_widget=lambda *a,**k:(_ for _ in ()).throw(AssertionError('unmanaged widget')))
    exec(compile(ast.Module(body=[cls],type_ignores=[]),str(ROOT/'experiment/routines.py'),'exec'),ns)
    result=ns[name]
    if name=='repeatSnakeScan':result.writeTimeStamps=lambda self:outputs.append('timestamps')
    return result


def scan_parameters(window, patterns=2, wavelengths=(1000,1100)):
    from collections import defaultdict
    paths=[dict(dX=1,M=1,i=0,X0=0,Y0=0,X1=1,Y1=-1,drift=0)]
    outputs=[]
    data=SimpleNamespace(dataCh1=[[[] for _ in wavelengths] for _ in range(patterns)],
        dataCh2=[[[] for _ in wavelengths] for _ in range(patterns)],
        X=[[None for _ in wavelengths] for _ in range(patterns)],
        Y=[[None for _ in wavelengths] for _ in range(patterns)],
        finishSnakeScan=lambda **k:outputs.append((k['pattern_idx'],k['wlwn_idx'])),
        guiFormat=lambda:outputs.append('format'),saveMat=lambda **k:outputs.append('mat'))
    return SimpleNamespace(stage=window.stage,laser=window.laser,pi_scanner=window.pi_scanner,
        pi_scanner_widget=object(), patterns=[paths for _ in range(patterns)],
        xParameters=[[10,1,1] for _ in range(patterns)],
        yParameters=[[20,1,2] for _ in range(patterns)],
        wlwnList=[list(wavelengths) for _ in range(patterns)],units='invcm',
        sampleNumbers=[2]*patterns,sampleRates=[100000]*patterns,speeds=[10]*patterns,
        timeStamps=defaultdict(list),data=data),outputs


class WorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def execute(self,name,autofocus=True, cancel=False, wavelengths=(1000,1100)):
        window,_,_,bridge,owner,ni=setup()
        qtwindow=QObject();qtwindow.__dict__.update(window.__dict__);bridge.window=qtwindow
        qtwindow.auto_relocation=SimpleNamespace(failures_label=SimpleNamespace(setText=lambda value:None))
        parent=SnakeWorkflow(bridge,name,SETTINGS if autofocus else None)
        params,outputs=scan_parameters(qtwindow,wavelengths=wavelengths)
        thread=QThread();qtwindow.threadRun=thread
        worker=snake_worker_factory(scan_class(name,outputs),bridge,thread,name,parent=parent)
        events=[]
        worker.autofocus_progress.connect(events.append)
        worker.parameters=params
        # A real GUI object here would raise if accessed. It has been replaced.
        self.assertIsNot(worker.parameters.pi_scanner_widget,params.pi_scanner_widget)
        create=ni.DAQmxCreateTask
        def objective_create(*args):
            self.assertNotEqual(QThread.currentThread(),self.app.thread())
            self.assertTrue(all(task.cleared for task in parent.scope.tasks))
            self.assertEqual(parent.phase,'AUTOFOCUS')
            return create(*args)
        ni.DAQmxCreateTask=objective_create
        if cancel:
            read=ni.read
            def cancel_read(*args):
                result=read(*args);parent.cancellation.request_cancel();return result
            ni.read=cancel_read
        qtwindow.pi_scanner.target_x=99999
        worker.moveToThread(thread);thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        thread.start();deadline=monotonic()+5
        while parent.phase not in ('COMPLETE','UNCERTAIN') and monotonic()<deadline:
            self.app.processEvents();sleep(.001)
        self.assertTrue(thread.wait(2000))
        self.assertEqual(parent.phase,'COMPLETE',worker._snake_daq_scope.error)
        self.assertEqual(ni.calls.count('create'),1 if cancel else 2*len(wavelengths) if autofocus else 0)
        self.assertEqual(ni.calls.count('clear'),1 if cancel else 2*len(wavelengths) if autofocus else 0)
        self.assertEqual(qtwindow.laser.wavelengths,[1000] if cancel else list(wavelengths)*2)
        if cancel:
            self.assertEqual(outputs,[]);self.assertEqual(parent.scope.tasks,[])
            self.assertEqual(parent.result.outcome,'CANCELLED')
            self.assertEqual(qtwindow.stage.position,(10.,20.))
        else:self.assertEqual(outputs[:2*len(wavelengths)],
                              [(p,w) for p in range(2) for w in range(len(wavelengths))])
        self.assertIsNone(bridge.snake_parent)
        self.assertTrue(owner.released())
        self.app.processEvents()
        starts=[e for e in events if e.kind=='start']
        finals=[e for e in events if e.kind=='result']
        self.assertEqual([e.requested_wavelength for e in starts],
                         ([1000] if cancel else list(wavelengths)*2) if autofocus else [])
        self.assertEqual(len(starts),len(finals))
        self.assertEqual(len({e.child_token for e in starts}),len(starts))
        self.assertTrue(all(e.parent_token==parent.token and e.units=='invcm' for e in events))
        if not cancel:worker.deleteLater()
        thread.deleteLater();qtwindow.deleteLater();self.app.processEvents()
        return outputs,params

    def test_snake_actual_scan_body(self):self.execute('snakeScan')
    def test_one_wavelength_telemetry(self):self.execute('snakeScan',wavelengths=(1658,))
    def test_repeat_actual_scan_body(self):
        outputs,params=self.execute('repeatSnakeScan')
        self.assertEqual(outputs[-3:],['format','mat','timestamps'])
        self.assertEqual(dict(params.timeStamps),{'1000':[123,123],'1100':[123,123]})
    def test_snake_without_autofocus(self):self.execute('snakeScan',False)
    def test_repeat_without_autofocus(self):self.execute('repeatSnakeScan',False)
    def test_cancelled_worker_restores_frame_and_never_images(self):self.execute('snakeScan',cancel=True)
