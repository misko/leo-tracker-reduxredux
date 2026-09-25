from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "evaluate_frozen_lane_satellite_models.py"
    spec = importlib.util.spec_from_file_location("frozen_lane_satellite_models_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _synthetic_lane(tool: ModuleType, *, acceleration_hz_s2: float = 0.0) -> tuple[object, ...]:
    times = np.arange(0.0, 8.01, 0.1, dtype=np.float64)
    train = np.zeros(times.size, dtype=np.bool_)
    train[:49] = True
    lane = tool.Lane(
        lane_id="lane-a",
        source_branch_id="branch-a",
        support_piece_index=0,
        start_s=float(times[0]),
        end_s=float(times[-1]),
        times_s=times,
        cfo_hz=np.zeros_like(times),
        observation_ids=tuple(f"observation-{index}" for index in range(times.size)),
        sample_starts=tuple(index * 1_000 for index in range(times.size)),
        source_observation_ids_by_observation=tuple(
            (f"source-{index}",) for index in range(times.size)
        ),
        train_mask=train,
        distinct_epoch_count=int(times.size),
        occupancy_fraction=1.0,
        maximum_gap_s=0.1,
    )
    bank_times = np.arange(-1.0, 9.01, 0.01, dtype=np.float64)
    doppler = 80_000.0 * np.sin(0.31 * bank_times) + 1_500.0 * bank_times
    reference = float(np.mean(times[train]))
    values = (
        np.interp(times + 0.2, bank_times, doppler)
        + 4_200.0
        + 0.5 * acceleration_hz_s2 * (times - reference) ** 2
    )
    lane = tool.Lane(
        lane_id=lane.lane_id,
        source_branch_id=lane.source_branch_id,
        support_piece_index=lane.support_piece_index,
        start_s=lane.start_s,
        end_s=lane.end_s,
        times_s=lane.times_s,
        cfo_hz=values,
        observation_ids=lane.observation_ids,
        sample_starts=lane.sample_starts,
        source_observation_ids_by_observation=(lane.source_observation_ids_by_observation),
        train_mask=lane.train_mask,
        distinct_epoch_count=lane.distinct_epoch_count,
        occupancy_fraction=lane.occupancy_fraction,
        maximum_gap_s=lane.maximum_gap_s,
    )
    elevation = np.full(bank_times.size, 30.0, dtype=np.float64)
    return lane, bank_times, doppler, elevation


def test_cfo_tau_profile_recovers_delay_without_using_holdout() -> None:
    tool = _tool()
    lane, bank_times, doppler, elevation = _synthetic_lane(tool)

    fit = tool.fit_cfo_profile(
        lane,
        bank_times,
        doppler,
        elevation,
        np.arange(-0.3, 0.301, 0.05),
        horizon_deg=0.0,
        cfo_scale_hz=100.0,
        acceleration_bound_hz_s2=None,
    )

    assert fit is not None
    assert fit["tau_s"] == pytest.approx(0.2)
    assert fit["composite_frequency_offset_hz"] == pytest.approx(4_200.0, abs=0.1)
    assert fit["offset_reference_time_s"] == pytest.approx(np.mean(lane.times_s[lane.train_mask]))
    assert fit["holdout_rmse_hz"] < 0.1


def test_quadratic_profile_reports_residual_curvature_as_a_bounded_sensitivity() -> None:
    tool = _tool()
    lane, bank_times, doppler, elevation = _synthetic_lane(tool, acceleration_hz_s2=60.0)

    fit = tool.fit_cfo_profile(
        lane,
        bank_times,
        doppler,
        elevation,
        np.arange(-0.3, 0.301, 0.05),
        horizon_deg=0.0,
        cfo_scale_hz=100.0,
        acceleration_bound_hz_s2=200.0,
    )

    assert fit is not None
    assert fit["tau_s"] == pytest.approx(0.2)
    assert fit["residual_acceleration_hz_s2"] == pytest.approx(60.0, abs=0.1)
    assert fit["acceleration_at_bound"] is False


def test_greedy_facility_sweep_selects_on_train_and_freezes_holdout_assignment() -> None:
    tool = _tool()
    train = np.asarray([[1.0, 9.0, 8.0], [2.0, 8.0, 9.0], [9.0, 1.0, 8.0]])
    # Satellite 30 would win if holdout leaked into selection.
    holdout = np.asarray([[9.0, 8.0, 0.1], [9.0, 8.0, 0.1], [8.0, 9.0, 0.1]])
    parameters = [
        [{"tag": f"{lane}-{satellite}"} for satellite in (10, 20, 30)] for lane in range(3)
    ]

    rows = tool.greedy_facility_sweep(
        ["a", "b", "c"],
        [10, 20, 30],
        train,
        holdout,
        parameters,
        maximum_k=3,
        unassigned_cost=25.0,
    )

    assert [row["k"] for row in rows] == [0, 1, 2, 3]
    assert rows[1]["selected_satellite_numbers"] == [10]
    assert rows[2]["selected_satellite_numbers"] == [10, 20]
    assert rows[2]["active_satellite_numbers"] == [10, 20]
    assert rows[2]["assignments"][0]["satellite_number"] == 10
    assert rows[2]["assignments"][2]["satellite_number"] == 20
    assert rows[2]["holdout_total_standardized_mse"] == pytest.approx(27.0)


def test_shared_tau_sweep_uses_one_delay_state_per_physical_satellite() -> None:
    tool = _tool()
    states = [
        {"satellite_number": 10, "tau_s": -0.1},
        {"satellite_number": 10, "tau_s": 0.1},
        {"satellite_number": 20, "tau_s": 0.0},
    ]
    train = np.asarray([[1.0, 4.0, 20.0], [2.0, 5.0, 20.0], [3.0, 6.0, 1.0]])
    holdout = train.copy()
    parameters = [
        [
            {
                "tau_s": state["tau_s"],
                "composite_frequency_offset_hz": float(lane * 100 + state_index),
            }
            for state_index, state in enumerate(states)
        ]
        for lane in range(3)
    ]

    rows = tool.greedy_shared_tau_facility_sweep(
        ["a", "b", "c"],
        states,
        train,
        holdout,
        parameters,
        maximum_k=2,
        unassigned_cost=25.0,
        lane_intervals_s=[(0.0, 0.5), (1.0, 1.5), (2.0, 2.5)],
        error_scale=100.0,
        error_unit="Hz",
    )

    assert rows[1]["selected_satellite_states"] == [{"satellite_number": 10, "tau_s": -0.1}]
    assert rows[2]["selected_satellite_numbers"] == [10, 20]
    assert len(set(rows[2]["selected_satellite_numbers"])) == 2
    satellite_10_tau = {
        item["shared_satellite_tau_s"]
        for item in rows[2]["assignments"]
        if item["satellite_number"] == 10
    }
    assert satellite_10_tau == {-0.1}
    diagnostic = rows[2]["selected_satellite_diagnostics"][0]
    assert diagnostic["tau_at_bound"] is True
    assert diagnostic["aggregate_train_tau_profile_near_width_s"] == 0.0
    assert rows[2]["train_equal_lane_rms_hz"] == pytest.approx(100.0 * np.sqrt(4.0 / 3.0))


def test_overlap_exclusion_prevents_one_satellite_from_owning_competing_lanes() -> None:
    tool = _tool()
    states = [{"satellite_number": 10, "tau_s": 0.0}]
    costs = np.asarray([[1.0], [2.0], [3.0]])
    parameters = [[{"tau_s": 0.0}] for _ in range(3)]

    row = tool.greedy_shared_tau_facility_sweep(
        ["a", "b", "c"],
        states,
        costs,
        costs,
        parameters,
        maximum_k=1,
        unassigned_cost=25.0,
        lane_intervals_s=[(0.0, 2.0), (1.0, 3.0), (3.1, 4.0)],
    )[1]

    assert [item["satellite_number"] for item in row["assignments"]] == [10, None, 10]
    assert row["overlap_violation_count"] == 0


def test_source_identity_conflict_is_independent_of_norad_but_probe_epoch_is_allowed() -> None:
    tool = _tool()
    states = [
        {"satellite_number": 10, "tau_s": 0.0},
        {"satellite_number": 20, "tau_s": 0.0},
    ]
    costs = np.asarray([[1.0, 20.0], [20.0, 1.0], [1.0, 20.0]])
    parameters = [[{"tau_s": 0.0}, {"tau_s": 0.0}] for _ in range(3)]

    row = tool.greedy_shared_tau_facility_sweep(
        ["a", "b", "c"],
        states,
        costs,
        costs,
        parameters,
        maximum_k=2,
        unassigned_cost=25.0,
        lane_intervals_s=[(0.0, 0.5), (1.0, 1.5), (2.0, 2.5)],
        lane_observation_ids=[("oa",), ("ob",), ("oc",)],
        lane_source_observation_ids=[("shared",), ("shared",), ("distinct",)],
        lane_sample_starts=[(100,), (200,), (100,)],
    )[2]

    assert [item["satellite_number"] for item in row["assignments"]] == [10, None, 10]
    assert row["source_observation_conflict_violation_count"] == 0
    assert row["duplicate_assigned_source_observation_id_count"] == 0
    assert row["shared_assigned_sample_starts"] == [100]


def test_global_split_closes_holdout_over_source_and_sample_groups() -> None:
    tool = _tool()

    def lane(label: str, source_groups: list[tuple[str, ...]], starts: list[int]) -> object:
        times = np.arange(10, dtype=np.float64) * 0.025
        train = np.asarray([True] * 6 + [False] * 4)
        return tool.Lane(
            lane_id=label,
            source_branch_id=label,
            support_piece_index=0,
            start_s=float(times[0]),
            end_s=float(times[-1]),
            times_s=times,
            cfo_hz=np.arange(10, dtype=np.float64),
            observation_ids=tuple(f"{label}-o-{index}" for index in range(10)),
            sample_starts=tuple(starts),
            source_observation_ids_by_observation=tuple(source_groups),
            train_mask=train,
            distinct_epoch_count=10,
            occupancy_fraction=1.0,
            maximum_gap_s=0.025,
        )

    first_sources = [(f"a-{index}",) for index in range(10)]
    second_sources = [(f"b-{index}",) for index in range(10)]
    first_sources[1] = ("cross-source",)
    second_sources[8] = ("cross-source",)
    first_starts = list(range(10))
    second_starts = list(range(100, 110))
    first_starts[2] = 777
    second_starts[7] = 777

    lanes, audit, rejected = tool._group_disjoint_train_holdout(
        [lane("a", first_sources, first_starts), lane("b", second_sources, second_starts)]
    )

    assert rejected == set()
    first = next(item for item in lanes if item.lane_id == "a")
    assert first.train_mask[1] == np.bool_(False)
    assert first.train_mask[2] == np.bool_(False)
    assert audit["cross_split_sample_start_overlap_count"] == 0
    assert audit["cross_split_source_observation_id_overlap_count"] == 0


def test_activation_penalty_selects_k_from_training_objective_only() -> None:
    tool = _tool()
    rows = [
        {
            "k": 0,
            "train_total_standardized_mse": 30.0,
            "holdout_total_standardized_mse": 1.0,
            "train_equal_lane_normalized_rms": 3.0,
            "holdout_equal_lane_normalized_rms": 1.0,
            "selected_satellite_numbers": [],
            "active_satellite_numbers": [],
        },
        {
            "k": 1,
            "train_total_standardized_mse": 10.0,
            "holdout_total_standardized_mse": 1_000.0,
            "train_equal_lane_normalized_rms": 2.0,
            "holdout_equal_lane_normalized_rms": 20.0,
            "selected_satellite_numbers": [10],
            "active_satellite_numbers": [10],
        },
        {
            "k": 2,
            "train_total_standardized_mse": 8.0,
            "holdout_total_standardized_mse": 0.1,
            "train_equal_lane_normalized_rms": 1.0,
            "holdout_equal_lane_normalized_rms": 0.1,
            "selected_satellite_numbers": [10, 20],
            "active_satellite_numbers": [10, 20],
        },
    ]

    result = tool.activation_penalty_sweep(rows, [0.0, 3.0, 25.0])

    assert [item["selected_k"] for item in result] == [2, 1, 0]


def test_holdout_acceptance_rejects_orbit_sets_that_lose_to_radio_nulls() -> None:
    tool = _tool()
    models = {}
    for model_name, suffix, value in (
        ("rate_only", "hz_s", 230.0),
        ("cfo_tau", "hz", 402.0),
        ("cfo_tau_quadratic", "hz", 310.0),
    ):
        models[model_name] = {
            "facility_sweep": [
                {"k": 0, f"holdout_equal_lane_rms_{suffix}": 500.0},
                {"k": 1, f"holdout_equal_lane_rms_{suffix}": value - 10.0},
                {"k": 8, f"holdout_equal_lane_rms_{suffix}": value},
            ],
            "activation_penalty_sweep": [
                {
                    "activation_penalty": 0.0,
                    "selected_k": 8,
                    f"holdout_equal_lane_rms_{suffix}": value,
                }
            ],
        }
    nulls = {
        "constant_train_rate": {"holdout_equal_lane_rms_hz_s": 168.0},
        "affine": {"holdout_equal_lane_rms_hz": 163.0},
        "quadratic": {"holdout_equal_lane_rms_hz": 150.0},
    }

    result = tool.holdout_acceptance_against_radio_nulls(models, nulls)

    assert result["all_evaluated_training_greedy_k_states_rejected"] is True
    assert all(
        item["every_evaluated_k_fails_simpler_holdout_null"] for item in result["comparisons"]
    )

    models["rate_only"]["facility_sweep"][1]["holdout_equal_lane_rms_hz_s"] = 100.0
    passing = tool.holdout_acceptance_against_radio_nulls(models, nulls)

    assert passing["all_evaluated_training_greedy_k_states_rejected"] is False
    assert passing["conclusion"].startswith("at least one")


def test_lane_loader_enforces_duration_and_chronological_split(tmp_path: Path) -> None:
    tool = _tool()
    times = np.arange(0.0, 1.201, 0.025)
    observations = [
        {
            "observation_id": f"obs-{index}",
            "time_s": time_s,
            "component_cfo_hz": 100.0 + index,
            "sample_start": index * 62_500,
            "source_observation_ids": [f"source-{index}"],
        }
        for index, time_s in enumerate(times)
    ]
    artifact = {
        "status": "complete",
        "observations": observations,
        "branches": [
            {
                "branch_id": "long",
                "observation_ids": [item["observation_id"] for item in observations],
            },
            {
                "branch_id": "short",
                "observation_ids": [item["observation_id"] for item in observations[:3]],
            },
        ],
    }
    path = tmp_path / "lanes.json"
    path.write_text(json.dumps(artifact))

    lanes = tool.load_lanes(path, minimum_span_s=1.0, train_fraction=0.6)

    assert [lane.source_branch_id for lane in lanes] == ["long"]
    assert lanes[0].distinct_epoch_count == 49
    assert lanes[0].occupancy_fraction == pytest.approx(1.0)
    assert int(np.count_nonzero(lanes[0].train_mask)) == 30
    assert int(np.count_nonzero(~lanes[0].train_mask)) == 19
