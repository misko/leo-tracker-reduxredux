"""Portable integrity/reproduction checks for saved checkpoint evidence."""

import gzip
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tools.evaluate_scanner_admission import evaluate

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "reports/evidence/2026_09_10_scanner_provider_admission"


def test_checkpoint_files_match_published_hash_index():
    index = json.loads((ROOT / "index.json").read_text())
    assert len(index["files"]) == 36
    for entry in index["files"]:
        path = (REPO / entry["path"]).resolve()
        assert path.is_relative_to(REPO)
        data = path.read_bytes()
        assert len(data) == entry["bytes"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
    for entry in index["originals"]:
        data = gzip.decompress((ROOT / entry["path"]).read_bytes())
        assert len(data) == entry["original_bytes"]
        assert hashlib.sha256(data).hexdigest() == entry["original_sha256"]
        if "test_counts" in entry:
            suites = ET.fromstring(data).findall("testsuite")
            observed = {
                key: sum(int(s.get(key, "0")) for s in suites)
                for key in ("tests", "failures", "errors", "skipped")
            }
            assert observed == entry["test_counts"]


@pytest.mark.parametrize(
    "session",
    [
        "scan-hop-b5521c5e306d0bd3",
        "scan-hop-bef2de33984fbfd1",
        "scan-hop-ff2ddd107a031611",
        "scan-hop-125ccf74f6736019",
    ],
)
def test_all_saved_model_inventories_reproduce(session):
    source = (ROOT / f"{session}.json.gz").read_bytes()
    result = evaluate(json.loads(gzip.decompress(source)))
    result["snapshot_sha256"] = hashlib.sha256(source).hexdigest()
    saved = json.loads(gzip.decompress((ROOT / f"{session}-model.json.gz").read_bytes()))
    assert result == saved
    for scenario in result["scenarios"]:
        scenario.pop("checks")
    summary = json.loads((ROOT / "summary.json").read_text())
    assert result == next(s for s in summary if s["session_id"] == session)


def test_arm_receipt_is_explicitly_local_not_radio_qualification():
    build = json.loads(gzip.decompress((ROOT / "arm-build-receipt.json.gz").read_bytes()))
    stage = json.loads(gzip.decompress((ROOT / "arm-local-stage-receipt.json.gz").read_bytes()))
    index = json.loads((ROOT / "index.json").read_text())
    assert build["leo_revision"] == index["sdk_revision"]
    assert build["libiio_revision"] == index["provider_revision"]
    assert build["manifest_sha256"] == stage["manifest_sha256"]
    assert stage["remote_calls"] == 0 and stage["companions"] == 8
    assert stage["script_operations"] == 12
    assert build["open_gates"]


@pytest.mark.parametrize("figure", ["target-admission", "coverage-freshness-tradeoff"])
def test_report_figures_are_real_pngs(figure):
    path = REPO / f"reports/figures/2026_09_10_scanner_provider_admission/{figure}.png"
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert int.from_bytes(data[16:20], "big") >= 1600
    assert int.from_bytes(data[20:24], "big") >= 900
