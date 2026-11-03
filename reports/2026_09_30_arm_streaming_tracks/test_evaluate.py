import unittest
from types import SimpleNamespace as NS
from evaluate import fit_quality


def fixture(times, frequencies):
    observations={str(i):NS(center_ns=round(t*1e9)) for i,t in enumerate(times)}
    points=[NS(candidate=str(i),dealiased_cfo_hz=f) for i,f in enumerate(frequencies)]
    tracks=NS(values=[NS(index=0,points=points,lane=NS(rf_hz=11.2e9))])
    return tracks,observations


class EvaluationTests(unittest.TestCase):
    def test_straight_line_and_constant_alias_shift(self):
        for shift in (0,1/4.4e-6):
            result=fit_quality(*fixture(range(12),[shift-1500*t for t in range(12)]))
            self.assertEqual(result['evaluated_predictions'],7)
            self.assertLess(result['p95_hz'],1e-7)

    def test_future_outlier_not_used_to_predict_itself(self):
        result=fit_quality(*fixture(range(6),[0,-1500,-3000,-4500,-6000,12500]))
        self.assertAlmostEqual(result['median_hz'],20000)
        self.assertEqual(result['fraction_over_2500_hz'],1)

    def test_gap_not_treated_as_short_range_prediction(self):
        result=fit_quality(*fixture([0,1,2,3,4,10],[0,-1500,-3000,-4500,-6000,-15000]))
        self.assertEqual(result['evaluated_predictions'],0)


if __name__=='__main__':
    unittest.main()
