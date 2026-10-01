"""Legacy callback code is compiled without executing vendor imports/startup."""
from pathlib import Path
from types import MethodType, SimpleNamespace, CodeType, FunctionType
import unittest
from unittest.mock import patch

from ui.legacy_daq_tracking import invoke_acquisition
from ui.localization_orchestration import OwnershipError
from test_operational_localization_bridge import environment, FakeThread
import test_translation_localization as production

ROOT=Path(__file__).resolve().parents[1]


def actual_callback(name, window, namespace):
    path=ROOT/'qcl_scanning_imaging_ui.py'
    compiled=compile(path.read_bytes(),str(path),'exec',dont_inherit=True)
    cls=next(c for c in compiled.co_consts if isinstance(c,CodeType) and c.co_name=='mainWindow')
    code=next(c for c in cls.co_consts if isinstance(c,CodeType) and c.co_name==name)
    return MethodType(FunctionType(code,namespace,name),window)


class AttestationTests(unittest.TestCase):
    def setUp(self):
        self.window,self.state,self.controller,self.bridge=environment()

    def legacy_window(self, armed=False):
        button=lambda checked:SimpleNamespace(isChecked=lambda:checked,setChecked=lambda _:None)
        self.window.btn={name:[button(armed if name=='Arm' else False)]
                         for name in ('Arm','Start','Sweep','RefEnable')}
        self.window.parameters=SimpleNamespace()
        self.window.laser=object()
        self.window.notes=SimpleNamespace(toPlainText=lambda:'fixture')
        self.window.inputField={name:[SimpleNamespace(text=lambda v=value:v)] for name,value in
            (('WlStart','1500'),('WlEnd','1600'),('WlStep','1'),('SamplesPerWl','32'),('SamplingRate','100000'),('Speed','1'))}
        self.window.wlUnits='invcm'
        self.window.lock_controls=lambda:None
        self.window.statusbar=SimpleNamespace(showMessage=lambda _:None)

    def test_fresh_state_never_acquired_not_release_required(self):
        self.assertFalse(self.bridge.legacy_daq_cleanup_unverified)
        self.assertEqual(self.bridge.legacy_daq_evidence.snapshot()['state'],'never_acquired')
        self.assertEqual(self.bridge.blockers(),())

    def test_reproduces_old_false_latch_on_actual_no_task_callback(self):
        self.legacy_window()
        calls=[]
        callback=actual_callback('run_experiment',self.window,{'QThread':lambda:calls.append('thread')})
        # Prior wrapper marked dirty even though actual callback rejects unarmed laser.
        self.bridge.legacy_daq_cleanup_unverified=True
        callback()
        self.assertEqual(calls,[])
        self.assertIn('legacy_DAQ_release_not_attested_fresh_session_required',self.bridge.blockers())

    def test_actual_early_return_does_not_dirty_clean_session(self):
        self.legacy_window()
        calls=[]
        callback=actual_callback('run_experiment',self.window,{'QThread':lambda:calls.append('thread')})
        invoke_acquisition(callback,self.bridge.mark_legacy_daq_uncertain)
        self.assertEqual(calls,[])
        self.assertEqual(self.bridge.blockers(),())

    def test_task_capable_worker_creation_latches_before_factory(self):
        self.legacy_window(armed=True)
        def creating():
            self.assertTrue(self.bridge.legacy_daq_cleanup_unverified)
            raise RuntimeError('inert factory boundary')
        callback=actual_callback('run_experiment',self.window,{'QThread':creating})
        with self.assertRaisesRegex(RuntimeError,'factory boundary'):
            invoke_acquisition(callback,self.bridge.mark_legacy_daq_uncertain)
        self.assertEqual(self.bridge.legacy_daq_evidence.snapshot()['transitions'][0]['source'],
                         'worker_creation:run_experiment')

    def test_active_worker_blocks_even_with_positive_verifier(self):
        token=self.bridge.mark_legacy_daq_uncertain('fake owner',owner=object(),verifier=lambda _:True)
        self.window.threadRun=FakeThread()
        with self.assertRaisesRegex(OwnershipError,'still_active'):
            self.bridge.confirm_legacy_daq_release(token)
        self.assertTrue(self.bridge.legacy_daq_cleanup_unverified)

    def test_positive_owner_bound_release_permits_localization(self):
        owner=object();seen=[]
        token=self.bridge.mark_legacy_daq_uncertain('instrumented fake owner',owner=owner,
            verifier=lambda obj:seen.append(obj) or True)
        self.bridge.confirm_legacy_daq_release(token)
        self.assertEqual(seen,[owner])
        self.assertEqual(self.bridge.blockers(),())
        self.assertEqual(self.bridge.legacy_daq_evidence.snapshot()['state'],'released')

    def test_uncertain_release_and_uninstrumented_completion_stay_blocked(self):
        token=self.bridge.mark_legacy_daq_uncertain('uncertain fake owner',owner=object(),verifier=lambda _:False)
        with self.assertRaisesRegex(OwnershipError,'unconfirmed'):self.bridge.confirm_legacy_daq_release(token)
        self.window.threadRun=FakeThread(running=False)
        self.assertTrue(self.bridge.legacy_daq_cleanup_unverified)
        unknown=self.bridge.mark_legacy_daq_uncertain('legacy worker without cleanup attestation')
        with self.assertRaisesRegex(OwnershipError,'no_release_verifier'):self.bridge.confirm_legacy_daq_release(unknown)
        with self.assertRaises(OwnershipError):self.bridge.legacy_daq_cleanup_unverified=False

    def test_release_cannot_clear_other_owner_or_stale_token(self):
        first=self.bridge.mark_legacy_daq_uncertain('one',owner=object(),verifier=lambda _:True)
        self.bridge.mark_legacy_daq_uncertain('two')
        self.bridge.confirm_legacy_daq_release(first)
        self.assertTrue(self.bridge.legacy_daq_cleanup_unverified)
        with self.assertRaises(OwnershipError):self.bridge.confirm_legacy_daq_release(first)

    def test_noop_cannot_erase_previous_uncertain_acquisition(self):
        self.legacy_window()
        self.bridge.mark_legacy_daq_uncertain('previous acquisition')
        callback=actual_callback('run_experiment',self.window,{'QThread':lambda:None})
        invoke_acquisition(callback,self.bridge.mark_legacy_daq_uncertain)
        self.assertTrue(self.bridge.legacy_daq_cleanup_unverified)

    def test_nonowning_PI_object_is_not_NI_widget(self):
        self.window.pi_scanner=SimpleNamespace(pidevice=object())
        self.assertEqual(self.bridge.blockers(),())
        self.window.pi_scanner_widget=SimpleNamespace(daq=object())
        self.assertIn('objective_daq_autofocus_ownership_unconfirmed',self.bridge.blockers())

    def test_objective_active_or_uncertain_flags_remain_blockers(self):
        for field in ('autofocus_active','objective_motion_active','objective_daq_active',
                      'objective_ownership_uncertain','legacy_daq_active'):
            setattr(self.window,field,True)
            self.assertIn(field,self.bridge.blockers())
            setattr(self.window,field,False)

    def test_new_session_does_not_inherit_attestation(self):
        self.bridge.mark_legacy_daq_uncertain('old session')
        *_,fresh=environment()
        self.assertFalse(fresh.legacy_daq_cleanup_unverified)
        self.assertNotEqual(fresh.legacy_daq_evidence.session_id,self.bridge.legacy_daq_evidence.session_id)

    def test_unknown_callback_never_assumed_clean(self):
        invoke_acquisition(lambda:None,self.bridge.mark_legacy_daq_uncertain)
        self.assertTrue(self.bridge.legacy_daq_cleanup_unverified)


