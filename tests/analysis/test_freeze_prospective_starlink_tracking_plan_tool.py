from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from leo.contracts.digests import canonical_digest  # type: ignore[import-untyped]


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools/freeze_prospective_starlink_tracking_plan.py"
    spec = importlib.util.spec_from_file_location(
        "freeze_prospective_starlink_tracking_plan_tool",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TOOL = _tool()
TLE = """STARLINK-1008
1 44714U 19074B   26232.62719907  .00001103  00000-0  92799-4 0  9992
2 44714  53.0537 172.0234 0001334  87.1234 273.0021 15.06393004260127
"""
ACQUIRED_UTC_NS = 1_787_270_400_000_000_000
AVAILABLE_UTC_NS = ACQUIRED_UTC_NS + 1_000_000_000
FROZEN_UTC_NS = 1_787_688_000_000_000_000
ISSUED_UTC_NS = FROZEN_UTC_NS + 60_000_000_000
NOT_BEFORE_UTC_NS = FROZEN_UTC_NS + 3_600_000_000_000


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, document: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(document, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _calibration(tool: ModuleType) -> dict[str, Any]:
    return {
        "schema": tool.raw_replay.CALIBRATION_SCHEMA_V1,
        "score_threshold": 0.1,
        "detection_probability": 0.75,
        "pseudocount": 1.0,
        "null": {"positive_count": 0, "total_count": 1_000},
        "signal": {"positive_count": 1_000, "total_count": 1_000},
        "sources": {
            "disjoint_pilot_scan_digests": True,
            "null": [{"file_digest": "sha256:" + "1" * 64}],
            "signal": [{"pilot_scan": {"file_digest": "sha256:" + "2" * 64}}],
        },
    }


def _pilot_configuration() -> dict[str, Any]:
    return {
        "schema_version": 3,
        "algorithm_version": "standard-pilot-scan-v3",
        "maximum_scored_candidates_per_probe": 10,
        "methods": ["anchor8", "glrt64", "symbolwise"],
        "probe_samples": 50,
        "coarse_window_samples": 1_000,
        "subwindow_samples": 100,
        "frequency_coordinate": "baseband_cfo_hz",
        "frequency_reference": "uncalibrated_prior",
    }


def _proposal(
    tool: ModuleType,
    *,
    tle_path: Path,
    calibration_path: Path,
) -> dict[str, Any]:
    raw_config = asdict(
        tool.raw_replay.RawReplayConfig(
            resolution_epoch_tolerance_samples=0,
            resolution_tracking_cfo_tolerance_hz=0.0,
        )
    )
    stable_path_tuple = [
        "standard-primary",
        "radio-a",
        "synthetic-radio-001",
        0,
        "ku-a",
        11.325e9,
    ]
    primary_path_scope = {
        "algorithm": tool.PRIMARY_PATH_POLICY_ALGORITHM,
        "path_id": canonical_digest(stable_path_tuple),
        "stream_id": "standard-primary",
        "radio_id": "radio-a",
        "radio_serial": "synthetic-radio-001",
        "receiver_id": 0,
        "tuning_tag": "ku-a",
        "sky_frequency_hz": 11.325e9,
    }
    return {
        "plan_id": "synthetic-prospective-starlink-001",
        "frozen_at_utc_ns": FROZEN_UTC_NS,
        "future_evidence_not_before_utc_ns": NOT_BEFORE_UTC_NS,
        "tle": {
            "path": str(tle_path),
            "file_digest": _digest(tle_path),
            "maximum_snapshot_age_at_dwell_s": 7 * 24 * 60 * 60,
        },
        "score_calibration": {
            "path": str(calibration_path),
            "file_digest": _digest(calibration_path),
            "schema": tool.raw_replay.CALIBRATION_SCHEMA_V1,
        },
        "observer": {
            "schema_version": 1,
            "latitude_deg": 37.0,
            "longitude_deg": -122.0,
            "altitude_m": 25.0,
            "label": "synthetic-observer",
        },
        "future_dwell_window_policy": {
            "algorithm": tool.WINDOW_POLICY_ALGORITHM,
            "required_input_schema": tool.INPUT_SCHEMA,
            "required_seal_status": "sealed",
            "required_tuning_tag": "ku-a",
            "required_sky_frequency_hz": 11.325e9,
            "start_offset_s": 50.0,
            "duration_s": 10.0,
            "scheduled_probe_count": 400,
            "cell_count": 100,
            "complete_scheduled_probe_inventory_required": True,
            "post_acquisition_persisted_inventory_untruncated_required": True,
            "pre_acquisition_candidate_inventory_complete": False,
            "physical_raw_candidate_inventory_complete": False,
            "upstream_candidate_cap_saturation_must_be_reported": True,
            "capture_clock_binding_required": True,
            "recording_manifest_digest_binding_required": True,
            "future_product_paths_predeclared": False,
            "primary_path": {
                **primary_path_scope,
                "path_scope_digest": canonical_digest(primary_path_scope),
                "inferential_path_count": 1,
                "score_based_path_selection_permitted": False,
                "other_receiver_paths_role": "noninferential-diagnostics-only",
                "all_path_inference_requires_separately_bound_producer": True,
            },
        },
        "pilot_scan_configuration": _pilot_configuration(),
        "raw_replay_configuration": raw_config,
        "catalogue_screen": {
            "output_schema": tool.bounded.OUTPUT_SCHEMA_V2,
            "algorithm": tool.bounded.ALGORITHM_V2,
            "catalogue_name_prefix": "STARLINK",
            "geometry_spacing_s": 0.5,
            "full_window_visibility_required": True,
            "identity_partition_required": True,
            "every_eligible_catalogue_scored_on_complete_fine_bank": True,
            "shortlist_or_catalogue_pruning_permitted": False,
            "nuisance_state_pruning_permitted": False,
        },
        "paired_full_catalogue_producer": {
            "output_schema": tool.PAIRED_OUTPUT_SCHEMA,
            "algorithm": tool.PAIRED_ALGORITHM,
            "implementation_path": tool.PAIRED_IMPLEMENTATION_PATH,
            "implementation_manifest_digest": None,
            "implementation_binding_status": "required-before-first-future-dwell",
        },
        "prediction_time_randomization": {
            "algorithm": tool.BLOCK_PERMUTATION_ALGORITHM,
            "control_indices": list(range(20)),
            "block_duration_s": 0.5,
            "maximum_delay_support_s": 2.0,
            "randomization_p_value_formula": tool.RANDOMIZATION_FORMULA,
            "randomization_exchangeability_verified": False,
            "rerun_full_catalogue_selection_in_every_arm": True,
            "same_observations_and_objective_in_every_arm": True,
            "only_prediction_epoch_mapping_varies_between_arms": True,
            "ties_count_against_identity": True,
        },
        "decision_thresholds": {
            "beta_association_cost": 100.0,
            "mu_catalogue_runner_margin_cost": 50.0,
            "gamma_cohort_control_margin_cost": 75.0,
            "gamma_dwell_control_margin_cost": 25.0,
            "all_comparisons_are_strict": True,
            "equality_passes_any_threshold": False,
            "thresholds_frozen_before_future_evidence": True,
        },
        "presence_qualification": {
            "natural_capture_wide_null": {
                "receipt_schema": tool.PRESENCE_NULL_RECEIPT_SCHEMA,
                "algorithm": tool.PRESENCE_NULL_QUALIFICATION_ALGORITHM,
                "minimum_independent_capture_count": 59,
                "required_false_activation_count": 0,
                "maximum_familywise_false_activation_rate": 0.05,
                "confidence_level": 0.95,
                "natural_unmodified_captures_required": True,
                "sources_disjoint_from_future_tracking_evidence": True,
            },
            "positive_sensitivity": {
                "receipt_schema": tool.POSITIVE_SENSITIVITY_RECEIPT_SCHEMA,
                "algorithm": tool.POSITIVE_SENSITIVITY_QUALIFICATION_ALGORITHM,
                "minimum_independent_capture_count": 29,
                "required_detected_capture_count": 29,
                "minimum_detection_probability_lower_bound": 0.9,
                "confidence_level": 0.95,
                "independent_known_positive_or_injection_required": True,
                "sources_disjoint_from_future_tracking_evidence": True,
            },
            "block_controls_calibrate_presence_false_positive_rate": False,
            "both_qualifications_required_before_association": True,
        },
        "cross_session_promotion": {
            "minimum_association_distinct_session_count": 2,
            "minimum_tracking_prediction_session_count": 2,
            "candidate_after_first_passing_full_selection_dwell": True,
            "association_requires_same_norad_from_full_selection_in_every_session": True,
            "association_sessions_must_have_distinct_recording_manifests": True,
            "tracking_requires_target_lock_before_later_session": True,
            "tracking_later_session_uses_fixed_norad_without_catalogue_reselection": True,
            "tracking_session_must_be_distinct_and_chronologically_later": True,
            "maximum_consecutive_coasting_sessions": 2,
            "maximum_tracking_horizon_s": 86_400.0,
            "initial_tracking_confirmation_uses_exact_frozen_holdout_ordinals": True,
            "initial_hold_nonactivation_consumes_ordinal_and_cannot_be_replaced": True,
            "coasting_only_after_confirmed_under_separately_frozen_monitoring_schedule": True,
            "post_confirmation_nonactivation_advances_coasting_not_lost": True,
            "lost_requires_positive_contradiction_or_coast_limit_exceeded": True,
            "invalid_provenance_or_incomplete_artifact_rejected_without_counter_mutation": True,
            (
                "valid_identity_control_margin_failure_wrong_identity_or_"
                "innovation_rejection_means_lost"
            ): True,
            "weaker_control_activation_alone_is_not_loss": True,
            "target_lock_receipt_schema": tool.TARGET_LOCK_RECEIPT_SCHEMA,
            "prediction_confirmation_receipt_schema": (tool.PREDICTION_CONFIRMATION_RECEIPT_SCHEMA),
        },
        "prospective_cohort_policy": {
            "algorithm": tool.COHORT_POLICY_ALGORITHM,
            "total_eligible_dwell_count": 4,
            "association_selection_dwell_count": 2,
            "tracking_prediction_holdout_dwell_count": 2,
            "chronological_order_keys": [
                "sealed_at_utc_ns",
                "session_id",
                "recording_manifest_digest",
            ],
            "take_first_eligible_dwells_in_order": True,
            "association_and_holdout_roles_are_contiguous": True,
            "replacement_after_analysis_permitted": False,
            "optional_stopping_permitted": False,
            "every_frozen_ordinal_must_be_adjudicated": True,
        },
    }


def _specification(
    tmp_path: Path,
    *,
    mutate_proposal: Callable[[dict[str, Any]], None] | None = None,
    mutate_tle_receipt: Callable[[dict[str, Any]], None] | None = None,
    mutate_chronology: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[Path, dict[str, Any], Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    tle_path = tmp_path / "synthetic-starlink.tle"
    tle_path.write_text(TLE, encoding="utf-8")
    calibration_path = tmp_path / "synthetic-calibration.json"
    _write_json(calibration_path, _calibration(TOOL))
    proposal = _proposal(TOOL, tle_path=tle_path, calibration_path=calibration_path)
    if mutate_proposal is not None:
        mutate_proposal(proposal)

    tle_receipt = {
        "schema": TOOL.TLE_AUTHORITY_RECEIPT_SCHEMA,
        "authority": "synthetic-tle-authority",
        "authority_snapshot_id": "synthetic-snapshot-001",
        "tle_file_digest": _digest(tle_path),
        "snapshot_acquired_utc_ns": ACQUIRED_UTC_NS,
        "available_to_analysis_utc_ns": AVAILABLE_UTC_NS,
    }
    if mutate_tle_receipt is not None:
        mutate_tle_receipt(tle_receipt)
    tle_receipt_path = tmp_path / "tle-receipt.json"
    _write_json(tle_receipt_path, tle_receipt)

    chronology = {
        "schema": TOOL.CHRONOLOGY_RECEIPT_SCHEMA,
        "authority": "synthetic-chronology-authority",
        "receipt_id": "synthetic-prereg-001",
        "proposal_digest": canonical_digest(proposal),
        "issued_utc_ns": ISSUED_UTC_NS,
        "future_evidence_not_before_utc_ns": NOT_BEFORE_UTC_NS,
        "proposal_reviewed_before_future_evidence": True,
    }
    if mutate_chronology is not None:
        mutate_chronology(chronology)
    chronology_path = tmp_path / "chronology-receipt.json"
    _write_json(chronology_path, chronology)

    specification = {
        "schema": TOOL.SPECIFICATION_SCHEMA,
        "proposal": proposal,
        "receipts": {
            "tle_authority": {
                "path": str(tle_receipt_path),
                "file_digest": _digest(tle_receipt_path),
            },
            "chronology": {
                "path": str(chronology_path),
                "file_digest": _digest(chronology_path),
            },
        },
    }
    specification_path = tmp_path / "prospective-specification.json"
    _write_json(specification_path, specification)
    return specification_path, specification, tle_path, calibration_path


def _freeze(path: Path) -> dict[str, Any]:
    return TOOL.freeze_prospective_plan(
        specification_path=path,
        expected_specification_digest=_digest(path),
    )


def _redigest_plan(plan: dict[str, Any]) -> None:
    payload = dict(plan)
    payload.pop("plan_content_digest")
    plan["plan_content_digest"] = canonical_digest(payload)


def test_freezes_complete_pre_evidence_plan_without_future_paths(tmp_path: Path) -> None:
    path, _specification_document, _tle, _calibration_path = _specification(tmp_path)

    first = _freeze(path)
    second = _freeze(path)

    assert first == second
    assert first["schema"] == TOOL.PLAN_SCHEMA
    assert first["future_evidence_consumed_by_freezer"] is False
    assert first["future_product_paths_frozen_or_inspected"] is False
    assert first["authority_and_chronology"]["digest_and_chronology_structurally_verified"]
    assert not first["authority_and_chronology"]["external_authority_authentication_performed"]
    assert not first["authority_and_chronology"]["external_preregistration_verified"]
    payload = dict(first)
    content_digest = payload.pop("plan_content_digest")
    assert content_digest == canonical_digest(payload)

    execution = first["execution"]
    assert execution["future_dwell_window_policy"]["start_offset_s"] == 50.0
    assert execution["future_dwell_window_policy"]["duration_s"] == 10.0
    assert execution["future_dwell_window_policy"]["scheduled_probe_count"] == 400
    assert first["post_acquisition_persisted_inventory_must_be_untruncated"]
    assert not first["pre_acquisition_candidate_inventory_complete"]
    assert not first["physical_raw_candidate_inventory_complete"]
    primary = execution["future_dwell_window_policy"]["primary_path"]
    assert primary["inferential_path_count"] == 1
    assert not primary["score_based_path_selection_permitted"]
    assert primary["other_receiver_paths_role"] == "noninferential-diagnostics-only"
    assert execution["full_catalogue_search"]["algorithm"] == TOOL.bounded.ALGORITHM_V2
    assert execution["paired_full_catalogue_producer"]["algorithm"] == TOOL.PAIRED_ALGORITHM

    randomization = execution["prediction_time_randomization"]
    assert randomization["control_count"] == 20
    assert randomization["arm_count"] == 21
    assert randomization["reserved_minimum_rank_fraction"] == pytest.approx(1 / 21)
    assert randomization["randomization_exchangeability_verified"] is False
    assert randomization["permutation_p_value"] is None
    assert len({item["transform_digest"] for item in randomization["control_arms"]}) == 20
    assert all(
        not item["transform"]["diagnostics"]["mapping_is_affine"]
        for item in randomization["control_arms"]
    )
    assert all(item["full_catalogue_selection_required"] for item in randomization["control_arms"])

    presence = first["qualification_gates"]["presence"]
    bounds = presence["mathematical_adjudication"]
    assert bounds["natural_null_zero_activation_upper_bound"] <= 0.05
    assert bounds["positive_all_detection_lower_bound"] == pytest.approx(0.9018553723227044)
    assert first["qualification_gates"][
        "block_controls_are_not_a_presence_false_positive_calibration"
    ]
    assert not first["association_claimed"]
    assert not first["tracking_claimed"]


def test_control_margin_gate_counts_ties_but_never_claims_a_permutation_p_value() -> None:
    passing = TOOL.adjudicate_randomization_gate(
        identity_best_improvement=40.0,
        control_best_improvements=tuple(float(index) for index in range(20)),
        gamma_dwell_control_margin_cost=10.0,
    )
    assert passing["reserved_rank_fraction_numerator"] == 1
    assert passing["reserved_rank_fraction_denominator"] == 21
    assert passing["permutation_p_value"] is None
    assert passing["randomization_exchangeability_verified"] is False
    assert passing["specificity_gate_passed"]

    tied = TOOL.adjudicate_randomization_gate(
        identity_best_improvement=40.0,
        control_best_improvements=(40.0, *(0.0 for _ in range(19))),
        gamma_dwell_control_margin_cost=1.0,
    )
    assert tied["controls_at_least_identity_count"] == 1
    assert tied["reserved_rank_fraction"] == pytest.approx(2 / 21)
    assert tied["permutation_p_value"] is None
    assert not tied["strict_margin_passed"]
    assert not tied["specificity_gate_passed"]


@pytest.mark.parametrize(
    "mutation,match",
    [
        (
            lambda proposal: proposal["prediction_time_randomization"].update(
                control_indices=list(range(19))
            ),
            "exactly control indices 0 through 19",
        ),
        (
            lambda proposal: proposal["prediction_time_randomization"].update(
                control_indices=[*range(19), 18]
            ),
            "exactly control indices 0 through 19",
        ),
        (
            lambda proposal: proposal["prediction_time_randomization"].update(
                control_indices=list(range(21))
            ),
            "exactly control indices 0 through 19",
        ),
        (
            lambda proposal: proposal["prediction_time_randomization"].update(
                control_indices=list(range(1, 21))
            ),
            "exactly control indices 0 through 19",
        ),
        (
            lambda proposal: proposal["cross_session_promotion"].update(
                minimum_tracking_prediction_session_count=1
            ),
            "integer >= 2",
        ),
        (
            lambda proposal: proposal["future_dwell_window_policy"]["primary_path"].update(
                score_based_path_selection_permitted=True
            ),
            "score-based receiver-path selection",
        ),
        (
            lambda proposal: proposal["future_dwell_window_policy"]["primary_path"].update(
                radio_serial="posthoc-radio"
            ),
            "path ID does not recompute",
        ),
        (
            lambda proposal: proposal["prospective_cohort_policy"].update(
                optional_stopping_permitted=True
            ),
            "optional_stopping_permitted must be false",
        ),
        (
            lambda proposal: proposal["future_dwell_window_policy"].update(
                start_offset_s=0.0,
                duration_s=60.0,
                scheduled_probe_count=2_400,
                cell_count=600,
            ),
            r"\[50, 60\).*10-second/100-cell/400-probe",
        ),
        (
            lambda proposal: proposal["future_dwell_window_policy"].update(
                scheduled_probe_count=100
            ),
            r"10-second/100-cell/400-probe",
        ),
    ],
)
def test_rejects_underpowered_or_posthoc_plan_choices(
    tmp_path: Path,
    mutation: Callable[[dict[str, Any]], None],
    match: str,
) -> None:
    path, _document, _tle, _calibration_path = _specification(
        tmp_path,
        mutate_proposal=mutation,
    )
    with pytest.raises(ValueError, match=match):
        _freeze(path)


@pytest.mark.parametrize(
    "mutation,match",
    [
        (
            lambda proposal: proposal["presence_qualification"]["natural_capture_wide_null"].update(
                minimum_independent_capture_count=58
            ),
            "cannot attain.*upper-bound",
        ),
        (
            lambda proposal: proposal["presence_qualification"]["positive_sensitivity"].update(
                minimum_independent_capture_count=28,
                required_detected_capture_count=28,
            ),
            "cannot attain.*lower-bound",
        ),
        (
            lambda proposal: proposal["presence_qualification"]["natural_capture_wide_null"].update(
                required_false_activation_count=1
            ),
            "requires zero activations",
        ),
        (
            lambda proposal: proposal["presence_qualification"]["natural_capture_wide_null"].update(
                minimum_independent_capture_count=10**18,
                maximum_familywise_false_activation_rate=1e-18,
            ),
            "cannot attain.*upper-bound",
        ),
        (
            lambda proposal: proposal["presence_qualification"]["positive_sensitivity"].update(
                minimum_detection_probability_lower_bound=1.0,
            ),
            "finite.*cannot attain.*lower-bound target of 1",
        ),
        (
            lambda proposal: proposal["presence_qualification"]["natural_capture_wide_null"].update(
                minimum_independent_capture_count=10**309,
            ),
            "natural-null independent capture count must be <=",
        ),
        (
            lambda proposal: proposal["presence_qualification"]["positive_sensitivity"].update(
                minimum_independent_capture_count=10**309,
                required_detected_capture_count=10**309,
            ),
            "positive-sensitivity independent capture count must be <=",
        ),
    ],
)
def test_recomputes_presence_qualification_sample_sufficiency(
    tmp_path: Path,
    mutation: Callable[[dict[str, Any]], None],
    match: str,
) -> None:
    path, _document, _tle, _calibration_path = _specification(
        tmp_path,
        mutate_proposal=mutation,
    )
    with pytest.raises(ValueError, match=match):
        _freeze(path)


def test_rejects_receipt_chronology_or_proposal_digest_drift(tmp_path: Path) -> None:
    late_path, _document, _tle, _calibration_path = _specification(
        tmp_path / "late",
        mutate_chronology=lambda receipt: receipt.update(issued_utc_ns=NOT_BEFORE_UTC_NS),
    )
    with pytest.raises(ValueError, match="pre-evidence proposal ordering"):
        _freeze(late_path)

    drift_root = tmp_path / "drift"
    drift_root.mkdir()
    drift_path, _document, _tle, _calibration_path = _specification(
        drift_root,
        mutate_chronology=lambda receipt: receipt.update(proposal_digest="sha256:" + "9" * 64),
    )
    with pytest.raises(ValueError, match="different proposal digest"):
        _freeze(drift_path)


def test_rejects_noncausal_tle_or_changed_calibration_bytes(tmp_path: Path) -> None:
    noncausal_root = tmp_path / "noncausal"
    noncausal_root.mkdir()
    path, _document, _tle, _calibration_path = _specification(
        noncausal_root,
        mutate_tle_receipt=lambda receipt: receipt.update(
            available_to_analysis_utc_ns=FROZEN_UTC_NS + 1
        ),
    )
    with pytest.raises(ValueError, match="not causally available"):
        _freeze(path)

    changed_root = tmp_path / "changed"
    changed_root.mkdir()
    path, _document, _tle, calibration_path = _specification(changed_root)
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    calibration["score_threshold"] = 0.2
    _write_json(calibration_path, calibration)
    with pytest.raises(ValueError, match="score calibration file digest mismatch"):
        _freeze(path)


def test_tle_age_uses_snapshot_acquisition_not_recent_analysis_availability(
    tmp_path: Path,
) -> None:
    path, _document, _tle, _calibration_path = _specification(
        tmp_path,
        mutate_proposal=lambda proposal: proposal["tle"].update(
            maximum_snapshot_age_at_dwell_s=90_000.0
        ),
        mutate_tle_receipt=lambda receipt: receipt.update(
            available_to_analysis_utc_ns=FROZEN_UTC_NS
        ),
    )
    assert (NOT_BEFORE_UTC_NS - FROZEN_UTC_NS) / 1e9 < 90_000.0
    assert (NOT_BEFORE_UTC_NS - ACQUIRED_UTC_NS) / 1e9 > 90_000.0
    with pytest.raises(ValueError, match="already too old"):
        _freeze(path)


def test_rejects_any_future_artifact_locator_in_the_strict_policy(tmp_path: Path) -> None:
    def add_future_path(proposal: dict[str, Any]) -> None:
        proposal["future_dwell_window_policy"]["future_duration_dataset_path"] = (
            "/future/not-yet-sealed.json"
        )

    path, _document, _tle, _calibration_path = _specification(
        tmp_path,
        mutate_proposal=add_future_path,
    )
    with pytest.raises(ValueError, match="future dwell window policy fields differ"):
        _freeze(path)


def test_output_writer_is_create_only_and_refuses_protected_roots(tmp_path: Path) -> None:
    output = tmp_path / "plan.json"
    TOOL._write_new({"schema": "test"}, output)
    with pytest.raises(ValueError, match="already exists"):
        TOOL._write_new({"schema": "test"}, output)
    with pytest.raises(ValueError, match="/mnt/qnap01"):
        TOOL._refuse_protected_output(Path("/mnt/qnap01/research-plan.json"))


def test_public_plan_loader_recomputes_content_and_control_transforms(tmp_path: Path) -> None:
    path, _document, _tle, _calibration_path = _specification(tmp_path / "source")
    plan = _freeze(path)
    plan_path = tmp_path / "plan.json"
    _write_json(plan_path, plan)
    assert (
        TOOL.load_and_validate_prospective_plan(
            plan_path=plan_path,
            expected_plan_file_digest=_digest(plan_path),
        )
        == plan
    )

    forged = copy.deepcopy(plan)
    transform = forged["execution"]["prediction_time_randomization"]["control_arms"][0]["transform"]
    transform["prediction_block_by_observation_block"][0] = transform[
        "prediction_block_by_observation_block"
    ][1]
    _redigest_plan(forged)
    forged_path = tmp_path / "forged-plan.json"
    _write_json(forged_path, forged)
    with pytest.raises(ValueError, match="does not exactly reconstruct"):
        TOOL.load_and_validate_prospective_plan(
            plan_path=forged_path,
            expected_plan_file_digest=_digest(forged_path),
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda plan: plan["qualification_gates"]["decision_thresholds"]["validated_values"].update(
            gamma_dwell_control_margin_cost=26.0
        ),
        lambda plan: plan["execution"]["prospective_cohort_policy"].update(
            chronological_order_keys=["session_id"],
            take_first_eligible_dwells_in_order=False,
        ),
        lambda plan: plan["promotion_state_machine"].update(
            states=["unqualified", "confirmed"],
            maximum_consecutive_coasting_sessions=99,
        ),
        lambda plan: plan.update(frozen_at_utc_ns=plan["future_evidence_not_before_utc_ns"] + 1),
    ],
)
def test_specification_replay_rejects_redigested_semantic_tampering(
    tmp_path: Path,
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    specification_path, _document, _tle, _calibration_path = _specification(tmp_path / "source")
    plan = _freeze(specification_path)
    mutation(plan)
    _redigest_plan(plan)
    plan_path = tmp_path / "tampered-plan.json"
    _write_json(plan_path, plan)

    with pytest.raises(ValueError, match="does not exactly reconstruct"):
        TOOL.load_and_validate_prospective_plan(
            plan_path=plan_path,
            expected_plan_file_digest=_digest(plan_path),
        )


def test_validation_fails_closed_when_bound_specification_is_missing(tmp_path: Path) -> None:
    specification_path, _document, _tle, _calibration_path = _specification(tmp_path / "source")
    plan = _freeze(specification_path)
    moved = specification_path.with_name("moved-specification.json")
    specification_path.rename(moved)

    with pytest.raises(ValueError, match="bound prospective specification path cannot be resolved"):
        TOOL.validate_prospective_plan(plan)


def test_unbound_paired_implementation_slot_keeps_execution_not_ready(tmp_path: Path) -> None:
    def unbind(proposal: dict[str, Any]) -> None:
        producer = proposal["paired_full_catalogue_producer"]
        producer["implementation_manifest_digest"] = None
        producer["implementation_binding_status"] = "required-before-first-future-dwell"

    path, _document, _tle, _calibration_path = _specification(
        tmp_path,
        mutate_proposal=unbind,
    )
    plan = _freeze(path)
    readiness = plan["execution_readiness"]
    assert not readiness["paired_producer_implementation_digest_slot_filled"]
    assert not readiness["paired_producer_implementation_bytes_verified_by_freezer"]
    assert not readiness["ready_to_consume_future_evidence"]
    assert not readiness["ready_to_claim_association"]


def test_paired_implementation_slot_must_match_current_manifest_bytes(tmp_path: Path) -> None:
    module = importlib.import_module(
        "tools.replay_raw_full_catalogue_paired_prediction_time_specificity"
    )
    current_digest = canonical_digest(module.producer_implementation_manifest())

    def bind(proposal: dict[str, Any]) -> None:
        producer = proposal["paired_full_catalogue_producer"]
        producer["implementation_manifest_digest"] = current_digest
        producer["implementation_binding_status"] = "pre-evidence-bound"

    path, _document, _tle, _calibration_path = _specification(
        tmp_path / "valid",
        mutate_proposal=bind,
    )
    plan = _freeze(path)
    readiness = plan["execution_readiness"]
    assert readiness["paired_producer_implementation_digest_slot_filled"]
    assert readiness["paired_producer_implementation_bytes_verified_by_freezer"]

    def forge(proposal: dict[str, Any]) -> None:
        producer = proposal["paired_full_catalogue_producer"]
        producer["implementation_manifest_digest"] = "sha256:" + "3" * 64
        producer["implementation_binding_status"] = "pre-evidence-bound"

    forged_path, _document, _tle, _calibration_path = _specification(
        tmp_path / "forged",
        mutate_proposal=forge,
    )
    with pytest.raises(ValueError, match="implementation-manifest digest is not current"):
        _freeze(forged_path)


def test_fixed_cohort_reserves_two_later_prediction_sessions(tmp_path: Path) -> None:
    path, _document, _tle, _calibration_path = _specification(tmp_path)
    plan = _freeze(path)
    cohort = plan["execution"]["prospective_cohort_policy"]
    roles = cohort["ordinal_roles"]
    assert [item["ordinal"] for item in roles] == list(range(1, 5))
    assert [item["role"] for item in roles[:2]] == ["full-catalogue-association-selection"] * 2
    assert [item["role"] for item in roles[2:]] == ["fixed-target-tracking-prediction-holdout"] * 2
    assert not cohort["prediction_holdout_identity_reselection_permitted"]
    states = plan["promotion_state_machine"]
    assert states["tracking_status_states"] == ["confirmed", "coasting"]
    assert {"confirming", "initial_confirmation_failed", "lost", "expired"} <= set(states["states"])
    assert states["accepted_later_update_count_state_invariant"]["target_locked"] == 0
    assert states["accepted_later_update_count_state_invariant"]["confirming"] == 1
    assert states["coasting_tracking_claim_requires_accepted_later_update_count_at_least"] == 2
    assert states["maximum_consecutive_coasting_sessions"] == 2
    assert states["maximum_tracking_horizon_s"] == 86_400.0
    assert states["nonactivation_is_not_physical_loss_evidence"]


def test_initial_tracking_holds_are_exact_and_cannot_be_rescued(tmp_path: Path) -> None:
    path, _document, _tle, _calibration_path = _specification(tmp_path)
    plan = _freeze(path)
    state_machine = plan["promotion_state_machine"]
    initial = state_machine["initial_tracking_confirmation_policy"]
    assert initial["frozen_cohort_ordinals"] == [3, 4]
    assert initial["accepted_update_required_at_every_ordinal"]
    assert initial["every_ordinal_consumed_even_after_failure"]
    assert not initial["replacement_or_fifth_session_rescue_permitted"]
    assert not initial["coasting_state_permitted_before_confirmation"]
    assert initial["failure_requires_a_new_prospective_plan"]

    hold = plan["execution"]["tracking_prediction_hold_protocol"]
    assert hold["frozen_initial_holdout_ordinals"] == [3, 4]
    assert not hold["replacement_or_fifth_session_rescue_permitted"]
    assert not hold["coasting_permitted_during_initial_tracking_confirmation"]
    assert not hold["post_confirmation_monitoring_authorized_by_this_plan"]
    assert hold["post_confirmation_coasting_requires_separately_frozen_schedule"]

    transitions = state_machine["transitions"]
    assert not any(
        transition["from"] == "coasting" and "confirming" in transition["to"]
        for transition in transitions
    )
    assert [transition["from"] for transition in transitions if transition["to"] == "coasting"] == [
        "confirmed"
    ]

    miss = "valid-nonactivation-or-no-rf-opportunity"
    accepted = "accepted-fixed-target-update"
    for outcomes in ((miss, accepted), (accepted, miss)):
        result = TOOL.adjudicate_initial_tracking_confirmation(holdout_outcomes=outcomes)
        assert result["frozen_holdout_ordinals"] == [3, 4]
        assert result["every_frozen_holdout_ordinal_consumed"]
        assert result["diagnostic_adjudication_state"] == "initial_confirmation_failed"
        assert not result["tracking_claimed"]
        assert not result["promotion_authority_granted"]
        assert not result["replacement_or_fifth_session_rescue_permitted"]
        assert result["new_plan_required_after_initial_confirmation_failure"]

    numerical_pass = TOOL.adjudicate_initial_tracking_confirmation(
        holdout_outcomes=(accepted, accepted)
    )
    assert numerical_pass["initial_confirmation_numerical_gate_passed"]
    assert numerical_pass["diagnostic_adjudication_state"] == (
        "confirmation-gate-passed-awaiting-typed-receipt"
    )
    assert not numerical_pass["tracking_claimed"]
    assert not numerical_pass["promotion_authority_granted"]
    assert numerical_pass["typed_plan_target_session_and_digest_receipt_required_for_promotion"]


def test_state_failure_categories_and_control_margin_semantics_agree(tmp_path: Path) -> None:
    path, _document, _tle, _calibration_path = _specification(tmp_path)
    plan = _freeze(path)
    state_machine = plan["promotion_state_machine"]
    hold = plan["execution"]["tracking_prediction_hold_protocol"]

    invalid = state_machine["invalid_evidence_semantics"]
    assert invalid["categories"] == ["invalid-provenance", "incomplete-artifact"]
    assert not invalid["evidence_accepted"]
    assert not invalid["rf_miss_counter_mutated"]
    assert not invalid["coast_counter_mutated"]
    assert invalid["resulting_protocol_state"] == "protocol_invalid"
    assert hold["invalid_provenance_or_incomplete_artifact_result"] == (
        "protocol-invalid-reject-evidence-no-counter-mutation"
    )

    contradiction = state_machine["valid_positive_contradiction_semantics"]
    assert contradiction["categories"] == [
        "identity-over-strongest-control-margin-gate-failure",
        "wrong-identity",
        "innovation-rejection",
    ]
    assert contradiction["resulting_tracking_state"] == "lost"
    assert (
        hold["valid_identity_control_margin_failure_wrong_identity_or_innovation_result"] == "lost"
    )

    weaker_control = TOOL.adjudicate_randomization_gate(
        identity_best_improvement=40.0,
        control_best_improvements=(10.0, *(0.0 for _ in range(19))),
        gamma_dwell_control_margin_cost=25.0,
    )
    assert weaker_control["strongest_control_best_improvement"] > 0.0
    assert weaker_control["specificity_gate_passed"]
    weaker_semantics = state_machine["weaker_control_activation_semantics"]
    assert not weaker_semantics["positive_contradiction"]
    assert not weaker_semantics["loss_permitted_when_identity_strictly_beats_control_by_gamma"]
    assert hold["weaker_control_activation_with_strict_margin_pass_result"] == (
        "not-alone-a-contradiction"
    )


def test_all_four_pre_evidence_thresholds_are_strict_and_per_dwell_dominance_is_required(
    tmp_path: Path,
) -> None:
    path, _document, _tle, _calibration_path = _specification(tmp_path)
    plan = _freeze(path)
    thresholds = plan["qualification_gates"]["decision_thresholds"]
    assert thresholds["validated_values"] == {
        "beta_association_cost": 100.0,
        "mu_catalogue_runner_margin_cost": 50.0,
        "gamma_cohort_control_margin_cost": 75.0,
        "gamma_dwell_control_margin_cost": 25.0,
    }
    assert thresholds["all_comparisons_are_strict"]
    assert not thresholds["equality_passes_any_threshold"]
    assert not thresholds["decision_thresholds_empirically_calibrated"]
    assert not thresholds["decision_threshold_calibration_receipt_present"]
    assert thresholds["frozen_threshold_values_are_not_calibration_authority"]
    assert thresholds["per_dwell_dominance_required_so_one_session_cannot_carry_the_cohort"]

    equality = TOOL.adjudicate_randomization_gate(
        identity_best_improvement=40.0,
        control_best_improvements=(15.0, *(0.0 for _ in range(19))),
        gamma_dwell_control_margin_cost=25.0,
    )
    assert equality["identity_margin_over_strongest_control_cost"] == 25.0
    assert not equality["strict_margin_passed"]
    assert not equality["specificity_gate_passed"]

    qualifiers = {
        "same_norad_selected_in_both_sessions": True,
        "sessions_are_distinct": True,
        "natural_presence_null_qualified": True,
        "positive_sensitivity_qualified": True,
        "decision_threshold_calibration_qualified": True,
    }
    passing = TOOL.adjudicate_discovery_association_gate(
        association_improvement_cost=101.0,
        identity_improvements=(40.0, 41.0),
        catalogue_runner_margin_cost=51.0,
        dwell_control_margins=(26.0, 27.0),
        cohort_control_margin_cost=76.0,
        beta_association_cost=100.0,
        mu_catalogue_runner_margin_cost=50.0,
        gamma_cohort_control_margin_cost=75.0,
        gamma_dwell_control_margin_cost=25.0,
        **qualifiers,
    )
    assert passing["discovery_association_gate_passed"]

    equality_fails = TOOL.adjudicate_discovery_association_gate(
        association_improvement_cost=100.0,
        identity_improvements=(40.0, 41.0),
        catalogue_runner_margin_cost=51.0,
        dwell_control_margins=(26.0, 27.0),
        cohort_control_margin_cost=76.0,
        beta_association_cost=100.0,
        mu_catalogue_runner_margin_cost=50.0,
        gamma_cohort_control_margin_cost=75.0,
        gamma_dwell_control_margin_cost=25.0,
        **qualifiers,
    )
    assert not equality_fails["association_improvement_passed"]
    assert not equality_fails["discovery_association_gate_passed"]

    one_weak_dwell = TOOL.adjudicate_discovery_association_gate(
        association_improvement_cost=101.0,
        identity_improvements=(40.0, 41.0),
        catalogue_runner_margin_cost=51.0,
        dwell_control_margins=(25.0, 100.0),
        cohort_control_margin_cost=100.0,
        beta_association_cost=100.0,
        mu_catalogue_runner_margin_cost=50.0,
        gamma_cohort_control_margin_cost=75.0,
        gamma_dwell_control_margin_cost=25.0,
        **qualifiers,
    )
    assert one_weak_dwell["dwell_control_margin_passed_by_dwell"] == [False, True]
    assert not one_weak_dwell["discovery_association_gate_passed"]
