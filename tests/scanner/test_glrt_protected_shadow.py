"""Explicit protected replay: real numerical/queue/policy paths, synthetic IQ."""

import json
import subprocess

import pytest

from tests.scanner.test_glrt_sdk_replay import artifacts as artifacts
from tests.scanner.test_glrt_shadow_integration import synthetic_workload as synthetic_workload
from tests.scanner.test_glrt_shadow_integration import threaded as threaded
from tools.qualify_scanner_glrt_sdk import POSITIVE_PROFILE, PROTECTION_PROFILE
from tools.qualify_scanner_glrt_shadow import verify

pytestmark = pytest.mark.libiio_integration


@pytest.fixture(scope="module", params=[False, True])
def protected_run(threaded, synthetic_workload, request):
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
    result = subprocess.run(command, capture_output=True, text=True, timeout=20)
    with (pack.parent / f"protected-{request.param}.jsonl").open("x") as output:
        output.write(result.stdout)
    assert result.returncode == 0 and not result.stderr, result.stderr
    return result.stdout, manifest, request.param


def checked(raw, manifest, injected):
    return verify(
        raw, manifest, 4840, jitter_ms=40, capture_protection=True, pressure_smoke=injected
    )


def test_protected_inventory_numerical_parity_and_independent_policy(protected_run):
    raw, manifest, injected = protected_run
    result = checked(raw, manifest, injected)
    assert result["results"] == result["observations"] == result["choices"] == 40
    assert result["computed_results"] + result["unavailable_checks"] == 40
    assert result["policy_model_matched"]
    stats = result["protection_stats"]
    assert stats["watchdog_trips"] == stats["clock_faults"] == stats["disabled"] == 0
    assert stats["peak_occupied_slots"] <= 2
    rows = [json.loads(line) for line in raw.splitlines()]
    choices = [row for row in rows if row["kind"] == "shadow-choice"]
    if injected:
        assert result["unavailable_checks"] >= 3
        assert stats["history_blocks_skipped"] >= 23
        assert stats["resumptions"] >= 1 and stats["pressure_entries"] >= 1
        fallback = next(i for i, row in enumerate(choices) if row["reason"] == 4)
        assert all(row["reason"] == 4 for row in choices[fallback:])
        assert result["observation_outcomes"]["detected"] > 0
    else:
        # This is a functional test on a shared desktop, not an assertion of
        # uncontended timing. Actual measured pressure may also shed checks;
        # the independent verifier requires the exact reported block policy.
        assert result["computed_results"] > 0
        assert result["all_checks_computed"] == (result["computed_results"] == 40)
    with pytest.raises(ValueError, match="schema required"):
        verify(raw, manifest, 4840, jitter_ms=40)


@pytest.mark.parametrize(
    "mutation", ["profile", "busy_count", "history", "miss", "positive", "occupancy"]
)
def test_protected_verifier_rejects_fabricated_diagnostics_or_outcomes(protected_run, mutation):
    raw, manifest, injected = protected_run
    rows = [json.loads(line) for line in raw.splitlines()]
    if mutation == "profile":
        rows[0]["capture_protection"]["worker_timeout_ms"] = 501
    elif mutation == "busy_count":
        rows[-1]["protection_stats"]["backlog_skips"] += 1
    elif mutation == "history":
        next(row for row in rows if row["kind"] == "block")["protection_stats"][
            "history_blocks_skipped"
        ] += 1
    elif mutation == "occupancy":
        rows[-1]["protection_stats"]["occupied_slots"] = 3
    else:
        observations = [row for row in rows if row["kind"] == "observation"]
        row = next((row for row in observations if not row["healthy"]), observations[0])
        row["outcome"] = 2 if mutation == "miss" else 1
        row["healthy"] = 1
        if not injected:
            # Also mutate source identity so an already-matching positive
            # cannot make this adversarial branch accidentally a no-op.
            row["session"] = "72"
    with pytest.raises(ValueError):
        checked("\n".join(map(json.dumps, rows)), manifest, injected)
