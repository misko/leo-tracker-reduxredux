from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

from leo.contracts.digests import canonical_digest  # type: ignore[import-untyped]
from leo.contracts.sky import ObserverSiteV1  # type: ignore[import-untyped]

START_UTC_NS = 1_000_000_000_000
END_UTC_NS = START_UTC_NS + 1_000_000_000


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools/replay_raw_multipath_satellite_activity.py"
    spec = importlib.util.spec_from_file_location(
        "replay_raw_multipath_satellite_activity_tool", path
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


def _candidate(cfo_hz: float) -> dict[str, Any]:
    return {
        "rank": 0,
        "acquired_cfo_hz": cfo_hz,
        "local_epoch_sample": 10,
        "scores": [_score(cfo_hz, 0.5)],
    }


def _v3_calibration(tool: ModuleType) -> dict[str, Any]:
    null_digest = "sha256:" + "1" * 64
    signal_scan_digest = "sha256:" + "2" * 64
    null_probe_count = 10_000
    null_group_counts = (10_000, 9_000, 30_000, 50_000)
    null_positive_counts = (1, 0, 0, 0)
    signal_positive_counts = (900, 50, 30, 20)
    signal_group_count = 1_000
    bucket_specs = (
        ("rank0", 0, 0),
        ("rank1", 1, 1),
        ("rank2_4", 2, 4),
        ("rank5_plus", 5, None),
    )
    familywise_alpha = 0.05
    tail = familywise_alpha / (2.0 * len(bucket_specs))
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
        upper_mean = tool.raw_replay.poisson_count_upper_mean(null_positive_count, tail)
        upper_intensity = upper_mean / null_probe_count
        signal_lower = tool.raw_replay.wilson_probability_lower(
            signal_positive_count, signal_group_count, tail
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
        "schema": tool.raw_replay.CALIBRATION_SCHEMA_V3,
        "score_threshold": 0.1,
        "detection_probability": 0.75,
        "confidence": {
            "familywise_alpha": familywise_alpha,
            "rank_bucket_count": len(bucket_specs),
            "null_source_count": 1,
            "null_source_bucket_tail_probability": tail,
            "signal_bucket_tail_probability": tail,
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


def _timing() -> dict[str, Any]:
    return {
        "first_earliest_utc_ns": START_UTC_NS - 10_000,
        "first_estimate_utc_ns": START_UTC_NS,
        "first_latest_utc_ns": START_UTC_NS + 10_000,
        "last_earliest_utc_ns": END_UTC_NS - 1_000_000 - 10_000,
        "last_estimate_utc_ns": END_UTC_NS - 1_000_000,
        "last_latest_utc_ns": END_UTC_NS - 1_000_000 + 10_000,
        "observation_utc_method": (
            "linear interpolation between manifest first/last sample timing anchors"
        ),
        "receiver_relative_time_origin": "first captured sample",
    }


def _fixture_path(
    tmp_path: Path,
    tool: ModuleType,
    *,
    path_index: int,
    offset_hz: float,
) -> tuple[dict[str, Any], Path]:
    sample_rate_hz = 1_000
    timing = _timing()
    probes = []
    detections = []
    scheduled = []
    for index in range(10):
        sample_start = index * 100
        probe_id = f"probe-{index}"
        status = "no_result" if index == 5 else "complete"
        candidates = [] if status == "no_result" else [_candidate(offset_hz + 10.0 * index)]
        probes.append(
            {
                "probe_id": probe_id,
                "sample_start": sample_start,
                "sample_count": 50,
                "time_s": sample_start / sample_rate_hz,
            }
        )
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
        probe_utc = tool._interpolated_utc(timing, sample_start, 1_000)
        scheduled.append(
            {
                "probe_id": probe_id,
                "schedule_ordinal": index,
                "coarse_window_index": index,
                "subwindow_index": 0,
                "probe_offset_ms": 0,
                "probe_sample_start": sample_start,
                "probe_sample_count": 50,
                "probe_start_time_s": sample_start / sample_rate_hz,
                "probe_start_utc": probe_utc,
                "scan_detection_present": True,
                "scan_status": status,
                "usable_for_activity": True,
                "source_candidate_count": len(candidates),
                "retained_candidate_count": len(candidates),
                "truncated_candidate_count": 0,
            }
        )
    schedule = {
        "schema_version": 2,
        "algorithm_version": "standard-probe-schedule-v2",
        "schedule_digest": f"sha256:schedule-{path_index}",
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
        "maximum_scored_candidates_per_probe": 1,
        "probe_samples": 50,
        "coarse_window_samples": 1_000,
        "subwindow_samples": 100,
        "methods": ["glrt64"],
        "detections": detections,
    }
    alias = {
        "schema_version": 2,
        "algorithm_version": "standard-cfo-alias-map-v2",
        "pilot_scan_digest": canonical_digest(scan),
        "status": "no_result",
        "members": [],
        "components": [],
    }
    schedule_path = tmp_path / f"schedule-{path_index}.json"
    scan_path = tmp_path / f"scan-{path_index}.json"
    alias_path = tmp_path / f"alias-{path_index}.json"
    _write(schedule_path, schedule)
    _write(scan_path, scan)
    _write(alias_path, alias)
    dataset = {
        "schema": tool.INPUT_SCHEMA,
        "candidate_only": True,
        "capture": {
            "session_id": "session-one",
            "stream_id": f"stream-{path_index}",
            "radio_id": f"radio-{path_index}",
            "radio_serial": f"serial-{path_index}",
            "receiver_id": path_index,
            "recording_manifest_digest": "sha256:" + "a" * 64,
            "sample_rate_hz": sample_rate_hz,
            "declared_sample_count": 1_000,
            "observed_sample_count": 1_000,
            "coverage_fraction": 1.0,
        },
        "frequency_binding": {
            "sky_frequency_hz": 11_000_000_000 + path_index * 100_000_000,
            "tuning_tag": f"tuning:stream-{path_index}:ch1:lower",
        },
        "timing_binding": timing,
        "alias_collapse": {"alias_spacing_hz": 227_272.72727272726},
        "scheduled_probes": scheduled,
        "branches": [],
        "alias_components": [],
        "source_products": {
            "schedule": {"path": str(schedule_path), "file_digest": _digest(schedule_path)},
            "scan": {"path": str(scan_path), "file_digest": _digest(scan_path)},
            "alias_map": {"path": str(alias_path), "file_digest": _digest(alias_path)},
        },
    }
    dataset_path = tmp_path / f"duration-{path_index}.json"
    _write(dataset_path, dataset)
    return dataset, dataset_path


def _case(tmp_path: Path, tool: ModuleType) -> dict[str, Any]:
    first, first_path = _fixture_path(tmp_path, tool, path_index=0, offset_hz=100.0)
    second, second_path = _fixture_path(tmp_path, tool, path_index=1, offset_hz=300.0)
    calibration = _v3_calibration(tool)
    calibration_path = tmp_path / "calibration.json"
    _write(calibration_path, calibration)
    tle_path = tmp_path / "catalog.tle"
    tle_path.write_text("digest-bound synthetic TLE\n", encoding="utf-8")
    return {
        "datasets": (first, second),
        "paths": (first_path, second_path),
        "digests": (_digest(first_path), _digest(second_path)),
        "calibration": calibration,
        "calibration_path": calibration_path,
        "calibration_digest": _digest(calibration_path),
        "tle_path": tle_path,
        "tle_digest": _digest(tle_path),
    }


def _fake_science(monkeypatch: pytest.MonkeyPatch, tool: ModuleType) -> None:
    catalogue = SimpleNamespace(satellite_numbers=(10, 20), names=("STARLINK-10", "STARLINK-20"))
    monkeypatch.setattr(tool, "parse_element_sets", lambda _text: catalogue)

    def doppler(
        *,
        catalogue: Any,
        satellite_index: int,
        context: Any,
        delay_s: float,
        observer: Any,
    ) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any], np.ndarray[Any, Any]]:
        del catalogue, delay_s, observer
        count = len(context.probe_utc)
        if satellite_index == 0:
            curve = np.arange(count, dtype=np.float64) * 10.0
        else:
            curve = 500.0 - np.arange(count, dtype=np.float64) * 20.0
        return curve, np.full(count, 60.0), np.full(count, 550.0)

    monkeypatch.setattr(tool, "_path_doppler", doppler)


def _run(
    tool: ModuleType,
    case: dict[str, Any],
    *,
    config: Any | None = None,
    eligibility: tuple[dict[str, Any], Path, str] | None = None,
) -> dict[str, Any]:
    return tool.replay_raw_multipath_window(
        dataset_paths=case["paths"],
        expected_dataset_digests=case["digests"],
        calibration_document=case["calibration"],
        calibration_path=case["calibration_path"],
        expected_calibration_digest=case["calibration_digest"],
        tle_path=case["tle_path"],
        expected_tle_digest=case["tle_digest"],
        catalog_numbers=(20, 10),
        start_utc_ns=START_UTC_NS,
        end_utc_ns=END_UTC_NS,
        observer=ObserverSiteV1(
            latitude_deg=37.8,
            longitude_deg=-122.4,
            altitude_m=10.0,
            label="test site",
        ),
        config=(
            config
            if config is not None
            else tool.MultipathReplayConfig(
                cfo_sigma_hz=10.0,
                satellite_cost=2.0,
                episode_cost=2.0,
                delay_min_s=0.0,
                delay_max_s=0.0,
                mode_bin_hz=50.0,
                mode_half_width_hz=100.0,
                modes_per_delay=1,
                retained_states_per_catalog=1,
            )
        ),
        eligibility_document=None if eligibility is None else eligibility[0],
        eligibility_plan_path=None if eligibility is None else eligibility[1],
        expected_eligibility_plan_digest=None if eligibility is None else eligibility[2],
    )


def test_multipath_adapter_maps_utc_preserves_empty_probes_and_decodes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = _tool()
    case = _case(tmp_path, tool)
    _fake_science(monkeypatch, tool)

    document = _run(tool, case)

    assert document["schema"] == tool.OUTPUT_SCHEMA
    assert document["search_configuration_digest"] == canonical_digest(
        document["search_configuration"]
    )
    assert document["window"]["cell_count"] == 10
    assert document["decision"]["selected_catalog_numbers"] == [10]
    assert document["null_vs_any_activation_solved"] is True
    assert document["null_vs_supplied_retained_state_bank_solved"] is True
    assert document["per_catalog_state_banks_pruned"] is False
    assert document["association"]["algorithm"] == tool.FIXED_JOINT_ALGORITHM
    assert document["association"]["exact"] is True
    assert len(document["path_inventories"]) == 2
    for inventory in document["path_inventories"]:
        assert inventory["scheduled_probe_count"] == 10
        assert inventory["usable_probe_count"] == 10
        assert inventory["usable_empty_probe_count"] == 1
        assert [item["cell_index"] for item in inventory["probe_grid_mapping"]] == list(range(10))

    selected = next(iter(document["selected_path_assignment_details"].values()))
    offsets = sorted(path["cfo_offset_hz"] for path in selected["paths"].values())
    assert offsets == pytest.approx([100.0, 300.0])
    for path in selected["paths"].values():
        assert len(path["assignments"]) == 9
        assert path["missed_probe_ids"] == ["probe-5"]
        assert max(abs(item["residual_hz"]) for item in path["assignments"]) < 1e-9
    assert len(document["path_full_persisted_inventory_objectives"]) == 2
    assert document["full_window_shared_band_occupancy_assumed"] is True
    assert document["external_rf_eligibility_plan_supplied"] is False
    assert document["rf_eligibility_inferred_from_scored_observations"] is False
    eligibility = document["search_configuration"]["rf_eligibility"]
    assert eligibility["mode"] == "implicit-all-cells-eligible-v1"
    assert all(
        path["eligible_cell_runs"] == [[0, 10]]
        for catalog in eligibility["catalogs"]
        for path in catalog["paths"]
    )
    assert document["specificity_claimed"] is False


def _eligibility_fixture(
    tmp_path: Path,
    tool: ModuleType,
    case: dict[str, Any],
) -> tuple[dict[str, Any], Path, str]:
    path_ids = tuple(tool._path_identity(dataset)[0] for dataset in case["datasets"])
    document = {
        "schema": tool.ELIGIBILITY_PLAN_SCHEMA,
        "basis": "synthetic predeclared RF allocation used only by this test",
        "window": {
            "start_utc_ns": START_UTC_NS,
            "end_utc_ns": END_UTC_NS,
            "cell_duration_ns": tool.UTC_CELL_NS,
            "cell_count": 10,
        },
        "catalogs": [
            {
                "catalog_number": 10,
                "paths": [
                    {"path_id": path_ids[0], "eligible_cell_runs": [[0, 4]]},
                    {"path_id": path_ids[1], "eligible_cell_runs": [[6, 10]]},
                ],
            },
            {
                "catalog_number": 20,
                "paths": [{"path_id": path_id, "eligible_cell_runs": []} for path_id in path_ids],
            },
        ],
    }
    path = tmp_path / "eligibility.json"
    _write(path, document)
    return document, path, _digest(path)


def test_digest_bound_path_cell_eligibility_limits_assignments_but_retains_clutter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = _tool()
    case = _case(tmp_path, tool)
    _fake_science(monkeypatch, tool)
    eligibility = _eligibility_fixture(tmp_path, tool, case)

    document = _run(tool, case, eligibility=eligibility)

    assert document["external_rf_eligibility_plan_supplied"] is True
    assert document["full_window_shared_band_occupancy_assumed"] is False
    assert document["rf_eligibility_inferred_from_scored_observations"] is False
    receipt = document["search_configuration"]["rf_eligibility"]
    assert receipt["mode"] == "explicit-fixed-path-cell-runs-v1"
    assert receipt["plan_file_digest"] == eligibility[2]
    assert receipt["plan_content_digest"] == canonical_digest(eligibility[0])
    assert document["input"]["eligibility_plan"]["file_digest"] == eligibility[2]
    selected = next(iter(document["selected_path_assignment_details"].values()))
    selected_paths = sorted(selected["paths"].values(), key=lambda item: item["cfo_offset_hz"])
    assert [item["eligible_cell_runs"] for item in selected_paths] == [
        [[0, 4]],
        [[6, 10]],
    ]
    assert [
        [assignment["probe_id"] for assignment in item["assignments"]] for item in selected_paths
    ] == [
        [f"probe-{index}" for index in range(4)],
        [f"probe-{index}" for index in range(6, 10)],
    ]
    assert [item["missed_probe_ids"] for item in selected_paths] == [[], []]
    latent_support = selected["latent_activity_support"]
    assert latent_support["global_active_cell_runs"] == [[0, 10]]
    assert latent_support["all_paths_rf_ineligible_active_cell_count"] == 2
    assert latent_support["all_paths_rf_ineligible_active_cell_runs"] == [[4, 6]]
    assert latent_support["no_eligible_usable_probe_active_cell_runs"] == [[4, 6]]
    selected_satellite = next(
        item for item in document["association"]["satellites"] if item["selected"]
    )
    assert [sum(path["eligible_by_cell"]) for path in selected_satellite["paths"]] == [4, 4]
    assert selected_satellite["latent_activity_support"] == latent_support
    assert document["association"]["objective"]["clutter_cost"] > 0.0


def test_eligibility_plan_rejects_tampering_and_noncanonical_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = _tool()
    case = _case(tmp_path, tool)
    _fake_science(monkeypatch, tool)
    document, path, digest = _eligibility_fixture(tmp_path, tool, case)

    with pytest.raises(ValueError, match="digest mismatch"):
        _run(tool, case, eligibility=(document, path, "sha256:" + "f" * 64))

    malformed = copy.deepcopy(document)
    malformed["catalogs"][0]["paths"][0]["eligible_cell_runs"] = [[0, 3], [3, 5]]
    _write(path, malformed)
    with pytest.raises(ValueError, match="sorted, disjoint, and coalesced"):
        _run(tool, case, eligibility=(malformed, path, _digest(path)))

    with pytest.raises(ValueError, match="must be supplied together"):
        tool._eligibility_binding(
            document=document,
            plan_path=None,
            expected_plan_digest=digest,
            catalog_numbers=(10, 20),
            path_ids=tuple(tool._path_identity(item)[0] for item in case["datasets"]),
            start_utc_ns=START_UTC_NS,
            end_utc_ns=END_UTC_NS,
        )


def test_empty_decision_is_only_a_conditional_retained_bank_null(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = _tool()
    case = _case(tmp_path, tool)
    _fake_science(monkeypatch, tool)
    document = _run(
        tool,
        case,
        config=tool.MultipathReplayConfig(
            cfo_sigma_hz=10.0,
            satellite_cost=100_000.0,
            episode_cost=100_000.0,
            delay_min_s=0.0,
            delay_max_s=0.0,
            modes_per_delay=1,
            retained_states_per_catalog=1,
        ),
    )

    assert document["decision"]["result_kind"] == ("conditional_null_over_retained_state_bank")
    assert document["decision"]["selected_catalog_numbers"] == []
    assert document["null_vs_any_activation_solved"] is False
    assert document["null_vs_supplied_retained_state_bank_solved"] is True


def test_capped_empty_decision_is_only_an_evaluated_prefix_null(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = _tool()
    case = _case(tmp_path, tool)
    _fake_science(monkeypatch, tool)
    original_modes = tool.raw_replay._offset_modes

    def two_modes(**kwargs: Any) -> tuple[Any, ...]:
        first = original_modes(**kwargs)[0]
        return (
            first,
            tool.raw_replay._OffsetMode(
                cfo_offset_hz=first.cfo_offset_hz + 1_000.0,
                support_group_count=0,
                support_probe_count=0,
            ),
        )

    monkeypatch.setattr(tool.raw_replay, "_offset_modes", two_modes)
    document = _run(
        tool,
        case,
        config=tool.MultipathReplayConfig(
            cfo_sigma_hz=10.0,
            satellite_cost=100_000.0,
            episode_cost=100_000.0,
            delay_min_s=0.0,
            delay_max_s=0.0,
            modes_per_delay=2,
            retained_states_per_catalog=2,
            maximum_state_combinations=1,
        ),
    )

    assert document["nuisance_state_search"]["possible_retained_joint_state_combination_count"] == 4
    assert (
        document["nuisance_state_search"]["evaluated_retained_joint_state_combination_count"] == 1
    )
    assert document["decision"]["result_kind"] == (
        "conditional_null_over_evaluated_retained_state_prefix"
    )
    assert document["decision"]["selected_catalog_numbers"] == []
    assert document["null_vs_supplied_retained_state_bank_solved"] is False


def test_multipath_adapter_is_order_invariant_and_binds_every_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = _tool()
    case = _case(tmp_path, tool)
    _fake_science(monkeypatch, tool)
    forward = _run(tool, case)
    reverse_case = {
        **case,
        "paths": tuple(reversed(case["paths"])),
        "digests": tuple(reversed(case["digests"])),
    }
    reverse = _run(tool, reverse_case)

    assert forward["search_configuration_digest"] == reverse["search_configuration_digest"]
    assert forward["decision"] == reverse["decision"]
    implementation_digests = forward["search_configuration"]["implementation_file_digests"]
    assert set(implementation_digests) == set(tool._IMPLEMENTATION_FILE_PATHS)
    assert {
        "src/leo/contracts/base.py",
        "src/leo/contracts/digests.py",
    } <= set(implementation_digests)
    for relative_path, digest in implementation_digests.items():
        assert digest == tool._file_digest(tool.REPOSITORY_ROOT / relative_path)
    assert forward["search_configuration"]["runtime_versions"] == tool._runtime_versions()

    bad = {**case, "digests": ("sha256:" + "f" * 64, case["digests"][1])}
    with pytest.raises(ValueError, match="duration-input digest mismatch"):
        _run(tool, bad)
    bad_calibration = {**case, "calibration_digest": "sha256:" + "f" * 64}
    with pytest.raises(ValueError, match="score-calibration file digest mismatch"):
        _run(tool, bad_calibration)
    altered_document = copy.deepcopy(case["calibration"])
    altered_document["detection_probability"] = 0.7
    with pytest.raises(ValueError, match="does not match its digest-bound file"):
        _run(tool, {**case, "calibration": altered_document})
    bad_tle = {**case, "tle_digest": "sha256:" + "f" * 64}
    with pytest.raises(ValueError, match="TLE digest mismatch"):
        _run(tool, bad_tle)

    non_v3 = copy.deepcopy(case["calibration"])
    non_v3["schema"] = tool.raw_replay.CALIBRATION_SCHEMA_V2
    non_v3_path = tmp_path / "calibration-v2.json"
    _write(non_v3_path, non_v3)
    with pytest.raises(ValueError, match="requires raw V3"):
        tool.replay_raw_multipath_window(
            dataset_paths=case["paths"],
            expected_dataset_digests=case["digests"],
            calibration_document=non_v3,
            calibration_path=non_v3_path,
            expected_calibration_digest=_digest(non_v3_path),
            tle_path=case["tle_path"],
            expected_tle_digest=case["tle_digest"],
            catalog_numbers=(10, 20),
            start_utc_ns=START_UTC_NS,
            end_utc_ns=END_UTC_NS,
            observer=ObserverSiteV1(
                latitude_deg=0.0, longitude_deg=0.0, altitude_m=0.0, label="site"
            ),
            config=tool.MultipathReplayConfig(delay_min_s=0.0, delay_max_s=0.0),
        )


def test_path_offset_cartesian_cap_is_explicit_and_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = _tool()
    case = _case(tmp_path, tool)
    _fake_science(monkeypatch, tool)
    original_modes = tool.raw_replay._offset_modes

    def two_modes(**kwargs: Any) -> tuple[Any, ...]:
        first = original_modes(**kwargs)[0]
        return (
            first,
            tool.raw_replay._OffsetMode(
                cfo_offset_hz=first.cfo_offset_hz + 1_000.0,
                support_group_count=0,
                support_probe_count=0,
            ),
        )

    monkeypatch.setattr(tool.raw_replay, "_offset_modes", two_modes)
    config = tool.MultipathReplayConfig(
        cfo_sigma_hz=10.0,
        satellite_cost=2.0,
        episode_cost=2.0,
        delay_min_s=0.0,
        delay_max_s=0.0,
        modes_per_delay=2,
        retained_states_per_catalog=1,
        maximum_path_offset_combinations_per_delay=3,
    )
    first = _run(tool, case, config=config)
    second = _run(tool, case, config=config)

    assert first["decision"] == second["decision"]
    for catalog in first["nuisance_state_search"]["catalogs"]:
        assert catalog["possible_path_offset_combination_count"] == 4
        assert catalog["evaluated_path_offset_combination_count"] == 3
        assert catalog["path_offset_cartesian_exhausted"] is False
        assert catalog["generated_state_count"] == 3


def test_multipath_adapter_rejects_timing_session_and_scan_identity_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = _tool()
    case = _case(tmp_path, tool)
    _fake_science(monkeypatch, tool)

    with pytest.raises(ValueError, match="align to 100-ms"):
        tool.replay_raw_multipath_window(
            dataset_paths=case["paths"],
            expected_dataset_digests=case["digests"],
            calibration_document=case["calibration"],
            calibration_path=case["calibration_path"],
            expected_calibration_digest=case["calibration_digest"],
            tle_path=case["tle_path"],
            expected_tle_digest=case["tle_digest"],
            catalog_numbers=(10, 20),
            start_utc_ns=START_UTC_NS + 1,
            end_utc_ns=END_UTC_NS,
            observer=ObserverSiteV1(
                latitude_deg=0.0, longitude_deg=0.0, altitude_m=0.0, label="site"
            ),
            config=tool.MultipathReplayConfig(delay_min_s=0.0, delay_max_s=0.0),
        )

    second = copy.deepcopy(case["datasets"][1])
    second["capture"]["session_id"] = "other-session"
    _write(case["paths"][1], second)
    mismatched_session = {
        **case,
        "digests": (case["digests"][0], _digest(case["paths"][1])),
    }
    with pytest.raises(ValueError, match="one nonempty session"):
        _run(tool, mismatched_session)

    duplicate_path = copy.deepcopy(case["datasets"][1])
    duplicate_path["capture"].update(
        {
            key: case["datasets"][0]["capture"][key]
            for key in ("radio_serial", "receiver_id", "stream_id")
        }
    )
    duplicate_path["frequency_binding"]["tuning_tag"] = case["datasets"][0]["frequency_binding"][
        "tuning_tag"
    ]
    _write(case["paths"][1], duplicate_path)
    duplicate_identity = {
        **case,
        "digests": (case["digests"][0], _digest(case["paths"][1])),
    }
    with pytest.raises(ValueError, match="repeat one receiver-path identity"):
        _run(tool, duplicate_identity)

    bad_timing = copy.deepcopy(case["datasets"][1])
    bad_timing["scheduled_probes"][3]["probe_start_utc"]["estimate_utc_ns"] += 1
    _write(case["paths"][1], bad_timing)
    timing_mismatch = {
        **case,
        "digests": (case["digests"][0], _digest(case["paths"][1])),
    }
    with pytest.raises(ValueError, match="UTC disagrees"):
        _run(tool, timing_mismatch)

    # Restore the second input, then point it at the first raw scan.
    second = copy.deepcopy(case["datasets"][1])
    second["source_products"]["scan"] = copy.deepcopy(
        case["datasets"][0]["source_products"]["scan"]
    )
    _write(case["paths"][1], second)
    duplicate_scan = {
        **case,
        "digests": (case["digests"][0], _digest(case["paths"][1])),
    }
    with pytest.raises(ValueError, match="repeat one raw pilot-scan identity"):
        _run(tool, duplicate_scan)
