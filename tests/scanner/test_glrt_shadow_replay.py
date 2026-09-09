"""Portable policy-model checks; SDK framing is separately tested end-to-end."""

import copy
import json

import pytest

from tests.scanner.test_adaptive_scan import Observation, Scan
from tests.scanner.test_adaptive_scan import policy as policy
from tools.qualify_scanner_glrt_sdk import BASE
from tools.qualify_scanner_glrt_shadow import verify


@pytest.fixture
def trace(policy, monkeypatch):
    def make(rate=5000000, mask=13, changing=False):
        jobs = 120
        rows = [dict(kind="protocol", schema="leo-sdk-threaded-shadow-replay-v1")]
        s = Scan(policy, rate=rate)
        previous = None
        try:
            for i in range(jobs):
                now = BASE + i * rate * 121 // 1000
                s.now = now
                if previous is not None:
                    s.observe(previous)
                c = s.choose()
                rows.append(
                    dict(
                        kind="shadow-choice",
                        visit=i,
                        actual_target=i % 8,
                        proposed_target=c.target,
                        decision=str(now),
                        basis_visit=str(c.basis_visit),
                        active_mask=c.active_mask,
                        quiet_mask=c.quiet_mask,
                        reason=c.reason,
                        misses=c.consecutive_misses,
                        cooldown_samples=str(c.cooldown_remaining_samples),
                        begin_ms=i * 121 + 0.2,
                        end_ms=i * 121 + 0.3,
                        cpu_ms=0.05,
                        offered_before=i,
                        offered_after=i,
                    )
                )
                start, end = now + rate // 1000, now + rate * 121 // 1000
                assert policy.leo_adaptive_commit_actual(s.ptr, i % 8, start, end) == 0
                outcome = 1 if mask & (1 << (i % 8)) else 2
                if changing and 40 <= i < 80:
                    outcome = 0 if i % 11 == 0 else 2
                previous = Observation(71, 9, i, start, end, rate, 1, i % 8, outcome, 1)
                rows.append(
                    dict(
                        kind="observation",
                        target=i % 8,
                        end=str(end),
                        outcome=outcome,
                        # Match the real observation passed to the C policy.
                        # This fixture stubs SDK validation, not its health field.
                        healthy=previous.healthy,
                        elapsed_ms=(i + 1) * 121 + 0.02,
                    )
                )
                rows.append(
                    dict(
                        kind="shadow-offer",
                        visit=i,
                        begin_ms=(i + 1) * 121,
                        end_ms=(i + 1) * 121 + 0.01,
                    )
                )
        finally:
            s.close()
        rows.append(
            dict(
                kind="shadow-final",
                choices=jobs,
                offered=jobs,
                mock_restores=1,
                parent_maxrss_kib=48000,
                worker_maxrss_kib=15000,
            )
        )
        rows.append(dict(kind="summary"))

        def verified_core(raw, manifest, duration, **kwargs):
            core = [json.loads(line) for line in raw.splitlines()]
            assert core[0]["schema"] == "leo-sdk-modeled-positive-feedback-replay-v1"
            assert not any(r["kind"].startswith("shadow-") for r in core)
            assert kwargs["positive_feedback"] and kwargs["enabled"]
            return dict(jobs=jobs, rate_hz=rate, verified=True)

        monkeypatch.setattr("tools.qualify_scanner_glrt_shadow.verify_sdk", verified_core)
        return rows

    return make


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("mask", [0, 1, 13, 85, 127, 255])
@pytest.mark.parametrize("changing", [False, True])
def test_python_model_matches_native_actual_target_policy_with_cooldown(
    trace, rate, mask, changing
):
    checked = verify(
        "\n".join(map(json.dumps, trace(rate, mask, changing))), {}, 14520, jitter_ms=40
    )
    assert checked["policy_model_matched"] and checked["choices"] == 120
    assert checked["applied_observations"] == 119
    assert checked["tail_observations_without_later_choice"] == 1
    assert checked["feedback_age_at_decision_ms"]["max"] == 0
    if mask == 13 and not changing:
        assert checked["proposals_differing_from_actual"] > 0


@pytest.mark.parametrize(
    "kind,key,value",
    [
        ("shadow-choice", "actual_target", 7),
        ("shadow-choice", "decision", str(BASE + 1)),
        ("shadow-choice", "proposed_target", 7),
        ("shadow-choice", "basis_visit", "0"),
        ("shadow-choice", "active_mask", 255),
        ("shadow-choice", "quiet_mask", 255),
        ("shadow-choice", "misses", 3),
        ("shadow-choice", "cooldown_samples", "1"),
        ("shadow-choice", "reason", 4),
        ("shadow-choice", "end_ms", 122),
        ("shadow-choice", "cpu_ms", -1),
        ("shadow-choice", "offered_after", True),
        ("shadow-offer", "begin_ms", 0),
        ("shadow-offer", "end_ms", 1e6),
        ("shadow-final", "mock_restores", 2),
        ("shadow-final", "choices", 119),
        ("shadow-final", "worker_maxrss_kib", 0),
    ],
)
def test_model_rejects_changed_choice_causality_and_lifecycle(trace, kind, key, value):
    rows = trace()
    next(r for r in rows if r["kind"] == kind)[key] = value
    with pytest.raises(ValueError):
        verify("\n".join(map(json.dumps, rows)), {}, 14520, jitter_ms=40)


@pytest.mark.parametrize("kind", ["shadow-choice", "shadow-offer", "shadow-final"])
@pytest.mark.parametrize("duplicate", [False, True])
def test_shadow_inventory_is_exactly_once(trace, kind, duplicate):
    rows = trace()
    i = next(i for i, r in enumerate(rows) if r["kind"] == kind)
    if duplicate:
        rows.insert(i, copy.deepcopy(rows[i]))
    else:
        del rows[i]
    with pytest.raises(ValueError, match="inventory"):
        verify("\n".join(map(json.dumps, rows)), {}, 14520, jitter_ms=40)


def test_no_future_feedback_may_explain_a_choice(trace):
    rows = trace()
    offer = next(r for r in rows if r["kind"] == "shadow-offer")
    observation = next(r for r in rows if r["kind"] == "observation")
    offer["begin_ms"], offer["end_ms"], observation["elapsed_ms"] = 200, 201, 202
    with pytest.raises(ValueError, match="before it was offered"):
        verify("\n".join(map(json.dumps, rows)), {}, 14520, jitter_ms=40)
