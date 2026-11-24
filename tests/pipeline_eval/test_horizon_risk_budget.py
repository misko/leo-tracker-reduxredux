from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import tempfile
import unittest


MODULE = Path(__file__).resolve().parents[2]/'reports/ALGO08/v3/horizon_risk_budget.py'
SPEC = spec_from_file_location('horizon_risk_budget', MODULE)
BUDGET = module_from_spec(SPEC)
SPEC.loader.exec_module(BUDGET)


class TestHorizonRiskBudget(unittest.TestCase):
    def test_census_preserves_unsplit_and_uses_median_of_paired_ratios(self):
        result = BUDGET.historical_envelope([
            {'case': 'a', 'stages': [2., 7., 1.]},
            {'case': 'b', 'stages': [9., 1., 1.]},
            {'case': 'c', 'stages': [0., 0., 20.]},
        ])
        self.assertEqual(result['splits'], 2)
        self.assertEqual(result['unsplit_elapsed_s'], {'c': 20.})
        self.assertEqual(result['free_solve']['relative_total'], 33/41)
        self.assertEqual(result['free_solve']['median_paired_ratio'], 10/11)

    def test_census_refuses_partial_clock(self):
        with self.assertRaisesRegex(ValueError, 'split stage clock'):
            BUDGET.historical_envelope([{'case': 'a', 'stages': [3., 0., 2.]}])

    def test_projection_subtracts_only_nested_wall_scopes(self):
        def row(case, stock, candidate, prepare, infer):
            return dict(case=case, stock={'clock': {'elapsed_s': stock}}, candidate={'clock': {'elapsed_s': candidate}},
                        candidate_scopes={'prepare': {'elapsed_s': prepare, 'cpu_s': prepare+0.1},
                                          'infer': {'elapsed_s': infer, 'cpu_s': infer+0.1}})

        result = BUDGET.raw_envelope([row('fix', 10., 8., 1.5, .5), row('withhold', 1.5, .5, 0., 0.)])
        self.assertEqual(result['free_prepare_and_infer']['remaining_s_by_case'], {'fix': 6., 'withhold': .5})
        self.assertEqual(result['free_prepare_and_infer']['positive_gap_to_half_s'], .75)

    def test_ceiling_requires_expected_caller_and_bills_all_children(self):
        def leaf(kernel, caller, count, inclusive):
            return {'source': ['frames.py', 1, kernel], 'stages': {'prepare': {'calls': count,
                    'inclusive_cpu_s': inclusive, 'exclusive_cpu_s': inclusive/2,
                    'callers': [[['caller.py', 1, caller], count, inclusive/2]]}}}

        leaves = [leaf('look_angles', 'regional_bank', 1, .04), leaf('teme_to_ecef', 'ecef_states', 2, .05)]
        document = {'profile': {'profiles': {'leaves': leaves}}}
        self.assertEqual(BUDGET.profiled_outer_ceiling(document)['whole_scope_ceiling_cpu_s'], .09)
        leaves[0] = leaf('look_angles', 'unknown', 1, .04)
        with self.assertRaisesRegex(ValueError, 'caller or count'):
            BUDGET.profiled_outer_ceiling(document)

    def test_pin_checks_exact_evidence_bytes(self):
        with tempfile.TemporaryDirectory(dir='/dev/shm') as root:
            receipt = Path(root)/'receipt.json'
            receipt.write_bytes(b'{}\n')
            with self.assertRaisesRegex(ValueError, 'Unrecognized evidence'):
                BUDGET.checked(receipt, BUDGET.sha256(b'{}').hexdigest())


if __name__ == '__main__':
    unittest.main()
