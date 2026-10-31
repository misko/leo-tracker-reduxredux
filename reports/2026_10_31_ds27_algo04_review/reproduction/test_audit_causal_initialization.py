"""Component tests for the metadata audit, using synthetic TLE text only."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest


SOURCE = Path(__file__).with_name("audit_causal_initialization.py")
SPEC = importlib.util.spec_from_file_location("causal_initialization_audit", SOURCE)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def test_tle_alpha5_and_exact_epoch(tmp_path):
    path = tmp_path / "selected.tle"
    path.write_text("0 SYNTHETIC\n1 A0004U 19074B   26301.85637857  .00034042  00000-0  30194-3 0  9995\n"
                    "2 A0004  53.1434 138.7470 0001786 162.3219 197.7861 15.68273203385088\n")
    records = audit.tle_records(path)
    assert set(records) == {"100004"}
    assert records["100004"][1] == 1793219591108448000


def test_duplicate_tle_rejected(tmp_path):
    path = tmp_path / "selected.tle"
    pair = "1 44714U 19074B   26301.85637857  .00034042  00000-0  30194-3 0  9995\n2 44714 x\n"
    path.write_text(pair + pair)
    with pytest.raises(ValueError, match="duplicate"):
        audit.tle_records(path)


def test_age_summary_exposes_future_values():
    result = audit.age_summary(10**13, [10**13 - 3600 * 10**9, 10**13 + 10**9])
    assert result["minimum_age_hours"] < 0
    assert result["maximum_age_hours"] == 1
    assert result["latest_utc_ns"] == 10**13 + 10**9


def test_hash_normalization_and_byte_sensitivity(tmp_path):
    path = tmp_path / "metadata.json"
    path.write_bytes(b"{}\n")
    original = audit.digest(path)
    assert audit.normalized(original.removeprefix("sha256:")) == original
    path.write_bytes(b"{}")
    assert audit.digest(path) != original


@pytest.mark.parametrize("future_collection", [False, True])
def test_complete_snapshot_causality_and_future_collection(tmp_path, future_collection):
    root = tmp_path / "inference"
    scan = root / "SCAN"
    scan.mkdir(parents=True)
    line1 = "1 44714U 19074B   26301.85637857  .00034042  00000-0  30194-3 0  9995"
    line2 = "2 44714  53.1434 138.7470 0001786 162.3219 197.7861 15.68273203385088"
    previous_line = line1.replace("26301.85637857", "26300.85637857")
    (scan / "selected.tle").write_text(line1 + "\n" + line2 + "\n")
    (scan / "previous.tle").write_text(previous_line + "\n" + line2 + "\n")
    epoch = audit.tle_records(scan / "selected.tle")["44714"][1]
    earlier = audit.tle_records(scan / "previous.tle")["44714"][1]
    cutoff = epoch + 3600 * 10**9
    collection = cutoff + 1 if future_collection else cutoff - 1
    (scan / "tracking.json").write_text(json.dumps({"clock_anchor": {
        "before": {"realtime_ns": cutoff}, "after": {"realtime_ns": cutoff + 2}}}))
    tracking_hash = audit.digest(scan / "tracking.json")
    (scan / "prepared.json").write_text(json.dumps({"metadata": {
        "causal_cutoff_utc_ns": cutoff, "anchor_utc_ns": cutoff + 1}, "tracking_sha256": tracking_hash}))
    (scan / "nominal_elements.json").write_text(json.dumps({"44714": {
        "lines": [line1, line2], "provenance": {
            "element_epoch_utc_ns": epoch, "collected_utc_ns": collection}}}))
    np.savez(scan / "bank.npz", norad=np.array([44714]))
    previous_hash = audit.digest(scan / "previous.tle")
    (scan / "previous_receipt.json").write_text(json.dumps({
        "sources": {"44714": {"epoch_utc_ns": earlier, "collected_utc_ns": cutoff - 1}},
        "catalogue_sha256": previous_hash}))
    receipt = {"cutoff_utc_ns": cutoff, "origin_utc_ns": cutoff + 1, "candidate_count": 1,
               "latest_max_epoch_utc_ns": epoch, "latest_max_collection_utc_ns": collection,
               "bank_sha256": audit.digest(scan / "bank.npz"),
               "latest_tle_sha256": audit.digest(scan / "selected.tle"),
               "previous_tle_sha256": previous_hash, "previous_count": 1,
               "reference_position_used": False, "candidate_filter": "regional elevation >= -12deg; no whitelist",
               "search_center": [37.906, -122.545], "search_box_width_km": 25.0,
               "regional_center": [37.5, -122.0], "radius_km": 250.0}
    (scan / "receipt.json").write_text(json.dumps(receipt))
    descriptor = {"root": str(root), "input_sha256": tracking_hash, "files": {
        str(path.relative_to(root)): audit.digest(path) for path in scan.iterdir()},
        "terminal": {"reference_usage": "none", "future_TLE_used": False,
                     "region_center": [37.906, -122.545], "box_width_km": 25.0,
                     "start_east_north_km": [0.0, 0.0]}}
    path = tmp_path / "descriptor.json"
    path.write_text(json.dumps(descriptor))
    result = audit.audit_snapshot(path)
    assert result["status"] == ("fail" if future_collection else "pass")
    assert ("latest_each_collection_causal" in result["failed_checks"]) is future_collection
    if not future_collection:
        public_input = tmp_path / "public-input.json"
        public_input.write_bytes((scan / "tracking.json").read_bytes())
        (scan / "tracking.json").write_text(json.dumps(json.loads(public_input.read_text()), indent=2))
        descriptor["files"]["SCAN/tracking.json"] = audit.digest(scan / "tracking.json")
        path.write_text(json.dumps(descriptor))
        result = audit.audit_snapshot(path, public_input)
        assert result["status"] == "pass"
        assert result["snapshot_tracking_byte_identical_to_public_input"] is False
