import json
import unittest
import numpy as np
import propagation_audit as audit


class PropagationAuditTests(unittest.TestCase):
    def test_explicit_consistent_model_failure_only(self):
        states=np.ones((4,3));missing=np.full((4,3),np.nan)
        self.assertEqual(audit.classify([0]*4,states,states),'eligible')
        for code in audit.EXPLICIT_MODEL_INVALID_CODES:
            self.assertEqual(audit.classify([code]*4,missing,missing),'exclude_consistent_model_invalid_all_grid')
        self.assertTrue(audit.classify([0,0,1,1],states,states).startswith('block'))
        self.assertTrue(audit.classify([1,2,1,2],missing,missing).startswith('block'))
        self.assertTrue(audit.classify([99]*4,missing,missing).startswith('block'))
        self.assertTrue(audit.classify([5]*4,missing,missing).startswith('block'))
        self.assertTrue(audit.classify([0]*4,missing,missing).startswith('block'))
        self.assertEqual(audit.classification_receipt([1]*4,missing,missing),dict(
            status='exclude_consistent_model_invalid_all_grid',knots=4,error_counts={'1':4},
            zero_error_knots=0,finite_position_knots=0,finite_velocity_knots=0))

    def test_recorded_grid_and_failure_coverage(self):
        result=json.loads((audit.OUT/'propagation_audit.json').read_text())
        self.assertEqual(result['grid']['knots'],381);self.assertEqual(len(result['results']),9)
        for case in result['results']:
            self.assertTrue(case['nominal_causality_verified']);self.assertEqual(case['partial_or_unknown_blocks'],[])
            self.assertEqual(case['candidate_count'],sum(case['classification_counts'].values()))
            self.assertEqual(case['inherited_bank_failed_ids'],[r['norad'] for r in case['failures']])
            for row in case['failures']:
                self.assertEqual(row['error_counts'],{'1':381});self.assertEqual(row['zero_error_knots'],0)
                self.assertEqual(row['finite_position_knots'],0);self.assertIsNone(row['finite_radius_min_km'])
                self.assertEqual(row['classification'],'exclude_consistent_model_invalid_all_grid')


if __name__=='__main__':unittest.main()