class FreshProductionTests(unittest.TestCase):
    setUpClass=classmethod(production.TranslationTests.setUpClass.__func__)
    def setUp(self):
        from test_persistent_prior_owner import InertWindow
        self.legacy_factory_calls=[]
        callback=actual_callback('run_experiment',SimpleNamespace(),
            {'QThread':lambda:self.legacy_factory_calls.append('thread')})
        hook=patch.object(InertWindow,'run_experiment',callback.__func__,create=True)
        hook.start()
        self.addCleanup(hook.stop)
        production.TranslationTests.setUp(self)
    pump=production.TranslationTests.pump
    cleanup_window=production.TranslationTests.cleanup_window
    run_production=production.TranslationTests.run_production

    def test_experimental_wrapper_noop_preserves_production_eligibility(self):
        self.window.btn={name:[SimpleNamespace(isChecked=lambda:False,setChecked=lambda _:None)]
                         for name in ('Arm','Start','Sweep')}
        self.window.run_experiment()
        self.assertEqual(self.legacy_factory_calls,[])
        self.assertFalse(self.window.localization_bridge.legacy_daq_cleanup_unverified)
        self.run_production()
        self.assertIsNotNone(self.state.registration)

    def test_fresh_experimental_constructor_permits_unchanged_HV_production(self):
        self.assertEqual(self.window.localization_bridge.legacy_daq_evidence.snapshot()['state'],'never_acquired')
        self.window.pi_scanner=SimpleNamespace(pidevice=object())
        self.run_production()
        self.assertEqual(self.state.registration.registration_mode,'translation_only')
        self.assertEqual([p.name for p in self.runner.services.journals],['initial_H.jsonl','initial_V.jsonl'])
