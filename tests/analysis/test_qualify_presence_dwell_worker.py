"""Reject incomplete, mismatched and misleading whole-dwell replay receipts."""

import copy
import gzip
import json
import math
from pathlib import Path

import pytest

from tools.qualify_native_presence import digest
from tools.qualify_presence_dwell_worker import _counter, verify


def receipt():
    rank = {"scores": [0.0] * 6, "order": list(range(6)), "projected_epoch_samples": [0] * 6}
    screens = {
        "available_mask": 3,
        "selected": 0,
        "contrast": [0.0, 0.0],
        "scores": [[0.0] * 6] * 2,
        "order": [list(range(6))] * 2,
        "epochs": [[0] * 6] * 2,
    }
    expected = {
        "candidates": [],
        "nuisance": {
            "enabled": 1,
            "applied": 0,
            "frequency_hz": 0.0,
            "spectral_fraction": 0.0,
            "fitted_power_fraction": 0.0,
        },
        "rank": rank,
        "screen_diagnostics": screens,
        "confirmation_window_mask": 1,
    }
    manifest = {
        "schema": "org.leo.research.presence-dwell-worker-pack/v1",
        "rate_hz": 5000000,
        "records": [
            {
                "counter": "10000000000000037",
                "visit": 92,
                "channel": 3,
                "edge": "upper",
                "rx": 1,
                "expected": expected,
            }
        ],
    }
    row = {
        **copy.deepcopy(expected),
        "schema": "native-worker-dwell-result-v1",
        "sequence": 0,
        "probe_index": 0,
        "status": 0,
        "rx": 1,
        "rate_hz": 5000000,
        "visit": 92,
        "channel": 3,
        "edge": 1,
        "device_counter": "10000000000000037",
        "valid_end": "10000000000600037",
        "sample_count": 600000,
        "search_window_mask": 63,
        "total_cpu_ms": 90.0,
        "total_wall_ms": 95.0,
        "confirmation_cpu_ms": 60.0,
        "confirmation_wall_ms": 63.0,
        "delivery_latency_ms": 100.0,
    }
    row["rank"].update(total_cpu_ms=30.0, total_wall_ms=32.0)
    terminal = {
        "schema": "native-worker-dwell-summary-v1",
        "rate_hz": 5000000,
        "duration_ms": 126,
        "elapsed_ms": 127.0,
        "submitted": 1,
        "completed": 1,
        "dropped": 0,
        "skipped": 0,
        "pool_bytes": 7258496,
        "max_occupied_slots": 1,
    }
    return manifest, [row, terminal]


def test_complete_full_dwell_receipt_passes_without_claiming_live_duty():
    manifest, rows = receipt()
    report = verify("\n".join(map(json.dumps, rows)), manifest, 126)
    assert report["all_outputs_match_desktop"] and report["executions"] == 1
    assert report["timings"]["total_cpu_ms"]["p99"] == 90
    assert "not original DMA/metadata timing" in report["limitations"]


def test_120ms_period_is_explicit_and_changes_expected_job_count():
    manifest, rows = receipt()
    second = copy.deepcopy(rows[0])
    second["sequence"] = 1
    rows.insert(1, second)
    rows[-1].update(arrival_period_ms=120, completed=2, submitted=2)
    raw = "\n".join(map(json.dumps, rows))
    checked = verify(raw, manifest, 126, arrival_period_ms=120)
    assert checked["executions"] == 2
    assert "every 120 ms" in checked["limitations"]
    assert "not original DMA/metadata timing" in checked["limitations"]
    with pytest.raises(ValueError):
        verify(raw, manifest, 126)
    del rows[-1]["arrival_period_ms"]
    with pytest.raises(ValueError):
        verify("\n".join(map(json.dumps, rows)), manifest, 126, arrival_period_ms=120)


