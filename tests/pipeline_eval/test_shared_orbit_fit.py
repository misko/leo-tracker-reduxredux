"""Verify shared satellite profiling and the observed mixture curvature."""

import numpy as np
import pytest

from tools.pipeline_eval.variants import shared_orbit_fit as model


def _fragment(hz, lane):
    t = np.arange(8.0)
    y = np.asarray(hz, dtype=float) * np.linspace(-1, 1, len(t))
    tr = model.lean.Track(t, y, 11.5e9, lane, True, t / 100, np.eye(len(t)) / 150)
    direction = 250 * np.linspace(-1, 1, len(t))
    slope = np.column_stack((np.sin(t), 20 * np.cos(t)))
    arc = model.lean.Arc(
        tr, np.array([0]), y[None], slope[None], direction[None], np.zeros(1), np.zeros(1),
    )
    return model.soft.prepare(arc, np.zeros(9))


def test_one_bounded_displacement_is_fitted_jointly_across_both_receivers():
    tracks = [_fragment(350, 0), _fragment(450, 2)]
    x = np.zeros(9)
    normal, _ = model.blocks(tracks, x, np.zeros(1))
    _, _, phase = model.profile(x, *normal)
    assert len(phase) == 1
    assert 1.2 < phase[0] < 1.9
    # Adding both fragments adds their data precision to a single Gaussian prior.
    both = normal[-1]
    separate = sum(model.blocks([track], x, np.zeros(1))[0][-1] for track in tracks)
    np.testing.assert_allclose(both, separate - model.PHASE_PRECISION)


def test_profile_gradient_remains_analytic_at_an_active_phase_bound():
    diag = np.diag([4.0, 5.0])
    rhs = np.array([10.0, -7.0])
    cross = np.array([[0.5, 0.2], [1.0, 0.1]])
    r = np.array([50.0, 0.5])
    precision = np.array([2.0, 3.0])
    x = np.array([0.2, -0.1])
    args = diag, rhs, cross, r, precision
    _, derivative, phase = model.profile(x, *args)
    assert phase[0] == model.lean.PHASE_BOUND_S
    axes = np.eye(2) * 1e-5
    expected = [
        (model.profile(x + e, *args)[0] - model.profile(x - e, *args)[0]) / 2e-5
        for e in axes
    ]
    np.testing.assert_allclose(derivative, expected, atol=1e-8)


def test_conditional_rf_stays_normalized_when_absolute_inlier_mass_underflows():
    track = _fragment(15_000, 0)
    mass, branches = model.branch(track, np.zeros(9), np.zeros(1), conditional=True)
    assert mass == 0.0
    assert branches.sum() == pytest.approx(1.0)
    assert branches.max() == pytest.approx(1.0)


def test_radius_matches_direct_finite_difference_of_full_mixture_gradient():
    tracks = [_fragment(500, 0), _fragment(650, 2)]
    test = np.zeros(9)
    test[8] = 2.3

    def gradient(joined):
        x, phase = np.r_[joined[:-1], 0.0], joined[-1:]
        (a, b, c, d, e), _ = model.blocks(tracks, x, phase)
        return np.r_[(a @ x - b + c.T @ phase)[:8], e * phase + c @ x - d]

    axes = np.eye(9) * 1e-5
    hessian = np.column_stack([(gradient(test + e) - gradient(test - e)) / 2e-5 for e in axes])
    expected = float(np.sqrt(5.991 * np.linalg.eigvalsh(np.linalg.inv(hessian)[:2, :2])[-1]))
    radius = model.curvature(tracks, np.zeros(9), test[-1:], 8)
    assert radius == pytest.approx(expected, rel=1e-6)
