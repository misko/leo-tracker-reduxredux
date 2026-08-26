from __future__ import annotations

import json
import math
from hashlib import sha256
from pathlib import Path

import pytest

from leo.analysis.research import final_holdout_protocol as protocol
from leo.contracts.digests import canonical_digest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FROZEN_PROTOCOL = (
    REPOSITORY_ROOT / "config/analysis/final-doppler-holdout-satellite-protocol-v1.json"
)
FAILED_ATTEMPT_DIR = (
    REPOSITORY_ROOT
    / "reports/figures/2026_08_26_final_doppler_holdout_failed_attempt1"
)
FAILED_ATTEMPT_RECEIPT = FAILED_ATTEMPT_DIR / "attempt-1-failure-receipt.json"
V1_FAILURE_AMENDMENT = (
    REPOSITORY_ROOT
    / "config/analysis/final-doppler-holdout-satellite-protocol-v1-amendment-001.json"
)


def _association() -> dict[str, object]:
    latitude = 37.858988
    longitude = -122.478103
    latitude_delta = 50.0 / 111_320.0
    longitude_delta = 50.0 / (111_320.0 * math.cos(math.radians(latitude)))
    return {
        "catalog_scope": "Starlink-only",
        "time_shift_s": 0.0,
        "primary_lane": "lean_500ms_quadratic",
        "baseline_lane": "fixed_500ms_linear",
        "bin_width_ms": 20.0,
        "training_fraction_of_full_target_span": 0.6,
        "maximum_pre_response_compute_seconds": 3600.0,
        "minimum_total_bins": 10,
        "minimum_training_bins": 6,
        "minimum_evaluation_bins": 4,
        "minimum_visible_candidates": 2,
        "nuisance_primary": "one-constant-CFO-offset-per-capture",
        "free_candidate_rate_primary": False,
        "shared_rate_diagnostic_only": True,
        "shared_rate_group": "physical_receiver_id",
        "shared_rate_prior_sigma_hz_s": 50.0,
        "shared_rate_hard_bound_hz_s": 150.0,
        "shared_rate_objective": (
            "(sum_capture_training_MSE + 50^2*sum_group(rate/50)^2)/capture_count"
        ),
        "wrong_time_offsets_s": [float(value) for value in range(-18000, 0, 900)]
        + [float(value) for value in range(900, 18001, 900)],
        "within_track_permutations": 20,
        "within_track_permutation_seed": 20260826,
        "rolling_origin_training_fractions": [0.4, 0.6, 0.8],
        "minimum_claim_heldout_odd_bins": 8,
        "minimum_heldout_odd_bin_fraction": 0.5,
        "maximum_claim_rank_one_heldout_odd_rms_hz": 100.0,
        "training_runner_margin_ratio_minimum": 1.10,
        "heldout_runner_margin_ratio_minimum": 1.10,
        "wrong_time_minimum_scored": 38,
        "null_empirical_p_maximum": 0.05,
        "all_20_permutations_required": True,
        "minimum_stable_rolling_origins": 2,
        "primary_baseline_rank_one_agreement_required": True,
        "utc_site_predecessor_identity_stability_required": True,
        "absolute_secure_norad_forced_false": True,
        "site_sensitivity": [
            {
                "control_id": "site-north-50m",
                "latitude_deg": latitude + latitude_delta,
                "longitude_deg": longitude,
                "altitude_m": -29.0,
                "label": "Spinnaker, Sausalito north 50 m sensitivity",
            },
            {
                "control_id": "site-south-50m",
                "latitude_deg": latitude - latitude_delta,
                "longitude_deg": longitude,
                "altitude_m": -29.0,
                "label": "Spinnaker, Sausalito south 50 m sensitivity",
            },
            {
                "control_id": "site-east-50m",
                "latitude_deg": latitude,
                "longitude_deg": longitude + longitude_delta,
                "altitude_m": -29.0,
                "label": "Spinnaker, Sausalito east 50 m sensitivity",
            },
            {
                "control_id": "site-west-50m",
                "latitude_deg": latitude,
                "longitude_deg": longitude - longitude_delta,
                "altitude_m": -29.0,
                "label": "Spinnaker, Sausalito west 50 m sensitivity",
            },
        ],
    }


