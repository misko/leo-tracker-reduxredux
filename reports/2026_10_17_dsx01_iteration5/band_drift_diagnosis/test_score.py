"""Mixture derivatives include every candidate and exclude held responses."""
import unittest
import numpy as np
from score import design, mixture_score, masked_score, profile_frequency_score
from leo.analysis.shared_scan_model import density
from leo.application.hard60_runner import HARD60_SCORE


def fixture():
    times = np.arange(16.)
    receiver = np.arange(16) % 2
    channel = np.where(np.arange(16) % 3, 6, 2)
    prediction = np.column_stack([100.+times*2., 200.+times*1.7, -100.+times])
    measured = 150.+times*3.
    visible = np.ones_like(prediction)
    q = np.full(3, HARD60_SCORE.satellite_budget/3) if hasattr(HARD60_SCORE, 'satellite_budget') else np.full(3, 1.6/3)
    return times, receiver, channel, prediction, measured, visible, q


class ScoreTests(unittest.TestCase):
    def test_exact_all_candidate_gradient_and_observed_hessian(self):
        times, rx, ch, prediction, measured, visible, q = fixture()
        basis, _ = design(times, rx, ch)
        terms, _ = density(measured, prediction, visible, np.full(16, 125.), q, HARD60_SCORE)
        result = mixture_score(terms.responsibilities, terms.residual_hz, 125., basis)
        step = 1e-3
        for j in range(4):
            high, _ = density(measured, prediction+step*basis[:, j, None], visible, np.full(16, 125.), q, HARD60_SCORE)
            low, _ = density(measured, prediction-step*basis[:, j, None], visible, np.full(16, 125.), q, HARD60_SCORE)
            self.assertAlmostEqual((high.nll-low.nll)/(2*step), result['gradient'][j], delta=1e-8)
            high_g = mixture_score(high.responsibilities, high.residual_hz, 125., basis)['gradient']
            low_g = mixture_score(low.responsibilities, low.residual_hz, 125., basis)['gradient']
            np.testing.assert_allclose((high_g-low_g)/(2*step), result['observed_hessian'][:, j], atol=1e-10)

    def test_all_held_cfo_perturbations_leave_score_and_design_identical(self):
        times, rx, ch, prediction, measured, visible, q = fixture()
        mask = np.arange(16) % 2 == 0
        a = masked_score(measured, prediction, visible, 125., q, HARD60_SCORE, times, rx, ch, mask)
        measured[~mask] += 1e8
        b = masked_score(measured, prediction, visible, 125., q, HARD60_SCORE, times, rx, ch, mask)
        np.testing.assert_array_equal(a[1], b[1])
        for key in a[3]:
            np.testing.assert_array_equal(a[3][key], b[3][key])

    def test_profile_removes_an_existing_direction_without_winner_labels(self):
        p = np.full((10, 2), .3)
        residual = np.column_stack([np.arange(10.), -np.arange(10.)])
        new = np.column_stack([np.ones(10), np.arange(10.)])
        old = np.ones((10, 2, 1))
        result = profile_frequency_score(p, residual, 125., new, old)
        self.assertAlmostEqual(result['complete_gaussian_information'][0, 0], 0., places=20)
        self.assertAlmostEqual(result['gradient'][0], 0., places=20)
        self.assertGreater(result['complete_gaussian_information'][1, 1], 0.)


if __name__ == '__main__':
    unittest.main()
