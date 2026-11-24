from importlib.util import module_from_spec, spec_from_file_location
import json
from math import log
from pathlib import Path
import unittest


MODULE = Path(__file__).resolve().parents[2]/'reports/ALGO08/v3/rank_block_0138.py'
SPEC = spec_from_file_location('rank_block_0138', MODULE)
AUDIT = module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class TestRankBlock0138(unittest.TestCase):
    def test_grouped_gamma_floor_is_sharp_in_rate(self):
        beta, count, energy = 2., 100, 10000.
        alpha = beta+count/2
        floor = AUDIT.grouped_gamma_floor(energy, count, beta=beta)

        def stock_component(rate):
            ratio = rate/beta
            return alpha/rate*energy + max(0., 2*alpha*(log(ratio)+1/ratio-1))

        optimum = beta+energy/2
        self.assertAlmostEqual(stock_component(optimum), floor, places=11)
        self.assertGreater(stock_component(1.), floor)
        self.assertGreater(stock_component(20_000.), floor)
        self.assertLess(floor, energy)
        self.assertEqual(AUDIT.grouped_gamma_floor(0., count), 0.)

    def test_only_direct_rank_edges_fund_the_late_score_ceiling(self):
        profile = json.loads(AUDIT.load(*AUDIT.FILES['profile']))
        report = AUDIT.rank_edges(profile)
        self.assertEqual(report['distinct'], 7)
        self.assertLess(report['post_signature_all_scores_free_upper_cpu_s'], .24)
        self.assertGreater(report['scopes']['corner_exploration']['inclusive_s'], 1.3)
        profile['cold'][0]['rank_calls'][0]['cpu_ns'] = 1
        with self.assertRaisesRegex(ValueError, 'Rank scopes overlap'):
            AUDIT.rank_edges(profile)

    def test_paid_third_and_fourth_are_distinct_exact_dense_scores(self):
        dense = json.loads(AUDIT.load(*AUDIT.FILES['dense_rank']))
        result = AUDIT.scored_dense(dense)
        self.assertAlmostEqual(result['fourth_gap'], 137.93087576956896)
        self.assertGreater(result['relative_fourth_gap'], 0.)
        self.assertLess(result['relative_fourth_gap'], .004)


if __name__ == '__main__':
    unittest.main()
