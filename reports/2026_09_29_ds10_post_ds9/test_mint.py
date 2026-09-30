"""DS10-owned admission regression tests; no hardware, database or storage required."""

import copy
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("ds10_mint", Path(__file__).with_name("mint.py"))
mint = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mint)


@pytest.fixture
def complete():
    row = dict(session_id="test-session", manifest_sha256="sha256:raw", visits=20)
    glrt = dict(
        session_id="test-session",
        input_manifest_sha256="sha256:raw",
        state="figures_ready",
        total_visits=20,
        checkpoint_visits=20,
        configuration=dict(probe_stride_ms=120),
        binding_sha256="sha256:binding",
        metrics_manifest_sha256="sha256:metrics",
    )
    tracking = dict(
        state="complete",
        session_id="test-session",
        product=dict(
            session_id="test-session",
            input_manifest_sha256="sha256:raw",
            analysis_manifest_sha256="sha256:metrics",
            configuration_digest="sha256:config",
            trajectory_state="complete",
            tle_state="complete",
            created_at="2026-09-28T00:00:00Z",
            attempted_group_count=4,
            deferred_group_count=190,
            group_limit=4,
        ),
    )
    return row, glrt, tracking, 1790600000000000000


def test_complete_bounded_analysis_keeps_deferred_groups(complete):
    before = copy.deepcopy(complete)
    assert mint.analysis_reasons(*complete) == []
    assert complete == before


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("state", "running", "glrt_incomplete"),
        ("checkpoint_visits", 19, "glrt_visit_coverage_incomplete"),
        ("input_manifest_sha256", "sha256:other", "glrt_binding_invalid"),
        ("metrics_manifest_sha256", None, "glrt_binding_invalid"),
        ("configuration", {"probe_stride_ms": 10}, "wrong_glrt_configuration"),
    ],
)
def test_glrt_failure(complete, field, value, reason):
    complete[1][field] = value
    assert reason in mint.analysis_reasons(*complete)


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("session_id", "other", "tracking_binding_invalid"),
        ("analysis_manifest_sha256", "sha256:stale", "tracking_binding_invalid"),
        ("input_manifest_sha256", "sha256:other", "tracking_binding_invalid"),
        ("trajectory_state", "pending", "tracking_stages_incomplete"),
        ("tle_state", "pending", "tracking_stages_incomplete"),
        ("created_at", "2026-09-29T00:00:00Z", "tracking_not_complete_at_cutoff"),
        ("created_at", None, "tracking_completion_time_unavailable"),
    ],
)
def test_tracking_failure(complete, field, value, reason):
    complete[2]["product"][field] = value
    assert reason in mint.analysis_reasons(*complete)


def test_pending_product_is_excluded(complete):
    complete[2].update(state="pending", product=None)
    assert "tracking_incomplete" in mint.analysis_reasons(*complete)


def test_cutoff_equality_is_inclusive(complete):
    row, glrt, tracking, _ = complete
    assert not mint.analysis_reasons(row, glrt, tracking, 1790553600000000000)
    assert "tracking_not_complete_at_cutoff" in mint.analysis_reasons(
        row, glrt, tracking, 1790553599999999999
    )


def test_existing_dataset_cannot_be_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(mint, "ROOT", tmp_path)
    (tmp_path / "manifest.json").write_text("existing authority")
    with pytest.raises(RuntimeError, match="already sealed"):
        mint.seal()
    assert (tmp_path / "manifest.json").read_text() == "existing authority"


def test_ds10_seal_and_tamper_detection(complete, tmp_path, monkeypatch):
    root = tmp_path / "dataset"
    for name in ("local", "analysis", "pose"):
        (root / name).mkdir(parents=True)
    parent = tmp_path / "parent.json"
    mint.write(parent, {"captures": [{
        "session_id": "parent", "manifest_sha256": "sha256:parent",
        "capture_end_utc_ns": 100,
    }]})
    monkeypatch.setattr(mint, "ROOT", root)
    monkeypatch.setattr(mint, "PARENT", parent)
    row, glrt, tracking, cutoff = complete
    evidence = root / "analysis/test-session.json"
    mint.write(evidence, {"glrt": glrt, "tracking": tracking})
    row.update(
        exclusion_reasons=[], capture_start_earliest_utc_ns=101,
        capture_end_utc_ns=150, finalized_utc_ns=160,
        compressed_bytes=100, valid_sample_count=40, sample_rate_hz=10,
        analysis_evidence_sha256=mint.digest(evidence.read_bytes()),
    )
    mint.write(root / "local/snapshot.json", {
        "cutoff": cutoff, "lower": 100,
        "candidates": [[None, 160, None, "test-session"]],
        "parent_manifest_sha256": mint.digest(parent.read_bytes()),
    })
    mint.write(root / "local/inventory.json", [row])
    mint.seal()
    manifest = mint.json.loads((root / "manifest.json").read_text())
    assert manifest["dataset_id"] == "DS10"
    assert manifest["parent_dataset"] == "DS9"
    assert manifest["counts"]["recordings"] == 1
    mint.verify()
    evidence.write_text("tampered")
    with pytest.raises(AssertionError):
        mint.verify()
