import unittest
from run import predict


def rows(values):
    return [dict(prediction_utc_ns=i*1000000000,category=y,source_window_id=str(i),role='reception') for i,y in enumerate(values)]


class CausalityTests(unittest.TestCase):
    def test_current_and_future_do_not_change_current_prediction(self):
        a=predict(rows([0,1,2]),[.25]*4,10)
        b=predict(rows([0,3,0]),[.25]*4,10)
        self.assertEqual(a[1]['probabilities'],b[1]['probabilities'])
        self.assertNotEqual(a[2]['probabilities'],b[2]['probabilities'])

    def test_probabilities_normalize_and_begin_at_prior(self):
        out=predict(rows([0,1,2,3]),[.1,.2,.3,.4],10)
        self.assertEqual(out[0]['probabilities'],[.1,.2,.3,.4])
        for r in out: self.assertAlmostEqual(sum(r['probabilities']),1)

    def test_long_gap_forgets_observations(self):
        data=rows([0,0]);data[1]['prediction_utc_ns']=10**15
        self.assertEqual(predict(data,[.25]*4,1)[1]['probabilities'],[.25]*4)

    def test_reversed_time_rejected(self):
        with self.assertRaises(ValueError): predict(rows([0,1])[::-1],[.25]*4,1)
