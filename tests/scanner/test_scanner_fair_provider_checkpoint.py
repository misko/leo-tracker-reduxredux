"""Provider/bundle receipts are bounded qualification, not an RF duty claim."""

import gzip
import hashlib
import json
from pathlib import Path

import pytest

EVIDENCE = Path(__file__).resolve().parents[2] / "reports/evidence/2026_09_10_scanner_fair_provider"


def archived(name):
    return gzip.decompress((EVIDENCE / (name + ".gz")).read_bytes())


def test_index_binds_original_receipts_and_archive_bytes():
    index = json.loads((EVIDENCE / "index.json").read_bytes())
    for entry in index["files"]:
        data = (EVIDENCE / entry["path"]).read_bytes()
        assert len(data) == entry["bytes"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
    for entry in index["originals"]:
        data = gzip.decompress((EVIDENCE / entry["path"]).read_bytes())
        assert len(data) == entry["original_bytes"]
        assert hashlib.sha256(data).hexdigest() == entry["original_sha256"]
        if "counts" in entry:
            assert entry["counts"]["tests"] in (34, 62)
            assert all(entry["counts"][key] == 0 for key in ("errors", "failures", "skipped"))


@pytest.mark.parametrize("case", ["off", "fair", "delayed", "asan"])
def test_provider_scenarios_cover_both_rates_with_truthful_overload(case):
    summaries = json.loads((EVIDENCE / "summary.json").read_bytes())
    summary = next(value for value in summaries if value["case"] == case)
    rows = summary["provider_scenarios"]
    assert len(rows) == 14
    assert {row["rate"] for row in rows} == {2500000, 5000000}
    for i, row in enumerate(rows):
        assert row["visits"] == (2 if row["cancelled"] else 34)
        if row["failure"]:
            assert row["fallback"] > 0
        else:
            assert row["fallback"] == 0
        if not row["failure"] and not row["cancelled"]:
            assert row["positives"] > 0 and row["weighted"] > 0
            if row["pressure"]:
                assert row["recovered"] > 0
        if case != "off" and not any(row[k] for k in ("pressure", "failure", "cancelled")):
            admission = summary["admission"][i]
            assert admission["rate"] == row["rate"] and admission["mode"] == row["mode"]
            if case == "fair":
                assert admission["dispatched"] == row["visits"]
            else:
                assert 0 < admission["dispatched"] < row["visits"]
                assert admission["replaced"] + admission["expired"] + admission["freshness"] > 0


def test_arm_candidate_binds_new_policy_without_test_delay_or_remote_installation():
    receipt = json.loads(archived("arm-receipt.json"))
    config_bytes = archived("arm-configuration.json")
    config = json.loads(config_bytes)
    manifest = archived("arm-bundle.json")
    assert receipt["configuration_sha256"] == hashlib.sha256(config_bytes).hexdigest()
    assert receipt["manifest_sha256"] == hashlib.sha256(manifest).hexdigest()
    assert config["capture_protection"]["max_occupied_slots"] == 3
    assert config["capture_protection"]["admission_age_ms"] == 450
    assert config["fair_admission"]["maximum_pending_age_ms"] == 120
    assert config["fair_admission"]["freshness_trigger_ms"] == 2500
    assert config["fair_admission"]["private_pool_abi"] == "LP03"
    assert not config["fair_admission"]["maximum_revisit_guaranteed"]
    symbols = json.loads(archived("arm-worker-symbols.json"))
    assert symbols["returncode"] == 0
    assert "__wrap_leo_presence_dwell_run_ci16" not in symbols["stdout"]
    stage = json.loads(archived("arm-local-stage-receipt.json"))
    assert stage["remote_calls"] == 0 and stage["companions"] == 8
    assert stage["scratch_removed"] and stage["original_release_retained"]
    assert stage["manifest_sha256"] == receipt["manifest_sha256"]


def test_sanitizer_scope_excludes_the_isolated_numerical_worker():
    receipt = json.loads(archived("asan-receipt.json"))
    assert receipt["passed"] and receipt["deliberate_worker_sleep_ms"] == 170
    assert (
        receipt["sanitizer_scope"]
        == "SDK, provider and policy; isolated numerical worker unsanitized"
    )
    sdk = json.loads(archived("sdk-asan.so.build.json"))
    assert "-fsanitize=address,undefined" in sdk["command"]
    worker = json.loads(archived("worker-delayed.build.json"))
    assert "-Wl,--wrap=leo_presence_dwell_run_ci16" in worker["command"]
    assert not any("sanitize" in arg for arg in worker["command"])
