"""Verify threaded shadow replay against an independent Python policy model.

This is modeled saved-IQ integration, not adaptive RF or independent detection
quality. Actual targets stay fixed; the policy is charged only for those visits.
"""

from __future__ import annotations

import json
import math

from tools.qualify_presence_dwell_worker import _counter
from tools.qualify_scanner_glrt_sdk import BASE, quantiles
from tools.qualify_scanner_glrt_sdk import verify as verify_sdk

NO_VISIT = 2**64 - 1


def verify(
    raw,
    manifest,
    duration,
    *,
    jitter_ms,
    algorithm_sha256="12" * 32,
    configuration_sha256="34" * 32,
):
    rows = [json.loads(line) for line in raw.splitlines()]
    if not rows or rows[0].get("schema") != "leo-sdk-threaded-shadow-replay-v1":
        raise ValueError("explicit threaded shadow schema required")
    choices = [r for r in rows if r.get("kind") == "shadow-choice"]
    offers = [r for r in rows if r.get("kind") == "shadow-offer"]
    finals = [r for r in rows if r.get("kind") == "shadow-final"]
    extra = {"shadow-choice", "shadow-offer", "shadow-final"}
    core = [dict(r) for r in rows if r.get("kind") not in extra]
    core[0]["schema"] = "leo-sdk-modeled-positive-feedback-replay-v1"
    checked = verify_sdk(
        "\n".join(map(json.dumps, core)),
        manifest,
        duration,
        delay_blocks=2,
        jitter_ms=jitter_ms,
        enabled=True,
        positive_feedback=True,
        algorithm_sha256=algorithm_sha256,
        configuration_sha256=configuration_sha256,
    )
    observations = [r for r in core if r["kind"] == "observation"]
    jobs, rate = checked["jobs"], checked["rate_hz"]
    if len(choices) != jobs or len(offers) != jobs or len(finals) != 1:
        raise ValueError("incomplete shadow inventory")
    final = finals[0]
    for key, value in dict(choices=jobs, offered=jobs, mock_restores=1).items():
        if type(final.get(key)) is not int or final[key] != value:
            raise ValueError("shadow lifecycle differs")
    for key in ("parent_maxrss_kib", "worker_maxrss_kib"):
        if type(final.get(key)) is not int or not 0 < final[key] < 1024 * 1024:
            raise ValueError("invalid shadow memory receipt")
    for i, offer in enumerate(offers):
        if type(offer.get("visit")) is not int or offer["visit"] != i:
            raise ValueError("shadow offers out of order")
        for key in ("begin_ms", "end_ms"):
            if type(offer.get(key)) not in (int, float) or not math.isfinite(offer[key]):
                raise ValueError("invalid shadow offer clock")
        if (
            not (i + 1) * 121
            <= offer["begin_ms"]
            <= offer["end_ms"]
            <= observations[i]["elapsed_ms"]
        ):
            raise ValueError("shadow offer predates IQ or follows observation receipt")

    # Independent executable specification of the frozen eight-target policy.
    state, misses, last_detection, last_visit, credits = (
        [0] * 8,
        [0] * 8,
        [None] * 8,
        [0] * 8,
        [0] * 8,
    )
    applied = 0
    callback_age, basis_lag, mismatches, max_pending = [], [], 0, 0
    for i, choice in enumerate(choices):
        now = BASE + i * rate * 121 // 1000
        if (
            type(choice.get("visit")) is not int
            or choice["visit"] != i
            or _counter(choice["decision"]) != now
            or type(choice.get("actual_target")) is not int
            or choice["actual_target"] != i % 8
        ):
            raise ValueError("shadow decision or actual target differs")
        for key in ("begin_ms", "end_ms", "cpu_ms"):
            if (
                type(choice.get(key)) not in (int, float)
                or not math.isfinite(choice[key])
                or choice[key] < 0
            ):
                raise ValueError("invalid shadow choice clock")
        if not i * 121 <= choice["begin_ms"] <= choice["end_ms"] < (i + 1) * 121:
            raise ValueError("scheduler missed a model tick")
        for key in ("offered_before", "offered_after"):
            if type(choice.get(key)) is not int or not 0 <= choice[key] <= jobs:
                raise ValueError("invalid offered observation count")
        if choice["offered_before"] > choice["offered_after"]:
            raise ValueError("offered count regressed")
        basis = _counter(choice["basis_visit"])
        end = 0 if basis == NO_VISIT else basis + 1
        if not applied <= end <= i or end - applied > 8:
            raise ValueError("noncausal or unbounded observation prefix")
        for j in range(applied, end):
            obs = observations[j]
            # Queue release can race the consumer within this interval. Do
            # not pretend an after-return producer timestamp is availability.
            if offers[j]["begin_ms"] > choice["end_ms"]:
                raise ValueError("decision used feedback before it was offered")
            age = (now - _counter(obs["end"])) * 1000 / rate
            if not 0 <= age <= 1000:
                raise ValueError("feedback expired at the actual decision boundary")
            callback_age.append(age)
            t = obs["target"]
            if obs["outcome"] == 1:
                state[t], misses[t], last_detection[t] = 1, 0, _counter(obs["end"])
            elif obs["outcome"] == 2:
                misses[t] = min(3, misses[t] + 1)
            else:
                misses[t] = 0
        applied = end
        for t in range(8):
            if misses[t] >= 3 and (
                last_detection[t] is None or now - last_detection[t] >= rate * 2
            ):
                state[t] = 2
        active = sum(1 << t for t in range(8) if state[t] == 1)
        quiet = sum(1 << t for t in range(8) if state[t] == 2)
        reason = 0 if i < 24 else (3 if not active else 1)
        target, total = i % 8, 0
        if reason != 1:
            credits = [0] * 8
        else:
            weights = [1 if s == 2 else 3 for s in state]
            credits = [c + w for c, w in zip(credits, weights, strict=True)]
            total = sum(weights)
            order = [(i + j) % 8 for j in range(8)]
            target = max(order, key=lambda t: credits[t])
            overdue = [t for t in order if now - last_visit[t] >= rate * 2840 // 1000]
            if overdue:
                target, reason = max(overdue, key=lambda t: now - last_visit[t]), 2
        cooldown = (
            0
            if last_detection[target] is None
            else max(0, rate * 2 - (now - last_detection[target]))
        )
        expected = dict(
            proposed_target=target,
            reason=reason,
            active_mask=active,
            quiet_mask=quiet,
            misses=misses[target],
            cooldown_samples=str(cooldown),
        )
        if any(type(choice.get(k)) is not type(v) or choice[k] != v for k, v in expected.items()):
            raise ValueError(f"independent policy mismatch at visit {i}")
        mismatches += target != i % 8
        basis_lag.append(i - end)
        max_pending = max(max_pending, choice["offered_after"] - end)
        if total:
            credits[i % 8] -= total
            credits = [max(-total, min(total, c)) for c in credits]
        last_visit[i % 8] = now + rate // 1000
    return dict(
        checked,
        schema="org.leo.research.threaded-shadow-verification/v1",
        choices=jobs,
        policy_model_matched=True,
        proposals_differing_from_actual=mismatches,
        applied_observations=applied,
        tail_observations_without_later_choice=jobs - applied,
        maximum_offered_not_in_basis=max_pending,
        decision_basis_lag_visits=quantiles(basis_lag),
        feedback_age_at_decision_ms=quantiles(callback_age),
        scheduler_choice_wall_ms=quantiles([c["end_ms"] - c["begin_ms"] for c in choices]),
        scheduler_choice_cpu_ms=quantiles([c["cpu_ms"] for c in choices]),
        parent_maxrss_kib=final["parent_maxrss_kib"],
        worker_maxrss_kib=final["worker_maxrss_kib"],
        limitations="Real SDK, policy SPSC queue and scheduler thread; "
        "quantized 121ms model clock and mock recalls. "
        "Saved IQ remains on its original target; shadow proposals are not executed. "
        "Not IIO/IRQ/network load, radio duty, original arrival replay or independent sensitivity. "
        "Offered-not-in-basis is a logical unapplied prefix, not direct internal queue occupancy. "
        "Terminal observations with no later choice remain recorded; no phantom hop is added.",
    )
