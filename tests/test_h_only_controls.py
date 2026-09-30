"""Qt worker/close lifecycle with a persistent fake Prior owner and fake NI."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from dataclasses import replace
from tempfile import TemporaryDirectory
from time import monotonic,sleep
from types import SimpleNamespace
from threading import Event
import unittest
from PyQt6.QtWidgets import QApplication
from test_persistent_prior_owner import NativeFake,InertWindow
from test_localization_daq import FakeNI
from test_reflection_scan import FakeClock
from qcl_scanning_imaging_autorelocation_ui import operational_window_class
from ui.persistent_prior_owner import PersistentPriorOwner
from ui.h_only_controls import HOnlyRunner
from ui.h_only_validation import HOnlyServices,HOnlySpec,OperatorConfirmation
from ui.localization_orchestration import AcquisitionState,OwnershipStatus,OwnershipError,WorkerEvent
from experiment.scan_1d import StageBounds


class FastServices(HOnlyServices):
    def __init__(self,*a,**k):super().__init__(*a,clock=FakeClock(),**k)


class HOnlyQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.log=[];self.observed=SimpleNamespace(position=(1000.,2000.))
        observed=self.observed
        class Prior(NativeFake):
            def message(self,command,verbose=False):
                result=super().message(command,verbose)
                observed.position=self.pos
                return result
        def factory(context):return PersistentPriorOwner(context,factory=lambda model:Prior(self.log,model),timeout_s=2.)
        self.window=operational_window_class(InertWindow,owner_factory=factory)()
        self.window.laser=SimpleNamespace(isArmed=True,isTuned=True,isEmitting=False)
        self.window.stage.joystick(enable=False)
        self.state=self.window.auto_relocation.state
        self.state.set_context(replace(self.state.context,gds_path='fixture.gds',marker_id='fixture-marker',
            frame_id='fixture-frame',sample_id='fixture-sample',inputs_id='fixture-input'))
        self.backend=FakeNI(self.observed)
        self.runner=HOnlyRunner(self.window,backend=self.backend,services_type=FastServices)
        self.window.h_only_runner=self.runner
        self.controller=self.window.localization_bridge.controller
        self.spec=HOnlySpec((1000.,2000.),StageBounds(649,1351,1999,2001,'fixture-frame'))
        self.confirm=OperatorConfirmation(True,True,True,True,note='inert validation')
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.cleanup_window)

    def pump(self,predicate,seconds=10):
        end=monotonic()+seconds
        while not predicate() and monotonic()<end:
            self.app.processEvents();sleep(.001)
        self.assertTrue(predicate(),'Qt fake did not finish')

    def cleanup_window(self):
        if self.runner.busy:
            self.controller.request_cancel();self.pump(lambda:not self.runner.busy)
        self.window.localization_display_timer.stop()
        # Test teardown of positively completed inert owner only.
        self.window.stage.command_guard=None
        self.window.prior_owner.on_uncertain=None
        self.assertTrue(self.window.prior_owner.shutdown())
        self.window.deleteLater();self.app.processEvents()

    def start(self):return self.runner.start(self.spec,self.confirm,self.tmp.name)

    def test_Qt_success_persistent_stage_and_owned_DAQ(self):
        self.start();self.pump(lambda:not self.runner.busy)
        self.assertEqual(self.controller.machine.state,AcquisitionState.COMPLETE,self.controller.reasons)
        report=self.window.auto_relocation.run_display['h_only_result']
        self.assertEqual(report['points'],71)
        self.assertEqual(report['return_status'],'PASS')
        self.assertFalse(report['registration_published'])
        self.assertTrue((self.runner.services.path/'h_only_result.json').exists())
        self.assertFalse(self.window.auto_relocation.locate_button.isEnabled())
        self.assertEqual(self.backend.calls.count('clear'),1)
        self.assertIs(self.backend.reset,False)
        self.assertEqual(len({tid for name,tid in self.log}),1)
        self.assertEqual(sum(name=='connect' for name,_ in self.log),1)

    def test_duplicate_start_rejected(self):
        self.start()
        self.assertFalse(self.window.h_only_controls.fields['x'].isEnabled())
        with self.assertRaisesRegex(OwnershipError,'already_active'):self.start()
        self.pump(lambda:not self.runner.busy)
        self.assertTrue(self.window.h_only_controls.fields['x'].isEnabled())

    def test_Qt_cancellation(self):
        self.start();self.controller.request_cancel()
        self.pump(lambda:not self.runner.busy)
        self.assertEqual(self.controller.machine.state,AcquisitionState.CANCELLED)
        self.assertIsNone(self.state.registration)

    def test_close_during_run_defers_then_closes_owner(self):
        self.start();self.window.close()
        self.assertTrue(self.window.localization_bridge.close_pending)
        self.assertFalse(self.window.prior_owner.closed)
        self.pump(lambda:self.window.prior_owner.closed)
        self.assertFalse(self.runner.busy)

    def test_cleanup_quarantine_prevents_deferred_close(self):
        self.backend.clear_fail=True
        self.start();self.pump(lambda:not self.runner.busy)
        self.assertEqual(self.controller.ownership.status,OwnershipStatus.QUARANTINED)
        self.window.close();self.app.processEvents()
        self.assertFalse(self.window.prior_owner.closed)

    def test_stale_signal_ignored(self):
        handle=self.start()
        self.window.auto_relocation.consume_localization_event(WorkerEvent('progress','other-run',handle.settings.context_generation,{'bad_stale':True}))
        self.assertNotIn('bad_stale',self.window.auto_relocation.run_display)
        self.pump(lambda:not self.runner.busy)

    def test_legacy_stage_command_blocked_before_native(self):
        self.start()
        with self.assertRaises(OwnershipError):self.window.stage.goto(123,456)
        self.assertFalse(any(n=='goto' for n,_ in self.log))
        self.pump(lambda:not self.runner.busy)

    def test_frame_mismatch_before_any_handoff(self):
        self.spec=replace(self.spec,bounds=replace(self.spec.bounds,frame_id='wrong-frame'))
        before=len(self.log)
        with self.assertRaisesRegex(ValueError,'frame_mismatch'):self.start()
        self.assertEqual(len(self.log),before)
        self.assertFalse(self.runner.busy)

    def test_context_change_prevents_success(self):
        self.start();self.window.localization_bridge.frame_event('sample')
        self.pump(lambda:not self.runner.busy)
        self.assertNotEqual(self.controller.machine.state,AcquisitionState.COMPLETE)
        self.assertIsNone(self.state.registration)

    def test_native_read_unresolved_defers_close_without_disconnect(self):
        entered,release=Event(),Event()
        original=self.backend.read
        def blocked(*args):
            entered.set();release.wait(5)
            return original(*args)
        self.backend.read=blocked
        self.start()
        try:
            self.pump(entered.is_set)
            self.window.close()
            self.app.processEvents()
            self.assertTrue(self.runner.busy)
            self.assertFalse(self.window.prior_owner.closed)
            self.assertNotIn('clear',self.backend.calls)
            self.assertFalse(any(n=='disconnect' for n,_ in self.log))
        finally:release.set()
        self.pump(lambda:self.window.prior_owner.closed)
        self.assertEqual(self.controller.machine.state,AcquisitionState.CANCELLED)

    def test_fresh_envelope_preview_required(self):
        controls=self.window.h_only_controls
        self.assertFalse(controls.run_button.isEnabled())
        controls.reviewed='stale'
        controls.fields['x'].setText('1000')
        self.assertIsNone(controls.reviewed)
        self.assertFalse(controls.run_button.isEnabled())


if __name__=='__main__':unittest.main()
