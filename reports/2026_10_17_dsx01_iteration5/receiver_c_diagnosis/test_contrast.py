"""All-candidate RF-contrast derivatives and held-response exclusion."""
import unittest
import numpy as np
from contrast import contrast_basis, mixture_score, masked_contrast_score
from leo.analysis.shared_scan_model import density
from leo.application.hard60_runner import HARD60_SCORE


class ContrastTests(unittest.TestCase):
    def fixture(self):
        receiver = np.arange(16) % 2
        rf_column = np.linspace(-.5, .5, 16)
        prediction = np.column_stack([np.linspace(100., 150., 16), np.linspace(200., 250., 16), np.linspace(-100., -50., 16)])
        measured = np.linspace(150., 200., 16)
        return receiver, rf_column, prediction, measured, np.ones_like(prediction), np.full(3, 1.6/3)

    def test_exact_gradient_and_curvature_match_full_density(self):
        rx, rf, prediction, measured, visible, q = self.fixture()
        basis = contrast_basis(rf, rx)
        sigma = np.full(16, 125.)
        terms, _ = density(measured, prediction, visible, sigma, q, HARD60_SCORE)
        local = mixture_score(terms.responsibilities, terms.residual_hz, sigma, basis)
        h = .01
        high, _ = density(measured, prediction+h*basis, visible, sigma, q, HARD60_SCORE)
        low, _ = density(measured, prediction-h*basis, visible, sigma, q, HARD60_SCORE)
        self.assertAlmostEqual((high.nll-low.nll)/(2*h), local['gradient'][0], delta=1e-9)
        high_g = mixture_score(high.responsibilities, high.residual_hz, sigma, basis)['gradient'][0]
        low_g = mixture_score(low.responsibilities, low.residual_hz, sigma, basis)['gradient'][0]
        self.assertAlmostEqual((high_g-low_g)/(2*h), local['observed_hessian'][0, 0], delta=1e-11)

    def test_arbitrary_or_invalid_held_cfo_never_enters_training_score(self):
        rx, rf, prediction, measured, visible, q = self.fixture()
        mask = np.arange(16) % 3 != 0
        before = masked_contrast_score(measured, prediction, visible, 125., q, HARD60_SCORE, rf, rx, mask)
        measured[~mask] = np.nan
        after = masked_contrast_score(measured, prediction, visible, 125., q, HARD60_SCORE, rf, rx, mask)
        for key in before:
            np.testing.assert_array_equal(before[key], after[key])

    def test_natural_contrast_is_opposite_hz_per_ghz_at_receivers(self):
        basis = contrast_basis(np.array([-.5, .5, -.5, .5]), np.array([0, 0, 1, 1]))
        np.testing.assert_array_equal(basis[:, 0], [-.5, .5, .5, -.5])
        # At contrast100 Hz/GHz, receiver slope coefficients differ by200.
        np.testing.assert_array_equal(100.*basis[:, 0], [-50., 50., 50., -50.])


if __name__ == '__main__':
    unittest.main()
