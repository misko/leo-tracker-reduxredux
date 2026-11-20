from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification.pass_hypotheses_chart_decisions import MARKER, terminal_copy
from tools.pipeline_eval.variants import pass_hypotheses as fit
from tools.pipeline_eval.variants import pass_hypotheses_audit as audit


def line(block, norad, normal, rhs):
    return SimpleNamespace(block=block, norad=norad, normal=np.array(normal, float), shift=rhs)


def test_two_constraints_intersect_and_same_pass_and_parallel_hypotheses_are_excluded():
    a = line(0, 13, [100, 0], 400)
    b = line(1, 27, [0, 90], -180)
    point, sigma = fit.intersect(a, b)
    np.testing.assert_allclose(point, [4, -2])
    assert sigma == pytest.approx(fit.SIGMA / 90)
    assert fit.intersect(a, line(0, 27, [0, 90], -180)) is None
    assert fit.intersect(a, line(1, 13, [0, 90], -180)) is None
    assert fit.intersect(a, line(2, 27, [90, 2], 200)) is None
    weak = line(2, 27, [0, 3], -6)
    assert fit.intersect(a, weak) is None
    report = audit.account([a, weak])
    assert report["raw_inside_pairs"] == 1
    assert report["conditioned_inside_pairs"] == 0


def test_training_prefix_clock_cancels_rf_calibration_and_affine_clock_on_held_data():
    t = np.linspace(-0.5, 0.5, 16)
    a = np.stack((np.ones_like(t), t), axis=1)
    h = 280 * (t**2 - t**3)
    y = 350 * t**3
    original, phase = fit.fit_clock(y, a, h, 10)
    adjusted, another = fit.fit_clock(y + 250_000 + 500 * t, a, h, 10)
    late = y.copy()
    late[10:] += 2000
    held, perturbed = fit.fit_clock(late, a, h, 10)
    np.testing.assert_allclose(original, adjusted, rtol=0, atol=1e-8)
    assert phase == pytest.approx(another)
    assert phase == pytest.approx(perturbed)
    np.testing.assert_allclose(original[:10], held[:10])
    np.testing.assert_allclose(original[10:] + 2000, held[10:])


def test_exact_line_of_sight_jacobian_sign_matches_receiver_displacement():
    p = np.array([[6930.0, -400.0, 800.0]])
    v = np.array([[1.0, 7.1, 0.5]])
    center = np.array([6370.0, 0.0, 0.0])
    site = np.array([[0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    _, j = fit.field(p, v, center, site, 11.8e9)
    for dim in (0, 1):
        f1 = fit.field(p, v, center + 0.01 * site[dim], site, 11.8e9)[0]
        f0 = fit.field(p, v, center - 0.01 * site[dim], site, 11.8e9)[0]
        assert (f1 - f0) / 0.02 == pytest.approx(j[..., dim])


def test_chart_terminal_marker_preserves_the_original_withhold_and_empty_endpoints():
    original = dict(
        id="example",
        method=fit.METHODS[0],
        result=dict(
            status="withheld",
            reason="no_conditioned_in_tile_intersections",
            boundary=fit.BOUNDARY,
            metrics=dict(position_attempted=False, in_tile_intersections=0),
            arms={a: dict(latlon=None, forced_latlon=None) for a in fit.ARMS},
        ),
    )
    frozen = deepcopy(original)
    marked = terminal_copy(original)
    assert original == frozen
    assert marked["result"]["metrics"] == original["result"]["metrics"] | {MARKER: True}
    assert marked["result"]["arms"] == original["result"]["arms"]
    assert marked["result"]["status"] == "withheld"
    altered = deepcopy(original)
    altered["result"]["arms"]["c0"]["forced_latlon"] = [11.4, -88.1]
    with pytest.raises(ValueError, match="without a numerical estimate"):
        terminal_copy(altered)
