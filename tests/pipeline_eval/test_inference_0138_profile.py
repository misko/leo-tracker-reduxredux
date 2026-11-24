from copy import deepcopy
from pathlib import Path
import sys
import unittest

import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'reports/ALGO08/v3'))
from inference_0138_budget import source, totals
from inference_0138_profile import Responses


class TestInference0138Profile(unittest.TestCase):
    def test_same_response_does_not_replace_any_original_curve_call(self):
        seen = []

        def original(_scan, i, y, predicted, method, *, shortlist):
            seen.append((i, method, shortlist))
            return y-predicted

        bound = Responses(original)
        scan = object()
        y = np.array([1., 2.])
        base = np.zeros((2, 2))
        first = bound(scan, 0, y, base, 'shared_phase')
        second = bound(scan, 0, y.copy(), base+1, 'shared_phase')
        bound(scan, 0, y, base, 'receiver_smooth')
        bound(scan, 1, y, base, 'shared_phase')
        self.assertEqual(len(seen), 4)
        self.assertFalse(np.array_equal(first, second))
        self.assertEqual(bound.by_method['shared_phase']['response_repeats'], 1)
        self.assertEqual(bound.by_method['receiver_smooth']['response_repeats'], 0)

    def test_frozen_receipts_close_nested_clocks_and_scope_ceilings(self):
        record = totals(*(source(name) for name in ('profile','verification','pair')))
        bound = record['extended_disjoint_rank_reuse_ceiling_cpu_s']
        self.assertGreater(bound, record['same_response_reuse_full_curve_ceiling_cpu_s'])
        self.assertLess(bound, .5)
        self.assertLess(record['grid_fixed_phase_geometry_ceiling_cpu_s'], 2.)
        self.assertGreater(record['required_fraction_of_paid_rank_wall_to_half_fresh_named'], .90)

    def test_response_savings_cannot_exceed_enclosing_paid_association(self):
        profile, verification, pair = (source(name) for name in ('profile','verification','pair'))
        broken = deepcopy(profile)
        changed = broken['cold'][0]['responses']
        changed['receiver_smooth']['repeat_cpu_ns'] = 3_000_000_000
        verification['responses'] = changed
        with self.assertRaisesRegex(ValueError, 'nested call accounting'):
            totals(broken, verification, pair)


if __name__ == '__main__':
    unittest.main()
