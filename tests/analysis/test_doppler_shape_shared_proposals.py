import json
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.channel_group_calibration import GroupCalibrationObjective
from leo.analysis.hard60_joint_clock import JointClockObjective
from leo.analysis.hard60_score import Hard60Objective
from leo.analysis.research.doppler_shape_shared_proposals import (
    PROPOSAL_IDS,
    decode_physical_correction,
    encode_initial_physical_seed,
    evaluate_physical_correction,
    ordered_seed_entries,
    project_shared_seed,
)
from leo.contracts.regional_position import POSITION_SCORES, PositionObservations


def model(observations=None, *, numbers=(10, 20, 30), baseline=None):
    if observations is None:
        count = 64
        channel = 1 + (np.arange(count) // 2) % 8
        observations = PositionObservations(
            tuple(f"w{i}" for i in range(count)),
            np.linspace(0.0, 150.0, count),
            np.zeros(count),
            10.5e9 + channel * 250e6,
            np.arange(count) % 2,
            channel,
            np.ones(count),
        )
    bank = SimpleNamespace(numbers=np.asarray(numbers), nodes_s=np.arange(-40.0, 201.0, 10.0))
    base = Hard60Objective(
        observations,
        bank,
        SimpleNamespace(radius_km=250.0),
        POSITION_SCORES["V16"],
        receiver_baseline_hz=baseline,
    )
    base = JointClockObjective(base, np.linspace(-1.0, 151.0, 7), np.zeros((2, 7)))
    return GroupCalibrationObjective(
        base, observations.channel >= 5, group_drift_sigma_hz_s=2.0, group_clock=True
    )


def entry(source):
    vector = np.zeros(source.size)
    vector[:2] = [20.0, -30.0]
    vector[2:7] = [120.0, 0.2, -50.0, -0.3, 80.0]
    vector[7:] = [0.2, 0.03, -0.04]
    nuisance = np.linspace(-10.0, 10.0, len(source.initial_nuisance))
    physical = encode_initial_physical_seed(source, vector, nuisance)
    return (
        {"proposal_id": "cold-0", "id": "cold-0", "point_km": vector[:2].tolist(), **physical},
        vector,
        nuisance,
    )


def test_initial_physical_function_serializes_without_claiming_a_stationary_fit():
    source = model()
    value, vector, nuisance = entry(source)
    value = json.loads(json.dumps(value))
    assert value["physical_correction_kind"] == "training-derived-initialization-function"
    assert "converged" not in value and "stationary" not in value
    assert value["source_closure_max_abs_hz"] < 1e-6
    np.testing.assert_allclose(
        evaluate_physical_correction(value, source.observations),
        source.correction(vector, nuisance),
        atol=1e-6,
    )
    state = decode_physical_correction(value)
    assert state.time_center_s == source.observations.time_center_s


def test_json_round_trip_preserves_common_clock_with_empty_half_view_group_matrix():
    all_observations = model().observations
    rows = np.flatnonzero(all_observations.channel <= 4)
    low = PositionObservations(
        tuple(all_observations.window_ids[i] for i in rows),
        all_observations.times_s[rows],
        all_observations.measured_hz[rows],
        all_observations.rf_hz[rows],
        all_observations.receiver[rows],
        all_observations.channel[rows],
        all_observations.margin[rows],
    )
    source = model(low)
    value, vector, nuisance = entry(source)
    value = json.loads(json.dumps(value))
    assert value["physical_correction"]["group_clock_knots_hz"] == []
    state = decode_physical_correction(value)
    assert state.group_clock_knots_hz.shape == (0, 7)
    np.testing.assert_allclose(
        evaluate_physical_correction(value, low), source.correction(vector, nuisance), atol=1e-6
    )


def test_physical_transfer_changes_centres_group_frame_baseline_and_satellite_order():
    source = model()
    value, _, _ = entry(source)
    observations = source.observations
    rows = np.arange(11, 59)
    target_obs = PositionObservations(
        tuple(observations.window_ids[i] for i in rows),
        observations.times_s[rows],
        observations.measured_hz[rows],
        observations.rf_hz[rows],
        observations.receiver[rows],
        observations.channel[rows],
        observations.margin[rows],
    )
    baseline = 200.0 + 0.4 * target_obs.times_s + 50.0 * target_obs.receiver
    target = model(target_obs, numbers=(30, 10, 20), baseline=baseline)
    projected = project_shared_seed(value, target)
    expected = evaluate_physical_correction(value, target_obs)
    np.testing.assert_allclose(
        target.correction(projected["vector"], projected["nuisance"]), expected, atol=1e-6
    )
    timings = projected["vector"][7] + target.basis @ projected["vector"][8:]
    by_number = dict(
        zip(
            value["orbit_timing"]["satellite_numbers"],
            value["orbit_timing"]["shifts_s"],
            strict=True,
        )
    )
    np.testing.assert_allclose(timings, [by_number[30], by_number[10], by_number[20]])
    json.dumps(projected["projection"])
    assert projected["projection"]["maximum_abs_hz"] < 1e-6


def test_target_bank_changes_are_rejected_instead_of_dropping_missing_timing():
    source = model()
    value, _, _ = entry(source)
    with pytest.raises(ValueError, match="candidate bank differ"):
        project_shared_seed(value, model(numbers=(10, 20, 31)))


def test_source_function_uses_original_rf_time_and_group_centres():
    source = model()
    value, _, _ = entry(source)
    obs = source.observations
    changed = replace(obs, measured_hz=obs.measured_hz + 1e6)
    np.testing.assert_array_equal(
        evaluate_physical_correction(value, changed), evaluate_physical_correction(value, obs)
    )


def test_six_sources_keep_order_and_coincident_geographic_proposals():
    states = [{"vector": [1.0, 2.0, 0.0], "nuisance": []} for _ in range(3)]
    proposals = [{"proposal_id": name, "point_km": [1.0, 2.0]} for name in PROPOSAL_IDS]
    result = ordered_seed_entries(states, states, proposals)
    assert tuple(row["proposal_id"] for row in result) == PROPOSAL_IDS
    assert len(result) == 6
    with pytest.raises(ValueError, match="ordering"):
        ordered_seed_entries(states, states, proposals[::-1])
