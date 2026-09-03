"""Pure, default-off qualification policy for persistent-hop tuning.

The adaptive ladder keeps every RF stage bounded and avoids a guard/kernel/block
Cartesian campaign.  This module evaluates already collected receipts and queue
telemetry; it does not schedule hardware, wait, or access storage.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Literal, Protocol

from leo.scanner.persistent_hop import PersistentHopSessionReceiptV1

PERSISTENT_HOP_QUALIFICATION_GUARD_MS = (11, 8, 5, 3)
PERSISTENT_HOP_QUALIFICATION_KERNEL_BUFFERS = (8, 4, 2)
PERSISTENT_HOP_QUALIFICATION_BLOCK_SAMPLES = (262_144, 131_072, 65_536)
PERSISTENT_HOP_QUALIFICATION_RATES_HZ = (2_500_000, 5_000_000)
PERSISTENT_HOP_QUALIFICATION_BASELINE_BLOCK_SAMPLES = 131_072
PERSISTENT_HOP_QUALIFICATION_BASELINE_KERNEL_BUFFERS = 8
PERSISTENT_HOP_QUALIFICATION_MAXIMUM_STAGE_SECONDS = 30 * 60

PersistentHopQualificationStatus = Literal["disabled", "not_qualified", "qualified"]
PersistentHopQualificationStageName = Literal[
    "guard_screen",
    "kernel_screen",
    "block_screen",
    "confirmation",
]


@dataclass(frozen=True, slots=True)
class PersistentHopQualificationCandidate:
    """One rate-independent guard, kernel-depth, and refill-size candidate."""

    guard_ms: int
    kernel_buffers: int
    samples_per_block: int

    def __post_init__(self) -> None:
        if self.guard_ms not in PERSISTENT_HOP_QUALIFICATION_GUARD_MS:
            raise ValueError("persistent-hop qualification guard is outside the fixed ladder")
        if self.kernel_buffers not in PERSISTENT_HOP_QUALIFICATION_KERNEL_BUFFERS:
            raise ValueError("persistent-hop qualification kernel depth is outside the ladder")
        if self.samples_per_block not in PERSISTENT_HOP_QUALIFICATION_BLOCK_SAMPLES:
            raise ValueError("persistent-hop qualification block size is outside the ladder")

    @property
    def canonical_key(self) -> tuple[int, int, int]:
        return (self.guard_ms, self.kernel_buffers, self.samples_per_block)


@dataclass(frozen=True, slots=True)
class PersistentHopQualificationStage:
    """One independently authorized, at-most-30-minute adaptive RF stage."""

    name: PersistentHopQualificationStageName
    sample_rate_hz: int
    candidates: tuple[PersistentHopQualificationCandidate, ...]
    passes_per_candidate: int = 1
    nominal_session_seconds: int = 300

    def __post_init__(self) -> None:
        if self.sample_rate_hz not in PERSISTENT_HOP_QUALIFICATION_RATES_HZ:
            raise ValueError("persistent-hop qualification stage rate is unsupported")
        if not self.candidates or len(set(self.candidates)) != len(self.candidates):
            raise ValueError("persistent-hop qualification stage candidates must be unique")
        if self.passes_per_candidate < 1 or self.nominal_session_seconds != 300:
            raise ValueError("persistent-hop qualification stage repetition is invalid")
        if self.planned_capture_seconds > PERSISTENT_HOP_QUALIFICATION_MAXIMUM_STAGE_SECONDS:
            raise ValueError("persistent-hop qualification stage exceeds 30 minutes")

    @property
    def planned_capture_seconds(self) -> int:
        return len(self.candidates) * self.passes_per_candidate * self.nominal_session_seconds


@dataclass(frozen=True, slots=True)
class PersistentHopQualificationPolicy:
    """Fail-closed policy; disabled until an operator explicitly enables it."""

    enabled: bool = False
    required_pass_count: int = 3
    required_sample_rates_hz: tuple[int, ...] = PERSISTENT_HOP_QUALIFICATION_RATES_HZ
    minimum_valid_duty_ppm: int = 900_000
    maximum_queue_high_water_ppm: int = 750_000
    # Enqueue may consume at most 1/24 of a 120 ms valid visit.  Writer service
    # must finish within one visit, before transition time supplies extra slack.
    maximum_enqueue_wait_ns: int = 5_000_000
    maximum_writer_service_ns: int = 120_000_000

    def __post_init__(self) -> None:
        if not 2 <= self.required_pass_count <= 6:
            raise ValueError("persistent-hop qualification requires 2..6 repeated passes")
        if (
            not self.required_sample_rates_hz
            or len(set(self.required_sample_rates_hz)) != len(self.required_sample_rates_hz)
            or any(
                rate not in PERSISTENT_HOP_QUALIFICATION_RATES_HZ
                for rate in self.required_sample_rates_hz
            )
        ):
            raise ValueError("persistent-hop qualification rates are unsupported or duplicated")
        if not 0 < self.minimum_valid_duty_ppm <= 1_000_000:
            raise ValueError("persistent-hop qualification duty threshold is invalid")
        if not 0 < self.maximum_queue_high_water_ppm < 1_000_000:
            raise ValueError("persistent-hop queue high-water threshold is invalid")
        if self.maximum_enqueue_wait_ns < 0 or self.maximum_writer_service_ns <= 0:
            raise ValueError("persistent-hop queue latency thresholds are invalid")


class PersistentHopQueueTelemetryLike(Protocol):
    """Structural view of storage ``PersistentHopQueueTelemetryV1``."""

    @property
    def capacity_visits(self) -> int: ...

    @property
    def high_water_visits(self) -> int: ...

    @property
    def enqueue_failure_count(self) -> int: ...

    @property
    def maximum_enqueue_wait_ns(self) -> int: ...

    @property
    def maximum_writer_service_ns(self) -> int: ...


@dataclass(frozen=True, slots=True)
class PersistentHopQualificationTrial:
    candidate: PersistentHopQualificationCandidate
    receipt: PersistentHopSessionReceiptV1 = field(repr=False)
    persisted_receipt: PersistentHopSessionReceiptV1 | None = field(repr=False)
    queue: PersistentHopQueueTelemetryLike | None


@dataclass(frozen=True, slots=True)
class PersistentHopQualificationTrialAssessment:
    session_id: str
    candidate: PersistentHopQualificationCandidate
    sample_rate_hz: int
    valid_duty_ppm: int
    queue_high_water_ppm: int | None
    maximum_enqueue_wait_ns: int | None
    maximum_writer_service_ns: int | None
    passed: bool
    failure_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PersistentHopCandidateQualification:
    candidate: PersistentHopQualificationCandidate
    trial_count_by_rate: tuple[tuple[int, int], ...]
    passing_trial_count_by_rate: tuple[tuple[int, int], ...]
    worst_valid_duty_ppm: int | None
    maximum_queue_high_water_ppm: int | None
    maximum_enqueue_wait_ns: int | None
    maximum_writer_service_ns: int | None
    qualified: bool
    failure_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PersistentHopQualificationDecision:
    status: PersistentHopQualificationStatus
    policy: PersistentHopQualificationPolicy
    selected_candidate: PersistentHopQualificationCandidate | None
    selected_worst_valid_duty_ppm: int | None
    assessments: tuple[PersistentHopQualificationTrialAssessment, ...]
    candidates: tuple[PersistentHopCandidateQualification, ...]
    reasons: tuple[str, ...]


def persistent_hop_guard_screen(sample_rate_hz: int) -> PersistentHopQualificationStage:
    """Screen guards safely from 11 ms down at baseline queue geometry."""

    return PersistentHopQualificationStage(
        name="guard_screen",
        sample_rate_hz=sample_rate_hz,
        candidates=tuple(
            PersistentHopQualificationCandidate(
                guard_ms=guard_ms,
                kernel_buffers=PERSISTENT_HOP_QUALIFICATION_BASELINE_KERNEL_BUFFERS,
                samples_per_block=PERSISTENT_HOP_QUALIFICATION_BASELINE_BLOCK_SAMPLES,
            )
            for guard_ms in PERSISTENT_HOP_QUALIFICATION_GUARD_MS
        ),
    )


def persistent_hop_kernel_screen(
    sample_rate_hz: int, *, guard_ms: int
) -> PersistentHopQualificationStage:
    """Screen kernel depth only after selecting one guard."""

    return PersistentHopQualificationStage(
        name="kernel_screen",
        sample_rate_hz=sample_rate_hz,
        candidates=tuple(
            PersistentHopQualificationCandidate(
                guard_ms=guard_ms,
                kernel_buffers=kernel_buffers,
                samples_per_block=PERSISTENT_HOP_QUALIFICATION_BASELINE_BLOCK_SAMPLES,
            )
            for kernel_buffers in PERSISTENT_HOP_QUALIFICATION_KERNEL_BUFFERS
        ),
    )


def persistent_hop_block_screen(
    sample_rate_hz: int,
    *,
    guard_ms: int,
    kernel_buffers: int,
) -> PersistentHopQualificationStage:
    """Screen refill size only after guard and kernel depth have survived."""

    return PersistentHopQualificationStage(
        name="block_screen",
        sample_rate_hz=sample_rate_hz,
        candidates=tuple(
            PersistentHopQualificationCandidate(
                guard_ms=guard_ms,
                kernel_buffers=kernel_buffers,
                samples_per_block=samples_per_block,
            )
            for samples_per_block in PERSISTENT_HOP_QUALIFICATION_BLOCK_SAMPLES
        ),
    )


def persistent_hop_confirmation_stage(
    sample_rate_hz: int,
    *,
    candidate: PersistentHopQualificationCandidate,
    policy: PersistentHopQualificationPolicy,
) -> PersistentHopQualificationStage:
    """Require repeated terminal passes for only the final staged candidate."""

    return PersistentHopQualificationStage(
        name="confirmation",
        sample_rate_hz=sample_rate_hz,
        candidates=(candidate,),
        passes_per_candidate=policy.required_pass_count,
    )


def evaluate_persistent_hop_qualification(
    policy: PersistentHopQualificationPolicy,
    trials: tuple[PersistentHopQualificationTrial, ...],
) -> PersistentHopQualificationDecision:
    """Evaluate closed evidence and select with an explicit deterministic rank."""

    session_counts = Counter(item.receipt.session_id for item in trials)
    assessments = tuple(
        _assess_trial(
            policy,
            trial,
            duplicate_session=session_counts[trial.receipt.session_id] != 1,
        )
        for trial in sorted(
            trials,
            key=lambda item: (
                item.candidate.canonical_key,
                item.receipt.plan.sample_rate_hz,
                item.receipt.session_id,
            ),
        )
    )
    by_candidate: dict[
        PersistentHopQualificationCandidate,
        list[PersistentHopQualificationTrialAssessment],
    ] = defaultdict(list)
    for assessment in assessments:
        by_candidate[assessment.candidate].append(assessment)
    candidates = tuple(
        _qualify_candidate(policy, candidate, tuple(candidate_assessments))
        for candidate, candidate_assessments in sorted(
            by_candidate.items(),
            key=lambda item: item[0].canonical_key,
        )
    )
    qualified = tuple(item for item in candidates if item.qualified)
    if not policy.enabled:
        return PersistentHopQualificationDecision(
            status="disabled",
            policy=policy,
            selected_candidate=None,
            selected_worst_valid_duty_ppm=None,
            assessments=assessments,
            candidates=candidates,
            reasons=("persistent-hop qualification policy is disabled",),
        )
    if not qualified:
        return PersistentHopQualificationDecision(
            status="not_qualified",
            policy=policy,
            selected_candidate=None,
            selected_worst_valid_duty_ppm=None,
            assessments=assessments,
            candidates=candidates,
            reasons=("no persistent-hop candidate passed every required rate and repetition",),
        )
    selected = min(qualified, key=_selection_rank)
    return PersistentHopQualificationDecision(
        status="qualified",
        policy=policy,
        selected_candidate=selected.candidate,
        selected_worst_valid_duty_ppm=selected.worst_valid_duty_ppm,
        assessments=assessments,
        candidates=candidates,
        reasons=(
            "selected by guard_ms ascending, worst duty descending, "
            "kernel depth ascending, block size descending",
        ),
    )


def _assess_trial(
    policy: PersistentHopQualificationPolicy,
    trial: PersistentHopQualificationTrial,
    *,
    duplicate_session: bool,
) -> PersistentHopQualificationTrialAssessment:
    receipt = trial.receipt
    queue = trial.queue
    candidate = trial.candidate
    reasons: list[str] = []
    if duplicate_session:
        reasons.append("session ID is duplicated across qualification trials")
    if receipt.plan.sample_rate_hz not in policy.required_sample_rates_hz:
        reasons.append("session sample rate is outside the required qualification strata")
    if receipt.plan.kernel_buffers != candidate.kernel_buffers:
        reasons.append("receipt kernel depth disagrees with qualification candidate")
    planned_guard_samples = getattr(receipt.plan, "transition_guard_samples", None)
    expected_guard_samples = receipt.plan.sample_rate_hz * candidate.guard_ms // 1_000
    if planned_guard_samples is not None and planned_guard_samples != expected_guard_samples:
        reasons.append("receipt transition guard disagrees with qualification candidate")
    planned_block_samples = getattr(receipt.plan, "samples_per_block", None)
    if planned_block_samples is not None and planned_block_samples != candidate.samples_per_block:
        reasons.append("receipt block size disagrees with qualification candidate")
    if trial.persisted_receipt is None:
        reasons.append("persisted manifest receipt is missing")
    elif trial.persisted_receipt != receipt:
        reasons.append("persisted manifest receipt disagrees with terminal receipt")
    if receipt.capture_outcome != "complete" or receipt.terminal_status.state != "completed":
        reasons.append("session did not reach a completed terminal state")
    if not receipt.terminal_status_attested:
        reasons.append("session terminal status is not attested")
    if not receipt.continuity_attested or receipt.continuity_faults:
        reasons.append("session continuity is not attested")
    if receipt.restoration.status != "restored":
        reasons.append("radio restoration is not attested")
    if not receipt.duty_target_met or receipt.valid_duty_ppm < policy.minimum_valid_duty_ppm:
        reasons.append("session valid duty is below qualification threshold")
    queue_high_water_ppm: int | None = None
    maximum_enqueue_wait_ns: int | None = None
    maximum_writer_service_ns: int | None = None
    if queue is None:
        reasons.append("persistent-hop queue telemetry is missing")
    elif (
        queue.capacity_visits <= 0
        or queue.high_water_visits < 0
        or queue.high_water_visits > queue.capacity_visits
        or queue.enqueue_failure_count < 0
        or queue.maximum_enqueue_wait_ns < 0
        or queue.maximum_writer_service_ns < 0
    ):
        reasons.append("persistent-hop queue telemetry is invalid")
    else:
        queue_high_water_ppm = queue.high_water_visits * 1_000_000 // queue.capacity_visits
        maximum_enqueue_wait_ns = queue.maximum_enqueue_wait_ns
        maximum_writer_service_ns = queue.maximum_writer_service_ns
        if queue.enqueue_failure_count:
            reasons.append("queue observed enqueue failures")
        if queue_high_water_ppm > policy.maximum_queue_high_water_ppm:
            reasons.append("queue high-water exceeds qualification threshold")
        if maximum_enqueue_wait_ns > policy.maximum_enqueue_wait_ns:
            reasons.append("queue enqueue wait exceeds qualification threshold")
        if maximum_writer_service_ns > policy.maximum_writer_service_ns:
            reasons.append("queue writer service exceeds qualification threshold")
    return PersistentHopQualificationTrialAssessment(
        session_id=receipt.session_id,
        candidate=candidate,
        sample_rate_hz=receipt.plan.sample_rate_hz,
        valid_duty_ppm=receipt.valid_duty_ppm,
        queue_high_water_ppm=queue_high_water_ppm,
        maximum_enqueue_wait_ns=maximum_enqueue_wait_ns,
        maximum_writer_service_ns=maximum_writer_service_ns,
        passed=not reasons,
        failure_reasons=tuple(reasons),
    )


def _qualify_candidate(
    policy: PersistentHopQualificationPolicy,
    candidate: PersistentHopQualificationCandidate,
    assessments: tuple[PersistentHopQualificationTrialAssessment, ...],
) -> PersistentHopCandidateQualification:
    trial_counts = tuple(
        (rate, sum(item.sample_rate_hz == rate for item in assessments))
        for rate in policy.required_sample_rates_hz
    )
    passing_counts = tuple(
        (rate, sum(item.sample_rate_hz == rate and item.passed for item in assessments))
        for rate in policy.required_sample_rates_hz
    )
    reasons = [
        f"{item.session_id}: {reason}" for item in assessments for reason in item.failure_reasons
    ]
    for rate, count in trial_counts:
        if count < policy.required_pass_count:
            reasons.append(
                f"{rate} Hz has {count}/{policy.required_pass_count} required repeated trials"
            )
    qualified = not reasons
    duties = tuple(item.valid_duty_ppm for item in assessments)
    high_waters = tuple(
        item.queue_high_water_ppm for item in assessments if item.queue_high_water_ppm is not None
    )
    enqueue_waits = tuple(
        item.maximum_enqueue_wait_ns
        for item in assessments
        if item.maximum_enqueue_wait_ns is not None
    )
    writer_services = tuple(
        item.maximum_writer_service_ns
        for item in assessments
        if item.maximum_writer_service_ns is not None
    )
    return PersistentHopCandidateQualification(
        candidate=candidate,
        trial_count_by_rate=trial_counts,
        passing_trial_count_by_rate=passing_counts,
        worst_valid_duty_ppm=min(duties) if duties else None,
        maximum_queue_high_water_ppm=max(high_waters) if high_waters else None,
        maximum_enqueue_wait_ns=max(enqueue_waits) if enqueue_waits else None,
        maximum_writer_service_ns=max(writer_services) if writer_services else None,
        qualified=qualified,
        failure_reasons=tuple(reasons),
    )


def _selection_rank(item: PersistentHopCandidateQualification) -> tuple[int, int, int, int]:
    assert item.worst_valid_duty_ppm is not None
    candidate = item.candidate
    return (
        candidate.guard_ms,
        -item.worst_valid_duty_ppm,
        candidate.kernel_buffers,
        -candidate.samples_per_block,
    )
