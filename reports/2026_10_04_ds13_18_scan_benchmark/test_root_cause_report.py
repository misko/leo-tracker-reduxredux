import unittest
from render_root_cause import pooled_rx_stats,table


class RootCauseReportTests(unittest.TestCase):
    def test_receiver_rms_pool_uses_window_weighted_energy(self):
        linear,quad,ratio=pooled_rx_stats(dict(per_rx=[
            dict(windows=3,linear_rms_hz=4.,quadratic_rms_hz=2.),
            dict(windows=1,linear_rms_hz=8.,quadratic_rms_hz=4.)]))
        self.assertAlmostEqual(linear**2,28.)
        self.assertAlmostEqual(quad**2,7.)
        self.assertAlmostEqual(ratio,2.)

    def test_empty_and_escaped_display(self):
        self.assertEqual(pooled_rx_stats(dict(per_rx=[])),(None,None,None))
        self.assertIn('&lt;bad&gt;',table([dict(x='<bad>')],[('x','Name')]))
