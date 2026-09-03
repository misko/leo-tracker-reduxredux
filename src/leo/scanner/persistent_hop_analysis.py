"""Storage-agnostic analysis views over valid persistent-hop CI16 payload.

The persisted payload is a concatenation of valid visit samples.  Device-counter
gaps occupied by startup, retune, and settling are deliberately absent from that
payload and remain authoritative in the session receipt.  This adapter keeps
both coordinate systems explicit so long-baseline CFO timing never collapses
those invalid intervals.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
import numpy.typing as npt

from leo.analysis.starlink import PilotMethod, StarlinkEdge, TrajectoryObservation
from leo.scanner.detector import (
    DwellGlrt64Analysis,
    Glrt64CandidateResponse,
    Glrt64ProbeResponse,
    analyze_glrt64_dwell,
)
from leo.scanner.models import ScanTarget
from leo.scanner.persistent_hop import (
    PersistentHopPlanV1,
    PersistentHopSessionReceiptV1,
    PersistentHopTransitionInvalidSpanV1,
    PersistentHopVisitV1,
)
from leo.scanner.ports import ScanRadioIdentity


class PersistentHopValidCi16Reader(Protocol):
    """Narrow reader for the valid-only, visit-concatenated CI16 payload."""

    @property
    def sample_count(self) -> int: ...

    @property
    def receiver_ids(self) -> tuple[int, ...]: ...

    def read_valid_ci16(self, sample_start: int, sample_count: int) -> npt.NDArray[np.int16]: ...


@dataclass(frozen=True, slots=True)
class PersistentHopAnalysisVisitSpan:
    """One valid visit in both compact-payload and device-counter coordinates."""

    payload_sample_start: int
    evidence: PersistentHopVisitV1
    sample_rate_hz: int
    bandwidth_hz: int
    receiver_ids: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.payload_sample_start < 0:
            raise ValueError("persistent-hop payload sample start must be nonnegative")
        if self.sample_rate_hz <= 0 or self.bandwidth_hz != self.sample_rate_hz:
            raise ValueError("persistent-hop analysis rate and bandwidth must match")
        if not self.receiver_ids or len(set(self.receiver_ids)) != len(self.receiver_ids):
            raise ValueError("persistent-hop analysis receiver IDs must be nonempty and unique")

    @property
    def visit_index(self) -> int:
        return self.evidence.visit_index

    @property
    def sweep_index(self) -> int:
        return self.evidence.sweep_index

    @property
    def target_index(self) -> int:
        return self.evidence.target_index

    @property
    def target(self) -> ScanTarget:
        return self.evidence.target

    @property
    def fastlock_profile_index(self) -> int:
        return self.evidence.fastlock_profile_index

    @property
    def requested_if_center_hz(self) -> int:
        return self.evidence.requested_if_center_hz

    @property
    def actual_lo_frequency_hz(self) -> int:
        return self.evidence.actual_lo_frequency_hz

    @property
    def actual_if_offset_hz(self) -> int:
        return self.evidence.actual_if_offset_hz

    @property
    def actual_if_center_hz(self) -> int:
        return self.actual_lo_frequency_hz + self.actual_if_offset_hz

    @property
    def transition_invalid_before(self) -> PersistentHopTransitionInvalidSpanV1:
        return self.evidence.transition_invalid_before

    @property
    def valid_sample_count(self) -> int:
        return self.evidence.valid_sample_count

    @property
    def payload_sample_end_exclusive(self) -> int:
        return self.payload_sample_start + self.valid_sample_count

    @property
    def valid_device_sample_counter(self) -> int:
        return self.evidence.valid_device_sample_counter

    @property
    def valid_device_sample_counter_end_exclusive(self) -> int:
        return self.evidence.valid_device_sample_counter_end_exclusive

    def payload_sample_for_local_offset(self, local_sample_offset: int) -> int:
        self._validate_local_offset(local_sample_offset)
        return self.payload_sample_start + local_sample_offset

    def device_counter_for_local_offset(self, local_sample_offset: int) -> int:
        self._validate_local_offset(local_sample_offset)
        return self.valid_device_sample_counter + local_sample_offset

    def _validate_local_offset(self, local_sample_offset: int) -> None:
        if not 0 <= local_sample_offset < self.valid_sample_count:
            raise ValueError("persistent-hop local sample lies outside its valid visit")


@dataclass(frozen=True, slots=True)
class PersistentHopAnalysisVisitInput:
    """A lazily read, immutable CI16 visit plus its counter-authoritative span."""

    span: PersistentHopAnalysisVisitSpan
    samples_ci16: npt.NDArray[np.int16]

    def __post_init__(self) -> None:
        values = np.asarray(self.samples_ci16)
        expected = (self.span.valid_sample_count, len(self.span.receiver_ids), 2)
        if values.dtype != np.dtype("<i2") or values.shape != expected:
            raise ValueError(
                f"persistent-hop analysis visit has shape/dtype {values.shape}/{values.dtype}, "
                f"expected {expected}/int16"
            )
        if not values.flags.c_contiguous:
            raise ValueError("persistent-hop analysis visit CI16 must be C-contiguous")
        values.setflags(write=False)
        object.__setattr__(self, "samples_ci16", values)

    def complex_samples(self) -> npt.NDArray[np.complex64]:
        """Return the existing GLRT analyzer's sample/receiver complex representation."""

        output = np.empty(self.samples_ci16.shape[:2], dtype=np.complex64)
        output.real = self.samples_ci16[:, :, 0]
        output.imag = self.samples_ci16[:, :, 1]
        output.setflags(write=False)
        return output


