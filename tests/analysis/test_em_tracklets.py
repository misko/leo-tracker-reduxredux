"""Component-owned controls for independent wrapped mixture discovery."""

from dataclasses import replace

import numpy as np
from numpy.polynomial import legendre as leg

from leo.analysis.em_tracklets import _expectation, _merge, _objective, fit_lane
from leo.analysis.polynomial_tracklets import TrackConfig


def _integrity(result, t, y, cfg):
    assert len(result["assignment"]) == len(t)
    seen = []
    for number, track in enumerate(result["tracks"]):
        rows = np.asarray(track["indices"])
        assert np.all(result["assignment"][rows] == number)
        assert len(rows) >= cfg.min_points
        assert np.ptp(t[rows]) >= cfg.min_span_s
        for piece in track["pieces"]:
            ix = piece["indices"]
            predicted = leg.legval(
                (t[ix] - piece["reference_time_s"]) / piece["time_scale_s"],
                piece["coefficients_hz"],
            )
            residual = y[ix] + result["alias_lifts"][ix] * cfg.alias_spacing_hz - predicted
            assert np.max(np.abs(residual)) < cfg.association_sigma * cfg.noise_sigma_hz
            assert piece["degree"] <= cfg.max_degree
            seen.extend(ix)
    assert len(seen) == len(set(seen))
    assert len(seen) == np.sum(result["assignment"] >= 0)


def test_wrapped_line_and_generalized_em_monotonicity():
    cfg = replace(TrackConfig(), max_slope_hz_s=8000)
    rng = np.random.default_rng(1301)
    t = np.linspace(0, 48, 145)
    y = (130000 - 2300 * t + rng.normal(0, 45, len(t)) + cfg.alias_spacing_hz / 2) % (
        cfg.alias_spacing_hz
    ) - cfg.alias_spacing_hz / 2
    result = fit_lane(t, y, cfg)
    _integrity(result, t, y, cfg)
    assert np.mean(result["assignment"] >= 0) > 0.9
    assert result["diagnostics"]["conditional_updates_monotonic"]
    for row in result["diagnostics"]["likelihood_trace"]:
        if row["accepted"]:
            assert row["proposed_objective"] <= row["before_objective"] + 1e-8


def test_e_step_assigns_soft_mass_to_tracks_aliases_and_clutter():
    cfg = TrackConfig()
    t = np.linspace(0, 12, 20)
    model = dict(
        indices=np.arange(len(t)),
        degree=1,
        reference_time_s=6.0,
        time_scale_s=6.0,
        coefficients_hz=np.array([3000.0, -600.0]),
    )
    y = 3000 - 100 * (t - 6)
    y[::2] -= cfg.alias_spacing_hz
    y[-1] += 400
    likelihood, weight, target = _expectation([model], t, y, cfg)
    assert np.isfinite(likelihood)
    assert np.all((weight > 0) & (weight < 1))
    assert weight[0, -1] < weight[0, 0]
    np.testing.assert_allclose(target[0, :-1], 3000 - 100 * (t[:-1] - 6), atol=1e-8)


def test_crossing_curves_with_uniform_clutter():
    rng = np.random.default_rng(1302)
    cfg = replace(TrackConfig(), max_slope_hz_s=8000)
    tt = np.linspace(0, 48, 97)
    t = np.concatenate((tt, tt + 0.06, rng.uniform(0, 48, 45)))
    y = np.concatenate((40000 - 900 * tt, -5000 + 1000 * tt, rng.uniform(-100000, 100000, 45)))
    y[:194] += rng.normal(0, 40, 194)
    result = fit_lane(t, y, cfg)
    _integrity(result, t, y, cfg)
    assert np.mean(result["assignment"][:194] >= 0) > 0.85
    assert np.mean(result["assignment"][194:] >= 0) < 0.25


def test_quadratic_curvature_and_long_observation_gap():
    rng = np.random.default_rng(1303)
    cfg = replace(TrackConfig(), max_slope_hz_s=8000)
    t = np.concatenate((np.linspace(0, 28, 85), np.linspace(70, 98, 85)))
    y = 65000 - 600 * t + 7 * t**2 + rng.normal(0, 35, len(t))
    result = fit_lane(t, y, cfg)
    _integrity(result, t, y, cfg)
    assert np.mean(result["assignment"] >= 0) > 0.85
    for track in result["tracks"]:
        for piece in track["pieces"]:
            assert np.max(np.diff(np.sort(t[piece["indices"]]))) <= cfg.max_gap_s


def test_real_frequency_step_does_not_become_one_smooth_piece():
    rng = np.random.default_rng(1304)
    cfg = TrackConfig()
    t = np.linspace(0, 60, 181)
    y = 50000 - 900 * t + (t >= 30) * 20000 + rng.normal(0, 35, len(t))
    result = fit_lane(t, y, cfg)
    _integrity(result, t, y, cfg)
    assert np.mean(result["assignment"] >= 0) > 0.8
    for track in result["tracks"]:
        for piece in track["pieces"]:
            times = t[piece["indices"]]
            assert not (times.min() < 27 and times.max() > 33)


def test_sparse_and_nonfinite_points_preserve_api_shape():
    t = np.array([0.0, np.nan, 2.0])
    y = np.array([1.0, 2.0, np.inf])
    result = fit_lane(t, y)
    assert result["tracks"] == []
    np.testing.assert_array_equal(result["assignment"], [-1, -1, -1])
    np.testing.assert_array_equal(result["alias_lifts"], [0, 0, 0])


def test_duplicate_soft_components_merge_with_lower_penalized_observed_objective():
    cfg = TrackConfig()
    t = np.linspace(0, 60, 121)
    y = 5000 - 100 * t
    left = dict(
        indices=np.flatnonzero(t <= 33),
        degree=1,
        reference_time_s=30.0,
        time_scale_s=30.0,
        coefficients_hz=np.array([2000.0, -3000.0]),
    )
    right = dict(left, indices=np.flatnonzero(t >= 27))
    diagnostics = {"structure_changes": []}
    before = _objective([left, right], t, y, cfg)
    models = _merge([left, right], t, y, cfg, diagnostics)
    assert len(models) == 1
    assert len(models[0]["indices"]) == len(t)
    assert _objective(models, t, y, cfg) < before
    assert diagnostics["structure_changes"][0]["operation"] == "merge"
