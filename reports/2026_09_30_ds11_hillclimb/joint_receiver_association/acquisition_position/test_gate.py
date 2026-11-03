import unittest
from gate import compare, evaluate


class PositionGateTests(unittest.TestCase):
    def test_median_gain_cannot_hide_tail_regression(self):
        self.assertFalse(compare([10., 20., 30.], [8., 15., 40.])['passed'])

    def test_missing_record_fails_instead_of_being_dropped(self):
        self.assertFalse(compare([10., 20.], [8., float('nan')])['passed'])

    def test_each_cohort_and_qualification_required(self):
        rows = [dict(cohort=c, original=dict(distance_m=100.), doppler=dict(qualified=True, distance_m=100.), signed=dict(qualified=True, distance_m=80.)) for c in ('original', 'additional')]
        self.assertTrue(evaluate(rows)['passed'])
        rows[1]['signed']['distance_m'] = 101.
        self.assertFalse(evaluate(rows)['passed'])
        rows[1]['signed'].update(distance_m=80., qualified=False)
        self.assertFalse(evaluate(rows)['passed'])
