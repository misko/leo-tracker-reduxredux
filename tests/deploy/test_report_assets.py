"""Bind release-local figure expectations to the reviewed repository originals."""

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REPORT = "2026_09_10_scanner_cooperative_skips_checkpoint"
NAMES = ("capture-vs-screening.png", "desktop-stage-profile.png", "screening-by-target.png")
PUBLIC = ROOT / "web/public/reports/scanner-2026-09-10"


def test_release_manifest_is_exact_projection_of_reviewed_report_inventory():
    original = json.loads((ROOT / f"reports/evidence/{REPORT}/index.json").read_bytes())
    manifest = json.loads((ROOT / "web/report-assets.manifest.json").read_bytes())
    expected = [
        entry
        for entry in original["artifacts"]
        if entry["path"] in {f"figures/{REPORT}/{name}" for name in NAMES}
    ]
    assert len(expected) == 3
    assert manifest == dict(schema_version=1, report=REPORT, artifacts=expected)
    assert sorted(p.name for p in PUBLIC.iterdir()) == sorted(NAMES)


@pytest.mark.parametrize("name", NAMES)
def test_public_figure_bytes_still_equal_original_report(name):
    manifest = json.loads((ROOT / "web/report-assets.manifest.json").read_bytes())
    source_path = f"figures/{REPORT}/{name}"
    entry = next(entry for entry in manifest["artifacts"] if entry["path"] == source_path)
    payload = (PUBLIC / name).read_bytes()
    assert payload == (ROOT / "reports" / source_path).read_bytes()
    assert len(payload) == entry["bytes"]
    assert hashlib.sha256(payload).hexdigest() == entry["sha256"]
