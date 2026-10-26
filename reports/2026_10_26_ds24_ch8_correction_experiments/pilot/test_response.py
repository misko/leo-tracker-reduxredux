import unittest
import numpy as np
from frequency_selective_pilot import ChannelPilotWorkspace
from local_pilot_refinement import PilotWorkspace
from nominate import choose
from response import compare, synthetic, symbol_rate_diagnostic


class ResponseTests(unittest.TestCase):
    def test_nomination_is_midpoint_then_visit_and_does_not_replace_missing(self):
        probes = [dict(receiver_id=0, channel=8, visit_index=k, valid_start_counter=t,
                       candidates=[dict(candidate_rank=2, fractional_margin=m, passed_fractional_margin_gate=m>=.025)])
                  for k,t,m in [(4,9,.02), (3,11,.02), (2,10,.04), (1,10,.005)]]
        self.assertEqual(choose(probes,0,8,'failed_near_gate',10)[0]['visit_index'],3)
        self.assertEqual(choose(probes,0,8,'passed',10)[0]['visit_index'],2)
        self.assertIsNone(choose(probes,1,8,'passed',10))

    def test_flat_score_matches_existing_baseline(self):
        args = synthetic(11, size=20000)
        y, rate, edge, epoch, cfo = args
        p = ChannelPilotWorkspace(y, rate, edge, epoch)
        old = PilotWorkspace(y, rate, edge, epoch)
        np.testing.assert_allclose(p.evaluate([cfo], flat=True), old.evaluate([cfo]),rtol=1e-6,atol=1e-10)

    def test_independent_channel_and_noise_predicts_other_symbols(self):
        result = compare(*synthetic(31))
        self.assertGreater(result['held_symbol_relative_SSE_improvement'],.1)
        self.assertTrue(result['response_predictive_support'])
        self.assertGreater(result['correct_over_wrong_descriptive_frame_bootstrap_95_interval'][0],.1)

    def test_wrong_sequence_and_noise_do_not_pass_predictive_support(self):
        for mode in ('wrong_sequence','noise'):
            result = compare(*synthetic(44,mode))
            self.assertFalse(result['response_predictive_support'])

    def test_guarded_clock_parity_predicts_known_flat_clock(self):
        result = symbol_rate_diagnostic(*synthetic(53,'channel',noise_sigma=.1,size=20000))
        self.assertEqual(len(result['models']['per_tone_received_rate']['fits']),2)
        self.assertTrue(np.isfinite(result['held_symbol_relative_SSE_improvement']))


if __name__ == '__main__':
    unittest.main()
