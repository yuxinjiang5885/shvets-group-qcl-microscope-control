"""Hardware-free Module 6 acquisition, journal, and offline-analysis tests.

Author: Yuxin Jiang
Email: yj546@cornell.edu

Uses only fake interfaces, a virtual clock, synthetic data, and temporary files.
"""

from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from experiment.scan_1d import ScanSettings, StageBounds, ScanStatus, load_scan, scan_1d
from experiment.reflection_analysis import EdgeSettings, analyze_edges, analyze_scan
from experiment.reflection_synthetic import synthetic_profile


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def time(self):
        return 1700000000.0 + self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeStage:
    def __init__(self, clock):
        self.clock = clock
        self.position = (0.0, 0.0)
        self.moves = []
        self.stops = 0
        self.ready_at = 0
        self.stuck = False
        self.readback = True
        self.offset = 0
        self.move_time = 0.02

    def move_to(self, x, y, *, timeout_s):
        self.moves.append((x, y))
        self.position = (x + self.offset, y)
        self.ready_at = self.clock.now + self.move_time

    def is_busy(self, *, timeout_s):
        return bool(self.moves and self.stuck) or self.clock.now < self.ready_at

    def get_position(self, *, timeout_s):
        return self.position if self.readback else None

    def stop(self, *, timeout_s):
        self.stops += 1
        self.stuck = False
        self.ready_at = self.clock.now


