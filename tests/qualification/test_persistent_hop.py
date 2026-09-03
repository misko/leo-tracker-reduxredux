from __future__ import annotations

import inspect
from dataclasses import dataclass
from functools import cache
from typing import Any, cast

import pytest

from leo.qualification import (
    PERSISTENT_HOP_QUALIFICATION_BLOCK_SAMPLES,
    PERSISTENT_HOP_QUALIFICATION_GUARD_MS,
    PERSISTENT_HOP_QUALIFICATION_KERNEL_BUFFERS,
    PersistentHopQualificationCandidate,
    PersistentHopQualificationPolicy,
    PersistentHopQualificationTrial,
    evaluate_persistent_hop_qualification,
    persistent_hop_block_screen,
    persistent_hop_confirmation_stage,
    persistent_hop_guard_screen,
    persistent_hop_kernel_screen,
)
from leo.scanner.fake_persistent_hop import FakePersistentHopRadio
from leo.scanner.persistent_hop import (
    PersistentHopPlanV1,
    PersistentHopSessionReceiptV1,
    compile_persistent_hop_plan_v1,
)


@dataclass(frozen=True, slots=True)
class _QueueTelemetry:
    capacity_visits: int = 16
    high_water_visits: int = 8
    enqueue_failure_count: int = 0
    maximum_enqueue_wait_ns: int = 1_000_000
    maximum_writer_service_ns: int = 80_000_000


def _candidate(
    *,
    guard_ms: int = 11,
    kernel_buffers: int = 8,
    samples_per_block: int = 131_072,
) -> PersistentHopQualificationCandidate:
    return PersistentHopQualificationCandidate(
        guard_ms=guard_ms,
        kernel_buffers=kernel_buffers,
        samples_per_block=samples_per_block,
    )


def _plan(
    *,
    guard_ms: int,
    kernel_buffers: int,
    samples_per_block: int,
    sample_rate_hz: int,
) -> PersistentHopPlanV1:
    """Bridge this lane and root's additive plan fields during cherry-pick."""

    parameters = inspect.signature(compile_persistent_hop_plan_v1).parameters
    arguments: dict[str, object] = {
        "sample_rate_hz": sample_rate_hz,
        "kernel_buffers": kernel_buffers,
    }
    if "transition_guard_us" in parameters:
        arguments["transition_guard_us"] = guard_ms * 1_000
    if "samples_per_block" in parameters:
        arguments["samples_per_block"] = samples_per_block
    compiler = cast(Any, compile_persistent_hop_plan_v1)
    return cast(PersistentHopPlanV1, compiler(**arguments))


@cache
def _base_receipt(
    guard_ms: int,
    kernel_buffers: int,
    samples_per_block: int,
    sample_rate_hz: int,
) -> PersistentHopSessionReceiptV1:
    radio = FakePersistentHopRadio(transition_invalid_ms=guard_ms)
    radio.open()
    plan = _plan(
        guard_ms=guard_ms,
        kernel_buffers=kernel_buffers,
        samples_per_block=samples_per_block,
        sample_rate_hz=sample_rate_hz,
    )
    session_id = (
        f"qualification-g{guard_ms}-k{kernel_buffers}-b{samples_per_block}-r{sample_rate_hz}"
    )
    receipt = radio.begin_session(plan, session_id=session_id).run_to_completion()
    radio.close()
    return receipt


def _receipt(
    candidate: PersistentHopQualificationCandidate,
    *,
    repetition: int,
    sample_rate_hz: int = 2_500_000,
) -> PersistentHopSessionReceiptV1:
    base = _base_receipt(
        candidate.guard_ms,
        candidate.kernel_buffers,
        candidate.samples_per_block,
        sample_rate_hz,
    )
    return base.model_copy(update={"session_id": f"{base.session_id}-pass-{repetition}"})


def _queue(
    **updates: object,
) -> _QueueTelemetry:
    values: dict[str, object] = {
        "capacity_visits": 16,
        "high_water_visits": 8,
        "enqueue_failure_count": 0,
        "maximum_enqueue_wait_ns": 1_000_000,
        "maximum_writer_service_ns": 80_000_000,
    }
    values.update(updates)
    return _QueueTelemetry(**values)  # type: ignore[arg-type]


