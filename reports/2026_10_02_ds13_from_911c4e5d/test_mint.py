"""DS13 boundary, admission, inventory completeness, and seal regression tests."""

import importlib.util
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

spec = importlib.util.spec_from_file_location("ds13_mint", Path(__file__).with_name("mint.py"))
mint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mint)


def test_inclusive_capture_boundaries_and_capture_order():
    index = [[400, 200, "radio", "last"], [500, 100, "radio", "anchor"],
             [100, 99, "radio", "before"], [600, 201, "radio", "after"]]
    assert [r[3] for r in mint.candidates(index, 100, 200)] == ["anchor", "last"]


def test_duplicate_session_is_rejected():
    with pytest.raises(AssertionError, match="Duplicate"):
        mint.candidates([[1, 100, "r", "same"], [2, 110, "r", "same"]], 100, 200)


@pytest.fixture
def inventory(tmp_path, monkeypatch):
    root = tmp_path / "local"
    (root / "analysis").mkdir(parents=True)
    (root / "published").mkdir()
    monkeypatch.setattr(mint, "ROOT", root)
    parent = tmp_path / "parent.json"
    mint.write(parent, {"captures": [{"session_id": "parent", "manifest_sha256": "sha256:parent", "uncompressed_sha256": "sha256:parent-iq"}]})
    monkeypatch.setattr(mint, "PARENT", parent)
    rows = []
    for i, sid in enumerate([mint.ANCHOR, "pending"]):
        row = dict(session_id=sid, manifest_sha256="sha256:" + sid, uncompressed_sha256="sha256:iq-" + sid,
                   capture_start_utc_ns=100 + i * 10, capture_start_earliest_utc_ns=95 + i * 10,
                   capture_end_utc_ns=105 + i * 10, finalized_utc_ns=109 + i * 10, utc_qualified=True,
                   visits=20, compressed_bytes=100, valid_sample_count=40, sample_rate_hz=10,
                   capture_quality_reasons=[])
        glrt = dict(session_id=sid, input_manifest_sha256=row["manifest_sha256"], state="metrics_ready",
                    total_visits=20, checkpoint_visits=20, configuration={"probe_stride_ms": 120},
                    binding_sha256="sha256:binding", metrics_manifest_sha256="sha256:metrics")
        tracking = dict(session_id=sid, state="complete", product=dict(
            session_id=sid, input_manifest_sha256=row["manifest_sha256"], analysis_manifest_sha256="sha256:metrics",
            configuration_digest="sha256:config", trajectory_state="complete", tle_state="complete",
            created_at="2026-10-02T16:00:00Z", attempted_group_count=4, deferred_group_count=200))
        if sid == "pending":
            tracking.update(state="pending", product=None)
        evidence = root / "analysis" / (sid + ".json")
        mint.write(evidence, {"glrt": glrt, "tracking": tracking})
        row["analysis_evidence_sha256"] = mint.digest(evidence.read_bytes())
        metadata = root / "published" / (sid + ".json")
        mint.write(metadata, {"session_id": sid})
        row["metadata_snapshot_sha256"] = mint.digest(metadata.read_bytes())
        row["analysis_reasons"] = mint.admission.analysis_reasons(row, glrt, tracking, mint.CUTOFF)
        row["exclusion_reasons"] = list(row["analysis_reasons"])
        rows.append(row)
    index = [[109 + i * 10, row["capture_start_utc_ns"], "radio", row["session_id"]] for i, row in enumerate(rows)]
    snapshot = dict(cutoff=mint.CUTOFF, start_session_id=mint.ANCHOR,
                    start_manifest_sha256=rows[0]["manifest_sha256"], lower_inclusive=100, lower_earliest=95,
                    candidates=index, published_index=index,
                    parent_manifest_sha256=mint.digest(parent.read_bytes()),
                    admission_source_sha256=mint.digest(mint.ADMISSION_SOURCE.read_bytes()), storage_reader_release="test")
    mint.write(root / "candidate-index.json", snapshot)
    mint.write(root / "inventory.json", rows)
    return root, snapshot, rows


def test_seal_includes_anchor_and_excludes_pending_analysis(inventory):
    root, _, _ = inventory
    mint.seal()
    manifest = json.loads((root / "manifest.json").read_bytes())
    assert [r["session_id"] for r in manifest["captures"]] == [mint.ANCHOR]
    assert [r["session_id"] for r in manifest["excluded"]] == ["pending"]
    assert manifest["counts"]["recordings"] == 1
    mint.verify()
    with pytest.raises(RuntimeError, match="already sealed"):
        mint.seal()
    (root / "analysis" / (mint.ANCHOR + ".json")).write_text("tampered")
    with pytest.raises(AssertionError):
        mint.verify()


def test_missing_candidate_cannot_be_sealed(inventory):
    root, _, rows = inventory
    mint.write(root / "inventory.json", rows[:1])
    with pytest.raises(AssertionError):
        mint.seal()
    assert not (root / "manifest.json").exists()


def test_removed_candidate_is_detected_against_frozen_index(inventory):
    _, snapshot, rows = inventory
    snapshot["candidates"] = snapshot["candidates"][:1]
    with pytest.raises(AssertionError):
        mint.validate_inventory(snapshot, rows[:1])


@pytest.mark.parametrize("change,reason", [
    ({"analysis_manifest_sha256": "sha256:stale"}, "tracking_binding_invalid"),
    ({"created_at": "2026-10-02T16:46:55Z"}, "tracking_not_complete_at_cutoff"),
    ({"trajectory_state": "pending"}, "tracking_stages_incomplete"),
])
def test_incomplete_or_stale_analysis_is_rejected(inventory, change, reason):
    root, _, rows = inventory
    evidence = json.loads((root / "analysis" / (mint.ANCHOR + ".json")).read_bytes())
    evidence["tracking"]["product"].update(change)
    assert reason in mint.admission.analysis_reasons(rows[0], evidence["glrt"], evidence["tracking"], mint.CUTOFF)


def test_api_failure_is_not_misclassified_as_missing_analysis(monkeypatch):
    def fail(*args, **kwargs):
        raise HTTPError("http://localhost", 503, "unavailable", {}, None)
    monkeypatch.setattr(mint, "urlopen", fail)
    with pytest.raises(HTTPError):
        mint.read_status("/test")
