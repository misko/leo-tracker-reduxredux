import copy
import unittest
from nominate02 import producer_pair_valid,nominate


class ProducerPrerequisiteTests(unittest.TestCase):
    def test_original_producer_valid_over15_phase_remains_nominatable(self):
        record=dict(gates=dict(tracks=[dict(compatible=True)]),linear_gates=[],
            final_phase_change_s=1e-7,endpoint_east_north_km=[0,0],state=dict(phases=[-15.23]))
        pair={a:copy.deepcopy(record) for a in ('c0','fitted_c')}
        self.assertTrue(producer_pair_valid(pair))
        target,control=nominate([dict(family=59188,has_eligible_owner=True,paired_score=1.)],
            [dict(owner='whole',family=59188,eligible=True,receiver=1,paired_score=1.)])
        self.assertEqual(target['owner'],'whole');self.assertIsNone(control)
        # This asserts selection-law fidelity only, not physical admission.
        pair['c0']['final_phase_change_s']=.02
        self.assertFalse(producer_pair_valid(pair))


if __name__=='__main__':unittest.main()
