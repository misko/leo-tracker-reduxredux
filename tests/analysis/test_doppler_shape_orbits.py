from dataclasses import replace

import numpy as np

from leo.analysis.research import doppler_shape_orbits as subject
from leo.contracts.regional_position import PositionObservations, PositionOrbitBank, RegionalPrior


def inputs():
    times = np.tile(np.linspace(-1.0, 1.0, 7), 2)
    observations = PositionObservations(
        tuple(f"w{i}" for i in range(14)),
        times,
        2.0 * times - 3.0 * times**2 + np.repeat([9000.0, -7000.0], 7),
        np.repeat([11.2e9, 12.5e9], 7),
        np.repeat([0, 1], 7),
        np.repeat([1, 7], 7),
        np.ones(14),
    )
    bank = PositionOrbitBank(
        np.array([100, 101]), np.array([-20.0, 20.0]), np.ones((2, 2, 3)), np.zeros((2, 2, 3))
    )
    return observations, bank, RegionalPrior(radius_km=20.0)


def predictor(bank, observations, prior, point, shifts_s, *, derivatives=True):
    t = observations.times_s
    base = point[0] * t + point[1] * t**2 + shifts_s[0] * t**3
    pred = np.column_stack((base, base + 800.0 * t))
    geo = np.tile(np.column_stack((t, t**2))[:, None, :], (1, 2, 1))
    timing = np.tile(t[:, None] ** 3, (1, 2))
    return pred, np.ones(pred.shape, bool), geo, timing


def test_orbit_shape_gradient_and_offset_rf_invariance(monkeypatch):
    monkeypatch.setattr(subject, "predict_orbits", predictor)
    observations, bank, prior = inputs()
    sequences = (tuple(range(7)), tuple(range(7, 14)))
    objective = subject.DopplerShapeOrbitObjective(
        observations, bank, prior, sequences, sigma_hz=1.0
    )
    theta = np.array([1.0, -2.0, 0.2, 230.0])
    value, gradient = objective.evaluate(theta, fitted_c=True)
    for index in range(4):
        delta = np.eye(4)[index] * 1e-4
        numeric = (
            objective.evaluate(theta + delta, fitted_c=True)[0]
            - objective.evaluate(theta - delta, fitted_c=True)[0]
        ) / 2e-4
        np.testing.assert_allclose(gradient[index], numeric, atol=2e-7)
    shifted = replace(
        observations, measured_hz=observations.measured_hz + np.repeat([4e5, -6e5], 7)
    )
    alternate = subject.DopplerShapeOrbitObjective(shifted, bank, prior, sequences, sigma_hz=1.0)
    np.testing.assert_allclose(alternate.evaluate(theta, fitted_c=True)[0], value, atol=1e-8)
    np.testing.assert_allclose(value, objective.evaluate(theta[:3])[0], atol=1e-8)
    assert objective.c_shape_norm < 1e-12


def test_controlled_c_arms_and_frozen_held_bank_score(monkeypatch):
    monkeypatch.setattr(subject, "predict_orbits", predictor)
    observations, bank, prior = inputs()
    sequences = (tuple(range(7)), tuple(range(7, 14)))
    objective = subject.DopplerShapeOrbitObjective(
        observations, bank, prior, sequences, sigma_hz=1.0
    )
    starts = [[0.0, 0.0], [5.0, 5.0], [-5.0, -5.0]]
    zero = subject.fit_doppler_shape(objective, starts, rf_arm="zero-c")
    fitted = subject.fit_doppler_shape(objective, starts, rf_arm="fitted-c")
    assert zero["winner"] is not None and fitted["winner"] is not None
    np.testing.assert_allclose(zero["winner"]["theta"][:2], [2.0, -3.0], atol=1e-4)
    np.testing.assert_allclose(zero["winner"]["theta"], fitted["winner"]["theta"][:3], atol=1e-4)
    assert fitted["winner"]["information"]["additional_nuisance_rank"] == 1
    before = tuple(zero["winner"]["theta"])
    shifted = replace(observations, measured_hz=observations.measured_hz + 500.0)
    held = subject.DopplerShapeOrbitObjective(shifted, bank, prior, sequences, sigma_hz=1.0)
    score = subject.held_shape_score(objective, before, held)
    assert score["shape_dof"] == 12
    assert score["failure"] is None
    assert tuple(zero["winner"]["theta"]) == before


def test_zero_gradient_at_invisible_bank_is_an_explicit_failure(monkeypatch):
    def invisible(*args, **kwargs):
        pred, visible, spatial, timing = predictor(*args, **kwargs)
        return pred, np.zeros_like(visible), spatial, timing

    monkeypatch.setattr(subject, "predict_orbits", invisible)
    observations, bank, prior = inputs()
    objective = subject.DopplerShapeOrbitObjective(
        observations, bank, prior, (tuple(range(7)), tuple(range(7, 14)))
    )
    result = subject.fit_doppler_shape(objective, [[0.0, 0.0]])
    assert result["winner"] is None
    assert not result["attempts"][0]["stationary"]