@dataclass(frozen=True, slots=True)
class PersistentHopGlrt64Configuration:
    """Non-persisted GLRT geometry for one valid persistent visit."""

    plan: PersistentHopPlanV1
    probe_ms: int = 20
    probe_stride_ms: int = 10
    glrt64_margin_gate: float = 0.025
    maximum_acquisition_candidates: int = 8

    def __post_init__(self) -> None:
        if self.probe_ms <= 0 or self.plan.valid_visit_ms % self.probe_ms:
            raise ValueError("persistent-hop GLRT probe must divide one valid visit")
        if self.probe_ms % 2:
            raise ValueError("persistent-hop GLRT probe must have an integral half-window stride")
        if not self.probe_ms // 2 <= self.probe_stride_ms <= self.plan.valid_visit_ms:
            raise ValueError("persistent-hop GLRT probe stride is outside the valid visit")
        if not math.isfinite(self.glrt64_margin_gate) or self.glrt64_margin_gate <= 0:
            raise ValueError("persistent-hop GLRT margin gate must be finite and positive")
        if not 1 <= self.maximum_acquisition_candidates <= 16:
            raise ValueError("persistent-hop GLRT candidate count must lie in 1..16")

    @property
    def sample_rate_hz(self) -> int:
        return self.plan.sample_rate_hz

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        return self.plan.receiver_ids

    @property
    def dwell_samples(self) -> int:
        return self.plan.valid_visit_samples

    @property
    def probe_samples(self) -> int:
        return self.sample_rate_hz * self.probe_ms // 1_000

    @property
    def probe_stride_samples(self) -> int:
        return self.sample_rate_hz * self.probe_stride_ms // 1_000

    @property
    def scheduled_probe_count(self) -> int:
        return (self.dwell_samples - self.probe_samples) // self.probe_stride_samples + 1


@dataclass(frozen=True, slots=True)
class PersistentHopGlrt64CfoObservation:
    """One GLRT CFO candidate bound to its target, visit, and true device time."""

    session_id: str
    visit_index: int
    sweep_index: int
    target_index: int
    target: ScanTarget
    fastlock_profile_index: int
    receiver_id: int
    probe_index: int
    candidate_rank: int
    payload_sample_start: int
    device_sample_counter: int
    actual_if_center_hz: int
    transition_invalid_before: PersistentHopTransitionInvalidSpanV1
    continuity_attested: bool
    trajectory: TrajectoryObservation

    def __post_init__(self) -> None:
        integer_values = (
            self.visit_index,
            self.sweep_index,
            self.target_index,
            self.fastlock_profile_index,
            self.receiver_id,
            self.probe_index,
            self.candidate_rank,
            self.payload_sample_start,
            self.device_sample_counter,
        )
        if not self.session_id or any(value < 0 for value in integer_values):
            raise ValueError("persistent-hop GLRT CFO observation identity is invalid")
        if self.actual_if_center_hz <= 0 or self.trajectory.method is not PilotMethod.GLRT64:
            raise ValueError("persistent-hop GLRT CFO observation settings are invalid")


