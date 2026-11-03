"""Synthetic numerical checks for the covariance/epoch confirmation."""
import numpy as np
import pytest

import core


def synthetic_likelihood(likelihood_type):
    start = 1_790_000_000_000_000_000
    offsets = np.array([0.0, 0.7, 1.8, 3.0, 4.2, 5.0])
    track = {
        "track_id": "track-a", "receiver_id": 0, "channel": 1,
        "rf_hz": 11_200_000_000.0,
        "times_utc_ns": (start + np.rint(offsets * 1e9).astype(np.int64)).tolist(),
        "measured_hz": [1200.0, 1090.0, 910.0, 700.0, 510.0, 390.0],
        "physical_observation_ids": [f"o-{index}" for index in range(offsets.size)],
        "support_start_utc_ns": start,
        "support_end_utc_ns": start + 5_000_000_000,
    }
    times = np.arange(-10.0, 25.0, 5.0)
    receiver = core.old.enu_state_ecef_km(
        0.0, 0.0, 0.0, core.old.CENTER_LAT, core.old.CENTER_LON
    )
    radial = receiver / np.linalg.norm(receiver)
    tangent = np.cross(radial, np.array([0.0, 0.0, 1.0]))
    tangent /= np.linalg.norm(tangent)
    positions, velocities = [], []
    for satellite, altitude in enumerate((550.0, 620.0)):
        base = radial * (np.linalg.norm(receiver) + altitude) + satellite * 30.0 * tangent
        velocity = (7.2 - 0.3 * satellite) * tangent
        acceleration = -(0.012 + 0.003 * satellite) * radial + 0.002 * tangent
        positions.append(np.stack([
            base + velocity * value + 0.5 * acceleration * value**2 for value in times
        ]))
        velocities.append(np.stack([velocity + acceleration * value for value in times]))
    bank = core.old.OrbitBank(
        (10001, 10002), times, np.stack(positions), np.stack(velocities)
    )
    likelihood = likelihood_type(
        {"tracks": [track]}, {"start_utc_ns": start}, bank, [track],
        {"track-a": np.ones(offsets.size, dtype=bool)},
    )
    prediction, _ = likelihood._pred(likelihood.rows[0], 0.0, 0.0, 0.0)
    likelihood.rows[0]["y"] = prediction[0] + np.array([8.0, -5.0, 3.0, -7.0, 4.0, -3.0])
    return likelihood


@pytest.mark.parametrize("arm", ["C1", "M2", "M4"])
def test_frozen_controls_are_pointwise_identical_on_actual_physics(arm):
    old_likelihood = synthetic_likelihood(core.old.DirectLikelihood)
    new_likelihood = synthetic_likelihood(core.DirectLikelihood)
    theta = np.array([12.0, -8.0, 0.2])
    old_problem = old_likelihood.association_problem(theta, arm)
    new_problem = new_likelihood.association_problem(theta, arm)
    assert np.array_equal(new_problem.signal_log_likelihood, old_problem.signal_log_likelihood)
    assert np.array_equal(new_problem.background_log_likelihood, old_problem.background_log_likelihood)
    assert new_likelihood.score_position(theta, arm)["negative_log_posterior"] == pytest.approx(
        old_likelihood.score_position(theta, arm)["negative_log_posterior"], abs=0.0
    )


def test_actual_single_zero_epoch_m24_collapses_to_normalized_m2():
    likelihood = synthetic_likelihood(core.DirectLikelihood)
    likelihood.epoch_nodes_s = (0.0,)
    theta = np.array([7.0, 4.0, -0.1])
    combined = likelihood.association_problem(theta, "M24")
    covariance = likelihood.association_problem(theta, "M2")
    assert np.array_equal(combined.signal_log_likelihood, covariance.signal_log_likelihood)
    assert np.array_equal(combined.background_log_likelihood, covariance.background_log_likelihood)
    assert likelihood.score_position(theta, "M24")["negative_log_posterior"] == pytest.approx(
        likelihood.score_position(theta, "M2")["negative_log_posterior"], abs=0.0
    )


def test_actual_covariance_and_epoch_quadrature_change_objective():
    likelihood = synthetic_likelihood(core.DirectLikelihood)
    theta = np.array([18.0, -11.0, 0.3])
    c1 = likelihood.score_position(theta, "C1")["negative_log_posterior"]
    m2 = likelihood.score_position(theta, "M2")["negative_log_posterior"]
    likelihood.epoch_nodes_s = (0.0,)
    zero_epoch = likelihood.score_position(theta, "M24")["negative_log_posterior"]
    likelihood.epoch_nodes_s = (-0.5, 0.0, 0.5)
    three_epoch = likelihood.score_position(theta, "M24")["negative_log_posterior"]
    assert m2 != pytest.approx(c1)
    assert three_epoch != pytest.approx(zero_epoch)


def test_m24_rejects_epoch_dependent_background(monkeypatch):
    original = core.old.DirectLikelihood.association_problem
    calls = 0

    def changed_background(self, theta, arm):
        nonlocal calls
        value = original(self, theta, arm)
        calls += 1
        return core.old.AssociationProblem(
            value.signal_log_likelihood,
            value.background_log_likelihood + calls,
            value.candidate_labels,
        )

    monkeypatch.setattr(core.old.DirectLikelihood, "association_problem", changed_background)
    likelihood = synthetic_likelihood(core.DirectLikelihood)
    with pytest.raises(RuntimeError, match="background changed"):
        likelihood.association_problem(np.zeros(3), "M24")


def test_confirmation_contract_declares_four_arms():
    assert set(core.load_methods()) == {"C1", "M2", "M4", "M24"}
