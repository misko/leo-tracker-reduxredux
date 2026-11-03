"""DS12 membership tests: raw membership must not depend on analysis readiness."""
import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location("ds12", Path(__file__).with_name("mint.py"))
mint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mint)


@pytest.mark.parametrize("start,expected", [(100, False), (101, True), (200, True), (201, False)])
def test_window(start, expected):
    assert mint.in_window(start, 100, 200) == expected


def row(sid, start=110, kind="published", digest="sha256:iq"):
    return dict(session_id=sid, capture_start_utc_ns=start, source_kind=kind,
                uncompressed_sha256=digest, manifest_sha256="sha256:" + kind,
                analysis_ready_at_cutoff=False)


def test_pending_analysis_and_archive_only_are_kept():
    result = mint.merge_sources([row("a")], [row("b", 120, "firmware_archive")])
    assert [r["session_id"] for r in result] == ["a", "b"]
    assert not any(r["analysis_ready_at_cutoff"] for r in result)


def test_duplicate_sources_count_once_and_bind_iq():
    result = mint.merge_sources([row("a")], [row("a", kind="firmware_archive")])
    assert len(result) == 1
    assert result[0]["source_kind"] == "published"
    assert result[0]["archive_manifest_sha256"] == "sha256:firmware_archive"
    with pytest.raises(AssertionError):
        mint.merge_sources([row("a")], [row("a", digest="sha256:other")])


def test_existing_seal_tamper_is_detected(tmp_path, monkeypatch):
    monkeypatch.setattr(mint, "ROOT", tmp_path)
    (tmp_path / "manifest.json").write_text("tampered")
    (tmp_path / "SHA256SUMS").write_text("0" * 64 + "  manifest.json\n")
    with pytest.raises(AssertionError):
        mint.verify()


def test_archive_accounts_for_visits_and_flags_terminal_failure(tmp_path):
    document = dict(
        schema="org.leo.firmware-adaptive-iq/v1", session_id="scan-test",
        evidence={"utc_timing": {"begin_before_realtime_ns": 110, "terminal_realtime_ns": 150}},
        setup={"source_rate_hz": 10}, created_utc_ns=160, physical_receivers=[0, 1],
        terminal={"error": 0, "cancelled": 0, "state": 1, "delivered": 1},
        visits=[{"iq": {"compressed_bytes": 32}, "record": {"valid_start": 10, "valid_end": 30, "missing_samples_before": 0}}],
        uncompressed_sha256="sha256:iq",
    )
    path = tmp_path / "scan-test/manifest.json"
    result = mint.archive_row(document, path, b"metadata")
    assert result["valid_sample_count"] == 20
    assert result["compressed_bytes"] == 32
    assert result["capture_quality_reasons"] == []
    assert not result["analysis_ready_at_cutoff"]
    document["visits"].append({"iq": None, "record": {"valid_start": 30, "valid_end": 50, "missing_samples_before": 0}})
    result = mint.archive_row(document, path, b"metadata")
    assert result["visits"] == 1 and result["scheduled_visits"] == 2
    assert result["valid_sample_count"] == 20
    assert result["capture_quality_reasons"] == ["skipped_visits_without_iq"]
    document["terminal"]["error"] = 1
    assert "capture_terminal_not_complete" in mint.archive_row(document, path, b"metadata")["capture_quality_reasons"]
