"""Actual experimental constructor + inert owner; preflight never calls devices."""
from dataclasses import replace
from enum import Enum
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch, Mock

import test_multi_h_controls as fixtures
from experiment.stage_registration import Orientation
from ui.multi_h_preflight import multi_h_preflight, run_settings
from ui.runtime_provenance import MODULES, REPO, runtime_provenance


class PreflightTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.MultiHQtTests.setUpClass.__func__)
    setUp = fixtures.MultiHQtTests.setUp
    cleanup_window = fixtures.MultiHQtTests.cleanup_window
    pump = fixtures.MultiHQtTests.pump
    select_fixture_marker = fixtures.MultiHQtTests.select_fixture_marker

    def test_experimental_constructor_button_has_zero_device_calls(self):
        controls = self.select_fixture_marker()
        # No envelope preview: preflight must not even read stage coordinates.
        stage_calls = list(self.log)
        files_before = list(Path(self.tmp.name).iterdir())
        laser = Mock()
        self.window.laser = laser
        approval = self.state.registration
        generation = self.state.context_generation
        with patch.object(self.window.stage, 'get_position', side_effect=AssertionError('readback')), \
             patch.object(self.window.stage, 'message', side_effect=AssertionError('stage command')), \
             patch('ui.h_only_controls.InputHandoff', side_effect=AssertionError('handoff')), \
             patch('ui.h_only_controls.LocalizationDAQProvider', side_effect=AssertionError('DAQ')):
            controls.multi_preflight_button.click()
        report = controls.preflight_report
        self.assertTrue(report['valid'], report)
        self.assertEqual(self.log, stage_calls)
        self.assertEqual(self.backend.calls, [])
        self.assertIsNone(self.controller.active)
        self.assertIs(self.state.registration, approval)
        self.assertEqual(self.state.context_generation, generation)
        self.assertEqual(list(Path(self.tmp.name).iterdir()), files_before)
        self.assertEqual(laser.mock_calls, [])
        self.assertFalse(report['registration_published'])
        self.assertTrue(report['orientation_gate']['identical'])
        self.assertEqual(len({m['class_id'] for m in report['orientation_gate']['orientation_modules']}), 1)
        for name in MODULES:
            self.assertEqual(report['provenance']['modules'][name]['resolved_path'],
                             str(REPO.joinpath(*name.split('.')).with_suffix('.py')))
        self.assertFalse(report['provenance']['duplicate_logical_modules'])
        self.assertFalse(self.window.auto_relocation.locate_button.isEnabled())

    def test_settings_are_same_builder_and_context_not_reconstructed(self):
        settings = run_settings(self.state.context,self.state.context_generation,(1000.,2000.),'multi_h')
        report = multi_h_preflight(self.state.context,self.state.context_generation,rough_start_xy=(1000.,2000.))
        self.assertIs(settings.context, self.state.context)
        self.assertEqual(report['settings']['expected_rough_start_id'], settings.expected_rough_start_id)
        self.assertEqual(report['settings']['purpose'], settings.purpose)

    def test_duplicate_import_and_enum_are_exposed_and_rejected(self):
        duplicate = Enum('Orientation', {'FLIP_X':'flip_x'}, type=str, module='alternate.stage_registration')
        module = ModuleType('alternate.stage_registration')
        module.__file__ = str(REPO/'experiment/stage_registration.py')
        module.Orientation = duplicate
        with patch.dict(sys.modules, {'alternate.stage_registration':module}):
            report = multi_h_preflight(replace(self.state.context, orientation=duplicate.FLIP_X), 0)
        self.assertFalse(report['valid'])
        self.assertTrue(report['orientation_gate']['equal'])
        self.assertFalse(report['orientation_gate']['identical'])
        self.assertEqual(report['orientation_gate']['actual']['module'], 'alternate.stage_registration')
        self.assertIn('stage_registration', report['provenance']['duplicate_logical_modules'])

    def test_frame_and_marker_gate_same_as_acquisition(self):
        self.assertFalse(multi_h_preflight(self.state.context, 0, frame_id='wrong')['valid'])
        self.assertFalse(multi_h_preflight(replace(self.state.context, marker_id=''), 0)['valid'])
        self.assertFalse(multi_h_preflight(replace(self.state.context, orientation='flip_x'), 0)['valid'])

    def test_reports_actual_gate_enum_if_gate_module_identity_is_wrong(self):
        duplicate = Enum('Orientation', {'FLIP_X':'flip_x'}, type=str, module='alternate.gate')
        with patch('ui.localization_pipeline.Orientation', duplicate):
            report = multi_h_preflight(self.state.context, 0)
        self.assertFalse(report['valid'])
        self.assertEqual(report['orientation_gate']['expected']['class_id'], id(duplicate))
        self.assertTrue(report['orientation_gate']['equal'])
        self.assertFalse(report['orientation_gate']['identical'])

    def test_sys_path_alternative_and_loaded_code_hash(self):
        root = Path(self.tmp.name)
        (root/'ui').mkdir()
        (root/'ui/localization_pipeline.py').write_text('# alternate copy', encoding='utf-8')
        with patch.object(sys, 'path', [str(root), *sys.path]):
            report = runtime_provenance()
        self.assertEqual(report['sys_path'][0]['candidate_sources'], [str((root/'ui/localization_pipeline.py').resolve())])
        self.assertEqual(report['alternate_repo_candidates'][0]['index'], 0)
        for code in report['code'].values():
            self.assertEqual(len(code['runtime_code_sha256']), 64)
        self.assertEqual(len(report['modules']['experiment.stage_registration']['source_file_sha256']),64)

    def test_supervised_breadcrumbs_complete_order_and_retained_journals(self):
        self.runner.start(self.spec,self.confirm,self.tmp.name)
        self.pump(lambda:not self.runner.busy)
        report = self.window.auto_relocation.run_display['multi_h_result']
        events = report['breadcrumbs']
        required = ['runner_start','handoff_begin','settings_created','ownership_acquired',
                    'services_prepare_enter','localization_prepare_enter','localization_prepare_exit',
                    'services_work_enter','initial_H_enter','initial_H_complete','initial_V_enter',
                    'initial_V_complete','planner_enter','profile_1_enter','classifier_enter',
                    'return_enter','cleanup_enter']
        names = [e['phase'] for e in events]
        positions = [names.index(name) for name in required]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual([e['sequence'] for e in events], list(range(1,len(events)+1)))
        self.assertTrue(all(e['run_id']==self.runner.services.handle.run_id for e in events))
        self.assertGreater(len({e['thread_id'] for e in events}),1)
        self.assertTrue((self.runner.services.path/'initial_H.jsonl').exists())
        self.assertTrue((self.runner.services.path/'multi_h_result.json').exists())

    def test_failed_scan_retains_run_and_partial_evidence(self):
        with patch('ui.localization_pipeline.analyze_scan', side_effect=ValueError('injected_analysis_failure')):
            self.runner.start(self.spec,self.confirm,self.tmp.name)
            self.pump(lambda:not self.runner.busy)
        report = self.window.auto_relocation.run_display['multi_h_result']
        self.assertEqual(report['final_state'],'FAILED')
        self.assertTrue((self.runner.services.path/'initial_H.jsonl').exists())
        self.assertTrue((self.runner.services.path/'multi_h_result.json').exists())
        self.assertNotIn('initial_V_enter',[e['phase'] for e in report['breadcrumbs']])
        self.assertFalse(report['registration_published'])