class FakeReader:
    def __init__(self, stage):
        self.stage = stage
        self.calls = []
        self.fail_after = None
        self.value = None

    def read(self, *, timeout_s):
        if self.fail_after is not None and len(self.calls) >= self.fail_after:
            raise IOError("Synthetic detector failure")
        self.calls.append(self.stage.clock.now)
        if self.value is not None:
            return self.value
        return synthetic_profile([self.stage.position[0]], edges_um=(30, 70))[0]


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "scan.jsonl"
        self.clock = FakeClock()
        self.stage = FakeStage(self.clock)
        self.reader = FakeReader(self.stage)
        self.settings = ScanSettings("x", 0, 4, 1, 0,
                                     StageBounds(-10, 110, -10, 110, "test-controller-session"),
                                     settling_s=0.03, movement_timeout_s=0.2,
                                     settling_timeout_s=0.2)

    def run_scan(self, **kwargs):
        return scan_1d(self.settings, self.stage, self.reader,
                       output_path=self.path, clock=self.clock, **kwargs)

    def test_both_axes_both_directions_and_roundtrip(self):
        for axis in ("x", "y"):
            for start, end in ((0, 4), (4, 0)):
                with self.subTest(axis=axis, start=start):
                    self.path = Path(self.temp.name) / f"{axis}-{start}.jsonl"
                    self.settings = replace(self.settings, axis=axis, start_um=start, end_um=end, fixed_um=2)
                    self.stage = FakeStage(self.clock)
                    self.reader = FakeReader(self.stage)
                    result = self.run_scan()
                    self.assertEqual(result.status, ScanStatus.COMPLETED, result.reasons)
                    expected = [(v, 2) if axis == "x" else (2, v)
                                for v in (range(5) if start == 0 else range(4, -1, -1))]
                    self.assertEqual(self.stage.moves, expected)
                    self.assertEqual([p.measured_um for p in result.points], expected)
                    restored = load_scan(self.path)
                    self.assertEqual(restored.points, result.points)
                    self.assertEqual(restored.settings, self.settings)
                    self.assertEqual(restored.status, ScanStatus.COMPLETED)
                    self.assertEqual(self.stage.stops, 0)

    def test_waits_for_movement_and_settling(self):
        result = self.run_scan()
        self.assertEqual(result.status, ScanStatus.COMPLETED)
        self.assertGreaterEqual(self.reader.calls[0], 0.05)
        self.assertTrue(all(b - a >= 0.049 for a, b in zip(self.reader.calls, self.reader.calls[1:])))

    def test_exact_endpoint_and_nonzero_coordinate_frame(self):
        self.stage.position = (100, 100)
        self.settings = replace(self.settings, start_um=100, end_um=102.5, step_um=1, fixed_um=100)
        result = self.run_scan()
        self.assertEqual(result.status, ScanStatus.COMPLETED)
        self.assertEqual([p.commanded_um[0] for p in result.points], [100, 101, 102, 102.5])
        self.assertEqual(result.initial_position_um, (100, 100))

    def test_entire_path_rejected_before_any_stage_call(self):
        self.settings = replace(self.settings, end_um=111)
        with patch.object(self.stage, "get_position", side_effect=AssertionError("Must not call stage")):
            result = self.run_scan()
        self.assertEqual(result.status, ScanStatus.FAILED)
        self.assertFalse(self.stage.moves)
        self.assertFalse(self.path.exists())

    def test_fixed_axis_and_initial_approach_bounds(self):
        self.settings = replace(self.settings, fixed_um=111)
        self.assertEqual(self.run_scan().status, ScanStatus.FAILED)
        self.assertFalse(self.stage.moves)
        self.settings = replace(self.settings, fixed_um=0)
        self.stage.position = (-11, 0)
        result = self.run_scan()
        self.assertEqual(result.status, ScanStatus.FAILED)
        self.assertFalse(self.stage.moves)
        self.assertIn("Initial position", result.reasons[0])

    def test_movement_timeout(self):
        self.stage.stuck = True
        result = self.run_scan()
        self.assertEqual(result.status, ScanStatus.FAILED)
        self.assertIn("Timeout", result.reasons[0])
        self.assertLessEqual(self.clock.now, 0.21)
        self.assertEqual(self.stage.stops, 1)
        self.assertFalse(self.reader.calls)

    def test_settling_timeout(self):
        calls = [False, False] + [True] * 100
        with patch.object(self.stage, "is_busy", side_effect=calls):
            result = self.run_scan()
        self.assertEqual(result.status, ScanStatus.FAILED)
        self.assertEqual(self.stage.stops, 1)
        self.assertFalse(self.reader.calls)

    def test_cancellation_before_movement(self):
        result = self.run_scan(cancelled=lambda: True)
        self.assertEqual(result.status, ScanStatus.CANCELLED)
        self.assertFalse(self.stage.moves)
        self.assertEqual(self.stage.stops, 0)

    def test_cancellation_during_motion(self):
        self.stage.stuck = True
        result = self.run_scan(cancelled=lambda: self.clock.now >= 0.03)
        self.assertEqual(result.status, ScanStatus.CANCELLED)
        self.assertEqual(self.stage.stops, 1)
        self.assertFalse(self.reader.calls)

    def test_cancellation_preserves_partial_data(self):
        result = self.run_scan(cancelled=lambda: len(self.reader.calls) >= 2)
        self.assertEqual(result.status, ScanStatus.CANCELLED)
        self.assertEqual(len(result.points), 2)
        self.assertEqual(load_scan(self.path).points, result.points)
        self.assertEqual(load_scan(self.path).status, ScanStatus.CANCELLED)
        self.assertEqual(self.stage.stops, 1)

    def test_reader_failure_preserves_partial_data(self):
        self.reader.fail_after = 2
        result = self.run_scan()
        self.assertEqual(result.status, ScanStatus.FAILED)
        self.assertEqual(len(result.points), 2)
        self.assertEqual(load_scan(self.path).points, result.points)
        self.assertEqual(self.stage.stops, 1)

    def test_reader_timeout_preserves_late_sample(self):
        def late_read(*, timeout_s):
            self.clock.sleep(timeout_s + 0.01)
            return 2.5

        with patch.object(self.reader, "read", side_effect=late_read):
            result = self.run_scan()
        self.assertEqual(result.status, ScanStatus.FAILED)
        self.assertIn("TimeoutError", result.reasons[0])
        self.assertEqual(result.points[0].signal, 2.5)
        self.assertEqual(load_scan(self.path).points, result.points)
        self.assertEqual(self.stage.stops, 1)

    def test_movement_adapter_deadline_violation(self):
        def late_move(x, y, *, timeout_s):
            self.clock.sleep(timeout_s + 0.01)

        with patch.object(self.stage, "move_to", side_effect=late_move):
            result = self.run_scan()
        self.assertEqual(result.status, ScanStatus.FAILED)
        self.assertFalse(self.reader.calls)
        self.assertEqual(self.stage.stops, 1)

    def test_cancel_during_settling(self):
        result = self.run_scan(cancelled=lambda: self.clock.now >= 0.04)
        self.assertEqual(result.status, ScanStatus.CANCELLED)
        self.assertFalse(self.reader.calls)
        self.assertEqual(self.stage.stops, 1)

    def test_keyboard_interrupt_stops_and_finalizes_partial_data(self):
        original = self.reader.read

        def interrupted_read(*, timeout_s):
            if self.reader.calls:
                raise KeyboardInterrupt()
            return original(timeout_s=timeout_s)

        with patch.object(self.reader, "read", side_effect=interrupted_read):
            result = self.run_scan()
        self.assertEqual(result.status, ScanStatus.CANCELLED)
        self.assertEqual(len(result.points), 1)
        self.assertEqual(load_scan(self.path).status, ScanStatus.CANCELLED)
        self.assertEqual(self.stage.stops, 1)

    def test_readback_unavailable_requires_explicit_start(self):
        self.stage.readback = False
        result = self.run_scan()
        self.assertFalse(self.stage.moves)
        self.assertEqual(result.status, ScanStatus.FAILED)
        self.path = Path(self.temp.name) / "explicit.jsonl"
        result = self.run_scan(initial_position_um=(0, 0))
        self.assertEqual(result.status, ScanStatus.COMPLETED)
        self.assertEqual(result.initial_position_source, "caller")
        self.assertTrue(all(p.measured_um is None for p in result.points))
        self.assertEqual(analyze_scan(result).reasons, ("missing_position_readback",))

    def test_bad_readback_rejects_acquisition(self):
        self.stage.offset = 3
        result = self.run_scan()
        self.assertEqual(result.status, ScanStatus.FAILED)
        self.assertFalse(self.reader.calls)
        self.assertEqual(self.stage.stops, 1)

    def test_nonfinite_signal_preserved_in_strict_json(self):
        self.reader.value = float("nan")
        result = self.run_scan()
        self.assertEqual(result.status, ScanStatus.FAILED)
        self.assertEqual(len(result.points), 1)
        records = [json.loads(line) for line in self.path.read_text().splitlines()]
        self.assertEqual(records[2]["signal"], "nan")
        self.assertEqual(len(load_scan(self.path).points), 1)

    def test_output_collision_prevents_movement(self):
        self.path.write_text("existing data", encoding="utf-8")
        result = self.run_scan()
        self.assertEqual(result.status, ScanStatus.FAILED)
        self.assertFalse(self.stage.moves)
        self.assertEqual(self.path.read_text(), "existing data")

    def test_storage_failure_retains_memory_and_stops(self):
        import experiment.scan_1d as module
        original = module._write_record

        def fail_point(stream, record):
            if record["type"] == "point":
                raise OSError("Synthetic disk full")
            original(stream, record)

        with patch.object(module, "_write_record", side_effect=fail_point):
            result = self.run_scan()
        self.assertEqual(result.status, ScanStatus.FAILED)
        self.assertEqual(len(result.points), 1)
        self.assertEqual(self.stage.stops, 1)
        self.assertEqual(load_scan(self.path).status, ScanStatus.FAILED)

    def test_interrupted_journal_recovers_intact_points(self):
        result = self.run_scan()
        lines = self.path.read_text().splitlines()
        self.path.write_text("\n".join(lines[:-1]) + '\n{"type": "poi', encoding="utf-8")
        recovered = load_scan(self.path)
        self.assertEqual(recovered.status, ScanStatus.FAILED)
        self.assertEqual(recovered.points, result.points)
        self.assertEqual(analyze_scan(recovered).reasons, ("incomplete_scan",))

    def test_false_completion_with_missing_points_is_rejected(self):
        self.run_scan()
        records = [json.loads(line) for line in self.path.read_text().splitlines()]
        records.pop(-2)
        records[-1]["point_count"] -= 1
        self.path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
        self.assertEqual(load_scan(self.path).status, ScanStatus.FAILED)

    def test_stop_failure_is_reported(self):
        self.reader.fail_after = 1
        with patch.object(self.stage, "stop", side_effect=IOError("stop refused")):
            result = self.run_scan()
        self.assertEqual(result.status, ScanStatus.FAILED)
        self.assertTrue(any("Stop failed" in reason for reason in result.reasons))
        self.assertEqual(len(result.points), 1)

    def test_adapter_string_busy_is_rejected(self):
        with patch.object(self.stage, "is_busy", return_value="0"):
            result = self.run_scan()
        self.assertEqual(result.status, ScanStatus.FAILED)
        self.assertFalse(self.stage.moves)

    def test_invalid_settings(self):
        for field, value in (("step_um", 0), ("step_um", float("nan")), ("axis", "z"),
                             ("movement_timeout_s", 0), ("poll_interval_s", -1),
                             ("settling_s", 2), ("position_tolerance_um", -1)):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    replace(self.settings, **{field: value}).positions()
        with self.assertRaises(ValueError):
            StageBounds(0, 1, 0, 1, "")

    def test_end_to_end_offline_analysis(self):
        self.settings = replace(self.settings, end_um=100)
        result = self.run_scan()
        edges = analyze_scan(load_scan(self.path))
        self.assertEqual(result.status, ScanStatus.COMPLETED)
        self.assertTrue(edges.valid, edges.reasons)
        self.assertEqual(edges.midpoint_um, 50)
        self.assertEqual(edges.position_source, "measured")

    def test_explicit_commanded_position_analysis(self):
        self.settings = replace(self.settings, end_um=100)
        self.stage.readback = False
        result = self.run_scan(initial_position_um=(0, 0))
        edges = analyze_scan(result, use_commanded_positions=True)
        self.assertTrue(edges.valid, edges.reasons)
        self.assertEqual(edges.position_source, "commanded")


