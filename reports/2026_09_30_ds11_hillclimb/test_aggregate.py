import copy
import unittest
from aggregate import validate_result, summarize_rows


class AggregateTests(unittest.TestCase):
    def test_error_cannot_select_a_lower_training_score(self):
        start=dict(qualified=True,success=True,boundary=False,gradient=0.,audit=0.,score=1.,x=[0,0,0])
        record=dict(starts=[start,dict(start,score=2.,x=[1,0,0])],selected=dict(start))
        with self.assertRaises(AssertionError):
            validate_result(record)
        record['selected']=dict(record['starts'][1])
        self.assertTrue(validate_result(record))

    def test_failures_stay_in_attempted_denominator(self):
        row=dict(qualified=True,error_m=500.,baseline_error_m=1500.,common_iid_held_gain=0.,runtime_s=1.)
        fail=dict(row,qualified=False,error_m=None)
        result=summarize_rows([row,fail])
        self.assertEqual(result['attempts'],2)
        self.assertEqual(result['qualified'],1)
        self.assertEqual(result['subkm'],1)
        self.assertEqual(result['paired_wins'],1)


if __name__=='__main__':
    unittest.main()
