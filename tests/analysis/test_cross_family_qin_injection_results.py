from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from leo.analysis.starlink.local_doppler import stable_measurement_floats
from leo.contracts.digests import canonical_digest

PROJECT_ROOT = Path(__file__).parents[2]
ATTEMPT1_ROOT = PROJECT_ROOT / "reports/figures/2026_08_27_satellite_pnt_cross_family_injection_v1"
ATTEMPT2_ROOT = (
    PROJECT_ROOT / "reports/figures/2026_08_27_satellite_pnt_cross_family_injection_attempt2"
)
ATTEMPT1_REPORT = (
    PROJECT_ROOT / "reports/2026_08_27_satellite_pnt_cross_family_injection_results.md"
)
ATTEMPT2_REPORT = (
    PROJECT_ROOT / "reports/2026_08_27_satellite_pnt_cross_family_injection_attempt2_results.md"
)
PROTOCOL = PROJECT_ROOT / "config/analysis/satellite-pnt-cross-family-injection-protocol-v1.json"


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _arm_digest(evidence: dict[str, Any], pair: dict[str, Any], lane: str) -> str:
    arm = pair[lane]
    return canonical_digest(
        {
            "algorithm_version": "cross-family-qin-arm-evidence-v1",
            "protocol_digest": evidence["protocol_digest"],
            "pair_id": pair["pair_id"],
            "truth_family": arm["truth_family"],
            "scenario_id": arm["scenario_id"],
            "diagnostics": arm["diagnostics"],
            "observation_rows": arm["observation_rows"],
            "training_uses_even_qin_only": True,
            "future_uses_odd_qin_only": True,
            "future_response_used_for_training": False,
        }
    )


def _pair_digest(
    evidence: dict[str, Any],
    pair: dict[str, Any],
    background: dict[str, Any],
    truth: dict[str, Any],
) -> str:
    return canonical_digest(
        {
            "algorithm_version": "paired-cross-family-qin-evidence-v1",
            "protocol_digest": evidence["protocol_digest"],
            "truth_digest": truth["truth_digest"],
            "pair_id": pair["pair_id"],
            "background_session_id": pair["background_session_id"],
            "background_recording_manifest_sha256": background["recording_manifest_sha256"],
            "background_analysis_manifest_sha256": background["analysis_manifest_sha256"],
            "background_chunk_compressed_sha256": background["chunk"]["compressed_sha256"],
            "background_chunk_uncompressed_sha256": background["chunk"]["uncompressed_sha256"],
            "orbit_evidence_digest": pair["orbit"]["evidence_digest"],
            "radio_evidence_digest": pair["radio"]["evidence_digest"],
            "occupancy_identical": pair["occupancy_identical"],
            "independent_unit": "background-pair",
            "independent_unit_count": 1,
            "identity_claimed": False,
            "threshold_fitted": False,
        }
    )


def test_attempt2_manifest_and_execution_close() -> None:
    manifest = _load(ATTEMPT2_ROOT / "manifest.json")
    execution = _load(ATTEMPT2_ROOT / "execution.json")

    assert _sha256(ATTEMPT2_ROOT / "evidence.json") == manifest["files"]["evidence.json"]
    assert _sha256(ATTEMPT2_ROOT / "execution.json") == manifest["files"]["execution.json"]
    assert _sha256(ATTEMPT2_REPORT) == execution["report_sha256"]
    assert execution["evidence_sha256"] == manifest["files"]["evidence.json"]
    assert execution["exit_status"] == 0
    assert execution["iq_read"] is True
    assert execution["new_rf_collection"] is False
    assert execution["authority"]["sha256"] == (
        "sha256:bc7cd241d2e1a165ff0504158e99dbe0bebd4faed091f03c13e6cf6d134f8bc5"
    )


def test_attempt2_audit_receipt_matches_sealed_outputs() -> None:
    audit = _load(
        PROJECT_ROOT
        / "reports/figures/2026_08_27_satellite_pnt_cross_family_injection_attempt2-audit.json"
    )

    for relative, expected in audit["sealed_files"].items():
        assert _sha256(PROJECT_ROOT / relative) == expected
    assert audit["arm_digest_closure"] == "6/6"
    assert audit["pair_digest_closure"] == "3/3"
    assert audit["observation_opportunity_count"] == 9_000
    assert audit["attempt1_files_byte_identical"] is True
    assert audit["disposition"] == "go-for-downstream-development-scoring"
    assert audit["identity_claimed"] is False


