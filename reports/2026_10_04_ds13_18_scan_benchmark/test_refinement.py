import math
import unittest

from refinement import ALIAS_HZ, circular, refine, winners


class RefinementTests(unittest.TestCase):
    def test_same_alias_seeds_recenter(self):
        def score(f, e):
            return dict(tracking_cfo_hz=123., margin=1-abs(e-.25), exact=2., control=1.)
        result = refine(score, 100., 0.)
        self.assertEqual(result['status'], 'refined')
        self.assertEqual(result['calls'], 13)
        self.assertEqual(result['epoch'], .25)
        self.assertEqual(result['tracking_cfo_hz'], 123.)

    def test_distant_peak_is_not_forced(self):
        result = refine(lambda f, e: dict(tracking_cfo_hz=f+2000, margin=1., exact=2., control=1.), 0., 0.)
        self.assertEqual(result['status'], 'no_local_maximum')
        self.assertEqual(result['calls'], 3)

    def test_nonfinite_score_is_not_selected(self):
        result = refine(lambda f, e: dict(tracking_cfo_hz=f, margin=math.nan, exact=2., control=1.), 0., 0.)
        self.assertEqual(result['status'], 'no_local_maximum')

    def test_alias_distance(self):
        self.assertAlmostEqual(circular(3*ALIAS_HZ+27), 27.)

    def test_winners_use_refined_margin_with_failure_fallback(self):
        rows = [dict(row_index=0, probe_key=[1, 0, 0], original_margin=.9,
                     refinement=dict(status='refined', margin=.1)),
                dict(row_index=1, probe_key=[1, 0, 0], original_margin=.2,
                     refinement=dict(status='no_local_maximum')),
                dict(row_index=2, probe_key=[1, 1, 0], original_margin=.1,
                     refinement=dict(status='refined', margin=.2))]
        self.assertEqual(winners(rows), [1, 2])


if __name__ == '__main__':
    unittest.main()
