import unittest
import summarize
from leo.contracts.regional_position import RegionalPrior
from leo.analysis.regional_position_score import coordinates
import numpy as np

class SummaryChecks(unittest.TestCase):
    def test_geographic_distance_and_antimeridian(self):
        self.assertEqual(summarize.distance_km(37.,-122.,[37.,-122.]),0.)
        self.assertAlmostEqual(summarize.distance_km(0.,1.,[0.,0.]),111.1950802335,places=7)
        self.assertAlmostEqual(summarize.distance_km(0.,179.5,[0.,-179.5]),111.1950802335,places=7)
    def test_tail_counts_and_empty_failure_group(self):
        self.assertEqual(summarize.distribution([]),{'count':0})
        result=summarize.distribution([1.,3.,101.,201.])
        self.assertEqual(result['count'],4)
        self.assertEqual(result['median'],52.)
        self.assertEqual(result['over100'],2)
        self.assertEqual(result['under5'],2)
    def test_chart_inverse_matches_forward_chart(self):
        prior=RegionalPrior()
        for point in ([0,0],[-90,-75],[150,190]):
            recovered=summarize.reference_point(prior,coordinates(prior,point))
            np.testing.assert_allclose(recovered,point,atol=1e-8,rtol=0)
if __name__=='__main__':unittest.main(verbosity=2)
