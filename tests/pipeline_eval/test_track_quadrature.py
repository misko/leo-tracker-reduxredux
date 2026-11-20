import numpy as np
import pytest
from numpy.polynomial.legendre import legvander

from tools.pipeline_eval.reference import grid
from tools.pipeline_eval.variants import robust_em as lean
from tools.pipeline_eval.variants import track_quadrature as variant


def track():
    t = np.r_[np.linspace(0.0, 10, 22), np.linspace(12.0, 72, 31), 82.0]
    y = 120128 + 500 * t + 1700 * np.cos(t / 36) + 100 * np.sin(2 * t)
    doc = dict(
        duration_s=100.0,
        tracks=[dict(times=t, values=y, rf_hz=11.325e9, receiver=2, channel=5)],
    )
    return lean.observations(doc)[0][0]


def test_positive_lobatto_rule_preserves_empirical_moments():
    t = track().t
    x = 2 * t / t[-1] - 1
    nodes, mass = variant.lobatto(x, variant.NODE_COUNT)
    assert nodes[0] == -1 and nodes[-1] == 1
    assert len(nodes) == variant.NODE_COUNT
    assert (mass > 0).all()
    assert (np.diff(nodes) > 0).all()
    degree = 2 * len(nodes) - 3
    np.testing.assert_allclose(
        mass @ legvander(nodes, degree), legvander(x, degree).mean(axis=0), atol=1e-13
    )


@pytest.mark.parametrize("method", ("uniform_samples", "track_quadrature"))
def test_node_profile_agrees_with_full_gls_for_model_polynomials(method):
    tr = track()
    packed = variant.compress(tr, method)
    assert packed.times[[0, -1]].tolist() == tr.t[[0, -1]].tolist()

    def field(t):
        x = t / 70
        return np.array([13200 + 1200 * x - 5000 * x**3, -500 - 14000 * x**2])

    def derivative(t):
        x = t / 70
        return np.array([200000 + 100 * x + 10 * x**7, 7000 - 640 * x**2])

    observed = tr.hz - field(tr.t)
    one = tr.whiten.sum(axis=1)
    r = lean._unlevel(observed @ tr.whiten.T, one)
    d = lean._unlevel(derivative(tr.t) @ tr.whiten.T, one)
    want, phase = variant.phase_score(r, d)
    got, fitted = packed.rank(field(packed.times), derivative(packed.times))
    np.testing.assert_allclose(got, want, atol=5e-9)
    np.testing.assert_allclose(fitted, phase, atol=5e-10)


def test_exact_shortlist_and_exact_correction_preserve_stock_scores():
    tr = track()
    step = grid.FINE_ORBIT_STEP_S
    knots = np.arange(0, 120, step)
    row = np.arange(24, dtype=float)[:, None]
    p = np.zeros((len(row), len(knots), 3))
    v = np.zeros_like(p)
    p[:, :, 2] = 500 + row
    p[:, :, 0] = 20 * row + 4 * knots
    p[:, :, 1] = 40 + row * knots / 100
    v[:, :, 0] = 4
    v[:, :, 1] = row / 100
    tile = grid.Tile(np.zeros(3), np.eye(3), 120.0, knots, p, v, {})
    expected = lean.shortlist(tile, tr)
    for result in (
        variant.exact_arc(tile, tr),
        variant.exact_arc(tile, tr, np.sort(expected.orbit)),
    ):
        assert result.track is tr
        for name in ("orbit", "residual", "xy", "phase", "shape_loss", "phase_seed"):
            np.testing.assert_array_equal(getattr(result, name), getattr(expected, name))
