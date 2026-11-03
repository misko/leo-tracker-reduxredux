"""Math and explicitly saved-analysis fixture checks for gradient attribution."""
import json
import unittest
from pathlib import Path
import numpy as np
from gradient_by_satellite import OUT,HERE,contribution_terms
from replay import digest


class GradientTests(unittest.TestCase):
    def test_units_and_additivity(self):
        w=np.array([[1.,2.],[3.,4.]])
        j=np.array([[[1.,2.],[3.,4.]],[[5.,6.],[7.,8.]]])
        terms=contribution_terms(w,j)
        np.testing.assert_allclose(terms.sum(axis=(0,1)),[5.,6.])
        with self.assertRaises(ValueError):contribution_terms(w,j[:,:,0])

    def test_saved_profile_decomposition(self):
        receipt=json.loads((OUT/'receipt.json').read_text())
        evidence=json.loads((HERE/'orientation-evidence.json').read_text())
        self.assertEqual(len(receipt['results']),4)
        for r in receipt['results']:
            self.assertEqual(r['capture_roof_lat_lon'],evidence['operator_roof_lat_lon'])
            self.assertTrue(r['roof_fit']['success'])
            self.assertTrue(all(x['success'] for x in r['roof_restarts']))
            for step in r['steps']:
                sat=np.array(step['satellite_gradients_per_100m'])
                rx=np.array(step['receiver_satellite_gradients_per_100m'])
                np.testing.assert_allclose(rx.sum(axis=0),sat,atol=1e-9)
                np.testing.assert_allclose(sat.sum(axis=0)+step['prior_gradient_per_100m'],r['direct_total_gradient_per_100m'],atol=.005,rtol=.01)
                np.testing.assert_allclose(step['profile_score_finite_difference_per_100m'],r['direct_total_gradient_per_100m'],atol=.005,rtol=.01)
                self.assertFalse(any(step['visibility_changes']))
            if r['arm']=='zero-c':self.assertEqual(r['roof_fit']['c_hz_per_ghz'],0.)
            for path,sha in r['sources'].items():self.assertEqual(digest(Path(path)),sha)
        for scan in 'AB':
            a,b=[r for r in receipt['results'] if r['scan']==scan]
            self.assertEqual([x['satellite'] for x in a['rows']],[x['satellite'] for x in b['rows']])
            self.assertEqual(a['observation_count'],b['observation_count'])


if __name__=='__main__':unittest.main()
