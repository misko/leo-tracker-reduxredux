from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

VALLADO_00005 = (
    "1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753\n"
    "2 00005  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667\n"
)


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools/replay_joint_fixed_satellite_activity.py"
    spec = importlib.util.spec_from_file_location(
        "replay_joint_fixed_satellite_activity_tool", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _checksum(line: str) -> str:
    value = (
        sum(
            int(character) if character.isdigit() else 1 if character == "-" else 0
            for character in line[:68]
        )
        % 10
    )
    return line[:68] + str(value)


def _renumber_pair(pair: str, catalog_number: int) -> str:
    result = []
    for line in pair.splitlines():
        changed = line[:2] + f"{catalog_number:05d}" + line[7:68] + "0"
        result.append(_checksum(changed))
    return "\n".join(result) + "\n"


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def _observation(
    *,
    branch_id: str,
    component_id: str,
    cell_index: int,
    label: str,
    cfo_hz: float,
) -> dict[str, Any]:
    sample_start = cell_index * 100 + 25
    source_id = f"source-{label}-{cell_index}"
    return {
        "branch_id": branch_id,
        "component_id": component_id,
        "probe_id": f"probe-{cell_index}",
        "probe_sample_start": sample_start,
        "measurement_sample": sample_start + 10,
        "measurement_time_s": (sample_start + 10) / 1_000,
        "source_observation_id": source_id,
        "candidate_rank": 0,
        "local_epoch_sample": 10,
        "source_tracking_cfo_hz": cfo_hz,
        "component_cfo_hz": cfo_hz,
    }


def _fixture(
    tmp_path: Path,
    tool: ModuleType,
) -> tuple[dict[str, Any], Path, Path, str]:
    component_id = "component:resolved"
    first_branch_id = "branch:first"
    second_branch_id = "branch:second"
    scheduled = []
    for cell_index in range(10):
        sample_start = cell_index * 100 + 25
        scheduled.append(
            {
                "probe_id": f"probe-{cell_index}",
                "schedule_ordinal": cell_index,
                "probe_sample_start": sample_start,
                "probe_sample_count": 20,
                "probe_start_time_s": sample_start / 1_000,
                "scan_detection_present": True,
                "scan_status": "complete",
                "usable_for_activity": True,
                "source_candidate_count": 2,
                "retained_candidate_count": 2,
                "truncated_candidate_count": 0,
            }
        )

    first_observations = [
        _observation(
            branch_id=first_branch_id,
            component_id=component_id,
            cell_index=cell_index,
            label="a",
            cfo_hz=100.0,
        )
        for cell_index in range(1, 6)
    ]
    duplicate = dict(first_observations[2])
    duplicate["branch_id"] = second_branch_id
    second_observations = [duplicate]
    second_observations.extend(
        _observation(
            branch_id=second_branch_id,
            component_id=component_id,
            cell_index=cell_index,
            label="b",
            cfo_hz=1_200.0,
        )
        for cell_index in range(4, 9)
    )
    dataset: dict[str, Any] = {
        "schema": tool.INPUT_SCHEMA,
        "candidate_only": True,
        "satellite_specificity_claimed": False,
        "capture": {
            "session_id": "cap-test",
            "stream_id": "stream-0",
            "radio_id": "radio-test",
            "radio_serial": "serial-test",
            "receiver_id": 0,
            "recording_manifest_digest": "sha256:manifest",
            "sample_rate_hz": 1_000,
            "declared_sample_count": 1_000,
            "observed_sample_count": 1_000,
            "coverage_fraction": 1.0,
        },
        "frequency_binding": {"sky_frequency_hz": 11_000_000_000},
        "timing_binding": {"first_estimate_utc_ns": 962_131_819_733_568_000},
        "frame_evidence_inventory": {
            "alias_expanded_truncated_track_count": 0,
            "evidence_complete": True,
        },
        "scheduled_probes": scheduled,
        "alias_components": [
            {
                "component_id": component_id,
                "status": "resolved",
                "branch_ids": [first_branch_id, second_branch_id],
            }
        ],
        "branches": [
            {
                "branch_id": first_branch_id,
                "component_id": component_id,
                "source_probe_count": len(first_observations),
                "observations": first_observations,
            },
            {
                "branch_id": second_branch_id,
                "component_id": component_id,
                "source_probe_count": len(second_observations),
                "observations": second_observations,
            },
        ],
        "source_products": {},
    }
    dataset_path = tmp_path / "input.json"
    _write(dataset_path, dataset)
    tle_path = tmp_path / "snapshot.tle"
    tle_path.write_text(
        "SATELLITE-A\n"
        + _renumber_pair(VALLADO_00005, 5)
        + "SATELLITE-B\n"
        + _renumber_pair(VALLADO_00005, 6),
        encoding="utf-8",
    )
    tle_digest = "sha256:" + hashlib.sha256(tle_path.read_bytes()).hexdigest()
    return dataset, dataset_path, tle_path, tle_digest


def _mock_geometry(
    *,
    catalogue: Any,
    satellite_index: int,
    scheduled_times_s: tuple[float, ...],
    calls: list[tuple[float, ...]],
    **_kwargs: object,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    calls.append(scheduled_times_s)
    catalog_number = catalogue.satellite_numbers[satellite_index]
    predicted = 0.0 if catalog_number == 5 else 1_000.0
    count = len(scheduled_times_s)
    return (
        np.full(count, predicted, dtype=np.float64),
        np.full(count, 60.0, dtype=np.float64),
        np.full(count, 550.0, dtype=np.float64),
    )


def _replay(
    tool: ModuleType,
    dataset: dict[str, Any],
    dataset_path: Path,
    tle_path: Path,
    tle_digest: str,
    *,
    config: object | None = None,
) -> dict[str, Any]:
    return tool.replay_window(
        dataset=dataset,
        dataset_path=dataset_path,
        tle_path=tle_path,
        expected_tle_digest=tle_digest,
        component_id="component:resolved",
        start_s=0.1,
        end_s=0.9,
        hypothesis_specs=(
            tool.FixedHypothesisSpec(5, 0.2, 100.0, 0.25),
            tool.FixedHypothesisSpec(6, -0.1, 200.0),
        ),
        observer=tool.ObserverSiteV1(
            latitude_deg=0.0,
            longitude_deg=0.0,
            altitude_m=0.0,
            label="test-observer",
        ),
        config=config
        or tool.ReplayConfig(
            cfo_sigma_hz=1.0,
            detection_probability=0.9,
            clutter_cost=8.0,
            satellite_cost=1.0,
            episode_cost=1.0,
            huber_threshold=1.0,
        ),
    )


def test_replay_pools_component_and_exactly_decodes_two_overlapping_satellites(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()
    dataset, dataset_path, tle_path, tle_digest = _fixture(tmp_path, tool)
    calls: list[tuple[float, ...]] = []
    monkeypatch.setattr(
        tool,
        "_doppler_curve",
        lambda **kwargs: _mock_geometry(calls=calls, **kwargs),
    )
    checker = tool.evaluate_joint_satellite_schedule
    checker_calls = 0

    def counted_checker(*args: object, **kwargs: object) -> object:
        nonlocal checker_calls
        checker_calls += 1
        return checker(*args, **kwargs)

    monkeypatch.setattr(tool, "evaluate_joint_satellite_schedule", counted_checker)

    result = _replay(tool, dataset, dataset_path, tle_path, tle_digest)

    assert result["schema"] == tool.OUTPUT_SCHEMA
    assert result["specificity_claimed"] is False
    assert result["satellite_identification_claimed"] is False
    assert result["conditional_on_resolved_component"] is True
    assert result["conditional_on_explicit_fixed_hypotheses"] is True
    assert result["parameters_fitted"] is False
    assert result["costs_calibrated"] is False
    assert result["window"]["scheduled_probe_count"] == 8
    assert result["component"]["raw_branch_observation_row_count"] == 11
    assert result["component"]["deduplicated_source_observation_count"] == 10
    assert result["component"]["duplicate_source_observation_row_count"] == 1
    assert result["component"]["source_observation_id_is_exclusion_group"] is True
    assert result["timing_approximation"]["prediction_epoch"] == "scheduled probe start"
    assert result["timing_approximation"][
        "maximum_absolute_candidate_local_epoch_offset_s"
    ] == pytest.approx(0.01)
    assert calls == [
        (0.125, 0.225, 0.325, 0.425, 0.525, 0.625, 0.725, 0.825),
        (0.125, 0.225, 0.325, 0.425, 0.525, 0.625, 0.725, 0.825),
    ]
    assert checker_calls == 1
    activity = result["activity"]
    assert activity["exact_for_fixed_hypotheses"] is True
    assert activity["independent_objective_check_passed"] is True
    assert activity["selected_catalog_numbers"] == [5, 6]
    assert activity["unexplained_observation_ids"] == []
    by_catalog = {item["catalog_number"]: item for item in activity["satellites"]}
    assert result["provisional_costs"]["horizon_mask_deg"] == pytest.approx(0.0)
    assert all(
        item["geometry"]["eligible_for_full_replay_window"] is True
        and item["geometry"]["full_window_horizon_gate_applied"] is True
        and item["geometry"]["visibility_mask_applied"] is False
        for item in by_catalog.values()
    )
    assert [(item["start_s"], item["end_s"]) for item in by_catalog[5]["episodes"]] == [(0.1, 0.6)]
    assert [(item["start_s"], item["end_s"]) for item in by_catalog[6]["episodes"]] == [(0.4, 0.9)]
    assigned = [
        assignment["observation_id"]
        for satellite in activity["satellites"]
        for assignment in satellite["assignments"]
    ]
    assert len(assigned) == 10
    assert len(set(assigned)) == 10
    assert all(
        assignment["residual_hz"] == pytest.approx(0.0)
        for satellite in activity["satellites"]
        for assignment in satellite["assignments"]
    )


def test_replay_is_deterministic_under_input_and_hypothesis_permutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()
    dataset, dataset_path, tle_path, tle_digest = _fixture(tmp_path, tool)
    monkeypatch.setattr(
        tool,
        "_doppler_curve",
        lambda **kwargs: _mock_geometry(calls=[], **kwargs),
    )
    first = _replay(tool, dataset, dataset_path, tle_path, tle_digest)
    permuted = deepcopy(dataset)
    permuted["scheduled_probes"].reverse()
    permuted["branches"].reverse()
    for branch in permuted["branches"]:
        branch["observations"].reverse()
    specs = (
        tool.FixedHypothesisSpec(6, -0.1, 200.0),
        tool.FixedHypothesisSpec(5, 0.2, 100.0, 0.25),
    )

    second = tool.replay_window(
        dataset=permuted,
        dataset_path=dataset_path,
        tle_path=tle_path,
        expected_tle_digest=tle_digest,
        component_id="component:resolved",
        start_s=0.1,
        end_s=0.9,
        hypothesis_specs=specs,
        observer=tool.ObserverSiteV1(
            latitude_deg=0.0,
            longitude_deg=0.0,
            altitude_m=0.0,
            label="test-observer",
        ),
        config=tool.ReplayConfig(
            cfo_sigma_hz=1.0,
            detection_probability=0.9,
            clutter_cost=8.0,
            satellite_cost=1.0,
            episode_cost=1.0,
            huber_threshold=1.0,
        ),
    )

    assert second == first


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("unresolved", "resolved CFO component"),
        ("cross-component", "cross-component observation"),
        ("truncated-probe", "truncated scheduled-candidate"),
        ("truncated-frame", "frame-track truncation"),
        ("summary", "full per-probe extraction"),
    ),
)
def test_replay_refuses_unresolved_cross_component_and_truncated_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    message: str,
) -> None:
    tool = _tool()
    dataset, dataset_path, tle_path, tle_digest = _fixture(tmp_path, tool)
    monkeypatch.setattr(
        tool,
        "_doppler_curve",
        lambda **kwargs: _mock_geometry(calls=[], **kwargs),
    )
    if mutation == "unresolved":
        dataset["alias_components"][0]["status"] = "insufficient"
    elif mutation == "cross-component":
        dataset["branches"][0]["observations"][0]["component_id"] = "component:other"
    elif mutation == "truncated-probe":
        dataset["scheduled_probes"][0]["truncated_candidate_count"] = 1
    elif mutation == "truncated-frame":
        dataset["frame_evidence_inventory"]["alias_expanded_truncated_track_count"] = 1
    else:
        dataset["per_probe_rows_omitted"] = True

    with pytest.raises(ValueError, match=message):
        _replay(tool, dataset, dataset_path, tle_path, tle_digest)


