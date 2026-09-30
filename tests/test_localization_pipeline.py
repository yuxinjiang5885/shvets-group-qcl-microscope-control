"""Full unchanged scan/analysis chain over numerical Prior and DAQ fakes."""
from dataclasses import replace
from math import tanh
from tempfile import TemporaryDirectory
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from test_operational_localization_bridge import environment
from test_reflection_scan import FakeClock
from ui.localization_orchestration import LocateMarkerWorker, RunSettings, AcquisitionState, OwnershipStatus
from ui.localization_pipeline import LocalizationSpec, LocalizationPipelineServices, DaqSettings, plan_profiles
from experiment.scan_1d import StageBounds
from ui.registration_state import replay_archived_evidence

ROOT = Path(__file__).resolve().parents[1]


class FakeDAQ:
    def __init__(self, stage, settings):
        assert settings == DaqSettings()
        self.stage = stage
        self.clear_count = 0
        self.clear_fails = False
        self.flat = False
        self.fail = False
        self.reads = 0

    def acquire_bounded(self, count, *, timeout_s):
        if self.fail:
            raise RuntimeError('synthetic_read_failure')
        x, y = self.stage.position
        fx = (tanh((x-750)/3)-tanh((x-1250)/3))/2
        fy = (tanh((y-1750)/3)-tanh((y-2250)/3))/2
        value = 1. if self.flat else 1.+3.*fx*fy
        self.reads += 1
        return [[value]*count, [0.]*count]

    def clear(self):
        self.clear_count += 1
        if self.clear_fails:
            raise RuntimeError('synthetic_clear_failure')


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.window, self.state, self.controller, self.bridge = environment()
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.spec = LocalizationSpec((1000., 2000.), StageBounds(600, 1400, 1600, 2400, 'fixture-frame'))
        self.clock = FakeClock()
        self.task = None
        self.events = []
        self.hook = None

    def run_pipeline(self):
        settings = RunSettings(self.state.context, self.state.context_generation, 'confirmed-fixture-start')
        self.handle = self.bridge.acquire(settings)
        def factory(config):
            self.task = FakeDAQ(self.window.stage, config)
            return self.task
        self.services = LocalizationPipelineServices(self.bridge, self.handle, self.spec,
            self.tmp.name, factory, clock=self.clock)
        def observe(event):
            self.events.append(event)
            if self.hook:
                self.hook(event)
        LocateMarkerWorker(self.controller, self.handle, self.services).run(observe)

    def test_complete_real_algorithms_chain_and_success_only_return(self):
        self.run_pipeline()
        self.assertEqual(self.controller.machine.state, AcquisitionState.COMPLETE, self.controller.reasons)
        self.assertEqual(len(self.services.journals), 7)
        self.assertEqual(self.state.evidence.classification.central_identifiers, ('P1','P2','P3','P4','P5'))
        self.assertEqual(self.state.evidence.rotation.used_profile_count, 5)
        self.assertAlmostEqual(self.state.registration.registration.marker_stage_x_um, 1000, places=5)
        self.assertAlmostEqual(self.state.registration.registration.marker_stage_y_um, 2000, places=5)
        self.assertEqual(self.window.stage.position, self.spec.rough_start_xy)
        self.assertEqual(self.task.clear_count, 1)
        self.assertIsNone(self.bridge.daq.run_id)
        self.assertEqual(sum(event.name == 'profile_completed' for event in self.events), 7)

    def test_return_renewed_busy_restarts_full_idle_interval(self):
        from types import SimpleNamespace
        observations = []
        def busy(**kwargs):
            observations.append(self.clock.monotonic())
            return len(observations) == 2
        service = SimpleNamespace(spec=self.spec, clock=self.clock,
            stage=SimpleNamespace(move_to=lambda *a, **k: None,
                is_busy=busy, get_position=lambda **k: self.spec.rough_start_xy))
        LocalizationPipelineServices._return(service, lambda: None)
        self.assertGreaterEqual(self.clock.monotonic()-observations[2], self.spec.settling_s)

    def fail_at(self, phase, *, flat=False):
        def hook(event):
            if event.name == 'phase_changed' and event.detail == phase:
                self.task.flat = flat
                self.task.fail = not flat
        self.hook = hook

    def test_initial_h_edge_failure(self):
        self.fail_at('initial_H', flat=True)
        self.run_pipeline()
        self.assertEqual(self.controller.machine.state, AcquisitionState.FAILED)
        self.assertEqual(len(self.services.journals), 0)
        self.assertIn('edge_failed:initial_H', str(self.controller.reasons))

    def test_initial_v_failure_retains_h_journal(self):
        self.fail_at('initial_V')
        self.run_pipeline()
        self.assertEqual(len(self.services.journals), 1)
        self.assertEqual(self.controller.machine.state, AcquisitionState.FAILED)

    def test_profile_n_failure_stops_no_extra_scan_or_return(self):
        self.fail_at('P3')
        self.run_pipeline()
        self.assertEqual(len(self.services.journals), 4)
        self.assertFalse((self.services.path/'P4.jsonl').exists())
        self.assertNotEqual(self.window.stage.position, self.spec.rough_start_xy)

    def test_planning_failure(self):
        with patch('ui.localization_pipeline.plan_profiles', side_effect=ValueError('planning_failure')):
            self.run_pipeline()
        self.assertEqual(len(self.services.journals), 2)
        self.assertEqual(self.controller.machine.state, AcquisitionState.FAILED)

    def test_classification_failure(self):
        from experiment.marker_profile_classification import classify_profiles
        def reject(*args, **kwargs):
            return replace(classify_profiles(*args, **kwargs), sufficient_for_rotation_fit=False,
                           reasons=('synthetic_insufficient',), usable_final_fits=None)
        with patch('ui.localization_pipeline.classify_profiles', side_effect=reject):
            self.run_pipeline()
        self.assertIn('classification_failed', str(self.controller.reasons))
        self.assertIsNone(self.state.registration)

    def test_rotation_failure(self):
        from experiment.marker_rotation import fit_rotation
        def reject(*args, **kwargs):
            return replace(fit_rotation(*args, **kwargs), valid=False, reasons=('synthetic_hard_failure',))
        with patch('ui.localization_pipeline.fit_rotation', side_effect=reject):
            self.run_pipeline()
        self.assertIn('rotation_failed', str(self.controller.reasons))

    def test_center_failure(self):
        from experiment.marker_center_refinement import refine_marker_center
        def reject(*args, **kwargs):
            return replace(refine_marker_center(*args, **kwargs), valid=False, reasons=('synthetic_chord_failure',))
        with patch('ui.localization_pipeline.refine_marker_center', side_effect=reject):
            self.run_pipeline()
        self.assertIn('center_failed', str(self.controller.reasons))

    def test_registration_build_failure(self):
        with patch('ui.localization_pipeline.build_stage_registration', side_effect=ValueError('synthetic_bridge_failure')):
            self.run_pipeline()
        self.assertIsNone(self.state.registration)
        self.assertIn('synthetic_bridge_failure', str(self.controller.reasons))

    def test_return_failure_prevents_publication(self):
        def hook(event):
            if event.name == 'phase_changed' and event.detail == 'return':
                self.window.stage.fail = lambda command: 'goto-position' in command
        self.hook = hook
        self.run_pipeline()
        self.assertIn(self.controller.machine.state, (AcquisitionState.FAILED, AcquisitionState.CANCELLED))
        self.assertIsNone(self.state.registration)

    def test_cleanup_failure_quarantines(self):
        def hook(event):
            if self.task:
                self.task.clear_fails = True
        self.hook = hook
        self.run_pipeline()
        self.assertEqual(self.controller.ownership.status, OwnershipStatus.QUARANTINED)
        self.assertIsNone(self.state.registration)

    def test_cancellation_at_multiple_phase_boundaries(self):
        for phase in ('initial_H', 'initial_V', 'P2', 'return'):
            with self.subTest(phase=phase):
                self.setUp()
                self.hook = lambda event: self.controller.request_cancel() if event.name == 'phase_changed' and event.detail == phase else None
                self.run_pipeline()
                self.assertEqual(self.controller.machine.state, AcquisitionState.CANCELLED)
                self.assertIsNone(self.state.registration)

    def test_context_change_before_publication(self):
        self.hook = lambda event: self.bridge.frame_event('sample') if event.name == 'phase_changed' and event.detail == 'cleanup' else None
        self.run_pipeline()
        self.assertIsNone(self.state.registration)
        self.assertEqual(self.controller.machine.state, AcquisitionState.CANCELLED)

    def test_prior_approval_survives_safe_failed_candidate(self):
        evidence = replay_archived_evidence(ROOT)
        self.state.accept(replace(evidence, context=self.state.context))
        previous = self.state.registration
        self.fail_at('initial_H', flat=True)
        self.run_pipeline()
        self.assertIs(self.state.registration, previous)

    def test_warning_retained_end_to_end(self):
        from experiment.marker_rotation import fit_rotation
        def warn(*args, **kwargs):
            return replace(fit_rotation(*args, **kwargs), warnings=('synthetic_edge_warning',))
        with patch('ui.localization_pipeline.fit_rotation', side_effect=warn):
            self.run_pipeline()
        self.assertEqual(self.controller.machine.state, AcquisitionState.COMPLETE, self.controller.reasons)
        self.assertIn('synthetic_edge_warning', self.state.warnings)

    def test_planner_and_spec_translation_not_archived_coordinates(self):
        moved = replace(self.spec, rough_start_xy=(0, 0), bounds=StageBounds(-400,400,-400,400,'another'))
        original = plan_profiles(self.spec, (1000, 2000))
        self.assertEqual(tuple(v-2000 for v in original), plan_profiles(moved, (0,0)))
        self.assertGreaterEqual(max(original)-min(original), 100)
        self.assertEqual(len(set(original)), 5)

    def test_invalid_specs(self):
        for changes in ({'step_um': 0}, {'step_um': .5}, {'supported_rotation_deg': 45},
                        {'profile_count': 2}, {'rough_start_xy': (1000.5,2000)},
                        {'required_y_span_um': 10}, {'center_uncertainty_um': 300}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.spec, **changes)
        with self.assertRaises(ValueError):
            DaqSettings(reset=True)

    def test_journal_verification_failure(self):
        with patch('ui.localization_pipeline.load_scan', side_effect=ValueError('journal_corruption')):
            self.run_pipeline()
        self.assertEqual(self.controller.machine.state, AcquisitionState.FAILED)
        self.assertIsNone(self.state.registration)

    def test_cancel_inside_initial_h_retains_partial_journal(self):
        original = FakeDAQ.acquire_bounded
        def cancel_after_reads(task, *args, **kwargs):
            result = original(task, *args, **kwargs)
            if task.reads == 4:
                self.controller.request_cancel()
            return result
        with patch.object(FakeDAQ, 'acquire_bounded', cancel_after_reads):
            self.run_pipeline()
        from experiment.scan_1d import load_scan
        saved = load_scan(self.services.path/'initial_H.jsonl')
        self.assertEqual(len(saved.points), 4)
        self.assertEqual(self.controller.machine.state, AcquisitionState.CANCELLED)
        self.assertFalse((self.services.path/'initial_V.jsonl').exists())

    def test_position_error_does_not_continue_or_retry(self):
        original = self.window.stage.message
        def offset_readback(command):
            result = original(command)
            if command == 'controller.stage.position.get' and self.bridge.movement_attempted:
                x, y = self.window.stage.position
                return 0, f'{x+2},{y}'
            return result
        self.window.stage.message = offset_readback
        self.run_pipeline()
        self.assertEqual(self.controller.machine.state, AcquisitionState.FAILED)
        self.assertEqual(self.task.reads, 0)
        self.assertFalse((self.services.path/'initial_V.jsonl').exists())

    def test_start_mismatch_before_any_motion_or_daq(self):
        self.window.stage.position = (1001.,2000.)
        self.run_pipeline()
        self.assertFalse(self.bridge.movement_attempted)
        self.assertIsNone(self.task)
        self.assertIsNone(self.state.registration)

    def test_frame_change_invalidates_prior_approval(self):
        evidence = replay_archived_evidence(ROOT)
        self.state.accept(replace(evidence, context=self.state.context))
        self.hook = lambda event: self.bridge.frame_event('reset') if event.name == 'phase_changed' and event.detail == 'P2' else None
        self.run_pipeline()
        self.assertIsNone(self.state.registration)
        self.assertEqual(self.controller.machine.state, AcquisitionState.CANCELLED)

    def test_full_pipeline_blocks_hardware_imports(self):
        script = '''
import sys, importlib.abc
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('instruments','PyDAQmx','pipython','inputs','qcl_scanning_imaging_ui','PyQt6') or fullname == 'experiment.routines':
            raise AssertionError(fullname)
sys.meta_path.insert(0, Block())
sys.path.insert(0, 'tests')
from test_localization_pipeline import PipelineTests
test = PipelineTests('test_complete_real_algorithms_chain_and_success_only_return')
test.setUp()
try: test.test_complete_real_algorithms_chain_and_success_only_return()
finally: test.doCleanups()
'''
        result = subprocess.run([sys.executable,'-B','-c',script], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)


if __name__ == '__main__':
    unittest.main()
