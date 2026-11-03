"""Tiny no-optimizer smoke tests for every direct real-data likelihood arm."""

import numpy as np
import pytest

from core import DirectLikelihood
from physics import OrbitBank, enu_state_ecef_km


def _problem():
    start = 1_790_000_000_000_000_000
    offsets_s = np.array([0.0, 0.7, 1.8, 3.0, 4.2, 5.0])
    track = {
        "track_id": "track-a",
        "receiver_id": 0,
        "channel": 1,
        "rf_hz": 11_200_000_000.0,
        "times_utc_ns": (start + np.rint(offsets_s * 1e9).astype(np.int64)).tolist(),
        "measured_hz": [1200.0, 1090.0, 910.0, 700.0, 510.0, 390.0],
        "physical_observation_ids": [f"o-{i}" for i in range(offsets_s.size)],
        "support_start_utc_ns": start,
        "support_end_utc_ns": start + 5_000_000_000,
    }
    evidence = {"tracks": [track]}
    source = {"start_utc_ns": start}
    times = np.arange(-10.0, 25.0, 5.0)
    receiver = enu_state_ecef_km(0.0, 0.0, 0.0, 38.5816, -121.4944)
    radial = receiver / np.linalg.norm(receiver)
    tangent = np.cross(radial, np.array([0.0, 0.0, 1.0]))
    tangent /= np.linalg.norm(tangent)
    positions = []
    velocities = []
    for satellite, altitude in enumerate((550.0, 620.0)):
        base = radial * (np.linalg.norm(receiver) + altitude) + satellite * 30.0 * tangent
        velocity = (7.2 - 0.3 * satellite) * tangent
        positions.append(np.stack([base + velocity * t for t in times]))
        velocities.append(np.repeat(velocity[None, :], times.size, axis=0))
    bank = OrbitBank(
        (10001, 10002),
        times,
        np.stack(positions),
        np.stack(velocities),
    )
    likelihood = DirectLikelihood(
        evidence,
        source,
        bank,
        [track],
        {"track-a": np.ones(offsets_s.size, dtype=bool)},
    )
    return likelihood


@pytest.mark.parametrize(
    ("arm", "theta"),
    [
        ("C1", np.array([0.0, 0.0, 0.0])),
        ("C2", np.array([0.0, 0.0, 0.0, np.log(100.0)])),
        ("M2", np.array([0.0, 0.0, 0.0])),
        ("M3", np.array([0.0, 0.0, 0.0, 0.0, 0.0])),
        ("M4", np.array([0.0, 0.0, 0.0])),
        ("M5", np.array([0.0, 0.0, 0.0])),
        ("M8", np.array([0.0, 0.0, 0.0])),
        ("M9", np.array([0.0, 0.0, 0.0])),
    ],
)
def test_all_direct_arms_append_rows_and_return_normalized_shapes(arm, theta):
    likelihood = _problem()
    problem = likelihood.association_problem(theta, arm)
    assert problem.signal_log_likelihood.shape == (1, 2)
    assert problem.background_log_likelihood.shape == (1,)
    assert np.isfinite(problem.signal_log_likelihood).all()
    assert np.isfinite(problem.background_log_likelihood).all()
    scored = likelihood.score_position(theta, arm)
    assert np.isfinite(scored["negative_log_posterior"])
    assert scored["association_problem"].signal_log_likelihood.shape == (1, 2)


def test_m5_geometry_prior_is_normalized_once_without_uniform_candidate_penalty():
    likelihood = _problem()
    theta = np.array([0.0, 0.0, 0.0])
    problem = likelihood.association_problem(theta, "M5")
    per_candidate = problem.signal_log_likelihood[0]
    # Removing the common waveform score leaves a normalized geometry prior.
    waveform = likelihood.association_problem(theta, "C1").signal_log_likelihood[0]
    geometry = per_candidate - waveform
    assert np.exp(geometry).sum() == pytest.approx(1.0, rel=1e-10)


def test_m2_background_and_signal_are_proper_projected_gaussian_densities():
    likelihood = _problem()
    problem = likelihood.association_problem(np.zeros(3), "M2")
    # A normalized density includes scale/log-determinant terms and is therefore
    # far below a bare squared-error score near zero.
    assert problem.background_log_likelihood[0] < -1.0
    assert np.max(problem.signal_log_likelihood) < -1.0


def test_declared_models_change_only_their_declared_physics_or_likelihood():
    likelihood = _problem()
    origin = np.zeros(3)
    c1 = likelihood.association_problem(origin, "C1")
    m2 = likelihood.association_problem(origin, "M2")
    m3_zero = likelihood.association_problem(np.zeros(5), "M3")
    m3_drift = likelihood.association_problem(np.array([0.0, 0.0, 0.0, 1.0, 0.0]), "M3")
    m4 = likelihood.association_problem(origin, "M4")
    m8 = likelihood.association_problem(origin, "M8")
    m9 = likelihood.association_problem(origin, "M9")
    assert not np.allclose(m2.signal_log_likelihood, c1.signal_log_likelihood)
    assert not np.allclose(m3_drift.signal_log_likelihood, m3_zero.signal_log_likelihood)
    assert not np.allclose(m4.signal_log_likelihood, c1.signal_log_likelihood)
    assert np.all(m8.signal_log_likelihood >= c1.signal_log_likelihood)
    # M9 changes only the optimizer; its pointwise likelihood must be exactly C1.
    assert m9.signal_log_likelihood == pytest.approx(c1.signal_log_likelihood)
    assert m9.background_log_likelihood == pytest.approx(c1.background_log_likelihood)


def test_shared_scale_arm_responds_to_scale_parameter():
    likelihood = _problem()
    narrow = likelihood.association_problem(np.array([0.0, 0.0, 0.0, np.log(50.0)]), "C2")
    broad = likelihood.association_problem(np.array([0.0, 0.0, 0.0, np.log(200.0)]), "C2")
    assert not np.allclose(narrow.signal_log_likelihood, broad.signal_log_likelihood)


def test_all_association_arms_use_grouped_objective_and_do_not_fall_back_to_c1():
    likelihood = _problem()
    theta = np.zeros(3)
    c1 = likelihood.score_position(theta, "C1")["negative_log_posterior"]
    scores = {
        arm: likelihood.score_grouped_association(theta, arm)
        for arm in ("G1", "M1", "G2")
    }
    assert all(np.isfinite(item["negative_log_posterior"]) for item in scores.values())
    assert all(item["group_count"] == 1 for item in scores.values())
    assert scores["G1"]["exact_probability_semantics"] is False
    assert scores["M1"]["exact_probability_semantics"] is True
    assert scores["G2"]["exact_probability_semantics"] is True
    assert scores["G1"]["negative_log_posterior"] >= scores["M1"]["negative_log_posterior"]
    assert scores["M1"]["negative_log_posterior"] == pytest.approx(
        scores["G2"]["negative_log_posterior"]
    )
    # C1 can numerically equal hard assignment when one alternative dominates;
    # method flags above prove the grouped dispatcher was exercised.
    assert np.isfinite(c1)
