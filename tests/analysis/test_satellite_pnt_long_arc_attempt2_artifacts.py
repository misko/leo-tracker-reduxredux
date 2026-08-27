from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import zstandard as zstd
from PIL import Image

from leo.contracts.digests import canonical_digest

ROOT = Path(__file__).parents[2]
REPORT = ROOT / "reports" / "2026_08_27_satellite_pnt_long_arc_development_results_attempt2.md"
AUDIT_REPORT = ROOT / "reports" / "2026_08_27_satellite_pnt_long_arc_development_audit.md"
RECEIPT = (
    ROOT
    / "reports"
    / "figures"
    / "2026_08_27_satellite_pnt_long_arc_development_attempt2-execution-receipt.json"
)
ARTIFACT_ROOT = (
    ROOT / "reports" / "figures" / "2026_08_27_satellite_pnt_long_arc_development_attempt2"
)
MANIFEST = ARTIFACT_ROOT / "manifest.json"
ARCHIVE_MANIFEST = ARTIFACT_ROOT / "archive-manifest.json"
AUDIT_EVIDENCE = ARTIFACT_ROOT / "audit-evidence.json"


def _load(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _decompressed_receipt(path: Path) -> tuple[int, str]:
    byte_count = 0
    digest = hashlib.sha256()
    with (
        path.open("rb") as compressed,
        zstd.ZstdDecompressor().stream_reader(compressed) as source,
    ):
        while chunk := source.read(1024 * 1024):
            byte_count += len(chunk)
            digest.update(chunk)
    return byte_count, "sha256:" + digest.hexdigest()


def _assert_content_digest(document: dict[str, Any]) -> None:
    body = {key: value for key, value in document.items() if key != "content_digest"}
    assert document["content_digest"] == canonical_digest(body)


def test_execution_receipt_and_sealed_manifest_close() -> None:
    receipt = _load(RECEIPT)
    manifest = _load(MANIFEST)

    assert _sha256(RECEIPT) == (
        "sha256:92afc7b815fd3fd4aaa4434e5487f54863039886ba78e00b67be1b1a54c3930a"
    )
    assert receipt["status"] == "complete"
    assert receipt["attempt_number"] == 2
    assert receipt["implementation_commit"] == "fff1786fc029d4e0c818cccc2317327f6aa3cf3c"
    assert receipt["repository_head_at_start"] == "f82031f4effe75cff696080f8a38afeec157afb3"
    assert receipt["amendment_digest"] == (
        "sha256:02bd4bd74a62478015aff6d22f89e9cae5a92fad3ac7fa24c0f0327fbaf61ec7"
    )
    assert receipt["started_utc"] < receipt["finished_utc"]

    assert _sha256(MANIFEST) == receipt["manifest_sha256"]
    assert _sha256(REPORT) == receipt["report_sha256"]
    manifest_body = {key: value for key, value in manifest.items() if key != "manifest_digest"}
    assert manifest["manifest_digest"] == canonical_digest(manifest_body)
    assert manifest["implementation_commit"] == receipt["implementation_commit"]
    assert manifest["execution_amendment"]["semantic_digest"] == receipt["amendment_digest"]
    assert manifest["claim_boundary"] == {
        "new_rf_collection_authorized": False,
        "numerical_thresholds_are_set": False,
        "opened_development_only": True,
        "positioning_validation_permitted": False,
        "secure_norad_permitted": False,
        "wrong_epoch_is_gate": False,
        "wrong_epoch_is_null_distribution": False,
    }


def test_compressed_archives_reproduce_sealed_result_bytes() -> None:
    manifest = _load(MANIFEST)
    archive = _load(ARCHIVE_MANIFEST)
    _assert_content_digest(archive)

    sealed_results = {item["arc_id"]: item for item in manifest["results"]}
    assert {item["arc_id"] for item in archive["entries"]} == set(sealed_results)
    assert archive["sealed_manifest"]["sha256"] == _sha256(MANIFEST)
    assert archive["sealed_manifest"]["semantic_digest"] == manifest["manifest_digest"]

    for entry in archive["entries"]:
        sealed = sealed_results[entry["arc_id"]]
        assert entry["sealed_path"] == sealed["path"]
        assert entry["sealed_sha256"] == sealed["sha256"]
        assert entry["sealed_semantic_digest"] == sealed["result_digest"]
        archive_path = ARTIFACT_ROOT / entry["archive_path"]
        assert archive_path.stat().st_size == entry["archive_byte_size"]
        assert _sha256(archive_path) == entry["archive_sha256"]
        byte_count, digest = _decompressed_receipt(archive_path)
        assert byte_count == entry["sealed_byte_size"]
        assert digest == entry["sealed_sha256"]

        local_raw = ARTIFACT_ROOT / entry["sealed_path"]
        if local_raw.exists():
            assert local_raw.stat().st_size == entry["sealed_byte_size"]
            assert _sha256(local_raw) == entry["sealed_sha256"]


def test_machine_audit_preserves_claim_boundary_and_scientific_outcome() -> None:
    evidence = _load(AUDIT_EVIDENCE)
    _assert_content_digest(evidence)

    assert evidence["execution"]["status"] == "complete"
    assert evidence["claim_boundary"] == {
        "opened_development_only": True,
        "identity_claimed": False,
        "secure_norad_claimed": False,
        "positioning_validation_claimed": False,
        "numerical_thresholds_applied": False,
        "wrong_epoch_is_observe_only": True,
        "all_response_free_banks_built_before_response_scoring": True,
    }

    by_arc = {item["arc_id"]: item for item in evidence["arcs"]}
    arc_9981 = by_arc["long-arc-9981-r19f2-s1-rx1-upper-0-30s"]
    arc_150802 = by_arc["long-arc-150802-r19f2-s1-rx1-upper-37p575-51p4s"]

    assert [item["candidate_count"] for item in arc_9981["field_candidate_counts"]] == [
        503,
        488,
        501,
    ]
    assert [item["candidate_count"] for item in arc_150802["field_candidate_counts"]] == [
        572,
        573,
        576,
    ]
    assert all(
        item["complete"] for arc in evidence["arcs"] for item in arc["field_candidate_counts"]
    )

    assert [item["training_winner"] for item in arc_9981["partitions"]] == [
        67930,
        67930,
        67930,
        67930,
    ]
    assert all(item["persisted"] for item in arc_9981["partitions"])
    assert arc_9981["partitions"][0]["future_equal_calendar_block_rms_hz"] == (170.58541776553673)
    assert arc_9981["partitions"][0]["minus_500_future_rms_ratio"] == 0.917946213796042
    assert arc_9981["partitions"][2]["minus_500_future_rms_ratio"] == 0.8224798892766939
    assert arc_9981["partitions"][0]["cubic_radio_minus_orbit_predictive_nll"] < 0.0

    assert [item["training_winner"] for item in arc_150802["partitions"]] == [
        59748,
        65438,
        59748,
        59748,
    ]
    assert arc_150802["partitions"][0]["future_equal_calendar_block_rms_hz"] == (55.06189892619317)
    assert arc_150802["partitions"][0]["minus_500_future_rms_ratio"] == 15.434276333515179
    assert arc_150802["partitions"][0]["plus_500_future_rms_ratio"] == 20.648430475099694
    early = arc_150802["partitions"][1]
    assert early["heldout_winner"] == 59748
    assert early["training_winner_heldout_rank"] == 2
    assert early["persisted"] is False
    assert early["abstention_diagnostics"] == ["heldout-rank-instability"]

    assert evidence["overall_interpretation"] == {
        "curvature_is_useful": True,
        "single_arc_secure_identity_established": False,
        "cross_arc_norad_recurrence_established": False,
        "radio_likelihood_calibration_requires_revision": True,
        "ready_for_unopened_confirmation": False,
    }


def test_figures_and_report_links_resolve() -> None:
    manifest = _load(MANIFEST)
    for figure in manifest["figures"]:
        path = ARTIFACT_ROOT / figure["path"]
        assert _sha256(path) == figure["sha256"]
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            assert image.width >= 1200
            assert image.height >= 700

    for report in (REPORT, AUDIT_REPORT):
        links = re.findall(r"\[[^]]+\]\(([^)]+)\)", report.read_text(encoding="utf-8"))
        assert links
        for target in links:
            if "://" in target:
                continue
            path = (report.parent / target).resolve()
            if path.exists():
                continue
            assert path.suffix == ".json"
            assert path.with_suffix(path.suffix + ".zst").exists(), target

    report_text = REPORT.read_text(encoding="utf-8")
    assert "not independent confirmation" in report_text
    assert "not a null distribution, p-value, or gate" in report_text
    assert "no independent recurrence" in report_text
