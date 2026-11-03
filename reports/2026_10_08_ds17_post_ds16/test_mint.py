"""Offline DS17 boundary, membership, provenance and overwrite checks."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("ds17_mint", Path(__file__).with_name("mint.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def row(sid="a", iq="sha256:a", **kwargs):
    return dict(
        session_id=sid,
        uncompressed_sha256=iq,
        capture_start_utc_ns=m.LOW,
        finalized_utc_ns=m.HIGH,
        **kwargs,
    )


@pytest.mark.parametrize(
    "start,end,expected",
    [
        (m.LOW - 1, m.HIGH, False),
        (m.LOW, m.HIGH, True),
        (m.HIGH - 1, m.HIGH, True),
        (m.HIGH, m.HIGH, False),
        (m.LOW, m.HIGH + 1, False),
    ],
)
def test_boundaries(start, end, expected):
    assert m.eligible(start, end) is expected


def test_deduplicates_matching_sources():
    merged = m.merge([row()], [row(source_kind="firmware_archive")], {"captures": []})
    assert (
        len(merged) == 1 and merged[0]["archive_references"][0]["source_kind"] == "firmware_archive"
    )


def test_rejects_binding_mismatch():
    with pytest.raises(ValueError, match="binding"):
        m.merge([row()], [row(iq="sha256:other")], {"captures": []})


@pytest.mark.parametrize("parent", [row(), row(sid="other")])
def test_rejects_parent_overlap(parent):
    with pytest.raises(ValueError, match="overlap"):
        m.merge([row()], [], {"captures": [parent]})


def test_rejects_duplicate_iq_and_sessions():
    for rows in ([row(), row()], [row(), row(sid="b")]):
        with pytest.raises(ValueError, match="duplicate"):
            m.merge(rows, [], {"captures": []})


def test_quality_does_not_filter_membership():
    r = row(transport_missing_sample_count=42, terminal={"error": "capture failure"})
    assert len(m.merge([r], [], {"captures": []})) == 1


def test_exclusive_artifact_write(tmp_path):
    path = tmp_path / "manifest.json"
    m.write(path, {"frozen": True})
    with pytest.raises(FileExistsError):
        m.write(path, {"frozen": False})


def test_rejects_tampered_seal(tmp_path):
    m.write(tmp_path / "manifest.json", {})
    m.write(tmp_path / "seal.json", {"files": {"manifest.json": "sha256:wrong"}})
    with pytest.raises(ValueError, match="seal mismatch"):
        m.verify(tmp_path)


def test_late_publication_requires_bound_pre_cutoff_archive_receipt():
    d = dict(
        schema="leo.feature103-dual-rx-adaptive-summary/v1",
        created_at=m.END,
        iq_archive="/source/a",
        rate_hz=2500000,
        radio_serial="radio",
    )
    assert m.completed_archive_evidence(d, "a", 2500000, "radio") == m.HIGH
    for key, value in [
        ("iq_archive", "/source/b"),
        ("rate_hz", 10000000),
        ("radio_serial", "other"),
        ("created_at", "2026-10-08T14:36:57+00:00"),
    ]:
        with pytest.raises(ValueError, match="evidence mismatch"):
            m.completed_archive_evidence({**d, key: value}, "a", 2500000, "radio")
