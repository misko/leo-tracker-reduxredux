from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

from leo.contracts.digests import canonical_digest
from leo.contracts.sky import ObserverSiteV1


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools/replay_raw_grouped_satellite_activity.py"
    spec = importlib.util.spec_from_file_location(
        "replay_raw_grouped_satellite_activity_tool", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _score(cfo_hz: float, margin: float) -> dict[str, Any]:
    return {
        "method": "glrt64",
        "tracking_cfo_hz": cfo_hz,
        "residual_cfo_hz": 0.0,
        "exact_score": margin + 0.2,
        "control_score": 0.2,
        "margin": margin,
    }


def _candidate(
    rank: int,
    cfo_hz: float,
    margin: float,
    *,
    local_epoch_sample: int = 10,
) -> dict[str, Any]:
    return {
        "rank": rank,
        "acquired_cfo_hz": cfo_hz,
        "local_epoch_sample": local_epoch_sample,
        "qam_accuracy": None,
        "qam_evm": None,
        "scores": [_score(cfo_hz, margin)],
    }


def _v3_calibration(
    tool: ModuleType,
    *,
    signal_positive_counts: tuple[int, int, int, int] = (900, 50, 30, 20),
) -> dict[str, Any]:
    null_digest = "sha256:" + "1" * 64
    signal_scan_digest = "sha256:" + "2" * 64
    null_probe_count = 10_000
    null_group_counts = (10_000, 9_000, 30_000, 50_000)
    null_positive_counts = (1, 0, 0, 0)
    signal_group_count = 1_000
    bucket_specs = (
        ("rank0", 0, 0),
        ("rank1", 1, 1),
        ("rank2_4", 2, 4),
        ("rank5_plus", 5, None),
    )
    familywise_alpha = 0.05
    null_tail = familywise_alpha / (2.0 * len(bucket_specs))
    signal_tail = familywise_alpha / (2.0 * len(bucket_specs))
    buckets = []
    for (
        (label, minimum_rank, maximum_rank),
        null_group_count,
        null_positive_count,
        signal_positive_count,
    ) in zip(
        bucket_specs,
        null_group_counts,
        null_positive_counts,
        signal_positive_counts,
        strict=True,
    ):
        upper_mean = tool.poisson_count_upper_mean(null_positive_count, null_tail)
        upper_intensity = upper_mean / null_probe_count
        signal_lower = tool.wilson_probability_lower(
            signal_positive_count,
            signal_group_count,
            signal_tail,
        )
        buckets.append(
            {
                "label": label,
                "minimum_rank": minimum_rank,
                "maximum_rank": maximum_rank,
                "null": {
                    "group_count": null_group_count,
                    "positive_group_count": null_positive_count,
                    "source_bounds": [
                        {
                            "pilot_scan_digest": null_digest,
                            "probe_count": null_probe_count,
                            "group_count": null_group_count,
                            "positive_group_count": null_positive_count,
                            "poisson_count_upper_mean": upper_mean,
                            "positive_intensity_upper_per_probe": upper_intensity,
                        }
                    ],
                    "worst_source_pilot_scan_digest": null_digest,
                    "positive_intensity_upper_per_probe": upper_intensity,
                },
                "signal": {
                    "positive_group_count": signal_positive_count,
                    "total_group_count": signal_group_count,
                    "positive_mark_probability_lower": signal_lower,
                },
            }
        )
    null_group_count = sum(null_group_counts)
    null_positive_count = sum(null_positive_counts)
    signal_positive_count = sum(signal_positive_counts)
    return {
        "schema": tool.CALIBRATION_SCHEMA,
        "score_threshold": 0.1,
        "detection_probability": 0.75,
        "confidence": {
            "familywise_alpha": familywise_alpha,
            "rank_bucket_count": len(bucket_specs),
            "null_source_count": 1,
            "null_source_bucket_tail_probability": null_tail,
            "signal_bucket_tail_probability": signal_tail,
            "null_bound": "worst-source-exact-poisson-count-upper",
            "signal_bound": "simultaneous-wilson-mark-probability-lower",
        },
        "grouping": {
            "unit": "unresolved_probe_epoch_tracking_cfo_cell",
            "epoch_tolerance_samples": 1,
            "tracking_cfo_tolerance_hz": 500.0,
            "exact_duplicate_acquired_cfo_tolerance_hz": 0.0,
            "physical_source_identity_claimed": False,
        },
        "null": {
            "positive_group_count": null_positive_count,
            "group_count": null_group_count,
            "rank_buckets": buckets,
        },
        "signal": {
            "positive_group_count": signal_positive_count,
            "group_count": signal_group_count,
        },
        "sources": {
            "null": [
                {
                    "file_digest": null_digest,
                    "detection_count": null_probe_count,
                    "raw_glrt64_row_count": null_group_count,
                    "deduplicated_glrt64_row_count": null_group_count,
                    "resolution_group_count": null_group_count,
                    "positive_count": null_positive_count,
                }
            ],
            "signal": [
                {
                    "file_digest": "sha256:" + "3" * 64,
                    "pilot_scan": {"file_digest": signal_scan_digest},
                    "raw_glrt64_row_count": signal_group_count,
                    "deduplicated_glrt64_row_count": signal_group_count,
                    "resolution_group_count": signal_group_count,
                    "unique_resolution_group_probe_count": signal_group_count,
                    "positive_count": signal_positive_count,
                }
            ],
            "disjoint_pilot_scan_digests": True,
        },
        "accounting": {
            "null_input_file_count": 1,
            "signal_component_spec_count": 1,
            "null_raw_glrt64_row_count": null_group_count,
            "null_deduplicated_glrt64_row_count": null_group_count,
            "null_resolution_group_count": null_group_count,
            "signal_raw_glrt64_row_count": signal_group_count,
            "signal_deduplicated_glrt64_row_count": signal_group_count,
            "signal_resolution_group_count": signal_group_count,
            "signal_unique_resolution_group_probe_count": signal_group_count,
        },
    }


def _fixture(
    tmp_path: Path,
    tool: ModuleType,
    *,
    statuses: tuple[str, ...] = ("complete",) * 5,
    duplicate_first: bool = True,
) -> tuple[dict[str, Any], Path, dict[str, Any], Path]:
    sample_rate_hz = 1_000
    probes = []
    detections = []
    scheduled_rows = []
    for index, status in enumerate(statuses):
        sample_start = index * 100
        probe_id = f"probe-{index}"
        probes.append(
            {
                "probe_id": probe_id,
                "sample_start": sample_start,
                "sample_count": 50,
                "time_s": sample_start / sample_rate_hz,
            }
        )
        candidates: list[dict[str, Any]] = []
        if status == "complete":
            cfo_hz = 100.0 + 10.0 * index
            candidates.append(_candidate(0, cfo_hz, 0.5))
            if duplicate_first and index == 0:
                candidates.append(_candidate(1, cfo_hz, 0.5))
                candidates.append(_candidate(2, cfo_hz + 2_000.0, 0.5, local_epoch_sample=20))
        detections.append(
            {
                "sample_start": sample_start,
                "time_s": sample_start / sample_rate_hz,
                "status": status,
                "source_candidate_count": len(candidates),
                "truncated_candidate_count": 0,
                "candidates": candidates,
            }
        )
        scheduled_rows.append(
            {
                "probe_id": probe_id,
                "schedule_ordinal": index,
                "probe_sample_start": sample_start,
                "probe_sample_count": 50,
                "probe_start_time_s": sample_start / sample_rate_hz,
                "scan_detection_present": True,
                "scan_status": status,
                "usable_for_activity": status in {"complete", "no_result"},
                "source_candidate_count": len(candidates),
                "retained_candidate_count": len(candidates),
                "truncated_candidate_count": 0,
            }
        )
    schedule = {
        "schema_version": 2,
        "algorithm_version": "standard-probe-schedule-v2",
        "schedule_digest": "sha256:schedule",
        "source_probe_count": len(probes),
        "returned_probe_count": len(probes),
        "truncated_probe_count": 0,
        "probes": probes,
    }
    scan = {
        "schema_version": 3,
        "algorithm_version": "standard-pilot-scan-v3",
        "frequency_coordinate": "baseband_cfo_hz",
        "frequency_reference": "uncalibrated_prior",
        "probe_schedule_digest": schedule["schedule_digest"],
        "maximum_scored_candidates_per_probe": 3,
        "detections": detections,
    }
    alias_map = {
        "schema_version": 2,
        "algorithm_version": "standard-cfo-alias-map-v2",
        "pilot_scan_digest": canonical_digest(scan),
        "status": "no_result",
        "members": [],
        "components": [],
    }
    schedule_path = tmp_path / "schedule.json"
    scan_path = tmp_path / "scan.json"
    alias_path = tmp_path / "alias.json"
    _write(schedule_path, schedule)
    _write(scan_path, scan)
    _write(alias_path, alias_map)
    dataset = {
        "schema": tool.INPUT_SCHEMA,
        "candidate_only": True,
        "capture": {
            "sample_rate_hz": sample_rate_hz,
            "declared_sample_count": len(statuses) * 100,
        },
        "frequency_binding": {"sky_frequency_hz": 11_000_000_000},
        "timing_binding": {"first_estimate_utc_ns": 1_000_000_000_000},
        "alias_collapse": {"alias_spacing_hz": 227_272.72727272726},
        "scheduled_probes": scheduled_rows,
        "branches": [],
        "alias_components": [],
        "source_products": {
            "schedule": {"path": str(schedule_path), "file_digest": _digest(schedule_path)},
            "scan": {"path": str(scan_path), "file_digest": _digest(scan_path)},
            "alias_map": {"path": str(alias_path), "file_digest": _digest(alias_path)},
        },
    }
    dataset_path = tmp_path / "dataset.json"
    _write(dataset_path, dataset)
    calibration = _v3_calibration(tool)
    calibration_path = tmp_path / "calibration.json"
    _write(calibration_path, calibration)
    return dataset, dataset_path, calibration, calibration_path


def _inventory(
    tool: ModuleType,
    dataset: dict[str, Any],
    calibration: dict[str, Any],
) -> Any:
    rows = tuple(dataset["scheduled_probes"])
    return tool._load_raw_inventory(
        dataset=dataset,
        window_rows=rows,
        window_start_sample=0,
        window_cell_samples=100,
        window_cell_count=len(rows),
        calibration=tool._score(calibration),
        config=tool.RawReplayConfig(delay_min_s=0.0, delay_max_s=0.0),
    )


def test_raw_adapter_preserves_rank_ids_and_collapses_exact_duplicate_basins(
    tmp_path: Path,
) -> None:
    tool = _tool()
    dataset, _dataset_path, calibration, _calibration_path = _fixture(tmp_path, tool)

    inventory = _inventory(tool, dataset, calibration)
    first = [item for item in inventory.problem.observations if item.probe_id == "probe-0"]

    assert inventory.returned_candidate_count == 7
    assert inventory.exclusion_group_count == 6
    assert inventory.saturated_probe_count == 1
    assert len(first) == 3
    group_sizes = sorted(
        sum(item.exclusion_group_id == group_id for item in first)
        for group_id in {item.exclusion_group_id for item in first}
    )
    assert group_sizes == [1, 2]
    expected_ids = {
        canonical_digest({"sample_start": 0, "candidate_rank": rank, "method": "glrt64"})
        for rank in range(3)
    }
    assert {item.observation_id for item in first} == expected_ids
    assert all(item.component_id.startswith("raw:sha256:") for item in first)
    assert inventory.local_epoch_max_s == pytest.approx(0.02)


def test_raw_adapter_collapses_candidates_inside_one_detector_resolution_cell(
    tmp_path: Path,
) -> None:
    tool = _tool()
    dataset, _dataset_path, calibration, _calibration_path = _fixture(tmp_path, tool)
    scan_path = Path(dataset["source_products"]["scan"]["path"])
    scan = json.loads(scan_path.read_text(encoding="utf-8"))
    scan["maximum_scored_candidates_per_probe"] = 4
    scan["detections"][0]["candidates"].append(_candidate(3, 499.0, 0.5, local_epoch_sample=11))
    scan["detections"][0]["source_candidate_count"] = 4
    _write(scan_path, scan)
    dataset["source_products"]["scan"]["file_digest"] = _digest(scan_path)
    dataset["scheduled_probes"][0]["source_candidate_count"] = 4
    dataset["scheduled_probes"][0]["retained_candidate_count"] = 4
    alias_path = Path(dataset["source_products"]["alias_map"]["path"])
    alias_map = json.loads(alias_path.read_text(encoding="utf-8"))
    alias_map["pilot_scan_digest"] = canonical_digest(scan)
    _write(alias_path, alias_map)
    dataset["source_products"]["alias_map"]["file_digest"] = _digest(alias_path)

    inventory = _inventory(tool, dataset, calibration)
    first = [item for item in inventory.problem.observations if item.probe_id == "probe-0"]
    group_sizes = sorted(
        sum(item.exclusion_group_id == group_id for item in first)
        for group_id in {item.exclusion_group_id for item in first}
    )

    assert group_sizes == [1, 3]
    assert inventory.returned_candidate_count == 8
    assert inventory.exclusion_group_count == 6


def test_raw_adapter_elides_positive_rank_without_signal_support(tmp_path: Path) -> None:
    tool = _tool()
    dataset, _dataset_path, calibration, _calibration_path = _fixture(
        tmp_path,
        tool,
        duplicate_first=False,
    )
    calibration = _v3_calibration(tool, signal_positive_counts=(0, 50, 30, 20))

    inventory = _inventory(tool, dataset, calibration)

    assert inventory.problem.returned_observation_count == 0
    assert inventory.unsupported_positive_candidate_count == 5
    assert inventory.unsupported_positive_exclusion_group_count == 5
    assert inventory.modeled_exclusion_group_count == 0
    null_intensity = calibration["null"]["rank_buckets"][0]["null"][
        "positive_intensity_upper_per_probe"
    ]
    assert inventory.elided_clutter_constant == pytest.approx(5.0 * -math.log(null_intensity))


def test_no_result_is_usable_miss_while_insufficient_is_unusable(tmp_path: Path) -> None:
    tool = _tool()
    dataset, _dataset_path, calibration, _calibration_path = _fixture(
        tmp_path,
        tool,
        statuses=("no_result", "insufficient", "complete", "complete", "complete"),
        duplicate_first=False,
    )

    inventory = _inventory(tool, dataset, calibration)

    assert inventory.problem.probes[0].usable
    assert inventory.problem.probes[0].missed_detection_cost > 0.0
    assert not inventory.problem.probes[1].usable
    assert inventory.problem.probes[1].missed_detection_cost == 0.0
    assert not [item for item in inventory.problem.observations if item.probe_id == "probe-0"]


def test_raw_adapter_rejects_tracking_equation_and_explicit_truncation(tmp_path: Path) -> None:
    tool = _tool()
    dataset, _dataset_path, calibration, _calibration_path = _fixture(tmp_path, tool)
    scan_path = Path(dataset["source_products"]["scan"]["path"])
    scan = json.loads(scan_path.read_text(encoding="utf-8"))
    scan["detections"][0]["candidates"][0]["scores"][0]["tracking_cfo_hz"] += 1.0
    _write(scan_path, scan)
    dataset["source_products"]["scan"]["file_digest"] = _digest(scan_path)
    alias_path = Path(dataset["source_products"]["alias_map"]["path"])
    alias_map = json.loads(alias_path.read_text(encoding="utf-8"))
    alias_map["pilot_scan_digest"] = canonical_digest(scan)
    _write(alias_path, alias_map)
    dataset["source_products"]["alias_map"]["file_digest"] = _digest(alias_path)

    with pytest.raises(ValueError, match="acquired plus residual"):
        _inventory(tool, dataset, calibration)

    scan["detections"][0]["candidates"][0]["scores"][0]["tracking_cfo_hz"] -= 1.0
    scan["detections"][0]["source_candidate_count"] += 1
    scan["detections"][0]["truncated_candidate_count"] = 1
    _write(scan_path, scan)
    dataset["source_products"]["scan"]["file_digest"] = _digest(scan_path)
    alias_map["pilot_scan_digest"] = canonical_digest(scan)
    _write(alias_path, alias_map)
    dataset["source_products"]["alias_map"]["file_digest"] = _digest(alias_path)
    dataset["scheduled_probes"][0]["source_candidate_count"] += 1
    dataset["scheduled_probes"][0]["truncated_candidate_count"] = 1

    with pytest.raises(ValueError, match="truncated candidate inventory"):
        _inventory(tool, dataset, calibration)


def test_raw_adapter_rejects_inconsistent_glrt_margin(tmp_path: Path) -> None:
    tool = _tool()
    dataset, _dataset_path, calibration, _calibration_path = _fixture(tmp_path, tool)
    scan_path = Path(dataset["source_products"]["scan"]["path"])
    scan = json.loads(scan_path.read_text(encoding="utf-8"))
    scan["detections"][0]["candidates"][0]["scores"][0]["margin"] += 0.01
    _write(scan_path, scan)
    dataset["source_products"]["scan"]["file_digest"] = _digest(scan_path)
    alias_path = Path(dataset["source_products"]["alias_map"]["path"])
    alias_map = json.loads(alias_path.read_text(encoding="utf-8"))
    alias_map["pilot_scan_digest"] = canonical_digest(scan)
    _write(alias_path, alias_map)
    dataset["source_products"]["alias_map"]["file_digest"] = _digest(alias_path)

    with pytest.raises(ValueError, match="margin disagrees"):
        _inventory(tool, dataset, calibration)


def test_score_calibration_requires_disjoint_nonempty_sources(tmp_path: Path) -> None:
    tool = _tool()
    _dataset, _dataset_path, calibration, _calibration_path = _fixture(tmp_path, tool)
    calibration["sources"] = {
        "null": [],
        "signal": [],
        "disjoint_pilot_scan_digests": True,
    }

    with pytest.raises(ValueError, match="no null"):
        tool._score(calibration)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda document: document["null"]["rank_buckets"][0]["null"].__setitem__(
                "positive_intensity_upper_per_probe",
                0.5
                * document["null"]["rank_buckets"][0]["null"]["positive_intensity_upper_per_probe"],
            ),
            "worst-source null envelope",
        ),
        (
            lambda document: document["sources"]["null"][0].__setitem__(
                "resolution_group_count",
                document["sources"]["null"][0]["resolution_group_count"] + 1,
            ),
            "accounting",
        ),
        (
            lambda document: document["accounting"].__setitem__(
                "signal_resolution_group_count",
                document["accounting"]["signal_resolution_group_count"] + 1,
            ),
            "inventory accounting",
        ),
        (
            lambda document: document["confidence"].__setitem__("rank_bucket_count", 4.5),
            "must be an integer",
        ),
        (
            lambda document: (
                document["null"]["rank_buckets"][2].__setitem__("maximum_rank", 5),
                document["null"]["rank_buckets"][3].__setitem__("minimum_rank", 6),
            ),
            "fixed schema",
        ),
        (
            lambda document: document["sources"]["null"][0].__setitem__(
                "file_digest", "sha256:not-a-digest"
            ),
            "canonical lowercase SHA-256",
        ),
        (
            lambda document: (
                document["sources"]["null"][0].__setitem__("raw_glrt64_row_count", 1),
                document["accounting"].__setitem__("null_raw_glrt64_row_count", 1),
            ),
            "accounting is impossible",
        ),
    ],
)
def test_v3_score_loader_recomputes_bounds_and_provenance_accounting(
    tmp_path: Path,
    mutation: Any,
    message: str,
) -> None:
    tool = _tool()
    _dataset, _dataset_path, calibration, _calibration_path = _fixture(tmp_path, tool)
    tampered = copy.deepcopy(calibration)
    mutation(tampered)

    with pytest.raises(ValueError, match=message):
        tool._score(tampered)


