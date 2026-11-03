import unittest
import numpy as np
from association_search import Search, Settings


def mode(number, rows, errors=None):
    return dict(catalog_number=number, offset_s=0., eligible_rows=rows,
                residual_hz=[0.]*len(rows) if errors is None else errors)


class SearchTests(unittest.TestCase):
    def settings(self, penalty=1.):
        return Settings(penalty=penalty, minimum_windows=1, minimum_span_s=0., maximum_gap_s=100.)

    def search(self, modes, groups, **kwargs):
        count = len(groups)
        return Search(modes, groups, np.arange(count), np.zeros(count, int), np.ones(count, int), settings=self.settings(), **kwargs)

    def test_alternatives_cannot_inflate_window_count(self):
        # Two candidates per window; the second satellite cannot claim copies.
        result = self.search([mode(1, [0,2]), mode(2,[1,3])], [0,0,1,1]).run()
        self.assertEqual(result['final']['assigned'], 2)
        self.assertEqual(result['final']['satellites'], 1)

    def test_alternative_can_recover_otherwise_unexplained_window(self):
        records = [mode(1,[1,3])]
        baseline = self.search(records, [0,0,1,1], allowed=[True,False,True,False]).run()
        alternatives = self.search(records, [0,0,1,1]).run()
        self.assertEqual(baseline['final']['assigned'], 0)
        self.assertEqual(alternatives['final']['assigned'], 2)
        self.assertEqual(baseline['final']['denominator'], alternatives['final']['denominator'])

    def test_replacement_escapes_greedy(self):
        # Greedy covers 6 for cost 1. B/C together cover 8 for cost 2.
        result = self.search([mode(1,list(range(6))), mode(2,[0,1,2,6]), mode(3,[3,4,5,7])], list(range(8))).run()
        self.assertEqual(result['initial']['objective'], 5)
        self.assertEqual(result['final']['objective'], 6)
        self.assertEqual(result['final']['assigned'], 8)
        self.assertTrue(any(r['accepted'] for r in result['trials']))

    def test_minimum_support_not_number_of_candidates(self):
        search = Search([mode(1,list(range(4)))], [0,0,1,1], np.arange(4), np.zeros(4,int), np.ones(4,int),
                        settings=Settings(penalty=0, minimum_windows=3, minimum_span_s=0))
        self.assertEqual(search.run()['final']['assigned'], 0)

    def test_gap_splits_support(self):
        search = Search([mode(1,list(range(4)))], [0,1,2,3], [0,1,20,21], np.zeros(4,int), np.ones(4,int),
                        settings=Settings(penalty=0, minimum_windows=3, minimum_span_s=0))
        self.assertEqual(search.run()['final']['assigned'], 0)

    def test_tolerance_is_configurable(self):
        search = self.search([mode(1,[0,1],[601.,0.])], [0,1])
        self.assertEqual(search.run()['final']['assigned'], 0)  # single remaining point does not pay penalty

    def test_two_receivers_can_have_simultaneous_satellites(self):
        search = Search([mode(1,[0,1]),mode(2,[2,3])], [0,1,2,3], [0,1,0,1], [0,0,1,1], [1,1,1,1], settings=self.settings())
        self.assertEqual(search.run()['final']['satellites'], 2)

    def test_duplicate_mode_rows_rejected(self):
        with self.assertRaises(ValueError):
            self.search([mode(1,[0,0])], [0,1])


if __name__ == '__main__':
    unittest.main()