@dataclass(frozen=True, slots=True)
class PersistentHopChannelCfoSeries:
    """One RF channel with lower and upper edge trajectories kept separate."""

    channel: int
    lower: tuple[PersistentHopGlrt64CfoObservation, ...]
    upper: tuple[PersistentHopGlrt64CfoObservation, ...]

    def __post_init__(self) -> None:
        if self.channel not in range(1, 5):
            raise ValueError("persistent-hop channel must lie in 1..4")
        for edge, observations in (
            (StarlinkEdge.LOWER, self.lower),
            (StarlinkEdge.UPPER, self.upper),
        ):
            if any(
                item.target.channel != self.channel or item.target.edge is not edge
                for item in observations
            ):
                raise ValueError("persistent-hop CFO series mixes channel or edge targets")
            ordering = tuple(
                (item.device_sample_counter, item.receiver_id, item.trajectory.observation_id)
                for item in observations
            )
            if ordering != tuple(sorted(ordering)):
                raise ValueError("persistent-hop CFO series must be ordered by device time")

    def trajectory_observations(
        self,
        *,
        edge: StarlinkEdge,
        receiver_id: int,
    ) -> tuple[TrajectoryObservation, ...]:
        """Return one fit-safe channel/edge/receiver series without oscillator mixing."""

        if receiver_id not in (0, 1):
            raise ValueError("persistent-hop trajectory receiver must be 0 or 1")
        selected = self.lower if edge is StarlinkEdge.LOWER else self.upper
        return tuple(item.trajectory for item in selected if item.receiver_id == receiver_id)