def test_json_loader_rejects_duplicate_keys(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema":"first","schema":"second"}')

    with pytest.raises(ValueError, match="duplicate JSON key"):
        protocol._load_json_without_duplicate_keys(path)


def test_authorized_chunks_require_exact_paths_and_keys() -> None:
    chunks = [
        {
            "session_id": session,
            "stream_id": stream,
            "relative_path": relative,
            "sample_start": start,
            "sample_count": count,
            "compressed_sha256": digest,
        }
        for session, stream, relative, start, count, digest in protocol._EXPECTED_CHUNKS
    ]
    protocol._validate_chunks(chunks)

    substituted = json.loads(json.dumps(chunks))
    substituted[0]["relative_path"] = "radio-substituted/iq-000006.ci16.zst"
    with pytest.raises(ValueError, match="geometry/digest"):
        protocol._validate_chunks(substituted)

    extra = json.loads(json.dumps(chunks))
    extra[0]["unexpected"] = True
    with pytest.raises(ValueError, match="key set"):
        protocol._validate_chunks(extra)


def test_association_protocol_freezes_coordinates_and_availability() -> None:
    association = _association()
    protocol._validate_association(association)

    changed_fraction = json.loads(json.dumps(association))
    changed_fraction["minimum_heldout_odd_bin_fraction"] = 0.49
    with pytest.raises(ValueError, match="association/control"):
        protocol._validate_association(changed_fraction)

    changed_site = json.loads(json.dumps(association))
    changed_site["site_sensitivity"][0]["latitude_deg"] += 1e-9
    with pytest.raises(ValueError, match="association/control"):
        protocol._validate_association(changed_site)


def test_frozen_final_protocol_validates_against_exact_commit_and_authorities() -> None:
    document = protocol.load_and_validate_final_protocol(
        FROZEN_PROTOCOL,
        repository_root=REPOSITORY_ROOT,
    )

    assert document["chronology"]["implementation_commit"] == (
        "986ce7a4ba12b1048bf93f0b26935b753de8820a"
    )
    assert tuple(item["session_id"] for item in document["captures"]) == protocol.CAPTURE_IDS
    assert sum(item["target_count"] for item in document["captures"]) == 5_413
    assert len(document["authorized_odd_chunks"]) == 11
    assert document["site"]["absolute_secure_norad_permitted"] is False
    assert document["upstream_conditioning"]["end_to_end_odd_independent"] is False


def test_failed_attempt_receipt_binds_exact_fail_closed_evidence() -> None:
    receipt = json.loads(FAILED_ATTEMPT_RECEIPT.read_text())
    assert receipt["receipt_digest"] == canonical_digest(
        {key: value for key, value in receipt.items() if key != "receipt_digest"}
    )
    assert receipt["status"] == "failed_closed"
    assert receipt["rerun_authorized"] is False
    assert receipt["command"]["started_at_ms"] == 1_787_735_892_807
    assert receipt["command"]["completed_at_ms"] == 1_787_735_923_988
    assert receipt["command"]["exit_code"] == 1
    assert receipt["outcome_access"] == {
        "candidate_ids_inspected_by_operator_or_agent": False,
        "candidate_matrices_inspected_by_operator_or_agent": False,
        "candidate_rankings_inspected_by_operator_or_agent": False,
        "candidate_results_printed": False,
        "in_memory_candidate_propagation_function_invocations": 377,
        "in_memory_candidate_propagation_or_ranking_occurred": True,
        "in_memory_frozen_ranking_helper_invocations": 564,
        "odd_iq_accessed": False,
        "odd_response_accessed": False,
        "process_memory_inspected": False,
        "ranking_artifact_persisted": False,
        "shared_rate_diagnostic_executed": False,
    }
    for binding in receipt["artifacts"].values():
        if "path" not in binding:
            continue
        artifact = REPOSITORY_ROOT / binding["path"]
        assert artifact.stat().st_size == binding["byte_size"]
        assert "sha256:" + sha256(artifact.read_bytes()).hexdigest() == binding["sha256"]


def test_v1_failure_amendment_retires_attempt_without_changing_science() -> None:
    amendment = json.loads(V1_FAILURE_AMENDMENT.read_text())
    assert amendment["amendment_digest"] == canonical_digest(
        {key: value for key, value in amendment.items() if key != "amendment_digest"}
    )
    assert amendment["base_protocol"]["sha256"] == (
        "sha256:" + sha256(FROZEN_PROTOCOL.read_bytes()).hexdigest()
    )
    assert amendment["execution_state"]["base_protocol_execution_retired"] is True
    assert amendment["execution_state"]["rerun_under_base_protocol_authorized"] is False
    assert amendment["execution_state"]["attempt_1_results_printed_or_inspected"] is False
    assert all(amendment["scientific_freeze"].values())
    receipt_bytes = FAILED_ATTEMPT_RECEIPT.read_bytes()
    assert amendment["failed_attempt"]["failure_receipt_sha256"] == (
        "sha256:" + sha256(receipt_bytes).hexdigest()
    )


@pytest.mark.parametrize(
    ("poison", "message"),
    (
        ("capture_count", "capture artifact/selector"),
        ("chunk_path", "chunk geometry/digest"),
        ("tle_metadata", "TLE snapshot"),
        ("site_coordinate", "site/topology"),
        ("availability_gate", "association/control"),
        ("conditioning", "all-Qin conditioning"),
        ("policy_commit", "dataset policy"),
        ("implementation_tree", "implementation commit/tree"),
    ),
)
def test_resigned_protocol_authority_poison_fails_independent_validation(
    poison: str,
    message: str,
    tmp_path: Path,
) -> None:
    document = json.loads(FROZEN_PROTOCOL.read_text())
    if poison == "capture_count":
        document["captures"][0]["target_count"] += 1
    elif poison == "chunk_path":
        document["authorized_odd_chunks"][0]["relative_path"] = (
            "radio-substituted/iq-000006.ci16.zst"
        )
    elif poison == "tle_metadata":
        document["tle_authority"]["frozen_selection_inventory"][0]["metadata_sha256"] = (
            "sha256:" + "0" * 64
        )
    elif poison == "site_coordinate":
        document["site"]["latitude_deg"] += 1e-9
    elif poison == "availability_gate":
        document["association"]["minimum_heldout_odd_bin_fraction"] = 0.49
    elif poison == "conditioning":
        document["upstream_conditioning"]["end_to_end_odd_independent"] = True
    elif poison == "policy_commit":
        document["dataset_policy"]["repository_commit"] = "0" * 40
    else:
        document["chronology"]["implementation_tree"] = "0" * 40
    document["protocol_digest"] = canonical_digest(
        {key: value for key, value in document.items() if key != "protocol_digest"}
    )
    path = tmp_path / "poisoned-protocol.json"
    path.write_text(json.dumps(document, indent=2, sort_keys=True))

    with pytest.raises(ValueError, match=message):
        protocol.load_and_validate_final_protocol(path, repository_root=REPOSITORY_ROOT)