@pytest.mark.parametrize("period", [119, 127, 0, True, 120.0, "120"])
def test_unreviewed_period_is_rejected(period):
    manifest, rows = receipt()
    with pytest.raises(ValueError):
        verify("\n".join(map(json.dumps, rows)), manifest, 126, arrival_period_ms=period)


@pytest.mark.parametrize(
    "field,value",
    [
        ("sequence", 1),
        ("rx", 0),
        ("visit", 93),
        ("edge", 0),
        ("channel", 2),
        ("sample_count", 100000),
        ("status", -1),
        ("search_window_mask", 1),
        ("confirmation_window_mask", 2),
        ("device_counter", 10000000000000037),
        ("device_counter", "010000000000000037"),
        ("valid_end", "10000000000600038"),
        ("total_cpu_ms", 60.0),
        ("total_wall_ms", 63.0),
        ("total_cpu_ms", math.nan),
        ("delivery_latency_ms", -1.0),
    ],
)
def test_result_mutations_fail(field, value):
    manifest, rows = receipt()
    rows[0][field] = value
    with pytest.raises(ValueError):
        verify("\n".join(map(json.dumps, rows)), manifest, 126)


@pytest.mark.parametrize(
    "field,value",
    [
        ("skipped", 1),
        ("dropped", 1),
        ("completed", 0),
        ("elapsed_ms", 10),
        ("duration_ms", 252),
        ("pool_bytes", 1234944),
        ("max_occupied_slots", 4),
    ],
)
def test_terminal_accounting_mutations_fail(field, value):
    manifest, rows = receipt()
    rows[-1][field] = value
    with pytest.raises(ValueError):
        verify("\n".join(map(json.dumps, rows)), manifest, 126)


@pytest.mark.parametrize("diagnostic", ["rank", "screen_diagnostics"])
def test_diagnostics_cannot_be_omitted_or_changed(diagnostic):
    manifest, rows = receipt()
    rows[0][diagnostic]["scores"][0] = 1.0
    with pytest.raises(ValueError):
        verify("\n".join(map(json.dumps, rows)), manifest, 126)


@pytest.mark.parametrize(
    "value", [False, 2**64, -1, "-1", "1.0", "1e16", "01", "18446744073709551616"]
)
def test_uint64_identity_is_not_a_float_or_noncanonical_string(value):
    with pytest.raises(ValueError):
        _counter(value)


EVIDENCE = (
    Path(__file__).resolve().parents[2] / "reports/evidence/2026_09_08_arm_presence_dwell_worker"
)


def test_published_whole_dwell_replay_accounting_reproduces():
    inventory = json.loads((EVIDENCE / "manifest.json").read_text())
    assert all(digest(EVIDENCE / name) == sha for name, sha in inventory["files_sha256"].items())
    for rate in (2500000, 5000000):
        raw = gzip.decompress((EVIDENCE / f"paced-{rate}.jsonl.gz").read_bytes()).decode()
        manifest = json.loads((EVIDENCE / f"paced-{rate}-manifest.json").read_text())
        saved = json.loads((EVIDENCE / f"paced-{rate}-verification.json").read_text())
        checked = verify(raw, manifest, 300000)
        assert all(saved[key] == value for key, value in checked.items())
        assert checked["executions"] == 2381 and checked["unique_dwells"] == 48
    # The complete replay is not a pass of the CPU or single-interval tail gate.
    assert saved["timings"]["total_cpu_ms"]["p99"] > 100
    assert saved["timings"]["delivery_latency_ms"]["p99"] > 126


@pytest.mark.parametrize(
    "name,duration",
    [("rejected-cold-smoke.jsonl.gz", 1008), ("rejected-output-truncated.jsonl.gz", 300000)],
)
def test_retained_failed_runs_still_fail_qualification(name, duration):
    raw = gzip.decompress((EVIDENCE / name).read_bytes()).decode()
    manifest = json.loads((EVIDENCE / "rejected-first8-manifest.json").read_text())
    with pytest.raises(ValueError):
        verify(raw, manifest, duration)
