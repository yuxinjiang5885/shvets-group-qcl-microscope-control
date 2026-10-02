"""Deterministic confirmation clocks and inert PI; no native imports or motion."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from ui.snake_autofocus_service import SnakeAutofocusService, SnakeAutofocusSettings, AutofocusFailure
from ui.snake_workflow import WorkerPI


class Clock:
    def __init__(self): self.now=0.
    def monotonic(self): return self.now
    def sleep(self,seconds): self.now+=seconds


class PI:
    def __init__(self, offsets, clock):
        self.offsets=iter(offsets);self.offset=1.;self.clock=clock
        self.timeout=1000;self.moves=[];self.timeouts=[];self.target=0.
        self.on_target=True;self.read_error=False;self.read_delay=0.
    def MOV(self,axis,target): self.moves.append(target);self.target=target
    def qONT(self,axis): return {1:self.on_target}
    def qPOS(self,axis):
        self.timeouts.append(self.timeout)
        if self.read_error: raise RuntimeError('inert read error')
        self.clock.sleep(self.read_delay)
        self.offset=next(self.offsets,self.offset)
        return {1:self.target+self.offset}


class ConfirmationTests(unittest.TestCase):
    def run_move(self, offsets, *, phase='final_best', configure=lambda pi:None, failure=False):
        clock=Clock();pi=PI(offsets,clock);configure(pi)
        settings=SnakeAutofocusSettings(0,0,-1,1,1)
        parent=SimpleNamespace(check=lambda:None,settings=settings)
        service=SnakeAutofocusService(settings,None,WorkerPI(pi,parent),None,lambda:None,lambda:True)
        with patch('ui.snake_autofocus_service.monotonic',clock.monotonic),patch('ui.snake_autofocus_service.sleep',clock.sleep):
            if failure:
                with self.assertRaises(AutofocusFailure) as caught:service.pi_move(52.973608,phase=phase)
                result=caught.exception
            else:
                service.pi_move(52.973608,phase=phase)
                result=service.pi_diagnostics
        self.assertEqual(pi.moves,[52.973608])
        self.assertEqual(pi.timeout,1000)
        self.assertTrue(all(1 <= value <= 400 for value in pi.timeouts))
        return result,pi,clock

    def test_immediate_stable_confirmation(self):
        d,pi,clock=self.run_move([0.,0.])
        self.assertEqual(d['position_read_count'],2)
        self.assertEqual(d['consecutive_in_tolerance_observed'],2)
        self.assertEqual(d['tolerance_um'],.1)
        self.assertAlmostEqual(d['confirmation_elapsed_s'],.01)

    def test_observed_mismatch_then_settles(self):
        d,pi,_=self.run_move([.111828,.09,.08])
        self.assertEqual(d['position_read_count'],3)
        self.assertAlmostEqual(d['final_delta_um'],.08)
        self.assertEqual(d['phase'],'final_best')
        self.assertGreater(pi.timeouts[0],pi.timeouts[-1])

    def test_two_consecutive_required_after_transient_crossing(self):
        d,_,_=self.run_move([.11,.05,.12,.04,.03])
        self.assertEqual(d['position_read_count'],5)
        self.assertEqual(d['consecutive_in_tolerance_observed'],2)

    def test_transient_sample_does_not_pass(self):
        error,_,_=self.run_move([.05,.112],failure=True)
        self.assertEqual(error.outcome,'PI_READBACK_FAILURE')
        self.assertEqual(error.diagnostics['consecutive_in_tolerance_observed'],0)

    def test_persistent_mismatch_deadline_and_diagnostics(self):
        error,pi,clock=self.run_move([.112],failure=True)
        d=error.diagnostics
        self.assertEqual(error.outcome,'PI_READBACK_FAILURE')
        self.assertAlmostEqual(d['minimum_delta_seen_um'],.112)
        self.assertAlmostEqual(d['final_delta_um'],.112)
        self.assertAlmostEqual(d['confirmation_window_s'],.4)
        self.assertLessEqual(clock.now,.4)
        self.assertGreater(d['position_read_count'],2)
        self.assertTrue(d['wait_result'])

    def test_sweep_phase(self):
        d,_,_=self.run_move([.02,.02],phase='sweep_point')
        self.assertEqual(d['phase'],'sweep_point')
        error,_,_=self.run_move([.2],phase='sweep_point',failure=True)
        self.assertEqual(error.diagnostics['phase'],'sweep_point')

    def test_on_target_timeout_still_fails(self):
        error,pi,_=self.run_move([],configure=lambda pi:setattr(pi,'on_target',False),failure=True)
        self.assertEqual(error.outcome,'PI_WAIT_FAILURE')
        self.assertEqual(pi.timeouts,[])

    def test_qpos_exception_preserves_structured_failure(self):
        error,_,_=self.run_move([],configure=lambda pi:setattr(pi,'read_error',True),failure=True)
        self.assertEqual(error.outcome,'PI_READBACK_FAILURE')
        self.assertEqual(error.diagnostics['position_read_count'],1)
        self.assertEqual(error.diagnostics['phase'],'final_best')

    def test_late_native_result_cannot_be_accepted(self):
        error,_,_=self.run_move([0.,0.],configure=lambda pi:setattr(pi,'read_delay',.3),failure=True)
        self.assertEqual(error.outcome,'PI_READBACK_FAILURE')
        self.assertLessEqual(error.diagnostics['position_read_count'],2)
