"""Offline integrity/claim checks for the authorized live scanner campaign."""

import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "reports/evidence/2026_09_10_scanner_live"


def test_archived_live_evidence_and_figures_match_index():
    index = json.loads((EVIDENCE / "index.json").read_bytes())
    for row in index["originals"]:
        payload = gzip.decompress((EVIDENCE / row["path"]).read_bytes())
        assert len(payload) == row["bytes"]
        assert hashlib.sha256(payload).hexdigest() == row["sha256"]
    for row in index["figures"]:
        payload = (ROOT / row["path"]).read_bytes()
        assert payload.startswith(b"\x89PNG\r\n\x1a\n")
        assert hashlib.sha256(payload).hexdigest() == row["sha256"]


def test_live_claims_distinguish_full_adaptive_from_short_smoke():
    index = json.loads((EVIDENCE / "index.json").read_bytes())
    full = [row for row in index["cases"] if not row["smoke"]]
    assert {(r["rate_hz"], r["detector_enabled"]) for r in full} == {
        (2500000, False),
        (2500000, True),
        (5000000, False),
    }
    assert all(r["source_seconds"] >= 300 and r["valid_duty_ppm"] >= 900000 for r in full)
    assert all(r["full_iq_verified"] for r in full)
    adaptive = next(r for r in full if r["detector_enabled"])
    assert adaptive["terminal"] == "completed"
    assert adaptive["delivery_complete"] and adaptive["dropped_results"] == 0
    assert adaptive["classification_warning"] is None
    assert not any("fallback" in reason for reason in adaptive["decision_reasons"])
    assert adaptive["masks"] == {"63": adaptive["complete_visits"]}
    assert index["wall_ms_percentiles"]["p99"] < 120


def test_both_maintenance_scopes_resumed_and_restored_radio():
    index = json.loads((EVIDENCE / "index.json").read_bytes())
    assert index["firmware_changed"] is False
    for scope in ("0", "1"):
        resumed = json.loads(gzip.decompress((EVIDENCE / scope / "resumed.json.gz").read_bytes()))
        assert resumed["desired_state"] == resumed["observed_state"] == "running"
        for post in (EVIDENCE / scope).glob("case-*/postflight.json.gz"):
            before = json.loads(gzip.decompress(post.with_name("preflight.json.gz").read_bytes()))
            after = json.loads(gzip.decompress(post.read_bytes()))
            assert before["boot_id"] == after["boot_id"] == index["expected_boot_id"]
            assert before["attributes"] == after["attributes"]