# Frozen measured profiles; tests do not read hardware journals.
GOLD_PROFILE = [2.095023520997042, 2.0768108862129577, 2.074952242248048, 2.077556624729425, 2.0929698115570465, 2.0952970671003714, 5.182347964428967, 5.0759127728445295, 5.130068410741073, 5.10995126558957, 5.101516134859336, 5.092383245163629, 5.09506229721194, 5.104427269281647, 5.099134405997925, 5.102492272662829, 5.113932577508336, 5.115486751692975, 5.108949699061662, 5.101380790375972, 5.100848666376492, 5.100677174569953, 5.099206714058026, 5.100342018423941, 5.110641568692066, 5.105952639453621, 5.119645440808083, 5.119130304875052, 5.119915867872967, 5.091645515796996, 5.105600717779781, 1.8881096193035973, 2.0863643831865337, 2.034760663898228, 2.0456355817612772, 2.0438411382496686, 2.0341765376089915, 2.02533310152159, 1.897317071099668, 3.5777955687129195]
EXTENSION_PROFILE = [4.985478523830382, 4.997222475148376, 1.9275887160886123, 2.008762588368771, 1.9500282872674102, 1.9711681067077036, 1.9671538301489113, 1.9516633510651307, 1.9400298779553706, 1.8288119918644936, 3.46390617524636, 4.954145107544642, 4.906968136277324, 5.0197144528394055, 4.576558935144113, 1.9158724526767335, 1.686407648521747, 1.6928719345917465, 1.7578030810298417]

