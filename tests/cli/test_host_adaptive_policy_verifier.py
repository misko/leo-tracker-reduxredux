from types import SimpleNamespace as N

import pytest

from tests.scanner.test_adaptive_scan import Scan, policy  # noqa: F401
from tools.verify_host_adaptive_policy import verify_policy


def trace():
    events, records = [], []
    for i in range(32):
        now = 1_000_000 + i * 1_260_000
        events.append(
            N(
                target_index=i % 8,
                valid_start_counter=now + 10_000,
                decision=N(
                    decision_counter=now,
                    basis_visit=i - 1 if i else None,
                    proposed_target=i % 8,
                    reason="warmup" if i < 24 else "none_active",
                    active_mask=0,
                    quiet_mask=0,
                    consecutive_misses=0,
                    cooldown_remaining_samples=0,
                    mode="shadow",
                ),
            )
        )
        records.append(
            N(
                target_index=i % 8,
                valid_end_counter_exclusive=now + 1_210_000,
                feedback_outcome="unknown",
                health="healthy",
                feedback_disposition="accepted",
            )
        )
    return N(events=events, host_decisions=records)


def test_uniform_unknown_trace_preserves_unknown_and_revisit():
    result = verify_policy(trace())
    assert result["verified_choices"] == 32
    assert result["maximum_revisit_seconds"] == 1.008


@pytest.mark.parametrize("fault", ["mask", "target", "basis", "delivery", "outcome"])
def test_trace_disagreement_cannot_qualify(fault):
    receipt = trace()
    if fault == "mask":
        receipt.events[10].decision.active_mask = 1
    elif fault == "target":
        receipt.events[10].target_index = 3
    elif fault == "basis":
        receipt.events[10].decision.basis_visit = 10
    elif fault == "delivery":
        receipt.host_decisions[9].feedback_disposition = "rejected"
    else:
        receipt.host_decisions[9].feedback_outcome = "detected"
    with pytest.raises(ValueError):
        verify_policy(receipt)


@pytest.mark.parametrize("rx", [0, 1])
@pytest.mark.parametrize("mask", [1, 31, 127, 255])
def test_independent_replay_matches_native_weighting_and_cooldowns(policy, rx, mask):  # noqa: F811
    scan = Scan(policy, rate=10_000_000, single_rx=rx)
    events, records = [], []
    reasons = ["warmup", "weighted", "exploration", "none_active", "fault_fallback"]
    try:
        for index in range(160):
            choice = scan.choose()
            start = scan.now
            observation = scan.commit(choice)
            # Change activity halfway through to exercise cooldown/demotion.
            outcome = 1 if (mask >> choice.target & 1) and index < 80 else 2
            observation.outcome = outcome
            scan.observe(observation)
            events.append(
                N(
                    target_index=choice.target,
                    valid_start_counter=start,
                    decision=N(
                        decision_counter=choice.decision_counter,
                        basis_visit=None if index == 0 else choice.basis_visit,
                        proposed_target=choice.target,
                        reason=reasons[choice.reason],
                        active_mask=choice.active_mask,
                        quiet_mask=choice.quiet_mask,
                        consecutive_misses=choice.consecutive_misses,
                        cooldown_remaining_samples=choice.cooldown_remaining_samples,
                        mode="adaptive",
                    ),
                )
            )
            records.append(
                N(
                    target_index=choice.target,
                    valid_end_counter_exclusive=scan.now,
                    health="healthy",
                    feedback_disposition="accepted",
                    feedback_outcome="detected" if outcome == 1 else "not_detected",
                )
            )
        assert verify_policy(N(events=events, host_decisions=records))["verified_choices"] == 160
    finally:
        scan.close()