def _trials(
    candidates: tuple[PersistentHopQualificationCandidate, ...],
    *,
    repetitions: int = 2,
    sample_rates_hz: tuple[int, ...] = (2_500_000,),
) -> tuple[PersistentHopQualificationTrial, ...]:
    return tuple(
        PersistentHopQualificationTrial(
            candidate=candidate,
            receipt=(receipt := _receipt(candidate, repetition=repetition, sample_rate_hz=rate)),
            persisted_receipt=receipt,
            queue=_queue(),
        )
        for candidate in candidates
        for rate in sample_rates_hz
        for repetition in range(repetitions)
    )


def test_policy_is_default_off_and_adaptive_stages_avoid_cartesian_rf_runs() -> None:
    policy = PersistentHopQualificationPolicy()
    disabled = evaluate_persistent_hop_qualification(policy, ())

    assert disabled.status == "disabled"
    assert disabled.selected_candidate is None

    guard = persistent_hop_guard_screen(5_000_000)
    kernel = persistent_hop_kernel_screen(5_000_000, guard_ms=3)
    block = persistent_hop_block_screen(5_000_000, guard_ms=3, kernel_buffers=4)
    confirmation = persistent_hop_confirmation_stage(
        5_000_000,
        candidate=_candidate(guard_ms=3, kernel_buffers=4, samples_per_block=262_144),
        policy=PersistentHopQualificationPolicy(enabled=True, required_pass_count=6),
    )

    assert [item.guard_ms for item in guard.candidates] == [11, 8, 5, 3]
    assert [item.kernel_buffers for item in kernel.candidates] == [8, 4, 2]
    assert [item.samples_per_block for item in block.candidates] == [262_144, 131_072, 65_536]
    assert guard.planned_capture_seconds == 20 * 60
    assert kernel.planned_capture_seconds == 15 * 60
    assert block.planned_capture_seconds == 15 * 60
    assert confirmation.planned_capture_seconds == 30 * 60
    distinct = set(guard.candidates) | set(kernel.candidates) | set(block.candidates)
    assert len(distinct) == 8
    assert len(distinct) < (
        len(PERSISTENT_HOP_QUALIFICATION_GUARD_MS)
        * len(PERSISTENT_HOP_QUALIFICATION_KERNEL_BUFFERS)
        * len(PERSISTENT_HOP_QUALIFICATION_BLOCK_SAMPLES)
    )


def test_guard_ladder_quantifies_90_and_95_percent_duty_thresholds() -> None:
    candidates = tuple(_candidate(guard_ms=guard_ms) for guard_ms in (11, 8, 5, 3))
    trials = _trials(candidates)

    at_90 = evaluate_persistent_hop_qualification(
        PersistentHopQualificationPolicy(
            enabled=True,
            required_pass_count=2,
            required_sample_rates_hz=(2_500_000,),
            minimum_valid_duty_ppm=900_000,
        ),
        trials,
    )
    at_95 = evaluate_persistent_hop_qualification(
        PersistentHopQualificationPolicy(
            enabled=True,
            required_pass_count=2,
            required_sample_rates_hz=(2_500_000,),
            minimum_valid_duty_ppm=950_000,
        ),
        tuple(reversed(trials)),
    )

    assert at_90.status == "qualified"
    assert at_90.selected_candidate == _candidate(guard_ms=3)
    assert {item.candidate.guard_ms: item.worst_valid_duty_ppm for item in at_90.candidates} == {
        11: 916_030,
        8: 937_500,
        5: 960_000,
        3: 975_609,
    }
    assert {item.candidate.guard_ms for item in at_90.candidates if item.qualified} == {
        11,
        8,
        5,
        3,
    }
    assert {item.candidate.guard_ms for item in at_95.candidates if item.qualified} == {5, 3}
    assert at_95.selected_candidate == _candidate(guard_ms=3)


