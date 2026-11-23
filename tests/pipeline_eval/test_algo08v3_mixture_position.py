from importlib import import_module

import numpy as np
from scipy.optimize import lsq_linear


mixture = import_module("reports.ALGO08.v3.mixture_position")


def test_local_projection_matches_gaussian_penalty_and_phase_bound():
    tangent = np.array([-3., 0., 7., 11., 12.])
    two = np.column_stack((np.ones(len(tangent)), tangent))
    sigma, phase_sigma = 80., 7.
    augmented = np.vstack((two / sigma, np.diag([1 / 1000., 1 / phase_sigma])))
    for phase in (-60., -2., 1., 60.):
        raw = two @ [1650., phase] + np.array([2., 1., -2., 5., 7.])
        referee = lsq_linear(augmented, np.r_[raw / sigma, 0., 0.], bounds=([-np.inf, -15.], [np.inf, 15.]))
        square, fitted, offset, residual, _ = mixture.profile(raw, tangent, sigma, phase_sigma)
        np.testing.assert_allclose([offset, fitted], referee.x, atol=1e-5)
        np.testing.assert_allclose(square, 2 * referee.cost, atol=1e-9)
        np.testing.assert_allclose(residual, raw - two @ referee.x, atol=1e-5)


def test_schur_gram_matches_profiled_cost_around_free_and_clipped_phase():
    t = np.linspace(-5, 5, 9)
    design = np.c_[t**2, 10 * np.cos(t), np.ones(9)]
    shift = np.array([1., 2., 3.])
    for raw in (300 + t**2, -500 + 10_000 * t):
        square, _, _, _, gram = mixture.profile(raw, t, 60., 20., design=design)
        lower = mixture.profile(raw - design @ shift, t, 60., 20.)[0]
        upper = mixture.profile(raw + design @ shift, t, 60., 20.)[0]
        np.testing.assert_allclose(upper + lower - 2 * square, 2 * (shift @ gram @ shift) / 60**2, atol=1e-8)


def test_mixture_retains_correct_signed_alias_and_can_use_null():
    t = np.linspace(-1, 1, 9)
    shift = mixture.PERIOD
    sample = 1500 * t**2
    good = dict(design=np.zeros((len(t), 9)), raw=np.array([10 + 20 * t - shift, 70_000 * t**3]),
                tangent=np.stack((3 * t, t)), labels=np.array([10, 20]), phase=np.zeros(2),
                widths=np.ones(2) * 5, sample=sample)
    poor = dict(good, raw=np.full((2, 9), 17_000.))
    _, selected, _, _ = mixture.update([good, poor], 70., np.zeros(8), derivatives=False)
    assert selected[0]["index"] == 10 and selected[0]["alias"] == 1
    assert mixture.qualified(selected[0])
    assert not mixture.qualified(selected[1])


def test_no_visible_candidates_use_null_instead_of_reporting_an_owner():
    empty = dict(design=np.arange(63, dtype=float).reshape(7, 9), raw=np.empty((0, 7)), tangent=np.empty((0, 7)),
                 labels=np.empty(0, int), phase=np.empty(0), widths=np.empty(0), sample=np.ones(7))
    loss, records, gram, step = mixture.update([empty], 100., np.zeros(8), derivatives=True)
    assert np.isfinite(loss) and records == [None]
    np.testing.assert_array_equal(gram, np.eye(8))
    np.testing.assert_array_equal(step, np.zeros(8))
