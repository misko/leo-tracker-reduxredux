import unittest
from plot_comparison import match_passing


def point(rank=0, epoch=0, cfo=0, visit=0, rx=0, passing=True):
    return {"rank": rank, "epoch": epoch, "acquired_cfo": cfo,
            "visit": visit, "rx": rx, "passing": passing}


class MatchTests(unittest.TestCase):
    def test_duplicate_hypotheses_do_not_reuse_endpoints(self):
        self.assertEqual(len(match_passing([point(), point(rank=1)], [point()])), 1)
        self.assertEqual(len(match_passing([point()], [point(), point(rank=1)])), 1)

    def test_circular_boundary_and_limits(self):
        self.assertEqual(len(match_passing([point(epoch=3332)], [point(epoch=0)])), 1)
        self.assertEqual(len(match_passing([point(epoch=2, cfo=10000)], [point()])), 1)
        self.assertEqual(match_passing([point(epoch=3)], [point()]), [])
        self.assertEqual(match_passing([point(cfo=10001)], [point()]), [])

    def test_only_passing_candidates_on_same_window_pair(self):
        for other in (point(visit=1), point(rx=1), point(passing=False)):
            self.assertEqual(match_passing([point()], [other]), [])


if __name__ == "__main__":
    unittest.main()
