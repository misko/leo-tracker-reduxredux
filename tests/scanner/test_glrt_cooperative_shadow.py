"""Opt-in SDK skips through the actual libiio policy/thread; synthetic IQ, no RF."""

import json
import subprocess

import pytest

from tests.scanner.test_glrt_sdk_replay import artifacts as artifacts
from tests.scanner.test_glrt_shadow_integration import synthetic_workload as synthetic_workload
from tests.scanner.test_glrt_shadow_integration import threaded as threaded
from tools.qualify_scanner_glrt_sdk import COOPERATIVE_PROFILE, POSITIVE_PROFILE, PROTECTION_PROFILE
from tools.qualify_scanner_glrt_shadow import verify

pytestmark = pytest.mark.libiio_integration


@pytest.fixture(scope="module", params=[False, True])
def cooperative_run(threaded, synthetic_workload, request):
    worker, template, pack, manifest = synthetic_workload
    command = [
        str(threaded),
        str(worker),
        str(template),
        str(pack),
        "4840",
        "2",
        "40",
        "1",
        "12" * 32,
        "34" * 32,
        POSITIVE_PROFILE,
        PROTECTION_PROFILE,
    ]
    if request.param:
        command.append("pressure-smoke-v1")
    command.append(COOPERATIVE_PROFILE)
    result = subprocess.run(command, capture_output=True, text=True, timeout=20)
    (pack.parent / f"cooperative-{request.param}.jsonl").write_text(result.stdout)
    assert result.returncode == 0 and not result.stderr, result.stderr
    return result.stdout, manifest, request.param


def checked(raw, manifest, injected):
    return verify(
        raw,
        manifest,
        4840,
        jitter_ms=40,
        capture_protection=True,
        pressure_smoke=injected,
        cooperative_skips=True,
    )


def test_actual_threaded_policy_recovers_without_false_fault_latch(cooperative_run):
    raw, manifest, injected = cooperative_run
    result = checked(raw, manifest, injected)
    assert result["results"] == result["observations"] == result["choices"] == 40
    assert result["policy_model_matched"]
    assert result["computed_results"] > 0
    assert result["observation_outcomes"]["detected"] > 0
    assert result["protection_stats"]["disabled"] == 0
    rows = [json.loads(line) for line in raw.splitlines()]
    choices = [row for row in rows if row["kind"] == "shadow-choice"]
    assert all(row["reason"] != 4 for row in choices)
    assert any(row["reason"] == 1 for row in choices)
    if injected:
        assert len(result["cooperative_skipped_visits"]) >= 3
        assert result["protection_stats"]["resumptions"] >= 1
        skipped = [row for row in rows if row["kind"] == "observation" and row["skip_cause"]]
        assert all((row["outcome"], row["healthy"]) == (0, 1) for row in skipped)
    with pytest.raises(ValueError, match="schema required"):
        verify(raw, manifest, 4840, jitter_ms=40, capture_protection=True, pressure_smoke=injected)


@pytest.mark.parametrize("mutation", ["profile", "cause", "health", "outcome", "counter", "clock"])
def test_cooperative_receipts_reject_fabricated_skips(cooperative_run, mutation):
    raw, manifest, injected = cooperative_run
    rows = [json.loads(line) for line in raw.splitlines()]
    observations = [row for row in rows if row["kind"] == "observation"]
    row = next((row for row in observations if row["skip_cause"]), observations[0])
    if mutation == "profile":
        rows[0]["cooperative_skips_profile"] = "unreviewed"
    elif mutation == "cause":
        row["skip_cause"] = 2 if row["skip_cause"] != 2 else 1
    elif mutation == "health":
        row["healthy"] = 1 - row["healthy"]
    elif mutation == "outcome":
        row["outcome"] = (row["outcome"] + 1) % 3
    elif mutation == "counter":
        next(row for row in rows if row["kind"] == "block")["protection_stats"][
            "pressure_skips"
        ] += 1
    else:
        row["elapsed_ms"] = 0
    with pytest.raises(ValueError):
        checked("\n".join(map(json.dumps, rows)), manifest, injected)
