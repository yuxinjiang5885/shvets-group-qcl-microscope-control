"""No hardware: all native-like operations are thread-recording fakes."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from threading import Thread, Event, get_ident
from time import sleep
from types import SimpleNamespace
from pathlib import Path
from hashlib import sha256
import unittest
from PyQt6.QtWidgets import QApplication, QMainWindow, QTabWidget
from ui.persistent_prior_owner import PersistentPriorOwner, constructor_with_proxy
from ui.stage_command_dispatcher import DispatchRejected, NativeCallUncertain
from ui.operational_localization_bridge import OperationalLocalizationBridge
from ui.localization_orchestration import LocalizationController, RunSettings, CleanupOutcome, OwnershipError, OwnershipStatus
from ui.registration_state import RegistrationState, RegistrationContext
from experiment.scan_1d import StageBounds
from test_reflection_scan import FakeClock


class NativeFake:
    def __init__(self, log, model, hold=None):
        self.log, self.hold = log, hold
        self.pos=(1000.,2000.)
        self.speeds=[10,100]; self.steps=[1,10]; self.accs=[100]
        self.defaultSpeed=100; self.defaultAcc=100; self.realHw=False
        self.record('construct')
    def record(self,name): self.log.append((name,get_ident()))
    def connect(self,port): self.record('connect')
    def identify(self): self.record('identify')
    def message(self,command,verbose=False):
        self.record('message')
        if self.hold:
            self.hold[0].set(); self.hold[1].wait(2)
        if command=='fail': return 7,'bad'
        if command.endswith('position.get'): return 0,','.join(map(str,self.pos))
        if command.endswith('busy.get'): return 0,'0'
        if 'goto-position' in command: self.pos=tuple(map(float,command.split()[-2:]))
        return 0,'0'
    def goto(self,x=0,y=0): self.record('goto'); self.pos=(x,y)
    def get_position(self): self.record('get_position'); return self.pos
    def busy(self): self.record('busy'); return '0'
    def stop_smoothly(self): self.record('stop_smoothly')
    def set_speed(self,v=0): self.record('set_speed')
    def get_speed(self): self.record('get_speed'); return 100
    def set_acc(self,a=0): self.record('set_acc')
    def get_acc(self): self.record('get_acc'); return 100
    def joystick(self,enable=False): self.record('joystick')
    def set_position(self,x=0,y=0): self.record('set_position'); self.pos=(x,y)
    def reference(self): self.record('reference')
    def wait_until_ready(self,timeout=5): self.record('wait_until_ready')
    def make_snakes(self,**kwargs): self.record('make_snakes'); return [kwargs]
    def arm_trigger(self,**kwargs): self.record('arm_trigger')
    def move_at_velocity(self,*args): self.record('move_at_velocity')
    def move_rel(self,*args): self.record('move_rel')
    def encoder_res(self): self.record('encoder_res'); return 20
    def disconnect(self): self.record('disconnect')
    def close_session(self): self.record('close_session'); return 0
    def __del__(self): self.record('destroy')


def stageInitializer(**kwargs):
    raise AssertionError('legacy raw initializer must never run')


class InertWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        init=stageInitializer(MODEL='HLD117',COM_PORT=3)
        init.stageInstance.connect(self.stage_set)
        init.stage_initialize()
        self.stageMotionWindow=SimpleNamespace(stage=self.stage,threadG=None,workerG=None,threadMW=[])
        self.tabs=QTabWidget(); self.setCentralWidget(self.tabs)
        self.stage.get_position()
    def stage_set(self,stage): self.stage=stage
    def closeEvent(self,event): self.stage.disconnect(); event.accept()


class OwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.log=[]; self.context=SimpleNamespace(); self.hold=None
        self.owner=PersistentPriorOwner(self.context,
            factory=lambda model: NativeFake(self.log,model,self.hold),timeout_s=.5)
        self.proxy=self.owner.start()
        self.addCleanup(self.finish_fake)
    def finish_fake(self):
        if self.hold: self.hold[1].set()
        ticket=self.owner.dispatcher.last_ticket
        if ticket: ticket.done.wait(3)
        # Test teardown only: positively completed fake, no real/native recovery API.
        self.owner.dispatcher.uncertain=False
        self.owner.dispatcher._active=None
        self.owner._closing=False
        self.owner.on_uncertain=None
        self.owner.shutdown()
    def names(self): return [v[0] for v in self.log]
    def bridge(self):
        state=RegistrationState(); state.set_context(RegistrationContext(marker_id='marker',frame_id='frame'))
        c=LocalizationController(state)
        window=SimpleNamespace(stage=self.proxy,stageMotionWindow=SimpleNamespace(
            stage=self.proxy,threadG=None,workerG=None,threadMW=[]))
        b=OperationalLocalizationBridge(window,c,executor=lambda call,timeout:call(),joystick_disabled=lambda:True)
        b.install_guards(); self.owner.on_uncertain=b.owner_uncertain
        return b,c,state
    def test_construction_on_owner(self): self.assertNotEqual(self.log[0][1],get_ident())
    def test_connect_identify_same_thread(self): self.assertEqual(len(set(t for n,t in self.log)),1)
    def test_persistent_after_initialization(self): self.assertTrue(self.owner.running)
    def test_factory_once(self): self.assertEqual(self.names().count('construct'),1)
    def test_connect_once(self): self.assertEqual(self.names().count('connect'),1)
    def test_second_owner_context_rejected(self):
        with self.assertRaises(DispatchRejected): PersistentPriorOwner(self.context)
    def test_second_start_rejected(self):
        with self.assertRaises(DispatchRejected): self.owner.start()
    def test_second_connect_rejected(self):
        with self.assertRaises(DispatchRejected): self.proxy.connect(3)
    def test_main_thread_proxy_return(self): self.assertEqual(self.proxy.get_position(),(1000.,2000.))
    def test_worker_thread_proxy_return(self):
        out=[]; t=Thread(target=lambda:out.append(self.proxy.get_position())); t.start();t.join(1)
        self.assertEqual(out,[(1000.,2000.)]); self.assertNotEqual(t.ident,self.log[0][1])
    def test_many_callers_serialized(self):
        threads=[Thread(target=lambda:self.proxy.get_position()) for _ in range(8)]
        for t in threads:t.start()
        for t in threads:t.join(1)
        self.assertEqual(self.names().count('get_position'),8)
        self.assertEqual(len(set(t for n,t in self.log)),1)
    def test_no_raw_handles(self):
        for name in ('SDK','session','rx','raw','stage'):
            with self.assertRaises(AttributeError): getattr(self.proxy,name)
    def test_position_move_busy_stop(self):
        self.proxy.goto(1001,2002);self.assertEqual(self.proxy.get_position(),(1001,2002))
        self.assertEqual(self.proxy.busy(),'0');self.proxy.stop_smoothly()
    def test_speed_acceleration(self):
        self.proxy.set_speed(10);self.proxy.set_acc(100)
        self.assertEqual(self.proxy.get_speed(),100);self.assertEqual(self.proxy.get_acc(),100)
    def test_joystick(self): self.proxy.joystick(enable=False);self.assertIn('joystick',self.names())
    def test_attribute_copies(self):
        speeds=self.proxy.speeds; speeds.append(999);self.assertEqual(self.proxy.speeds,[10,100])
    def test_scan_helpers(self):
        self.assertEqual(self.proxy.make_snakes(M=2),[{'M':2}]);self.proxy.arm_trigger(F=1)
    def test_wait_ready(self): self.proxy.wait_until_ready(timeout=1)
    def test_disconnect_owner_thread_and_destruction(self):
        self.assertTrue(self.owner.shutdown())
        self.assertIn('destroy',self.names());self.assertEqual(len(set(t for n,t in self.log)),1)
    def test_clean_shutdown_thread_stops(self):
        self.assertTrue(self.owner.shutdown());self.assertFalse(self.owner.running)
    def test_shutdown_idempotent(self):
        self.owner.shutdown();self.owner.shutdown();self.assertEqual(self.names().count('disconnect'),1)
    def test_proxy_disconnect_owns_full_cleanup(self):
        self.proxy.disconnect();self.assertTrue(self.owner.closed)
    def test_closed_rejects_calls(self):
        self.owner.shutdown()
        with self.assertRaises(DispatchRejected):self.proxy.get_position()
    def test_sdk_error_checked(self):
        with self.assertRaisesRegex(RuntimeError,'Prior_native_command_failed'):self.proxy.message('fail')
    def test_no_hardware_imports(self):
        import subprocess,sys
        code = '''
import sys
class Deny:
    def find_spec(self,name,*args):
        if name.split('.')[0] in ('instruments','PyDAQmx','pipython') or name=='qcl_scanning_imaging_ui':
            raise RuntimeError('hardware import forbidden: '+name)
sys.meta_path.insert(0,Deny())
import ui.persistent_prior_owner
import qcl_scanning_imaging_autorelocation_ui
'''
        result=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
    def test_context_redefine_invalidates_ordinary_move_does_not(self):
        b,c,s=self.bridge();generation=s.context_generation
        self.proxy.goto(1001,2000);self.assertEqual(s.context_generation,generation)
        self.proxy.set_position(1001,2000);self.assertGreater(s.context_generation,generation)
    def test_partial_connect_failure_cleans_on_owner_thread(self):
        log=[]
        class BadConnect(NativeFake):
            def connect(self,port):
                super().connect(port);raise RuntimeError('fake connect failure')
        owner=PersistentPriorOwner(SimpleNamespace(),factory=lambda model:BadConnect(log,model))
        with self.assertRaisesRegex(RuntimeError,'fake connect failure'):owner.start()
        self.assertTrue(owner.closed)
        self.assertEqual(len(set(t for n,t in log)),1)
        self.assertIn('close_session',[n for n,t in log])
    def test_failed_cleanup_is_not_reported_closed(self):
        failure=[True];log=[]
        class BadClose(NativeFake):
            def close_session(self):
                self.record('close_session');return -1 if failure[0] else 0
        owner=PersistentPriorOwner(SimpleNamespace(),factory=lambda model:BadClose(log,model))
        owner.start()
        try:
            self.assertFalse(owner.shutdown());self.assertFalse(owner.closed)
            self.assertTrue(owner.uncertain);self.assertTrue(owner.running)
            with self.assertRaises(DispatchRejected):owner.proxy.get_position()
        finally:
            # Inert teardown only, not a production recovery operation.
            failure[0]=False;owner.dispatcher.uncertain=False;owner._closing=False
            owner.shutdown()
    def test_localization_via_proxy(self):
        b,c,s=self.bridge();h=b.acquire(RunSettings(s.context,s.context_generation,'fake'))
        api=b.stage_interface(h,bounds=StageBounds(900,1100,1900,2100,'frame'),polling_s=.01,clock=FakeClock())
        api.move_to(1001,2000,timeout_s=1)
        self.assertEqual(api.get_position(timeout_s=1),(1001.,2000.))
        c.finish(h,succeeded=False,cleanup=CleanupOutcome(True,True))
    def test_legacy_goto_blocked_by_lease(self):
        b,c,s=self.bridge();h=b.acquire(RunSettings(s.context,s.context_generation,'fake'))
        with self.assertRaises(OwnershipError):self.proxy.goto(1001,2000)
        c.finish(h,succeeded=False,cleanup=CleanupOutcome(True,True))
    def test_legacy_goto_without_lease(self):
        b,c,s=self.bridge();self.proxy.goto(1001,2000);self.assertEqual(self.proxy.get_position(),(1001,2000))
    def test_stale_localization(self):
        b,c,s=self.bridge();h=b.acquire(RunSettings(s.context,s.context_generation,'fake'))
        c.finish(h,succeeded=False,cleanup=CleanupOutcome(True,True))
        with self.assertRaises(OwnershipError):b.execute_stage(h,lambda:None,1)
    def test_stable_ui_unchanged_and_independent(self):
        p=Path('qcl_scanning_imaging_ui.py');text=p.read_text(encoding='utf-8')
        self.assertEqual(sha256(p.read_bytes()).hexdigest(),'fbf8bdf5238d04ad3e95649c38bcdfc9ce4b02be65bf844034972fecdfcffaab')
        self.assertNotIn('persistent_prior_owner',text);self.assertNotIn('autorelocation',text)
    def test_constructor_globals_isolated(self):
        original=InertWindow.__init__.__globals__['stageInitializer']
        clone=constructor_with_proxy(InertWindow,self.proxy)
        self.assertIs(InertWindow.__init__.__globals__['stageInitializer'],original)
        self.assertIsNot(clone.__globals__['stageInitializer'],original)
    def test_experimental_startup_one_proxy_no_legacy_initializer(self):
        from qcl_scanning_imaging_autorelocation_ui import operational_window_class
        log=[]; owners=[]
        def factory(context):
            owner=PersistentPriorOwner(context,factory=lambda model:NativeFake(log,model));owners.append(owner);return owner
        window=operational_window_class(InertWindow,owner_factory=factory)()
        self.assertIs(window.stage,owners[0].proxy)
        self.assertIs(window.stageMotionWindow.stage,window.stage)
        self.assertEqual([n for n,t in log].count('construct'),1)
        self.assertEqual(window.tabs.tabText(0),'Auto Location')
        window.close();self.assertTrue(owners[0].closed)


class TimeoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.hold=(Event(),Event());self.log=[]
        self.owner=PersistentPriorOwner(SimpleNamespace(),factory=lambda model:NativeFake(self.log,model,self.hold),timeout_s=.05)
        self.proxy=self.owner.start();self.addCleanup(self.cleanup)
    def cleanup(self):
        self.hold[1].set();self.owner.dispatcher.last_ticket.done.wait(3)
        self.owner.dispatcher.uncertain=False;self.owner.dispatcher._active=None
        self.owner._closing=False;self.owner.on_uncertain=None;self.owner.shutdown()
    def timeout(self):
        with self.assertRaises(NativeCallUncertain):self.proxy.message('delayed')
    def test_timeout_does_not_cancel(self):
        self.timeout();self.assertTrue(self.owner.dispatcher.unresolved);self.assertTrue(self.owner.running)
    def test_unresolved_shutdown_fails_without_disconnect(self):
        self.timeout();self.assertFalse(self.owner.shutdown());self.assertNotIn('disconnect',[n for n,t in self.log])
    def test_late_completion_keeps_quarantine(self):
        self.timeout();self.hold[1].set();self.owner.dispatcher.last_ticket.done.wait(1)
        self.assertTrue(self.owner.uncertain)
        with self.assertRaises(DispatchRejected):self.proxy.get_position()
    def test_no_concurrent_stop(self):
        self.timeout()
        with self.assertRaises(DispatchRejected):self.proxy.stop_smoothly()
        self.assertNotIn('stop_smoothly',[n for n,t in self.log])
    def test_shutdown_during_active_call(self):
        errors=[]
        def run():
            try:self.proxy.message('delayed')
            except Exception as e:errors.append(e)
        t=Thread(target=run);t.start();self.hold[0].wait(1)
        self.assertFalse(self.owner.shutdown());self.assertTrue(self.owner.running)
        t.join(1);self.assertTrue(errors)
    def test_timeout_quarantines_localization(self):
        state=RegistrationState();state.set_context(RegistrationContext(marker_id='m',frame_id='f'))
        controller=LocalizationController(state)
        window=SimpleNamespace(stage=self.proxy,stageMotionWindow=SimpleNamespace(
            stage=self.proxy,threadG=None,workerG=None,threadMW=[]))
        bridge=OperationalLocalizationBridge(window,controller,executor=lambda call,timeout:call(),joystick_disabled=lambda:True)
        bridge.install_guards();self.owner.on_uncertain=bridge.owner_uncertain
        handle=bridge.acquire(RunSettings(state.context,state.context_generation,'fake'))
        with self.assertRaises(NativeCallUncertain):
            bridge.execute_stage(handle,lambda:self.proxy.message('delayed'),1)
        self.assertEqual(controller.ownership.status,OwnershipStatus.QUARANTINED)
        controller.finish(handle,succeeded=False,cleanup=CleanupOutcome(False,False))