@dataclass(frozen=True, slots=True)
class PersistentHopAnalysisSource:
    """One persistent stream with lazy valid IQ and explicit invalid boundaries."""

    session_id: str
    input_uri: str
    input_manifest_sha256: str
    identity: ScanRadioIdentity
    receipt: PersistentHopSessionReceiptV1
    reader: PersistentHopValidCi16Reader = field(repr=False, compare=False)
    visits: tuple[PersistentHopAnalysisVisitSpan, ...]

    def __post_init__(self) -> None:
        if not self.session_id or not self.input_uri or not self.input_manifest_sha256:
            raise ValueError("persistent-hop analysis source binding is incomplete")
        if self.session_id != self.receipt.session_id:
            raise ValueError("persistent-hop analysis source session ID disagrees with receipt")
        if (
            self.identity.radio_id != self.receipt.radio_id
            or self.identity.serial != self.receipt.radio_serial
            or self.identity.uri != self.receipt.radio_uri
        ):
            raise ValueError("persistent-hop analysis radio identity disagrees with receipt")
        if self.reader.receiver_ids != self.receipt.plan.receiver_ids:
            raise ValueError("persistent-hop valid payload receiver IDs disagree with plan")
        if self.reader.sample_count != self.receipt.valid_sample_count:
            raise ValueError("persistent-hop valid payload length disagrees with receipt")
        if len(self.visits) != len(self.receipt.visits):
            raise ValueError("persistent-hop analysis visit count disagrees with receipt")
        payload_cursor = 0
        for span, evidence in zip(self.visits, self.receipt.visits, strict=True):
            if span.payload_sample_start != payload_cursor or span.evidence != evidence:
                raise ValueError("persistent-hop valid payload visit mapping is not gapless")
            if (
                span.sample_rate_hz != self.receipt.plan.sample_rate_hz
                or span.bandwidth_hz != self.receipt.plan.bandwidth_hz
                or span.receiver_ids != self.receipt.plan.receiver_ids
            ):
                raise ValueError("persistent-hop analysis visit settings disagree with plan")
            payload_cursor = span.payload_sample_end_exclusive
        if payload_cursor != self.receipt.valid_sample_count:
            raise ValueError("persistent-hop analysis visits do not cover the valid payload")

    @property
    def plan(self) -> PersistentHopPlanV1:
        return self.receipt.plan

    @property
    def sample_rate_hz(self) -> int:
        return self.plan.sample_rate_hz

    @property
    def bandwidth_hz(self) -> int:
        return self.plan.bandwidth_hz

    @property
    def receiver_ids(self) -> tuple[int, ...]:
        return self.plan.receiver_ids

    @property
    def stream_generation(self) -> str:
        return self.receipt.stream_generation

    @property
    def transition_invalid_spans(self) -> tuple[PersistentHopTransitionInvalidSpanV1, ...]:
        return tuple(item.transition_invalid_before for item in self.visits)

    def read_visit(self, visit_index: int) -> PersistentHopAnalysisVisitInput:
        try:
            span = self.visits[visit_index]
        except IndexError as error:
            raise ValueError("persistent-hop visit index lies outside the session") from error
        if visit_index < 0 or span.visit_index != visit_index:
            raise ValueError("persistent-hop visit index lies outside the session")
        values = self.reader.read_valid_ci16(
            span.payload_sample_start,
            span.valid_sample_count,
        )
        return PersistentHopAnalysisVisitInput(span=span, samples_ci16=values)

    def analyze_glrt64_visit(
        self,
        visit_index: int,
        *,
        configuration: PersistentHopGlrt64Configuration | None = None,
    ) -> DwellGlrt64Analysis:
        """Run the existing bounded GLRT dwell analyzer on one valid span."""

        selected = configuration or PersistentHopGlrt64Configuration(self.plan)
        if selected.plan != self.plan:
            raise ValueError("persistent-hop GLRT configuration disagrees with session plan")
        visit = self.read_visit(visit_index)
        return analyze_glrt64_dwell(
            visit.complex_samples(),
            selected,
            edge=visit.span.target.edge,
        )

    def glrt64_cfo_observation(
        self,
        visit_index: int,
        *,
        probe: Glrt64ProbeResponse,
        candidate: Glrt64CandidateResponse,
    ) -> PersistentHopGlrt64CfoObservation:
        """Bind one GLRT response to true device time, retaining compact payload time."""

        if probe.receiver_id not in self.receiver_ids:
            raise ValueError("persistent-hop GLRT response names an unknown receiver")
        if candidate not in probe.candidates:
            raise ValueError("persistent-hop GLRT candidate is not owned by its probe")
        span = self._span(visit_index)
        probe_start_sample = probe.probe_start_ms * self.sample_rate_hz // 1_000
        local_sample_offset = probe_start_sample + candidate.epoch_sample
        payload_sample = span.payload_sample_for_local_offset(local_sample_offset)
        device_counter = span.device_counter_for_local_offset(local_sample_offset)
        session_sample_start = device_counter - self.receipt.session_start_device_sample_counter
        observation_id = (
            f"{self.session_id}:visit:{visit_index}:rx:{probe.receiver_id}:"
            f"probe:{probe.probe_index}:candidate:{candidate.candidate_rank}"
        )
        trajectory = TrajectoryObservation(
            observation_id=observation_id,
            method=PilotMethod.GLRT64,
            sample_start=session_sample_start,
            time_s=session_sample_start / self.sample_rate_hz,
            tracking_cfo_hz=candidate.tracking_cfo_hz,
            score=candidate.exact_score,
            control_score=candidate.control_score,
            margin=candidate.margin,
        )
        return PersistentHopGlrt64CfoObservation(
            session_id=self.session_id,
            visit_index=span.visit_index,
            sweep_index=span.sweep_index,
            target_index=span.target_index,
            target=span.target,
            fastlock_profile_index=span.fastlock_profile_index,
            receiver_id=probe.receiver_id,
            probe_index=probe.probe_index,
            candidate_rank=candidate.candidate_rank,
            payload_sample_start=payload_sample,
            device_sample_counter=device_counter,
            actual_if_center_hz=span.actual_if_center_hz,
            transition_invalid_before=span.transition_invalid_before,
            continuity_attested=self.receipt.continuity_attested,
            trajectory=trajectory,
        )

    def glrt64_cfo_observations(
        self,
        visit_index: int,
        analysis: DwellGlrt64Analysis,
        *,
        passed_margin_only: bool = True,
    ) -> tuple[PersistentHopGlrt64CfoObservation, ...]:
        """Project a complete dwell result into deterministic trajectory candidates."""

        return tuple(
            self.glrt64_cfo_observation(
                visit_index,
                probe=probe,
                candidate=candidate,
            )
            for probe in analysis.probes
            for candidate in probe.candidates
            if candidate.passed_margin_gate or not passed_margin_only
        )

    def group_glrt64_cfo_by_channel(
        self,
        observations: tuple[PersistentHopGlrt64CfoObservation, ...],
    ) -> tuple[PersistentHopChannelCfoSeries, ...]:
        return group_persistent_hop_glrt64_cfo_by_channel(self, observations)

    def _span(self, visit_index: int) -> PersistentHopAnalysisVisitSpan:
        try:
            span = self.visits[visit_index]
        except IndexError as error:
            raise ValueError("persistent-hop visit index lies outside the session") from error
        if visit_index < 0 or span.visit_index != visit_index:
            raise ValueError("persistent-hop visit index lies outside the session")
        return span


