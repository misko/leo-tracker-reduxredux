import numpy as np
import pytest

from tools.pipeline_eval.variants import doppler_inflection as solver


def test_observed_inflection_root_survives_arbitrary_affine_frequency_offset():
    t = np.linspace(-12, 12, 81)
    f = 12 * (t - 0.8) ** 3 / 6 - 2700 * t
    a = solver.crossing(t, f)
    b = solver.crossing(t, f + 100_000 + 400 * t)
    assert a == pytest.approx(b)
    assert a[0] == pytest.approx(0.8)
    assert a[2] == pytest.approx(12)


def test_crossing_requires_positive_jerk_observed_bracket_and_independent_support():
    t = np.arange(0.0, 64.0, 0.25)
    f = -1800 * t + 12 * (t - 31.5) ** 3 / 6
    _, held = solver.scan(t, f)
    assert solver.unique(held)[0]["time_s"] == pytest.approx(31.5)
    assert not solver.scan(t, -f)[1]
    assert not solver.scan(t, -1800 * t + 12 * (t - 75) ** 3 / 6)[1]
    gap = np.abs(t - 31.5) > 4
    assert not solver.scan(t[gap], f[gap])[1]
    f[1::2] = -1800 * t[1::2]
    props, held = solver.scan(t, f)
    assert props and not held


def test_geometry_bound_uses_named_site_matched_orbits_and_timing_precision():
    model = {
        (0, 0): {1: 90, 2: 110},
        (10, 0): {1: 92, 2: 110},
        (-10, 0): {1: 88, 2: 110},
        (0, 10): {1: 90, 2: 111},
        (0, -10): {1: 90, 2: 109},
    }
    fitted = solver.sensitivity(model)
    assert fitted["known_identity_events"] == 2
    assert fitted["ideal_worst_axis_km"]["0.3"] == pytest.approx(3)
    assert fitted["ideal_worst_axis_km"]["18.0"] == pytest.approx(180)


def test_identity_mixture_remains_ambiguous_when_many_orbits_share_time():
    e = [dict(time_s=60, held_time_s=60, sigma_s=0.3)]
    assert solver.likelihood({1: 60}, e, 300)[1] == 1
    assert solver.likelihood(dict.fromkeys(range(12), 60), e, 300)[1] == 0
    assert solver.likelihood({}, e, 300)[1] == 0