def test_selection_prefers_smallest_stable_k_and_largest_equal_duty_block() -> None:
    kernel_candidates = tuple(
        _candidate(guard_ms=3, kernel_buffers=kernel_buffers)
        for kernel_buffers in PERSISTENT_HOP_QUALIFICATION_KERNEL_BUFFERS
    )
    policy = PersistentHopQualificationPolicy(
        enabled=True,
        required_pass_count=2,
        required_sample_rates_hz=(2_500_000,),
    )

    all_stable = evaluate_persistent_hop_qualification(policy, _trials(kernel_candidates))
    k2_saturated = tuple(
        replace_trial_queue(trial, high_water_visits=16)
        if trial.candidate.kernel_buffers == 2
        else trial
        for trial in _trials(kernel_candidates)
    )
    k2_rejected = evaluate_persistent_hop_qualification(policy, k2_saturated)

    assert all_stable.selected_candidate == _candidate(guard_ms=3, kernel_buffers=2)
    assert k2_rejected.selected_candidate == _candidate(guard_ms=3, kernel_buffers=4)

    block_candidates = tuple(
        _candidate(guard_ms=3, kernel_buffers=2, samples_per_block=samples_per_block)
        for samples_per_block in PERSISTENT_HOP_QUALIFICATION_BLOCK_SAMPLES
    )
    block_decision = evaluate_persistent_hop_qualification(policy, _trials(block_candidates))
    assert block_decision.selected_candidate == _candidate(
        guard_ms=3,
        kernel_buffers=2,
        samples_per_block=262_144,
    )


def replace_trial_queue(
    trial: PersistentHopQualificationTrial,
    **updates: object,
) -> PersistentHopQualificationTrial:
    return PersistentHopQualificationTrial(
        candidate=trial.candidate,
        receipt=trial.receipt,
        persisted_receipt=trial.persisted_receipt,
        queue=_queue(**updates),
    )


@pytest.mark.parametrize(
    ("queue_updates", "reason"),
    [
        ({"high_water_visits": 13}, "queue high-water"),
        ({"enqueue_failure_count": 1}, "enqueue failures"),
        ({"maximum_enqueue_wait_ns": 5_000_001}, "enqueue wait"),
        ({"maximum_writer_service_ns": 120_000_001}, "writer service"),
    ],
)
def test_queue_pressure_and_closure_fail_closed(
    queue_updates: dict[str, object], reason: str
) -> None:
    candidate = _candidate(guard_ms=5)
    receipt = _receipt(candidate, repetition=0)
    trial = PersistentHopQualificationTrial(
        candidate=candidate,
        receipt=receipt,
        persisted_receipt=receipt,
        queue=_queue(**queue_updates),
    )

    decision = evaluate_persistent_hop_qualification(
        PersistentHopQualificationPolicy(
            enabled=True,
            required_pass_count=2,
            required_sample_rates_hz=(2_500_000,),
        ),
        (trial,),
    )

    assert decision.status == "not_qualified"
    assert any(reason in item for item in decision.assessments[0].failure_reasons)


def test_receipt_failure_duplicate_session_and_missing_repetition_fail_closed() -> None:
    candidate = _candidate(guard_ms=5)
    healthy_receipt = _receipt(candidate, repetition=0)
    healthy = PersistentHopQualificationTrial(
        candidate=candidate,
        receipt=healthy_receipt,
        persisted_receipt=healthy_receipt,
        queue=_queue(),
    )
    duplicate = PersistentHopQualificationTrial(
        candidate=candidate,
        receipt=healthy_receipt,
        persisted_receipt=healthy_receipt,
        queue=_queue(),
    )

    duplicate_decision = evaluate_persistent_hop_qualification(
        PersistentHopQualificationPolicy(
            enabled=True,
            required_pass_count=2,
            required_sample_rates_hz=(2_500_000,),
        ),
        (duplicate, healthy),
    )
    one_pass_decision = evaluate_persistent_hop_qualification(
        PersistentHopQualificationPolicy(
            enabled=True,
            required_pass_count=2,
            required_sample_rates_hz=(2_500_000,),
        ),
        (healthy,),
    )

    assert duplicate_decision.status == "not_qualified"
    assert all(
        "duplicated" in assessment.failure_reasons[0]
        for assessment in duplicate_decision.assessments
    )
    assert one_pass_decision.status == "not_qualified"
    assert "1/2 required repeated trials" in one_pass_decision.candidates[0].failure_reasons[-1]