def build_persistent_hop_analysis_source(
    *,
    receipt: PersistentHopSessionReceiptV1,
    reader: PersistentHopValidCi16Reader,
    input_uri: str,
    input_manifest_sha256: str,
) -> PersistentHopAnalysisSource:
    """Map concatenated valid payload coordinates to receipt-attested visits."""

    cursor = 0
    visits: list[PersistentHopAnalysisVisitSpan] = []
    for evidence in receipt.visits:
        visits.append(
            PersistentHopAnalysisVisitSpan(
                payload_sample_start=cursor,
                evidence=evidence,
                sample_rate_hz=receipt.plan.sample_rate_hz,
                bandwidth_hz=receipt.plan.bandwidth_hz,
                receiver_ids=receipt.plan.receiver_ids,
            )
        )
        cursor += evidence.valid_sample_count
    return PersistentHopAnalysisSource(
        session_id=receipt.session_id,
        input_uri=input_uri,
        input_manifest_sha256=input_manifest_sha256,
        identity=ScanRadioIdentity(
            radio_id=receipt.radio_id,
            serial=receipt.radio_serial,
            uri=receipt.radio_uri,
        ),
        receipt=receipt,
        reader=reader,
        visits=tuple(visits),
    )


def group_persistent_hop_glrt64_cfo_by_channel(
    source: PersistentHopAnalysisSource,
    observations: tuple[PersistentHopGlrt64CfoObservation, ...],
) -> tuple[PersistentHopChannelCfoSeries, ...]:
    """Group deterministically by RF channel while preserving separate edge centers."""

    observation_ids = tuple(item.trajectory.observation_id for item in observations)
    if len(set(observation_ids)) != len(observation_ids):
        raise ValueError("persistent-hop GLRT observation IDs must be unique")
    grouped: dict[tuple[int, StarlinkEdge], list[PersistentHopGlrt64CfoObservation]] = {
        (channel, edge): []
        for channel in range(1, 5)
        for edge in (StarlinkEdge.LOWER, StarlinkEdge.UPPER)
    }
    for item in observations:
        span = source._span(item.visit_index)
        expected_session_sample = (
            item.device_sample_counter - source.receipt.session_start_device_sample_counter
        )
        if (
            item.session_id != source.session_id
            or item.sweep_index != span.sweep_index
            or item.target_index != span.target_index
            or item.target != span.target
            or item.fastlock_profile_index != span.fastlock_profile_index
            or item.receiver_id not in source.receiver_ids
            or item.actual_if_center_hz != span.actual_if_center_hz
            or item.transition_invalid_before != span.transition_invalid_before
            or item.continuity_attested != source.receipt.continuity_attested
            or not (
                span.valid_device_sample_counter
                <= item.device_sample_counter
                < span.valid_device_sample_counter_end_exclusive
            )
            or item.payload_sample_start
            != span.payload_sample_start
            + item.device_sample_counter
            - span.valid_device_sample_counter
            or item.trajectory.sample_start != expected_session_sample
            or not math.isclose(
                item.trajectory.time_s,
                expected_session_sample / source.sample_rate_hz,
                rel_tol=0.0,
                abs_tol=1e-15,
            )
        ):
            raise ValueError("persistent-hop GLRT observation disagrees with source evidence")
        grouped[(item.target.channel, item.target.edge)].append(item)

    def ordered(
        values: list[PersistentHopGlrt64CfoObservation],
    ) -> tuple[PersistentHopGlrt64CfoObservation, ...]:
        return tuple(
            sorted(
                values,
                key=lambda item: (
                    item.device_sample_counter,
                    item.receiver_id,
                    item.trajectory.observation_id,
                ),
            )
        )

    return tuple(
        PersistentHopChannelCfoSeries(
            channel=channel,
            lower=ordered(grouped[(channel, StarlinkEdge.LOWER)]),
            upper=ordered(grouped[(channel, StarlinkEdge.UPPER)]),
        )
        for channel in range(1, 5)
    )
