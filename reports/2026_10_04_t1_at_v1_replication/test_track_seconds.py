import unittest

import numpy as np

from plot_track_seconds_vs_position import track_spans


class TrackSpanTests(unittest.TestCase):
    def test_gap_duplicate_time_and_receivers(self):
        rows = track_spans(np.array([0., 0., 10., 1., 4., 9.]),
                           np.array([11, 11, 11, 11, 11, 22]),
                           np.array([0, 0, 0, 1, 1, 0]))
        self.assertEqual([r['span_s'] for r in rows], [10., 3., 0.])
        self.assertEqual(sum(r['windows'] for r in rows), 6)
        self.assertEqual(sum(r['span_s'] for r in rows), 13.)

    def test_order_does_not_change_spans(self):
        rows = track_spans(np.array([10., 0., 5.]), np.array([11, 11, 11]),
                           np.array([0, 0, 0]))
        self.assertEqual(rows[0]['span_s'], 10.)


if __name__ == '__main__':
    unittest.main()
