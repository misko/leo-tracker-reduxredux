"""Integrity and scope checks for recorded evidence; no hardware access."""

import gzip
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import pytest

from tools.qualify_presence_dwell_worker import FIELDS
from tools.qualify_presence_worker import compare_values
from tools.qualify_scanner_glrt_sdk import verify

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


def _compare_saved_result(result, metadata):
    assert result["rate_hz"] == metadata["rate_hz"]
    assert result["counter"] == str(metadata["counter"])
    assert result["edge"] == int(metadata["edge"] == "upper")
    expected = metadata["expected"]
    assert result["confirmation_count"] == 1
    assert result["confirmation_window_mask"] == expected["confirmation_window_mask"]
    assert result["rank"]["order"] == expected["rank"]["order"]
    compare_values(result["nuisances"][0], expected["nuisance"], nuisance=True)
    candidates = result["confirmations"][0]["candidates"]
    assert len(candidates) == len(expected["candidates"])
    for got, reference in zip(candidates, expected["candidates"], strict=True):
        compare_values({key: got[key] for key in FIELDS}, reference)


def test_all_saved_iq_arm_runs_match_separate_current_desktop_references():
    prepared = read("saved-iq/prepared.json")
    rows = {row["filename"]: row for row in prepared["rows"]}
    assert len(rows) == 96
    result = read("saved-iq/arm-results.json")
    assert result["completed"] and result["original_dwells"] == 96
    assert result["executions"] == len(result["results"]) == 288
    assert Counter(r["filename"] for r in result["results"]) == dict.fromkeys(rows, 3)
    for row in result["results"]:
        _compare_saved_result(row["result"], rows[row["filename"]]["metadata"])
    # Historical references remain a separate comparison, never overwritten
    # to make the current detector's different configuration pass.
    for row in rows.values():
        _compare_saved_result(row["legacy_result"], row["frozen_metadata"])
    for rate in (2500000, 5000000):
        frozen = read(f"saved-iq/frozen-{rate}.json")
        actual = [r["frozen_metadata"] for r in rows.values() if r["metadata"]["rate_hz"] == rate]
        assert len(actual) == 48 and actual == frozen["records"]
    assert (
        prepared["worker_algorithm_sha256"]
        == hashlib.sha256((ROOT / "runtime/scanner-glrt/algorithm.json").read_bytes()).hexdigest()
    )
    post = read("saved-iq/arm-postflight.json")
    assert post["installed_daemon_unchanged"]
    assert post["new_rf"] is False and post["firmware_changed"] is False


def test_release_integration_receipts_preserve_initial_setup_error_and_rerun():
    for filename, count in (
        ("all-deploy-tests.xml", 286),
        ("scanner-integration-configured.xml", 1720),
    ):
        suite = ET.fromstring(
            gzip.decompress((EVIDENCE / "saved-iq" / (filename + ".gz")).read_bytes())
        ).find("testsuite")
        assert int(suite.get("tests")) == count
        assert all(suite.get(key) == "0" for key in ("failures", "errors", "skipped"))
    initial = ET.fromstring(
        gzip.decompress((EVIDENCE / "saved-iq/scanner-integration.xml.gz").read_bytes())
    ).find("testsuite")
    assert initial.get("errors") == "61" and initial.get("failures") == "0"
    assert all("LEO_LIBIIO_SOURCE" in error.get("message") for error in initial.findall(".//error"))


def test_staging_and_parallel_diagnostics_do_not_hide_failure_or_claim_activation():
    failed = read("publication/parallel-release-gate-failed.json")
    repeated = read("publication/parallel-release-gate-diagnostic.json")
    assert failed["passed"] is False and repeated["passed"] is True
    assert failed["revision"] == repeated["revision"]
    manifest = read("publication/3324228/manifest.json")
    for i in range(32):
        raw = gzip.decompress(
            (EVIDENCE / f"publication/parallel-replay/{i:02}.jsonl.gz").read_bytes()
        ).decode()
        result = verify(
            raw, manifest, 968, delay_blocks=2, jitter_ms=40, enabled=True, positive_feedback=True
        )
        assert result["jobs"] == result["results"] == result["observations"] == 8
    stage = read("publication/release-publication-checkpoint.json")
    assert stage["staged_revision"] == repeated["revision"]
    assert stage["no_activation"] and not stage["new_rf"] and not stage["firmware_changed"]
    assert len(stage["runtime_assets_sha256"]) == 12
    for path, expected in stage["runtime_assets_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected
    assert all(
        not value.endswith(stage["staged_revision"]) for value in stage["selectors"].values()
    )