class EdgeTests(unittest.TestCase):
    def setUp(self):
        self.x = list(range(101))
        self.y = synthetic_profile(self.x)

    def assertFailure(self, result, reason):
        self.assertFalse(result.valid)
        self.assertIn(reason, result.reasons)
        self.assertIsNone(result.midpoint_um)

    def test_bright_dark_forward_reverse_and_noisy_profiles(self):
        for amplitude in (1, -1):
            for reverse in (False, True):
                with self.subTest(amplitude=amplitude, reverse=reverse):
                    y = synthetic_profile(self.x, amplitude=amplitude, noise_std=0.01,
                                          transition_um=0.5, seed=42)
                    x = self.x
                    if reverse:
                        x, y = x[::-1], y[::-1]
                    result = analyze_edges(x, y)
                    self.assertTrue(result.valid, result.reasons)
                    self.assertAlmostEqual(result.midpoint_um, 50, delta=0.1)
                    self.assertAlmostEqual(result.width_um, 40, delta=0.1)
                    self.assertAlmostEqual(result.contrast, 1, delta=0.03)
                    self.assertEqual(result.polarity, "bright" if amplitude == 1 else "dark")

    def test_width_validation(self):
        self.assertTrue(analyze_edges(self.x, self.y, EdgeSettings(expected_width_um=41, width_tolerance_um=0)).valid)
        self.assertFailure(analyze_edges(self.x, self.y, EdgeSettings(expected_width_um=10)), "width_mismatch")

    def test_flat(self):
        self.assertFailure(analyze_edges(self.x, [1] * 101), "flat_or_low_contrast")

    def test_noise(self):
        noisy = synthetic_profile(self.x, noise_std=2, seed=3)
        self.assertFailure(analyze_edges(self.x, noisy), "noisy_signal")

    def test_incomplete_and_single_edge(self):
        self.assertFailure(analyze_edges(self.x, self.y, complete=False), "incomplete_scan")
        self.assertFailure(analyze_edges(self.x[:60], self.y[:60]), "incomplete_feature")

    def test_nonfinite(self):
        for invalid in (float("nan"), float("inf"), float("-inf")):
            y = self.y.copy()
            y[40] = invalid
            self.assertFailure(analyze_edges(self.x, y), "nonfinite_data")

    def test_saturation_requires_explicit_rails(self):
        self.assertFailure(analyze_edges(self.x, self.y, EdgeSettings(saturation_high=2)), "saturated_signal")
        self.assertFailure(analyze_edges(self.x, self.y, EdgeSettings(saturation_low=1)), "saturated_signal")

    def test_ambiguous_pair_is_not_resolved_by_expected_width(self):
        y = [1 + int(10 <= x <= 30 or 60 <= x <= 80) for x in self.x]
        self.assertFailure(analyze_edges(self.x, y, EdgeSettings(expected_width_um=21)), "ambiguous_edges")

    def test_inadequate_edge_support(self):
        y = synthetic_profile(self.x, edges_um=(1, 70))
        self.assertFailure(analyze_edges(self.x, y), "insufficient_edge_support")

    def test_invalid_positions_and_lengths(self):
        self.assertFailure(analyze_edges(self.x[:-1], self.y), "length_mismatch")
        self.assertFailure(analyze_edges([0] * 101, self.y), "nonmonotonic_positions")
        self.assertFailure(analyze_edges([0, 1], [0, 1]), "insufficient_samples")

    def test_drifting_background(self):
        y = [v + (0.4 if x > 70 else 0) for x, v in zip(self.x, self.y)]
        self.assertFailure(analyze_edges(self.x, y), "inconsistent_background")

    def test_qc_settings_validation(self):
        for kwargs in ({"min_contrast": -1}, {"expected_width_um": 0},
                       {"width_tolerance_um": 1}, {"min_region_points": 2},
                       {"saturation_low": 2, "saturation_high": 1}):
            with self.assertRaises(ValueError):
                EdgeSettings(**kwargs)

    def test_width_guided_features_bright_dark_and_reverse(self):
        x = list(range(161))
        y = [1 + int(10 <= v < 20 or 50 <= v < 100 or 130 <= v < 140) for v in x]
        settings = EdgeSettings(expected_width_um=50, width_tolerance_um=1)
        for sign in (1, -1):
            for reverse in (False, True):
                xx, yy = x[:], [sign * v for v in y]
                if reverse:
                    xx.reverse()
                    yy.reverse()
                result = analyze_edges(xx, yy, settings)
                self.assertTrue(result.valid, result)
                self.assertEqual(result.midpoint_um, 74.5)
                self.assertEqual(result.polarity, 'bright' if sign == 1 else 'dark')
                self.assertEqual(result.support_counts, (30, 50, 30))
                self.assertEqual(sum(c.valid for c in result.candidates), 1)
        self.assertFailure(analyze_edges(x, y), 'ambiguous_edges')
        self.assertFailure(analyze_edges(x, y, EdgeSettings(expected_width_um=80)),
                           'no_valid_candidate')

    def test_no_ranking_or_nonconsecutive_pairs(self):
        x = list(range(121))
        y = [1 + (1 if 10 <= v < 30 else 0) + (1.2 if 70 <= v < 90 else 0) for v in x]
        result = analyze_edges(x, y, EdgeSettings(expected_width_um=20, width_tolerance_um=2))
        self.assertFailure(result, 'ambiguous_edges')
        self.assertEqual(sum(c.valid for c in result.candidates), 2)
        result = analyze_edges(x, y, EdgeSettings(expected_width_um=80, width_tolerance_um=2))
        self.assertFailure(result, 'no_valid_candidate')
        self.assertEqual(len(result.candidates), 3)
        self.assertTrue(all(c.width_um < 80 - 2 for c in result.candidates))

    def test_candidate_local_noise_and_background(self):
        x = list(range(201))
        y = [1 + int(20 <= v < 60 or v >= 100) for v in x]
        # A noisy distant run must not contaminate the first candidate's QC.
        for i in range(100, 201):
            y[i] = 1.6 if i % 2 else 3.0
        settings = EdgeSettings(expected_width_um=40, width_tolerance_um=2)
        self.assertTrue(analyze_edges(x, y, settings).valid)
        noisy = y[:]
        for i in range(20, 60):
            noisy[i] = 2.1 if i % 2 else 3.0
        result = analyze_edges(x, noisy, settings)
        self.assertFalse(result.valid)
        self.assertIn('noisy_signal', result.candidates[0].reasons)
        drift = [1 + int(20 <= v < 60 or v >= 120) for v in x]
        for i in range(60, 120):
            drift[i] = 1.4
        result = analyze_edges(x, drift, settings)
        self.assertFalse(result.valid)
        self.assertIn('inconsistent_background', result.candidates[0].reasons)

    def test_multi_feature_interior_support_and_low_contrast(self):
        x = list(range(101))
        y = [1 + int(10 <= v < 12 or 50 <= v < 80) for v in x]
        result = analyze_edges(x, y, EdgeSettings(expected_width_um=2, width_tolerance_um=0))
        self.assertFailure(result, 'no_valid_candidate')
        self.assertIn('insufficient_edge_support', result.candidates[0].reasons)
        y = [1 + (0.4 if 10 <= v < 30 else 0) + (0.6 if v >= 70 else 0) for v in x]
        result = analyze_edges(x, y, EdgeSettings(
            expected_width_um=20, width_tolerance_um=2, min_contrast=0.5))
        self.assertFailure(result, 'no_valid_candidate')
        self.assertIn('flat_or_low_contrast', result.candidates[0].reasons)

    def test_threshold_equality_and_width_boundary(self):
        x = list(range(21))
        y = [0.0] * 21
        y[5:15] = [1.0] * 10
        y[5] = y[14] = 0.5
        result = analyze_edges(x, y, EdgeSettings(expected_width_um=10, width_tolerance_um=1))
        self.assertTrue(result.valid, result)
        self.assertEqual((result.left_edge_um, result.right_edge_um), (5, 14))
        self.assertFailure(analyze_edges(x, y, EdgeSettings(
            expected_width_um=10, width_tolerance_um=0.99)), 'width_mismatch')

    def test_measured_gold_and_extension_regressions(self):
        settings = EdgeSettings(expected_width_um=500, width_tolerance_um=100)
        result = analyze_edges(list(range(3850, 4631, 20)), GOLD_PROFILE, settings)
        self.assertTrue(result.valid, result)
        self.assertAlmostEqual(result.left_edge_um, 3959.5972266309154)
        self.assertAlmostEqual(result.right_edge_um, 4459.50397219288)
        self.assertAlmostEqual(result.width_um, 499.90674556196427)
        self.assertAlmostEqual(result.midpoint_um, 4209.550599411898)
        self.assertEqual(result.polarity, 'bright')
        self.assertEqual(result.support_counts, (6, 25, 8))
        self.assertEqual(result.candidates[1].support_counts, (25, 8, 1))
        self.assertIn('insufficient_edge_support', result.candidates[1].reasons)
        self.assertIn('width_mismatch', result.candidates[1].reasons)
        extension = analyze_edges(list(range(4430, 4791, 20)), EXTENSION_PROFILE, settings)
        self.assertFailure(extension, 'no_valid_candidate')
        self.assertEqual(len(extension.candidates), 2)
        self.assertTrue(all('width_mismatch' in c.reasons for c in extension.candidates))
        self.assertEqual(extension.candidates[0].support_counts, (2, 8, 5))
        self.assertEqual(extension.candidates[1].support_counts, (8, 5, 4))

    def test_synthetic_repeatability(self):
        self.assertEqual(synthetic_profile(self.x, noise_std=0.1), synthetic_profile(self.x, noise_std=0.1))


class ImportIsolationTests(unittest.TestCase):
    def test_entire_suite_with_hardware_and_qt_imports_blocked(self):
        # Run the substantive tests under a guard installed BEFORE module import.
        code = '''
import importlib.abc, sys, unittest
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'instruments', 'PyDAQmx', 'PIPython', 'serial',
                                    'PyQt6', 'ui', 'qcl_scanning_imaging_ui', 'qcl_spectral_scan_ui'}:
            raise AssertionError('Forbidden import: ' + fullname)
sys.meta_path.insert(0, Guard())
sys.path.insert(0, 'tests')
import test_reflection_scan as tests
suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(cls)
                           for cls in (tests.AcquisitionTests, tests.EdgeTests))
result = unittest.TextTestRunner(verbosity=0).run(suite)
sys.exit(not result.wasSuccessful())
'''
        result = subprocess.run([sys.executable, "-B", "-c", code],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True,
                                text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