def test_attempt2_semantic_digests_and_parity_inventory_close() -> None:
    evidence = _load(ATTEMPT2_ROOT / "evidence.json")
    protocol = _load(PROTOCOL)
    base_protocol = _load(PROJECT_ROOT / protocol["authority"]["base_background_protocol_path"])
    backgrounds = {item["session_id"]: item for item in base_protocol["backgrounds"]}
    truths = {item["pair_id"]: item for item in evidence["truth_receipts"]}

    assert evidence["independent_background_count"] == 3
    assert evidence["truth_arm_count"] == 6
    assert len(evidence["paired_evidence"]) == 3
    assert evidence["claim_boundary"] == {
        "formal_coverage_claimed": False,
        "identity_claimed": False,
        "mechanistic_descriptive_only": True,
        "positioning_validated": False,
        "posterior_odds_produced": False,
        "threshold_fitted": False,
    }

    total_rows = 0
    for pair in evidence["paired_evidence"]:
        for lane in ("orbit", "radio"):
            arm = pair[lane]
            rows = arm["observation_rows"]
            total_rows += len(rows)
            assert len(rows) == 1_500
            assert arm["evidence_digest"] == _arm_digest(evidence, pair, lane)
            assert arm["future_response_used_for_training"] is False
            assert all(row["split"] == "training-even-qin" for row in rows[:900])
            assert all(row["split"] == "future-odd-qin" for row in rows[900:])
            assert arm["training_opportunity_count"] == 900
            assert arm["future_opportunity_count"] == 600
        assert pair["occupancy_identical"] is True
        assert pair["identity_claimed"] is False
        assert pair["threshold_fitted"] is False
        assert pair["pair_evidence_digest"] == _pair_digest(
            evidence,
            pair,
            backgrounds[pair["background_session_id"]],
            truths[pair["pair_id"]],
        )
    assert total_rows == 9_000


def test_attempt2_summaries_reproduce_from_future_rows() -> None:
    evidence = _load(ATTEMPT2_ROOT / "evidence.json")
    summaries = {item["pair_id"]: item for item in evidence["pair_summaries"]}

    for pair in evidence["paired_evidence"]:
        for lane in ("orbit", "radio"):
            usable = [
                row
                for row in pair[lane]["observation_rows"]
                if row["split"] == "future-odd-qin" and row["usable"]
            ]
            residuals = [float(row["residual_hz"]) for row in usable]
            rms = math.sqrt(sum(value * value for value in residuals) / len(residuals))
            summary = summaries[pair["pair_id"]][lane]
            assert len(usable) == summary["future_usable_count"]
            assert math.isclose(rms, summary["future_residual_rms_hz"], abs_tol=1e-12)


def test_attempt1_is_immutable_and_attempt2_changes_only_persisted_precision() -> None:
    assert _sha256(ATTEMPT1_REPORT) == (
        "sha256:651e9732bb92e854202cf6c4119bd9ab8aba7d1d60b2fd54b67daa7f1fda6dcf"
    )
    assert _sha256(ATTEMPT1_ROOT / "evidence.json") == (
        "sha256:723510c025165ef3cffc6514008debae79039db915ee57edad7ca84ce3e6e1ce"
    )
    assert _sha256(ATTEMPT1_ROOT / "execution.json") == (
        "sha256:7f2e9c9d6bf88f6bc35313b776aae0ac8d5afad9e93f99b50990f139a9eacaf2"
    )
    assert _sha256(ATTEMPT1_ROOT / "manifest.json") == (
        "sha256:f6a738578951dc0759ce6dc560ef290ab1bf4ddbfe5db777a791b584a1771614"
    )

    attempt1 = _load(ATTEMPT1_ROOT / "evidence.json")
    attempt2 = _load(ATTEMPT2_ROOT / "evidence.json")
    for evidence in (attempt1, attempt2):
        for pair in evidence["paired_evidence"]:
            pair.pop("pair_evidence_digest")
            pair["orbit"].pop("evidence_digest")
            pair["radio"].pop("evidence_digest")
    assert stable_measurement_floats(attempt2) == attempt1
