from pathlib import Path

import numpy as np


def _module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    import fit_causal_orbit_phase_uncertainty

    return fit_causal_orbit_phase_uncertainty


def test_quadratic_phase_state_recovers_known_shift(monkeypatch):
    module = _module(monkeypatch)
    phase = np.array([-0.7, 0.2, 1.4])
    centre = np.column_stack([np.ones(3), np.arange(3), np.zeros(3)])
    linear = np.array([0.5, -0.2, 0.1])
    quadratic = np.array([0.03, 0.04, -0.02])
    minus = centre - linear + quadratic
    plus = centre + linear + quadratic
    expected = centre + phase[:, None] * linear + phase[:, None] ** 2 * quadratic
    np.testing.assert_allclose(module.quadratic_phase_state(centre, minus, plus, phase), expected)


def test_joint_parameters_do_not_depend_on_heldout_values(monkeypatch):
    module = _module(monkeypatch)
    from leo.analysis.research.regional_doppler import LIGHT_KM_S, REFERENCE_RF_HZ, Region

    count = 12
    angle = np.linspace(-0.2, 0.2, count)
    p = np.column_stack([7000 * np.cos(angle), 7000 * np.sin(angle), np.full(count, 300.0)])
    v = np.column_stack([-7 * np.sin(angle), 7 * np.cos(angle), np.full(count, 0.1)])
    receiver = Region(37.0, -122.0, 100.0, 100.0).points([0.0], [0.0]).ecef_km[0]
    delta = p - receiver
    y = -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(delta * v, axis=1) / np.linalg.norm(delta, axis=1)
    training = np.arange(count) % 2 == 0
    data = {
        "p": p,
        "v": v,
        "y": y,
        "training": training,
        "segment": np.zeros(count, int),
    }
    sensitivity = {
        "p-1": p - v,
        "p1": p + v,
        "v-1": v,
        "v1": v,
    }
    region = Region(37.0, -122.0, 100.0, 100.0)
    kwargs = dict(
        sensitivity=sensitivity,
        region=region,
        initial=[0.0, 0.0],
        source=np.ones(count, int),
        age_h=np.ones(count),
        eligible=np.ones(count, bool),
        prior_sigma=0.1,
    )
    first = module.fit_uncertainty(data, **kwargs)
    altered = {key: value.copy() for key, value in data.items()}
    altered["y"][~training] += 1_000_000
    second = module.fit_uncertainty(altered, **kwargs)
    np.testing.assert_allclose(first["x_km"], second["x_km"], atol=1e-9)
    assert first["rate_corrections_s_h"] == second["rate_corrections_s_h"]


def test_joint_fit_recovers_known_phase_rate_and_receiver(monkeypatch):
    module = _module(monkeypatch)
    from leo.analysis.research.regional_doppler import LIGHT_KM_S, REFERENCE_RF_HZ, Region

    count = 80
    time = np.linspace(-30, 30, count)
    region = Region(37.0, -122.0, 20.0, 20.0)
    receiver = region.points([0.0], [0.0]).ecef_km[0]
    position = receiver + np.column_stack(
        [300 + 7 * time, 500 - 4 * time, 800 + 0.01 * time**2]
    )
    velocity = np.column_stack([np.full(count, 7.0), np.full(count, -4.0), 0.02 * time])
    acceleration = np.column_stack(
        [np.zeros(count), np.zeros(count), np.full(count, 0.02)]
    )
    sensitivity = {
        "p-1": position - velocity + 0.5 * acceleration,
        "p1": position + velocity + 0.5 * acceleration,
        "v-1": velocity - acceleration,
        "v1": velocity + acceleration,
    }
    true_rate = 0.08
    age_h = np.full(count, 10.0)
    shifted_position = module.quadratic_phase_state(
        position, sensitivity["p-1"], sensitivity["p1"], true_rate * age_h
    )
    shifted_velocity = module.quadratic_phase_state(
        velocity, sensitivity["v-1"], sensitivity["v1"], true_rate * age_h
    )
    delta = shifted_position - receiver
    measured = (
        -REFERENCE_RF_HZ
        / LIGHT_KM_S
        * np.sum(delta * shifted_velocity, axis=1)
        / np.linalg.norm(delta, axis=1)
    )
    data = {
        "p": position,
        "v": velocity,
        "y": measured,
        "training": np.arange(count) % 3 != 0,
        "segment": np.zeros(count, int),
    }
    answer = module.fit_uncertainty(
        data,
        sensitivity,
        region,
        [1.0, -1.0],
        np.ones(count, int),
        age_h,
        np.ones(count, bool),
        prior_sigma=10.0,
        prior_residual_scale_hz=0.01,
    )
    np.testing.assert_allclose(answer["x_km"], [0.0, 0.0], atol=1e-3)
    np.testing.assert_allclose(answer["rate_corrections_s_h"]["1"], true_rate, rtol=1e-5)
