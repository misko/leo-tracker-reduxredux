"""Integrity and scope checks for recorded evidence; no hardware access."""

import gzip
import hashlib
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "reports/evidence/2026_09_10_scanner_pending240"


def read(name):
    return json.loads(gzip.decompress((EVIDENCE / (name + ".gz")).read_bytes()))


@pytest.mark.parametrize("folder", ["scanner_fair_long_replay", "scanner_pending240"])
def test_original_receipts_and_rendered_files_have_their_recorded_hashes(folder):
    directory = ROOT / "reports/evidence" / ("2026_09_10_" + folder)
    index = json.loads((directory / "index.json").read_bytes())
    for item in index["files"]:
        data = (ROOT / item["path"]).read_bytes()
        assert len(data) == item["bytes"]
        assert hashlib.sha256(data).hexdigest() == item["sha256"], item["path"]
    for item in index["originals"]:
        data = gzip.decompress((directory / item["path"]).read_bytes())
        assert len(data) == item["original_bytes"]
        assert hashlib.sha256(data).hexdigest() == item["original_sha256"]


def test_all_42_paired_sdk_replays_preserve_inventory_and_bounded_pool():
    receipt = read("replay-receipt.json")
    assert receipt["completed"] and len(receipt["cases"]) == 42
    pairs = {}
    for case in receipt["cases"]:
        result = read("replays/" + Path(case["path"]).parent.name + ".json")
        actual = result["actual"]
        assert actual["records"] == actual["visits"]
        assert actual["screened"] == len(actual["checks"])
        assert not actual["starved_targets"]
        assert result["sampled_model"]["exact_dispatch_agreement"]
        for key in ("disabled", "occupied_slots", "watchdog_trips", "clock_faults"):
            assert actual["protection"][key] == 0
        assert actual["protection"]["peak_occupied_slots"] <= 3
        assert actual["admission"]["running"] == actual["admission"]["pending"] == 0
        key = case["shape"], case["timing_session"], case["cost_session"], case["profile"]
        pairs.setdefault(key, []).append(result)
    assert len(pairs) == 21
    for pair in pairs.values():
        assert {r["maximum_pending_age_ms"] for r in pair} == {120, 240}
        assert pair[0]["worker_cost_ms"] == pair[1]["worker_cost_ms"]
        assert pair[0]["owner_delivery_jitter_ms"] == pair[1]["owner_delivery_jitter_ms"]
        assert pair[0]["snapshot_sha256"] == pair[1]["snapshot_sha256"]


def test_improvement_and_regression_are_both_retained():
    rows = read("replay-receipt.json")["cases"]
    uneven = [r for r in rows if r["shape"] == "rescaled-uneven"]
    assert (
        max(r["worst_source_gap_ms"] for r in uneven if r["maximum_pending_age_ms"] == 120) > 10000
    )
    assert (
        max(r["worst_source_gap_ms"] for r in uneven if r["maximum_pending_age_ms"] == 240) < 5000
    )
    fixed = [r for r in rows if r["shape"] == "original" and r["rate"] == 5000000]
    for cost in {r["cost_session"] for r in fixed}:
        pair = {
            r["maximum_pending_age_ms"]: r
            for r in fixed
            if r["cost_session"] == cost and r["profile"] == "median"
        }
        assert pair[240]["screening_percent"] < pair[120]["screening_percent"]


def test_actual_arm_receipt_proves_execution_and_cleanup_not_live_rf():
    index = json.loads((EVIDENCE / "index.json").read_bytes())
    assert index["arm_provider_passed"] is True
    result = read("arm/arm-provider-result.json")["output"]
    rows = re.findall(r"adaptive provider rate=(\d+).*? PASS", result)
    assert rows.count("2500000") == rows.count("5000000") == 7
    assert "terminal drain and exact-gap tests passed" in result
    post = read("arm/arm-postflight.json")
    assert post["installed_daemon_unchanged"] and post["companions_removed"]
    assert not post["new_rf"] and not post["firmware_changed"]
    config = read("arm/release/configuration.json")
    assert config["fair_admission"]["maximum_pending_age_ms"] == 240
    assert config["capture_protection"]["max_occupied_slots"] == 3
    assert config["fair_admission"]["maximum_revisit_guaranteed"] is False


@pytest.mark.parametrize("mode", ["delayed", "asan"])
def test_provider_overload_and_failure_after_observed_recovery(mode):
    assert read(f"provider/{mode}-receipt.json")["passed"]
    output = gzip.decompress(
        (EVIDENCE / f"provider/v2-{mode}-test_scanner_glrt_provider.log.gz").read_bytes()
    ).decode()
    assert len(re.findall(r"adaptive provider .* PASS", output)) == 14
    injections = re.findall(r"fault injection rate=(\d+) frame=(\d+) recovered=(\d+)", output)
    assert len(injections) == 4
    for _, frame, recovered in injections:
        if int(frame) >= 130:
            assert int(recovered) > 0 and int(frame) < 200