def test_replay_rejects_digest_hypothesis_count_and_qnap_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()
    dataset, dataset_path, tle_path, tle_digest = _fixture(tmp_path, tool)
    monkeypatch.setattr(
        tool,
        "_doppler_curve",
        lambda **kwargs: _mock_geometry(calls=[], **kwargs),
    )
    with pytest.raises(ValueError, match="TLE digest mismatch"):
        _replay(tool, dataset, dataset_path, tle_path, "sha256:" + "0" * 64)
    with pytest.raises(ValueError, match="two or three"):
        tool.replay_window(
            dataset=dataset,
            dataset_path=dataset_path,
            tle_path=tle_path,
            expected_tle_digest=tle_digest,
            component_id="component:resolved",
            start_s=0.1,
            end_s=0.9,
            hypothesis_specs=(tool.FixedHypothesisSpec(5, 0.0, 100.0),),
            observer=tool.ObserverSiteV1(
                latitude_deg=0.0,
                longitude_deg=0.0,
                altitude_m=0.0,
                label="test-observer",
            ),
            config=tool.ReplayConfig(),
        )
    with pytest.raises(ValueError, match="refuses output"):
        tool._refuse_qnap_output(Path("/mnt/qnap01/research/joint-replay.json"))


def test_replay_fails_closed_when_hypothesis_is_below_full_window_horizon_mask(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()
    dataset, dataset_path, tle_path, tle_digest = _fixture(tmp_path, tool)
    monkeypatch.setattr(
        tool,
        "_doppler_curve",
        lambda **kwargs: _mock_geometry(calls=[], **kwargs),
    )

    with pytest.raises(ValueError, match="not above the 61 degree horizon mask"):
        _replay(
            tool,
            dataset,
            dataset_path,
            tle_path,
            tle_digest,
            config=tool.ReplayConfig(horizon_mask_deg=61.0),
        )


def test_repeatable_hypothesis_cli_syntax() -> None:
    tool = _tool()

    short = tool._parse_hypothesis("62124,0.15,-12574.25")
    full = tool._parse_hypothesis("66596,-0.7,-182330,0.08")

    assert short == tool.FixedHypothesisSpec(62124, 0.15, -12_574.25, 0.0)
    assert full == tool.FixedHypothesisSpec(66596, -0.7, -182_330.0, 0.08)
    with pytest.raises(argparse.ArgumentTypeError):
        tool._parse_hypothesis("62124,0.15")
