from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from leo.contracts.digests import canonical_digest  # type: ignore[import-untyped]


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools/associate_cross_dwell_shared_norad.py"
    spec = importlib.util.spec_from_file_location(
        "cross_dwell_shared_norad_adapter_tool",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(path: Path, value: Any) -> str:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _reference(path: Path, digest: str) -> dict[str, str]:
    return {"path": str(path), "file_digest": digest}


def _source(
    tool: ModuleType,
    root: Path,
    *,
    dwell_id: str,
    session_id: str,
    first_utc_ns: int,
    minima: dict[int, float],
    source_mutator: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[Path, str, dict[str, Any]]:
    dwell_root = root / dwell_id
    dwell_root.mkdir()
    scan_path = dwell_root / "scan.json"
    calibration_path = dwell_root / "calibration.json"
    tle_path = dwell_root / "catalog.tle"
    dataset_path = dwell_root / "duration.json"
    scan_document = {
        "schema": "test-pilot-scan",
        "dwell": dwell_id,
        "schema_version": 3,
        "algorithm_version": "standard-pilot-scan-v3",
        "maximum_scored_candidates_per_probe": 10,
        "methods": ["glrt64"],
        "probe_samples": 50,
        "coarse_window_samples": 1_000,
        "subwindow_samples": 100,
        "frequency_coordinate": "baseband_cfo_hz",
        "frequency_reference": "uncalibrated_prior",
    }
    scan_digest = _write(scan_path, scan_document)
    calibration_digest = _write(calibration_path, {"schema": "test-calibration"})
    tle_path.write_text("test TLE bytes\n", encoding="utf-8")
    tle_digest = "sha256:" + hashlib.sha256(tle_path.read_bytes()).hexdigest()
    recording_manifest_digest = (
        "sha256:" + hashlib.sha256(f"manifest:{session_id}".encode()).hexdigest()
    )
    dataset = {
        "schema": "org.leo.research.duration-constrained-satellite-assignment-input/v1",
        "capture": {
            "session_id": session_id,
            "recording_manifest_digest": recording_manifest_digest,
            "stream_id": "stream-0",
            "receiver_id": 0,
            "sample_rate_hz": 10,
            "declared_sample_count": 10,
        },
        "frequency_binding": {
            "tuning_tag": "tuning:test",
            "sky_frequency_hz": 10_000_000_000.0,
        },
        "scheduled_probes": [
            {
                "schedule_ordinal": 0,
                "probe_id": f"{dwell_id}-probe-0",
                "probe_sample_start": 0,
            },
            {
                "schedule_ordinal": 1,
                "probe_id": f"{dwell_id}-probe-1",
                "probe_sample_start": 5,
            },
        ],
        "timing_binding": {
            "first_earliest_utc_ns": first_utc_ns - 100,
            "first_estimate_utc_ns": first_utc_ns,
            "last_latest_utc_ns": first_utc_ns + 2_000_000_000,
        },
    }
    dataset_digest = _write(dataset_path, dataset)

    ordered = sorted(minima.items(), key=lambda item: (item[1], item[0]))
    ranking = [
        {
            "rank": rank,
            "catalog_number": catalog,
            "generated_state_count": 1,
            "best_single_delta_from_null": reduced,
            "best_single_selected": reduced < 0.0,
            "best_single_total_cost": 10.0 + reduced,
            "best_hypothesis_id": "sha256:"
            + hashlib.sha256(f"{dwell_id}:{catalog}".encode()).hexdigest(),
        }
        for rank, (catalog, reduced) in enumerate(ordered, start=1)
    ]
    best_delta = min((item for item in minima.values() if item < 0.0), default=0.0)
    selected = [] if best_delta == 0.0 else [ordered[0][0]]
    replay_config = tool.bounded.raw_replay.RawReplayConfig(
        delay_min_s=0.0,
        delay_max_s=0.0,
        modes_per_delay=1,
    )
    observer = tool.bounded.ObserverSiteV1(
        latitude_deg=0.0,
        longitude_deg=0.0,
        altitude_m=0.0,
        label="test-site",
    )
    evaluation_scope_digest = tool.bounded.screen.member_evaluation_scope_digest(
        duration_dataset_digest=dataset_digest,
        pilot_scan_digest=scan_digest,
        session_id=session_id,
        recording_manifest_digest=recording_manifest_digest,
        stream_id="stream-0",
        receiver_id=0,
        tuning_tag="tuning:test",
        sky_frequency_hz=10_000_000_000.0,
        scheduled_probe_ids=(f"{dwell_id}-probe-0", f"{dwell_id}-probe-1"),
        window_start_s=0.0,
        window_end_s=1.0,
    )
    search_configuration = tool.bounded._search_configuration(
        calibration_schema="test-calibration",
        calibration_digest=calibration_digest,
        tle_digest=tle_digest,
        sky_frequency_hz=10_000_000_000.0,
        pilot_scan_configuration=tool.bounded.screen._pilot_scan_configuration(scan_path),
        observer=observer,
        start_s=0.0,
        end_s=1.0,
        scheduled_probe_count=2,
        cell_count=10,
        evaluation_scope_digest=evaluation_scope_digest,
        config=replay_config,
        catalogue_name_prefix="STARLINK",
        geometry_spacing_s=0.5,
        output_schema=tool.SOURCE_SCHEMA,
        algorithm=tool.SOURCE_ALGORITHM,
    )
    named_catalogs = (10, 20, 30)
    eligible_catalogs = tuple(sorted(minima))
    ineligible_catalogs = tuple(sorted(set(named_catalogs) - set(eligible_catalogs)))
    partition_payload = {
        "schema": tool.SOURCE_IDENTITY_PARTITION_SCHEMA,
        "algorithm": tool.SOURCE_IDENTITY_PARTITION_ALGORITHM,
        "tle_digest": tle_digest,
        "catalogue_name_prefix": "STARLINK",
        "catalogue_object_count": 3,
        "named_catalog_count": len(named_catalogs),
        "eligible_catalog_count": len(eligible_catalogs),
        "named_ineligible_catalog_count": len(ineligible_catalogs),
        "named_catalog_numbers": list(named_catalogs),
        "eligible_catalog_numbers": list(eligible_catalogs),
        "named_ineligible_catalog_numbers": list(ineligible_catalogs),
        "named_catalog_numbers_digest": canonical_digest(list(named_catalogs)),
        "eligible_catalog_numbers_digest": canonical_digest(list(eligible_catalogs)),
        "named_ineligible_catalog_numbers_digest": canonical_digest(list(ineligible_catalogs)),
        "partition_exhausted": True,
        "partition_pruned": False,
        "eligibility_semantics": "named-and-full-window-visible-over-declared-delay-grid",
    }
    identity_partition = {
        **partition_payload,
        "partition_content_digest": canonical_digest(partition_payload),
    }
    source = {
        "schema": tool.SOURCE_SCHEMA,
        "algorithm": tool.SOURCE_ALGORITHM,
        "catalogue_search_performed": True,
        "catalogue_search_avoided_by_global_null_certificate": False,
        "catalogue_search_exact": False,
        "finite_universe_catalogue_search_exact": True,
        "null_vs_any_activation_solved": True,
        "conditional_on_raw_glrt64_inventory": True,
        "conditional_on_full_window_visibility_screen": True,
        "conditional_on_data_proposed_cfo_modes": True,
        "conditional_on_explicit_catalog_shortlist": False,
        "conditional_on_catalogue_screen_shortlist": False,
        "conditional_on_pruned_joint_shortlist": False,
        "conditional_on_pruned_nuisance_state_bank": False,
        "unrestricted_global_exactness_claimed": False,
        "input": {
            "duration_dataset_path": str(dataset_path),
            "duration_dataset_digest": dataset_digest,
            "pilot_scan_path": str(scan_path),
            "pilot_scan_digest": scan_digest,
            "score_calibration_path": str(calibration_path),
            "score_calibration_digest": calibration_digest,
            "tle_path": str(tle_path),
            "tle_digest": tle_digest,
        },
        "window": {
            "start_s": 0.0,
            "end_s": 1.0,
            "cell_duration_s": replay_config.cell_duration_s,
            "cell_count": 10,
            "minimum_active_cells": replay_config.minimum_active_cells,
            "minimum_active_duration_s": replay_config.minimum_active_duration_s,
            "scheduled_probe_count": 2,
        },
        "configuration": asdict(replay_config),
        "observer": {**observer.model_dump(mode="json"), "capture_bound": False},
        "raw_inventory": {
            "declared_post_acquisition_inventory_complete": True,
            "truncated_candidate_count": 0,
        },
        "catalogue_search": {
            "fine_stage": {
                "catalogue_rows_exhausted": True,
                "declared_discrete_delay_grid_exhausted": True,
                "generated_data_proposed_cfo_mode_bank_exhausted": True,
                "delay_grid": [0.0],
                "modes_per_delay": 1,
                "eligible_catalog_count": len(ranking),
                "scored_catalog_count": len(ranking),
                "omitted_eligible_catalog_count": 0,
                "generated_state_count": len(ranking),
                "generated_state_count_upper_bound": len(ranking),
                "negative_catalogue_minimum_count": sum(value < 0.0 for value in minima.values()),
                "all_catalogue_minima_nonactivating": all(
                    value >= 0.0 for value in minima.values()
                ),
                "ranking": ranking,
            },
            "finite_universe": {
                "eligible_catalogue_count": len(ranking),
                "catalogue_identity_scope": "named and full-window-visible",
                "identity_partition_content_digest": identity_partition["partition_content_digest"],
            },
            "separability_proof": {
                "single_satellite_minima_exact_over_generated_states": True,
                "joint_delta_is_sum_of_selected_satellite_reduced_contributions": True,
                "arbitrary_subsets_of_finite_catalogue_universe_covered": True,
                "satellite_and_episode_costs_nonnegative": True,
                "exclusion_group_assignment_capacity": 1,
            },
        },
        "decision": {
            "result_kind": "bounded_exact_null" if not selected else "activation_witness",
            "selected_catalog_numbers": selected,
            "full_persisted_inventory_objective": {
                "null_cost": 10.0,
                "total_cost": 10.0 + best_delta,
                "delta_from_null": best_delta,
            },
        },
        "search_configuration": search_configuration,
        "search_configuration_digest": canonical_digest(search_configuration),
        "catalogue_identity_partition": identity_partition,
        "timing_approximation": {
            "prediction_epoch": "scheduled_probe_start",
            "candidate_local_epoch_applied": False,
        },
    }
    if source_mutator is not None:
        source_mutator(source)
    source_path = dwell_root / "source.json"
    source_digest = _write(source_path, source)
    return (
        source_path,
        source_digest,
        {
            "dataset_path": dataset_path,
            "dataset_digest": dataset_digest,
            "scan_path": scan_path,
            "scan_digest": scan_digest,
            "calibration_path": calibration_path,
            "calibration_digest": calibration_digest,
            "tle_path": tle_path,
            "tle_digest": tle_digest,
            "session_id": session_id,
            "first_utc_ns": first_utc_ns,
        },
    )


def _control(
    tool: ModuleType,
    root: Path,
    *,
    dwell_id: str,
    nested: dict[str, Any],
    catalogs: list[int],
    selected: list[int],
    passed: bool,
    comparable: bool = True,
) -> tuple[Path, str, dict[str, Any]]:
    disposition = (
        "bounded_prediction_time_gate_pass"
        if passed
        else ("deranged_activation_witness" if comparable else "not_comparable")
    )
    adjudication = {
        "disposition": disposition,
        "comparable": comparable,
        "paired_gate_passed": passed,
        "specificity_claimed": False,
    }
    document = {
        "schema": tool.paired.OUTPUT_SCHEMA,
        "algorithm": tool.paired.ALGORITHM,
        "input": {
            "session_id": nested["session_id"],
            "score_calibration_path": str(nested["calibration_path"]),
            "score_calibration_digest": nested["calibration_digest"],
            "tle_path": str(nested["tle_path"]),
            "tle_digest": nested["tle_digest"],
            "duration_inputs": [
                {
                    "path": str(nested["dataset_path"]),
                    "file_digest": nested["dataset_digest"],
                    "pilot_scan_path": str(nested["scan_path"]),
                    "pilot_scan_digest": nested["scan_digest"],
                    "pilot_scan_content_digest": canonical_digest(
                        json.loads(nested["scan_path"].read_text(encoding="utf-8"))
                    ),
                }
            ],
        },
        "window": {
            "start_utc_ns": nested["first_utc_ns"],
            "end_utc_ns": nested["first_utc_ns"] + 1_000_000_000,
        },
        "common": {
            "family_plan": {
                "minimum_advantage_cost": 1.0,
                "advantage_threshold_calibrated": True,
                "external_preregistration_verified": True,
            },
            "search_universe": {
                "catalogs": [{"catalog_number": item} for item in catalogs],
            },
        },
        "arms": [
            {
                "role": "identity",
                "decision": {"selected_catalog_numbers": selected},
            },
            {"role": "block_permutation_control", "decision": {}},
        ],
        "adjudication": adjudication,
    }
    path = root / dwell_id / "control.json"
    digest = _write(path, document)
    return path, digest, adjudication


def _build_request(
    tool: ModuleType,
    tmp_path: Path,
    *,
    passed_controls: bool = True,
    no_controls: bool = False,
    duplicate_session: bool = False,
    source_mutator: Callable[[dict[str, Any]], None] | None = None,
    universe_catalogs: list[int] | None = None,
    minimum_improvement: float = 0.0,
) -> tuple[Path, str, dict[str, Any]]:
    sources = []
    nested_rows = []
    controls = []
    for index, (dwell_id, minima) in enumerate(
        (("d1", {10: -3.0, 20: 0.0}), ("d2", {10: -4.0, 30: 0.0}))
    ):
        session_id = "session-a" if index == 0 or duplicate_session else "session-b"
        source_path, source_digest, nested = _source(
            tool,
            tmp_path,
            dwell_id=dwell_id,
            session_id=session_id,
            first_utc_ns=100_000_000_000 + index * 10_000_000_000,
            minima=minima,
            source_mutator=source_mutator if index == 0 else None,
        )
        if no_controls:
            control_rows: list[tuple[Path, str, dict[str, Any]]] = []
        else:
            control_rows = [
                _control(
                    tool,
                    tmp_path,
                    dwell_id=dwell_id,
                    nested=nested,
                    catalogs=[10, 20 if index == 0 else 30],
                    selected=[10],
                    passed=passed_controls,
                )
            ]
        sources.append((dwell_id, source_path, source_digest))
        nested_rows.append(nested)
        controls.append(control_rows)

    union_path = tmp_path / "universe.json"
    union = {
        "schema": tool.UNIVERSE_SCHEMA,
        "algorithm": tool.UNIVERSE_ALGORITHM,
        "catalog_numbers": universe_catalogs or [10, 20, 30],
        "expected_catalog_count": len(universe_catalogs or [10, 20, 30]),
        "candidate_universe_exhausted": True,
        "candidate_universe_pruned": False,
        "source_artifacts": [
            {"dwell_id": dwell_id, "file_digest": digest} for dwell_id, _path, digest in sources
        ],
        "frozen_at_utc_ns": 90_000_000_000,
        "selection_frozen_before_reduction": True,
        "external_preregistration_verified": False,
    }
    union_digest = _write(union_path, union)

    request_dwells = []
    for (dwell_id, source_path, source_digest), nested, control_rows in zip(
        sources, nested_rows, controls, strict=True
    ):
        qualification_path = tmp_path / dwell_id / "qualification.json"
        qualification = {
            "schema": tool.QUALIFICATION_SCHEMA,
            "dwell_id": dwell_id,
            "source_artifact_file_digest": source_digest,
            "session_id": nested["session_id"],
            "tle_snapshot": {
                "file_digest": nested["tle_digest"],
                "authority": "test-causal-authority",
                "authority_snapshot_id": f"snapshot-{dwell_id}",
                "snapshot_acquired_utc_ns": nested["first_utc_ns"] - 2_000_000_000,
                "available_to_analysis_utc_ns": nested["first_utc_ns"] - 1_000_000_000,
            },
            "timing": {
                "duration_dataset_file_digest": nested["dataset_digest"],
                "authority": "test-capture-clock",
                "first_estimate_utc_ns": nested["first_utc_ns"],
                "window_start_utc_ns": nested["first_utc_ns"],
                "window_end_utc_ns": nested["first_utc_ns"] + 1_000_000_000,
                "capture_clock_binding_verified": True,
            },
            "control_artifact_file_digests": [item[1] for item in control_rows],
        }
        qualification_digest = _write(qualification_path, qualification)
        request_dwells.append(
            {
                "dwell_id": dwell_id,
                "source_artifact": _reference(source_path, source_digest),
                "qualification_receipt": _reference(
                    qualification_path,
                    qualification_digest,
                ),
                "control_artifacts": [
                    _reference(path, digest) for path, digest, _adjudication in control_rows
                ],
            }
        )
    request = {
        "schema": tool.REQUEST_SCHEMA,
        "association_id": "test-cross-dwell",
        "candidate_universe": _reference(union_path, union_digest),
        "dwells": request_dwells,
        "required_confirmation_dwell_ids": ["d1", "d2"],
        "minimum_distinct_session_count": 2,
        "shared_identity_cost": 1.0,
        "minimum_association_improvement_cost": minimum_improvement,
    }
    request_path = tmp_path / "request.json"
    request_digest = _write(request_path, request)
    return request_path, request_digest, request


def _install_adjudicator_stub(
    tool: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def adjudicate(**keywords: Any) -> dict[str, Any]:
        calls.append(keywords)
        identity = keywords["arms"][0]
        passed = bool(identity["decision"]["selected_catalog_numbers"])
        return {
            "disposition": (
                "bounded_prediction_time_gate_pass" if passed else "identity_nonactivation"
            ),
            "comparable": True,
            "paired_gate_passed": passed,
            "specificity_claimed": False,
        }

    monkeypatch.setattr(tool.paired, "adjudicate_paired_arms", adjudicate)
    return calls


def _freeze_spec(
    tool: ModuleType,
    tmp_path: Path,
    *,
    with_controls: bool = False,
) -> tuple[Path, str]:
    sources = []
    for index, (dwell_id, minima) in enumerate(
        (("d1", {10: -3.0, 20: 0.0}), ("d2", {10: -4.0, 30: 0.0}))
    ):
        source_path, source_digest, nested = _source(
            tool,
            tmp_path,
            dwell_id=dwell_id,
            session_id="session-a" if index == 0 else "session-b",
            first_utc_ns=100_000_000_000 + index * 10_000_000_000,
            minima=minima,
        )
        source_row: dict[str, Any] = {
            "dwell_id": dwell_id,
            "source_artifact": _reference(source_path, source_digest),
            "tle_snapshot": {
                "file_digest": nested["tle_digest"],
                "authority": "test-causal-authority",
                "authority_snapshot_id": f"snapshot-{dwell_id}",
                "snapshot_acquired_utc_ns": nested["first_utc_ns"] - 2_000_000_000,
                "available_to_analysis_utc_ns": nested["first_utc_ns"] - 1_000_000_000,
            },
            "timing": {
                "duration_dataset_file_digest": nested["dataset_digest"],
                "authority": "test-capture-clock",
                "first_estimate_utc_ns": nested["first_utc_ns"],
                "window_start_utc_ns": nested["first_utc_ns"],
                "window_end_utc_ns": nested["first_utc_ns"] + 1_000_000_000,
                "capture_clock_binding_verified": True,
            },
        }
        if with_controls:
            control_path, control_digest, _adjudication = _control(
                tool,
                tmp_path,
                dwell_id=dwell_id,
                nested=nested,
                catalogs=list(minima),
                selected=[10],
                passed=True,
            )
            source_row["control_artifacts"] = [_reference(control_path, control_digest)]
        sources.append(source_row)
    spec = {
        "schema": (tool.FREEZE_SPEC_SCHEMA_V2 if with_controls else tool.FREEZE_SPEC_SCHEMA),
        "association_id": "test-frozen-association",
        "frozen_at_utc_ns": 90_000_000_000,
        "sources": sources,
        "required_confirmation_dwell_ids": ["d1", "d2"],
        "minimum_distinct_session_count": 2,
        "shared_identity_cost": 1.0,
        "minimum_association_improvement_cost": 0.0,
    }
    spec_path = tmp_path / "freeze-spec.json"
    return spec_path, _write(spec_path, spec)


def test_freezer_derives_union_and_emits_explicit_zero_control_unknowns(
    tmp_path: Path,
) -> None:
    tool = _tool()
    spec_path, spec_digest = _freeze_spec(tool, tmp_path)
    output_directory = tmp_path / "frozen"

    frozen = tool.freeze_cross_dwell_request(
        spec_path=spec_path,
        expected_spec_digest=spec_digest,
        output_directory=output_directory,
    )
    document = tool.associate_cross_dwell_shared_norad(
        request_path=Path(frozen["request_path"]),
        expected_request_digest=frozen["request_file_digest"],
    )

    assert frozen["manifest"]["controls_status"] == ("unknown_no_control_artifacts_supplied")
    assert frozen["manifest"]["catalog_count"] == 3
    assert document["candidate_universe"]["catalog_numbers"] == [10, 20, 30]
    assert document["disposition"] == "unknown_control_evidence"
    assert not document["association_claimed"]
    for path in output_directory.glob("*.qualification.json"):
        qualification = json.loads(path.read_text(encoding="utf-8"))
        assert qualification["control_artifact_file_digests"] == []
    with pytest.raises(ValueError, match="will not be overwritten"):
        tool.freeze_cross_dwell_request(
            spec_path=spec_path,
            expected_spec_digest=spec_digest,
            output_directory=output_directory,
        )


def test_freezer_v2_recomputes_and_propagates_digest_bound_controls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()
    _install_adjudicator_stub(tool, monkeypatch)
    spec_path, spec_digest = _freeze_spec(tool, tmp_path, with_controls=True)
    output_directory = tmp_path / "frozen-controls"

    frozen = tool.freeze_cross_dwell_request(
        spec_path=spec_path,
        expected_spec_digest=spec_digest,
        output_directory=output_directory,
    )
    request = json.loads(Path(frozen["request_path"]).read_text(encoding="utf-8"))

    assert frozen["manifest"]["controls_status"] == "recomputed_control_artifacts_supplied"
    assert frozen["manifest"]["control_artifact_count"] == 2
    assert all(len(item["control_artifacts"]) == 1 for item in request["dwells"])
    for item in request["dwells"]:
        qualification = json.loads(
            Path(item["qualification_receipt"]["path"]).read_text(encoding="utf-8")
        )
        assert qualification["control_artifact_file_digests"] == [
            item["control_artifacts"][0]["file_digest"]
        ]


def test_freezer_refuses_protected_output_roots() -> None:
    tool = _tool()
    with pytest.raises(ValueError, match="/srv"):
        tool._refuse_protected_write(Path("/srv/leo-cross-dwell"))
    with pytest.raises(ValueError, match="/mnt/qnap01"):
        tool._refuse_protected_write(Path("/mnt/qnap01/leo-cross-dwell"))


def test_adapter_reduces_exact_union_and_marks_absent_catalogs_ineligible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()
    calls = _install_adjudicator_stub(tool, monkeypatch)
    request_path, request_digest, _request = _build_request(tool, tmp_path)

    document = tool.associate_cross_dwell_shared_norad(
        request_path=request_path,
        expected_request_digest=request_digest,
    )

    assert document["disposition"] == "association"
    assert document["association_claimed"]
    assert document["association_not_tracking"]
    assert not document["tracking_claimed"]
    assert document["claim"]["catalog_number"] == 10
    assert document["claim"]["scope"] == "association_not_tracking"
    assert document["reducer_result"]["reduced_objective"] == -6.0
    rows = document["finite_state_matrix"]["rows"]
    assert len(rows) == 6
    assert (
        next(item for item in rows if item["dwell_id"] == "d1" and item["catalog_number"] == 30)[
            "eligibility"
        ]
        == "certified_ineligible"
    )
    assert (
        next(item for item in rows if item["dwell_id"] == "d2" and item["catalog_number"] == 20)[
            "eligibility"
        ]
        == "certified_ineligible"
    )
    assert not document["finite_state_matrix"]["unknown_rows"]
    assert len(calls) == 2


def test_absent_controls_are_unknown_not_certified_null(
    tmp_path: Path,
) -> None:
    tool = _tool()
    request_path, request_digest, _request = _build_request(
        tool,
        tmp_path,
        no_controls=True,
    )

    document = tool.associate_cross_dwell_shared_norad(
        request_path=request_path,
        expected_request_digest=request_digest,
    )

    assert document["disposition"] == "unknown_control_evidence"
    assert not document["association_claimed"]
    assert document["reducer_result"]["selected_catalog_number"] == 10
    assert all(
        item["status"] == "unknown"
        for item in document["selected_contribution_qualification"]["rows"]
    )


def test_failed_controls_block_the_association_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()

    def failed_adjudication(**_keywords: Any) -> dict[str, Any]:
        return {
            "disposition": "deranged_activation_witness",
            "comparable": True,
            "paired_gate_passed": False,
            "specificity_claimed": False,
        }

    monkeypatch.setattr(tool.paired, "adjudicate_paired_arms", failed_adjudication)
    request_path, request_digest, request = _build_request(
        tool,
        tmp_path,
        passed_controls=False,
    )

    document = tool.associate_cross_dwell_shared_norad(
        request_path=request_path,
        expected_request_digest=request_digest,
    )

    assert request["shared_identity_cost"] == 1.0
    assert document["disposition"] == "qualification_failed"
    assert not document["association_claimed"]
    assert all(
        item["status"] == "failed"
        for item in document["selected_contribution_qualification"]["rows"]
    )


def test_frozen_improvement_threshold_is_strict_and_persisted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()
    _install_adjudicator_stub(tool, monkeypatch)
    request_path, request_digest, _request = _build_request(
        tool,
        tmp_path,
        minimum_improvement=6.0,
    )

    document = tool.associate_cross_dwell_shared_norad(
        request_path=request_path,
        expected_request_digest=request_digest,
    )

    assert document["disposition"] == "association_threshold_not_met"
    assert not document["association_claimed"]
    assert document["reducer_problem"]["minimum_association_improvement_cost"] == 6.0


@pytest.mark.parametrize(
    "mutator",
    [
        lambda source: source.__setitem__("conditional_on_explicit_catalog_shortlist", True),
        lambda source: source.__setitem__("conditional_on_pruned_nuisance_state_bank", True),
        lambda source: source["catalogue_search"]["fine_stage"].__setitem__(
            "catalogue_rows_exhausted", False
        ),
        lambda source: source["catalogue_search"]["fine_stage"].__setitem__(
            "omitted_eligible_catalog_count", 1
        ),
    ],
)
def test_shortlisted_pruned_unexhausted_or_omitted_source_is_unknown(
    tmp_path: Path,
    mutator: Callable[[dict[str, Any]], None],
) -> None:
    tool = _tool()
    request_path, request_digest, _request = _build_request(
        tool,
        tmp_path,
        no_controls=True,
        source_mutator=mutator,
    )

    with pytest.raises(tool.IncompleteAdapterEvidenceError):
        tool.associate_cross_dwell_shared_norad(
            request_path=request_path,
            expected_request_digest=request_digest,
        )


def test_v1_source_without_identity_partition_is_unknown(tmp_path: Path) -> None:
    tool = _tool()

    def downgrade(source: dict[str, Any]) -> None:
        source["schema"] = "org.leo.research.raw-catalogue-bounded-null-vs-any/v1"
        source["algorithm"] = "bounded-exact-all-eligible-fine-null-vs-any-v1"

    request_path, request_digest, _request = _build_request(
        tool,
        tmp_path,
        no_controls=True,
        source_mutator=downgrade,
    )
    with pytest.raises(tool.IncompleteAdapterEvidenceError, match="bounded all-eligible"):
        tool.associate_cross_dwell_shared_norad(
            request_path=request_path,
            expected_request_digest=request_digest,
        )


def test_current_producer_manifest_is_recomputed_not_trusted(tmp_path: Path) -> None:
    tool = _tool()

    def forge_manifest(source: dict[str, Any]) -> None:
        source["search_configuration"]["producer_implementation"]["wrapper"]["digest"] = (
            "sha256:" + "0" * 64
        )
        source["search_configuration_digest"] = canonical_digest(source["search_configuration"])

    request_path, request_digest, _request = _build_request(
        tool,
        tmp_path,
        no_controls=True,
        source_mutator=forge_manifest,
    )
    with pytest.raises(ValueError, match="producer implementation manifest"):
        tool.associate_cross_dwell_shared_norad(
            request_path=request_path,
            expected_request_digest=request_digest,
        )


def test_frozen_union_must_equal_the_exact_union_of_eligible_rows(tmp_path: Path) -> None:
    tool = _tool()
    request_path, request_digest, _request = _build_request(
        tool,
        tmp_path,
        no_controls=True,
        universe_catalogs=[10, 20],
    )

    with pytest.raises(tool.IncompleteAdapterEvidenceError, match="exact union"):
        tool.associate_cross_dwell_shared_norad(
            request_path=request_path,
            expected_request_digest=request_digest,
        )


def test_sessions_must_be_unique_even_when_dwell_ids_are_unique(tmp_path: Path) -> None:
    tool = _tool()
    request_path, request_digest, _request = _build_request(
        tool,
        tmp_path,
        no_controls=True,
        duplicate_session=True,
    )

    with pytest.raises(tool.IncompleteAdapterEvidenceError, match="unique session"):
        tool.associate_cross_dwell_shared_norad(
            request_path=request_path,
            expected_request_digest=request_digest,
        )


def test_source_bytes_are_checked_before_any_summary_is_trusted(tmp_path: Path) -> None:
    tool = _tool()
    request_path, request_digest, request = _build_request(tool, tmp_path, no_controls=True)
    source_path = Path(request["dwells"][0]["source_artifact"]["path"])
    source_path.write_bytes(source_path.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="source artifact file digest mismatch"):
        tool.associate_cross_dwell_shared_norad(
            request_path=request_path,
            expected_request_digest=request_digest,
        )


def test_request_digest_and_duplicate_json_keys_fail_before_reduction(tmp_path: Path) -> None:
    tool = _tool()
    request_path, request_digest, _request = _build_request(tool, tmp_path, no_controls=True)
    with pytest.raises(ValueError, match="request digest mismatch"):
        tool.associate_cross_dwell_shared_norad(
            request_path=request_path,
            expected_request_digest="sha256:" + "0" * 64,
        )

    duplicate_path = tmp_path / "duplicate.json"
    duplicate_path.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
    duplicate_digest = "sha256:" + hashlib.sha256(duplicate_path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="duplicate JSON object key"):
        tool.associate_cross_dwell_shared_norad(
            request_path=duplicate_path,
            expected_request_digest=duplicate_digest,
        )


def test_causal_tle_must_be_available_before_the_dwell_window(tmp_path: Path) -> None:
    tool = _tool()
    request_path, _request_digest, request = _build_request(tool, tmp_path, no_controls=True)
    receipt_ref = request["dwells"][0]["qualification_receipt"]
    receipt_path = Path(receipt_ref["path"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["tle_snapshot"]["available_to_analysis_utc_ns"] = (
        receipt["timing"]["window_start_utc_ns"] + 1
    )
    receipt_digest = _write(receipt_path, receipt)
    receipt_ref["file_digest"] = receipt_digest
    request_digest = _write(request_path, request)

    with pytest.raises(tool.IncompleteAdapterEvidenceError, match="causally available"):
        tool.associate_cross_dwell_shared_norad(
            request_path=request_path,
            expected_request_digest=request_digest,
        )


def test_control_adjudication_must_recompute_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()
    request_path, request_digest, _request = _build_request(tool, tmp_path)
    monkeypatch.setattr(
        tool.paired,
        "adjudicate_paired_arms",
        lambda **_keywords: {
            "disposition": "not_comparable",
            "comparable": False,
            "paired_gate_passed": False,
            "specificity_claimed": False,
        },
    )

    with pytest.raises(ValueError, match="does not recompute exactly"):
        tool.associate_cross_dwell_shared_norad(
            request_path=request_path,
            expected_request_digest=request_digest,
        )


@pytest.mark.parametrize(
    ("disposition", "identity_selected", "scientific_failed", "expected_disposition"),
    (
        ("target_selection_causality_not_verified", [10], False, "unknown_control_evidence"),
        ("block_permutation_control_activation", [10], True, "qualification_failed"),
        ("identity_nonactivation", [], True, "qualification_failed"),
    ),
)
def test_fixed_target_controls_separate_authority_unknown_from_scientific_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    disposition: str,
    identity_selected: list[int],
    scientific_failed: bool,
    expected_disposition: str,
) -> None:
    tool = _tool()
    source_path, source_digest, nested = _source(
        tool,
        tmp_path,
        dwell_id="d1",
        session_id="session-a",
        first_utc_ns=100_000_000_000,
        minima={10: -3.0},
    )
    adjudication = {
        "disposition": disposition,
        "comparable": True,
        "association_authority_comparable": False,
        "paired_gate_passed": False,
        "conditional_fixed_target_gate_passed": False,
        "conditional_comparison_completed": True,
        "conditional_control_test_failed": scientific_failed,
        "specificity_claimed": False,
    }
    document = {
        "schema": tool.fixed_target.OUTPUT_SCHEMA,
        "algorithm": tool.fixed_target.ALGORITHM,
        "input": {
            "session_id": nested["session_id"],
            "source_artifact_file_digest": source_digest,
            "score_calibration_path": str(nested["calibration_path"]),
            "score_calibration_digest": nested["calibration_digest"],
            "tle_path": str(nested["tle_path"]),
            "tle_digest": nested["tle_digest"],
            "duration_inputs": [
                {
                    "path": str(nested["dataset_path"]),
                    "file_digest": nested["dataset_digest"],
                    "pilot_scan_path": str(nested["scan_path"]),
                    "pilot_scan_digest": nested["scan_digest"],
                    "pilot_scan_content_digest": canonical_digest(
                        json.loads(nested["scan_path"].read_text(encoding="utf-8"))
                    ),
                }
            ],
        },
        "window": {
            "start_utc_ns": nested["first_utc_ns"],
            "end_utc_ns": nested["first_utc_ns"] + 1_000_000_000,
        },
        "common": {
            "family_plan": {
                "minimum_advantage_cost": 0.0,
                "advantage_threshold_calibrated": False,
                "external_preregistration_verified": False,
            },
            "search_universe": {"target_catalog_number": 10},
        },
        "arms": [
            {
                "role": "identity",
                "decision": {"selected_catalog_numbers": identity_selected},
            },
            {"role": "block_permutation_control", "decision": {}},
        ],
        "adjudication": adjudication,
    }
    document["payload_content_digest"] = canonical_digest(document)
    control_path = tmp_path / "fixed-target-control.json"
    control_digest = _write(control_path, document)
    monkeypatch.setattr(
        tool.fixed_target,
        "adjudicate_fixed_norad_arms",
        lambda **_keywords: adjudication,
    )
    evidence = tool._validated_control(
        reference=tool._FileReference(control_path, control_digest),
        dwell_id="d1",
        session_id=nested["session_id"],
        source_dataset_digest=nested["dataset_digest"],
        source_artifact_digest=source_digest,
        source_tle_digest=nested["tle_digest"],
        window_start_utc_ns=nested["first_utc_ns"],
        window_end_utc_ns=nested["first_utc_ns"] + 1_000_000_000,
    )

    assert evidence.fixed_target is True
    assert evidence.comparable is False
    assert evidence.scientific_control_failed is scientific_failed
    result = SimpleNamespace(
        selected_catalog_number=10,
        reduced_objective=-3.0,
        contributions=(SimpleNamespace(dwell_id="d1", active=True),),
    )
    observed_disposition, rows, _reasons = tool._qualification_for_selected(
        result=result,
        dwells=(SimpleNamespace(dwell_id="d1", controls=(evidence,)),),
        minimum_association_improvement_cost=0.0,
    )
    assert observed_disposition == expected_disposition
    assert rows[0]["status"] == (
        "failed" if expected_disposition == "qualification_failed" else "unknown"
    )


def test_output_payload_digest_recomputes_without_the_digest_field(
    tmp_path: Path,
) -> None:
    tool = _tool()
    request_path, request_digest, _request = _build_request(tool, tmp_path, no_controls=True)
    document = tool.associate_cross_dwell_shared_norad(
        request_path=request_path,
        expected_request_digest=request_digest,
    )
    observed = document.pop("payload_content_digest")
    assert canonical_digest(document) == observed


def test_cli_help_is_available() -> None:
    tool = _tool()
    assert callable(tool.main)
