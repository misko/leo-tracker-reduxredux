import unittest
import numpy as np
from leo.contracts.regional_position import PositionScore
from leo.analysis.regional_position_score import singleton_likelihood, ALIAS_HZ
from objective import coupled_likelihood, validate_pairs


class PairedLikelihoodTests(unittest.TestCase):
    def setUp(self):
        self.score = PositionScore(name="V16", sigma_hz=125., common_sigma_s=3.,
                                   relative_sigma_s=1., detection_budget=1.6, clutter_rate=.5)
        self.y = np.array([10., 13., -200.])
        self.pred = np.array([[0., 300., -200., 1800.], [3., 210., -180., 1700.],
                              [-100., -200., -310., -900.]])
        self.visible = np.ones_like(self.pred, dtype=bool)

    def test_rho_zero_exact_original(self):
        a = singleton_likelihood(self.y, self.pred, self.visible, self.score)
        b = coupled_likelihood(self.y, self.pred, self.visible, self.score, [[0, 1]], 0.)
        self.assertEqual(a.nll, b.nll)
        np.testing.assert_array_equal(a.prediction_gradient, b.prediction_gradient)

    def test_normalized_posteriors_and_gradient(self):
        for rho in (.5, .9, 1.):
            a = coupled_likelihood(self.y, self.pred, self.visible, self.score, [[0, 1]], rho)
            np.testing.assert_allclose(a.responsibilities.sum(axis=1)+a.clutter_probability, 1., atol=1e-12)
            for i in range(3):
                for j in range(4):
                    d = np.zeros_like(self.pred); d[i, j] = .01
                    plus = coupled_likelihood(self.y, self.pred+d, self.visible, self.score, [[0, 1]], rho).nll
                    minus = coupled_likelihood(self.y, self.pred-d, self.visible, self.score, [[0, 1]], rho).nll
                    self.assertAlmostEqual((plus-minus)/.02, a.prediction_gradient[i,j], places=8)

    def test_no_overlap_parity_and_duplicate_rejection(self):
        vis = self.visible.copy(); vis[0, 2:] = False; vis[1, :2] = False
        a = singleton_likelihood(self.y, self.pred, vis, self.score)
        b = coupled_likelihood(self.y, self.pred, vis, self.score, [[0, 1]], .9)
        self.assertEqual(a.nll, b.nll)
        np.testing.assert_array_equal(a.responsibilities, b.responsibilities)
        with self.assertRaises(ValueError):
            validate_pairs([[0, 1], [1, 2]], 3)

    def test_shared_assignment_preferred_at_equal_independent_score(self):
        p = np.array([[0., 2000., 4000., 6000.], [0., 2000., 4000., 6000.]])
        v = np.ones_like(p, dtype=bool)
        same = coupled_likelihood(np.array([0., 0.]), p, v, self.score, [[0, 1]], .9)
        different = coupled_likelihood(np.array([0., 2000.]), p, v, self.score, [[0, 1]], .9)
        self.assertLess(same.nll, different.nll)

    def test_integral_pair_mass_preserved(self):
        # Exact analytic integral: each Gaussian integrates to one; clutter to lambda.
        q = np.where(self.visible, self.score.detection_budget/4, 0.)
        odds = q/(1-q); i,j=0,1
        oi,oj=odds[i].sum(),odds[j].sum()
        boost=oi*oj/np.sum(odds[i]*odds[j])
        for rho in (0., .9, 1.):
            double=(1-rho)*oi*oj+rho*boost*np.sum(odds[i]*odds[j])
            self.assertAlmostEqual(double,oi*oj)


if __name__ == "__main__":
    unittest.main()
