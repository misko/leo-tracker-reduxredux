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


def test_sealed_host_network_checks_cover_both_rates_without_live_rf():
    definition = read("staged-host/staged-definition.json")
    result = read("staged-host/staged-result.json")
    assert result["exit_code"] == 0 and result["package_paths_unchanged"]
    assert result["no_radio_context"] and not definition["new_rf"]
    assert not definition["firmware_changed"]
    assert "not the production ARM bundle identity" in definition["loopback_fixture_identities"]
    for path in definition["modules"].values():
        assert Path(path).is_relative_to(Path(definition["staged_release"]) / ".venv")
    suite = ET.fromstring(
        gzip.decompress((EVIDENCE / "staged-host/staged-network.xml.gz").read_bytes())
    ).find("testsuite")
    assert suite.get("tests") == "62"
    assert all(suite.get(key) == "0" for key in ("failures", "errors", "skipped"))
    complete = []
    for case in suite.findall("testcase"):
        props = {p.get("name"): p.get("value") for p in case.findall("properties/property")}
        if props.get("ending") == "complete":
            complete.append((props["mode"], int(props["rate_hz"])))
            assert props["complete_visits"] == props["detector_results"] == "2480"
            assert int(props["source_span_samples"]) >= 300 * int(props["rate_hz"])
            assert props["published_recording_http_verified"] == "True"
            stats = json.loads(props["network_fixture_stats"])
            assert stats["opens"] == stats["destroys"] == stats["drains"] == 1
    assert set(complete) == {
        (mode, rate) for mode in ("shadow", "adaptive") for rate in (2500000, 5000000)
    }


def test_release_web_repair_preserves_failed_gate_and_exact_png_checks():
    initial = read("release-qualification/failed/receipt.json")
    assert initial["passed"] is False
    commands = {row["name"]: row for row in initial["commands"]}
    assert commands["production-web-build"]["exit_code"] == 1
    assert commands["production-chromium-e2e"]["exit_code"] == 70
    assert (
        "blocked by failed lane dependencies"
        in commands["production-chromium-e2e"]["validation_error"]
    )
    web = read("release-web-isolation/receipt.json")
    assert web["exit_code"] == 0 and web["sibling_reports_absent"]
    assert web["compiled_index_exists"]
    assert (
        web["manifest_sha256"]
        == hashlib.sha256((ROOT / "web/report-assets.manifest.json").read_bytes()).hexdigest()
    )


def test_corrected_immutable_gate_passes_without_claiming_activation():
    gate = read("release-qualification/corrected/receipt.json")
    assert gate["passed"] and gate["status"] == "passed"
    assert len(gate["commands"]) == 5
    assert all(c["passed"] and c["exit_code"] == 0 for c in gate["commands"])
    assert {lane["name"] for lane in gate["reused_lanes"]} == {
        "protected-real-corpus",
        "current-native-science",
        "current-native-postgresql",
    }
    for variant in ("failed", "corrected"):
        receipt = read(f"release-qualification/{variant}/receipt.json")
        for entry in receipt["evidence"]:
            path = EVIDENCE / f"release-qualification/{variant}/{entry['relative_path']}.gz"
            if path.is_file():
                payload = gzip.decompress(path.read_bytes())
                assert len(payload) == entry["bytes"]
                assert hashlib.sha256(payload).hexdigest() == entry["sha256"]
        for command in receipt["commands"]:
            assert (
                EVIDENCE / f"release-qualification/{variant}/{command['log_relative_path']}.gz"
            ).is_file()
    checkpoint = read("release-qualification/checkpoint.json")
    assert checkpoint["staged_revision"] == gate["git_revision"]
    assert checkpoint["qualification_database_final_schemas"] == ["public"]
    assert checkpoint["runtime_delta_from_staged_loopback_revision"] == []
    assert checkpoint["no_activation"] and not checkpoint["new_rf"]
    assert not checkpoint["firmware_changed"] and checkpoint["acquisition_service"] == "active"
    assert all(not path.endswith(gate["git_revision"]) for path in checkpoint["selectors"].values())
    assert len(checkpoint["runtime_assets_sha256"]) == 12
    for path, expected in checkpoint["runtime_assets_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected


def test_latest_main_qualification_keeps_rf_permission_separate_from_radio_availability():
    receipt = read("main-integration/receipt.json")
    checkpoint = read("main-integration/checkpoint.json")
    assert receipt["passed"] and len(receipt["commands"]) == 5
    assert all(command["passed"] for command in receipt["commands"])
    assert receipt["git_revision"] == checkpoint["staged_revision"]
    assert checkpoint["integrated_main"] == "732f1cdf0a6a1e3180b5ca5ebb4a2b5cb51873be"
    assert checkpoint["approved_rf_seconds"] == 1500 and checkpoint["rf_seconds_used"] == 0
    assert not checkpoint["new_rf"] and not checkpoint["firmware_changed"]
    assert not checkpoint["production_changed"]
    assert checkpoint["qualification_database_final_schemas"] == ["public"]
    assert checkpoint["capture_control"]["desired_state"] == "running"
    assert "needs maintenance permission" in checkpoint["blocker"]