def test_missing_queue_or_persisted_receipt_mismatch_fails_closed() -> None:
    candidate = _candidate(guard_ms=5)
    receipt = _receipt(candidate, repetition=0)
    missing_queue = PersistentHopQualificationTrial(
        candidate=candidate,
        receipt=receipt,
        persisted_receipt=receipt,
        queue=None,
    )
    mismatched_manifest = PersistentHopQualificationTrial(
        candidate=candidate,
        receipt=receipt.model_copy(update={"session_id": "different-terminal"}),
        persisted_receipt=receipt,
        queue=_queue(),
    )

    decision = evaluate_persistent_hop_qualification(
        PersistentHopQualificationPolicy(
            enabled=True,
            required_pass_count=2,
            required_sample_rates_hz=(2_500_000,),
        ),
        (missing_queue, mismatched_manifest),
    )
    reasons = tuple(
        reason for assessment in decision.assessments for reason in assessment.failure_reasons
    )

    assert decision.status == "not_qualified"
    assert any("queue telemetry is missing" in reason for reason in reasons)
    assert any("manifest receipt disagrees" in reason for reason in reasons)


def test_continuity_restoration_duty_and_candidate_binding_fail_closed() -> None:
    candidate = _candidate(guard_ms=11)
    plan = _plan(
        guard_ms=11,
        kernel_buffers=8,
        samples_per_block=131_072,
        sample_rate_hz=2_500_000,
    )

    continuity_radio = FakePersistentHopRadio(gaps_before_visits={3: 17})
    continuity_radio.open()
    continuity = continuity_radio.begin_session(plan, session_id="continuity-failure")
    continuity_receipt = continuity.run_to_completion()
    continuity_radio.close()

    restoration_radio = FakePersistentHopRadio(restoration_error="restore failed")
    restoration_radio.open()
    restoration = restoration_radio.begin_session(plan, session_id="restoration-failure")
    restoration_receipt = restoration.run_to_completion()
    restoration_radio.close()

    low_duty_receipt = _receipt(candidate, repetition=99)
    mismatch = _candidate(guard_ms=11, kernel_buffers=4)
    trials = (
        PersistentHopQualificationTrial(
            candidate=candidate,
            receipt=continuity_receipt,
            persisted_receipt=continuity_receipt,
            queue=_queue(),
        ),
        PersistentHopQualificationTrial(
            candidate=candidate,
            receipt=restoration_receipt,
            persisted_receipt=restoration_receipt,
            queue=_queue(),
        ),
        PersistentHopQualificationTrial(
            candidate=candidate,
            receipt=low_duty_receipt,
            persisted_receipt=low_duty_receipt,
            queue=_queue(),
        ),
        PersistentHopQualificationTrial(
            candidate=mismatch,
            receipt=low_duty_receipt.model_copy(update={"session_id": "kernel-mismatch"}),
            persisted_receipt=low_duty_receipt.model_copy(update={"session_id": "kernel-mismatch"}),
            queue=_queue(),
        ),
    )
    decision = evaluate_persistent_hop_qualification(
        PersistentHopQualificationPolicy(
            enabled=True,
            required_pass_count=2,
            required_sample_rates_hz=(2_500_000,),
            minimum_valid_duty_ppm=950_000,
        ),
        trials,
    )
    reasons = tuple(
        reason for assessment in decision.assessments for reason in assessment.failure_reasons
    )

    assert decision.status == "not_qualified"
    assert any("continuity is not attested" in reason for reason in reasons)
    assert any("restoration is not attested" in reason for reason in reasons)
    assert any("duty is below" in reason for reason in reasons)
    assert any("kernel depth disagrees" in reason for reason in reasons)


def test_candidate_requires_repeated_passes_at_both_scheduled_rates() -> None:
    candidate = _candidate(guard_ms=5)
    policy = PersistentHopQualificationPolicy(enabled=True, required_pass_count=2)

    one_rate = evaluate_persistent_hop_qualification(
        policy,
        _trials((candidate,), sample_rates_hz=(2_500_000,)),
    )
    both_rates = evaluate_persistent_hop_qualification(
        policy,
        _trials((candidate,), sample_rates_hz=(2_500_000, 5_000_000)),
    )

    assert one_rate.status == "not_qualified"
    assert both_rates.status == "qualified"
    assert both_rates.selected_candidate == candidate
