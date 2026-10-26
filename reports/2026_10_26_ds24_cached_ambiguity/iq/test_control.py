import unittest
import numpy as np
import control as c


class ControlTests(unittest.TestCase):
    def test_integral_epoch_frame_matches_deployed_pilot_law(self):
        from leo.analysis.starlink.templates import qin_edge_pilot_frame
        expected = qin_edge_pilot_frame(c.RATE, 'upper')
        actual = c.pilot(np.arange(len(expected)), 0.)
        self.assertLess(float(np.max(np.abs(actual-expected))), 5e-7)

    def test_fractional_time_translation_and_supported_symbols(self):
        x = np.arange(1000, dtype=float)
        np.testing.assert_array_equal(c.pilot(x, 127.25), c.pilot(x+1, 128.25))
        np.testing.assert_array_equal(c.pilot(np.arange(88), 0), np.zeros(88))

    def test_iq_noise_is_paired_across_scenarios_and_no_clipping(self):
        a, ma = c.synthesize([], c.SEEDS[0])
        b, mb = c.synthesize([], c.SEEDS[0])
        np.testing.assert_array_equal(a, b)
        self.assertEqual(ma['iq_sha256'], mb['iq_sha256'])
        self.assertEqual(a.shape, (200000, 2, 2))
        self.assertEqual(ma['clipping_samples'], 0)
        self.assertGreater(float(np.sum(a[:, 0] != a[:, 1])), 0)

    def test_report_keeps_actual_margin_winner_and_fractional_gate(self):
        base = dict(fractional_epoch_status='complete', epoch_sample=127,
                    fractional_epoch_offset_samples=.25)
        rows = [dict(base, candidate_rank=0, fractional_margin=.04,
                     fractional_tracking_cfo_hz=110000.),
                dict(base, candidate_rank=1, fractional_margin=.03,
                     fractional_tracking_cfo_hz=100000.),
                dict(base, candidate_rank=2, fractional_margin=.024,
                     fractional_tracking_cfo_hz=100000.)]
        out = c.summarize(rows, [c.source()])
        self.assertEqual(out['accepted_count'], 2)
        self.assertEqual(out['highest_margin_accepted']['candidate_rank'], 0)
        self.assertEqual(len(out['sources'][0]['epoch_near_candidates']), 3)


if __name__ == '__main__':
    unittest.main()
