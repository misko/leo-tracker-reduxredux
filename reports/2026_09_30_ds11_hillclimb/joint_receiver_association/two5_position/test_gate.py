import unittest
from gate import assess


class GateTests(unittest.TestCase):
    def rows(self):return [dict(family=0,cohort='additional' if i==2 else 'original',doppler=dict(qualified=True,error_m=100*(i+1)),signed=dict(qualified=True,error_m=90*(i+1))) for i in range(3)]
    def test_full_improvement_passes_but_missing_record_does_not(self):
        rows=self.rows();self.assertTrue(assess(rows)['0']['passed'])
        self.assertFalse(assess(rows[:2])['0']['passed'])
        rows[2]['doppler']['qualified']=False
        self.assertFalse(assess(rows)['0']['passed'])

    def test_additional_regression_cannot_be_hidden_by_original_gains(self):
        rows=self.rows();rows[2]['signed']['error_m']=301
        self.assertFalse(assess(rows)['0']['passed'])