def test_v3_score_loader_rejects_impossible_signal_mark_counts(tmp_path: Path) -> None:
    tool = _tool()
    _dataset, _dataset_path, calibration, _calibration_path = _fixture(tmp_path, tool)
    impossible = copy.deepcopy(calibration)
    signal_group_count = impossible["signal"]["group_count"]
    signal_tail = impossible["confidence"]["signal_bucket_tail_probability"]
    for bucket in impossible["null"]["rank_buckets"]:
        bucket["signal"]["positive_group_count"] = signal_group_count
        bucket["signal"]["positive_mark_probability_lower"] = tool.wilson_probability_lower(
            signal_group_count,
            signal_group_count,
            signal_tail,
        )
    impossible["signal"]["positive_group_count"] = 4 * signal_group_count
    impossible["sources"]["signal"][0]["positive_count"] = 4 * signal_group_count

    with pytest.raises(ValueError, match="exceeds its group count"):
        tool._score(impossible)


def test_end_to_end_raw_replay_selects_only_the_curve_compatible_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()
    dataset, dataset_path, calibration, calibration_path = _fixture(
        tmp_path,
        tool,
        duplicate_first=False,
    )
    tle_path = tmp_path / "snapshot.tle"
    tle_path.write_text("frozen-test-snapshot\n", encoding="utf-8")
    catalogue = SimpleNamespace(
        names=("STARLINK-GOOD", "STARLINK-BAD"),
        satellite_numbers=(10, 20),
    )
    monkeypatch.setattr(tool, "parse_element_sets", lambda _text: catalogue)

    def curve(**kwargs: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        count = len(kwargs["scheduled_times_s"])
        index = int(kwargs["satellite_index"])
        slope = 10.0 if index == 0 else 200.0
        return (
            np.arange(count, dtype=float) * slope,
            np.full(count, 45.0),
            np.full(count, 550.0),
        )

    monkeypatch.setattr(tool, "_doppler_curve", curve)
    config = tool.RawReplayConfig(
        delay_min_s=0.0,
        delay_max_s=0.0,
        modes_per_delay=1,
        retained_states_per_catalog=1,
        satellite_cost=2.0,
        episode_cost=1.0,
    )

    result = tool.replay_raw_window(
        dataset=dataset,
        dataset_path=dataset_path,
        calibration_document=calibration,
        calibration_path=calibration_path,
        tle_path=tle_path,
        expected_tle_digest=_digest(tle_path),
        catalog_numbers=(10, 20),
        start_s=0.0,
        end_s=0.5,
        observer=ObserverSiteV1(
            latitude_deg=37.0,
            longitude_deg=-122.0,
            altitude_m=0.0,
            label="test",
        ),
        config=config,
    )

    assert result["association"]["association"]["selected_catalog_numbers"] == [10]
    assert result["raw_inventory"]["returned_candidate_count"] == 5
    assert result["association"]["exact"]
    assert result["conditional_on_raw_glrt64_inventory"]
    assert not result["catalogue_search_performed"]
    assert result["resolution_group_score_frequency_estimated"]
    assert result["conservative_rank_mark_bounds_applied"]
    assert not result["pooled_candidate_row_score_frequency_estimated"]
    assert any("worst-null-source upper intensities" in caveat for caveat in result["caveats"])
    assignments_by_hypothesis = result["selected_assignment_details"]
    assert len(assignments_by_hypothesis) == 1
    assignments = next(iter(assignments_by_hypothesis.values()))
    assert assignments
    assert all(item["group_minimum_rank"] == 0 for item in assignments)
    assert all(item["group_member_count"] == 1 for item in assignments)
    assert max(abs(item["residual_hz"]) for item in assignments) == pytest.approx(0.0)
