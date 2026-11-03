"""Scientific guards for the bounded visible-arc diagnostic prototype."""

import numpy as np
from investigate_ds23_visible_arcs import (
    PERIOD,
    exact_orbit_frequency,
    polynomial_models,
    repair_path,
    spline_design,
)


def test_piecewise_basis_is_continuous_in_value_and_slope():
    knot, h = 50.0, 1e-4
    t = np.array([knot - h, knot, knot + h])
    design = spline_design(t, 4, [knot], 0.0, 100.0)
    left = (design[1] - design[0]) / h
    right = (design[2] - design[1]) / h
    np.testing.assert_allclose(left, right, atol=1e-7)
    assert design.shape == (3, 8)  # two quartics minus two exact C1 constraints


def test_bic_does_not_add_knots_to_a_noisy_line():
    rng = np.random.default_rng(91)
    t = np.linspace(0, 110, 150)
    y = 70000 - 1200 * t + rng.normal(0, 40, len(t))
    best = polynomial_models(t, y, 40.0)[0]
    assert best["degree"] == 1
    assert len(best["knots"]) == 0


def test_graph_path_repair_grows_alias_wrapped_points_without_satellites():
    rng = np.random.default_rng(92)
    t = np.linspace(0, 110, 150)
    x = t / 110
    signal = 260000 - 500000 * x + 150000 * np.maximum(x - 0.5, 0) ** 2
    y = signal + rng.normal(0, 25, len(t))
    wrapped = (y + PERIOD / 2) % PERIOD - PERIOD / 2
    path = np.unique(np.r_[np.arange(0, len(t), 2), len(t) - 1])
    fitted = repair_path(t, wrapped, path, y[path], 40.0)
    assert fitted is not None
    assert len(fitted["indices"]) == len(t)
    assert fitted["model"]["degree"] <= 4
    assert fitted["model"]["maximum_hz"] < 120
    assert fitted["model"]["diagnostics"]["noise_screen_pass"]


def test_real_frequency_step_is_not_forced_into_continuous_track():
    t = np.linspace(0, 110, 150)
    y = 70000 - 1200 * t + 20000 * (t > 55)
    assert repair_path(t, y, np.arange(len(t)), y, 40.0) is None


def test_zero_orbit_perturbation_agrees_with_original_satrec():
    from analyze_dsx01_fixed_site import ecef_states
    from sgp4.api import Satrec

    from leo.sky.frames import geodetic_to_ecef_km, julian_day_from_utc_ns
    from leo.sky.propagation import ElementSetCatalogue

    lines = [
        "1 25544U 98067A   19343.69339541  .00001764  00000-0  38792-4 0  9991",
        "2 25544  51.6436 211.2001 0007417  17.6667  85.6398 15.50103472202482",
    ]
    origin = 1575910000000000000
    times = np.array([0.0, 30.0, 100.0])
    sat = Satrec.twoline2rv(*lines)
    catalogue = ElementSetCatalogue(("test",), (25544,), (sat,))
    p, v, usable = ecef_states(catalogue, origin, times)
    assert usable.all()
    relative = p[0] - geodetic_to_ecef_km(37.0, -122.0, 0)
    expected = (
        -11e9 / 299792.458 * np.sum(relative * v[0], axis=1) / np.linalg.norm(relative, axis=1)
    )
    actual = exact_orbit_frequency(lines, origin, times, 37.0, -122.0, 11e9, np.zeros(9))
    np.testing.assert_allclose(actual, expected, atol=1e-6, rtol=0)
    jd, fr = julian_day_from_utc_ns(np.array([origin]))
    assert np.isfinite(jd[0] + fr[0])
