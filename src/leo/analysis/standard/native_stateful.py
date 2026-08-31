"""Segment-local orchestration for additive Standard-native stateful science.

The published Standard contracts remain unchanged.  This module deliberately
returns ordinary frozen dataclasses, not persisted contract models: the legacy
kernel products nested below use segment-local sample coordinates and must be
rebound to additive native contract majors before publication.

Every numerical chain receives exactly one contiguous segment reader.  The
lossless path retains its frozen local-zero schedule; gapped input instead uses
the persisted global probe schedule and translates each wholly valid window to
its containing segment.  Residual-Hough fitting, CFO de-aliasing and replay,
Kalman tracking, and pilot Doppler start from fresh state at every authoritative
continuity boundary.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Callable, Iterable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from typing import Any

import numpy as np
from pydantic import JsonValue

from leo.analysis.qam.pilot import PilotQamResult
from leo.analysis.qam.pilot_phase_locklet import PilotPhaseLockletConfig, PilotPhaseLockletResult
from leo.analysis.standard.configuration import require_receiver_standard_sample_rate
from leo.analysis.standard.native_qam import (
    NativePrimaryQamCapture,
    build_native_qam_probe_evidence,
)
from leo.analysis.standard.native_runner import validate_standard_native_source
from leo.analysis.standard.native_windows import (
    NativeSegmentKernelInput,
    NativeWindowIqReader,
    StandardNativeWindowAdapter,
)
from leo.analysis.standard.runner import (
    ReceiverStandardConfig,
    receiver_standard_configuration_digest,
)
from leo.analysis.starlink.acquisition import (
    ReceiverFrequencyCalibration,
    SymbolwiseAcquisitionConfig,
)
from leo.analysis.starlink.cfo_dealias import (
    _observed_lift_candidates_v2,
    build_cfo_alias_map,
    classify_observed_lift_replay_v4,
    fit_huber_linear_dealiased_trajectories,
    replay_observed_cfo_lifts_v4,
    select_final_trajectories_v3,
)
from leo.analysis.starlink.kalman_tracking import (
    PolynomialFrequencyModel,
    _build_track,
    build_standard_kalman_tracking,
    extract_probe_frame_measurements,
    raw_candidate_sources,
)
from leo.analysis.starlink.pilot_doppler_segments import (
    build_standard_pilot_doppler_segments_bundle_v3,
)
from leo.analysis.starlink.pilot_methods import (
    PilotProbeDetection,
    detect_pilot_method_candidates,
)
from leo.analysis.starlink.pilot_search_geometry import compile_pilot_search_geometry
from leo.analysis.starlink.trajectories import PolynomialTrajectory, TrajectoryBankResult
from leo.analysis.starlink.trajectory_feedback import (
    TrajectoryFeedbackConfig,
    fit_residual_hough_pilot_trajectories,
    replay_pilot_trajectories_at_detection_windows_with_conditioned_scores,
    replay_pilot_trajectories_with_conditioned_scores,
    resolve_hough_replay_alias_indices_by_native_replay,
    scan_pilot_detections,
    trajectory_observations,
    validate_trajectory_feedback_config,
)
from leo.contracts.cfo_dealias import (
    CfoAliasMapV2,
    CfoLiftReplayV4,
    DealiasedTrajectoryBankV4,
    FinalTrajectoryBankV3,
)
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.kalman_tracking import StandardKalmanTrackingV1
from leo.contracts.pilot_doppler_segments import StandardPilotDopplerSegmentsV2
from leo.contracts.standard_native import (
    NativeProbeWindowV3,
    StandardNativeSourceV1,
    StandardNativeSourceV2,
    StandardProbeScheduleV3,
    StandardProbeScheduleV4,
)
from leo.contracts.standard_native_path_report import NativeQamProbeEvidenceV1
from leo.contracts.standard_native_stateful import (
    NativeConditionedHoughReplayRowV1,
    NativePilotProbeDetectionV1,
    NativeRawTrajectoryBankV1,
    NativeSegmentLocalScienceV1,
    NativeStatefulSegmentDispositionV1,
    NativeStatefulSegmentV1,
    NativeTrajectoryRepresentativeV1,
    StandardNativeStatefulPathV1,
)
from leo.contracts.standard_native_stateful_v2 import (
    NativeStatefulSegmentDispositionV2,
    NativeStatefulSegmentV2,
    StandardNativeStatefulPathV2,
    StandardNativeStatefulPathV3,
)
from leo.contracts.standard_pipeline import (
    StandardPathInputBindV4,
    StandardPathInputBindV5,
    StandardScientificStatus,
)
from leo.contracts.states import StarlinkEdge
from leo.contracts.validity import ContinuitySegmentV1
from leo.pipeline.validity import ContinuitySegmentIqReader, ValidityAwareIqReader


class NativeSegmentExecutionDisposition(StrEnum):
    """Truthful reason a continuity segment did or did not enter the chain."""

    ANALYZED = "analyzed"
    EMPTY_TERMINAL = "empty_terminal"
    NO_COMPLETE_OUTER_WINDOW = "no_complete_outer_window"
    OUTER_WINDOW_BUDGET_EXHAUSTED = "outer_window_budget_exhausted"
    NO_VALID_GLOBAL_PROBE = "no_valid_global_probe"


class NativeStatefulScheduleAuthority(StrEnum):
    """In-process proof of which opportunity axis drove stateful science."""

    SEGMENT_LOCAL_ZERO_V1 = "segment_local_zero_v1"
    GLOBAL_PROBE_SCHEDULE_V3 = "global_probe_schedule_v3"


@dataclass(frozen=True, slots=True)
class NativeScheduledProbeInput:
    """One persisted global opportunity rebound to exact segment-local IQ."""

    opportunity_index: int
    opportunity: NativeProbeWindowV3
    segment: ContinuitySegmentV1
    iq: NativeWindowIqReader
    continuity_segment_index: int
    global_device_sample_start: int
    global_device_sample_stop: int
    segment_local_sample_start: int
    frequency_reference: ReceiverFrequencyCalibration

    def __post_init__(self) -> None:
        probe = self.opportunity.probe
        if (
            self.opportunity_index != self.iq.opportunity_index
            or self.continuity_segment_index != self.segment.segment_index
            or self.continuity_segment_index != self.iq.continuity_segment_index
            or self.global_device_sample_start != probe.sample_start
            or self.global_device_sample_start != self.iq.global_device_sample_start
            or self.global_device_sample_stop != probe.sample_start + probe.sample_count
            or self.global_device_sample_stop != self.iq.global_device_sample_stop
            or self.segment_local_sample_start
            != self.global_device_sample_start - self.segment.device_sample_start
            or self.segment_local_sample_start < 0
            or self.global_device_sample_stop > self.segment.device_sample_stop
        ):
            raise ValueError("scheduled native probe changed its global/segment-local mapping")
        validity = self.opportunity.validity
        if (
            validity.continuity_segment_index != self.continuity_segment_index
            or validity.device_sample_start != self.global_device_sample_start
            or validity.sample_count != self.iq.sample_count
            or validity.disposition.value != "valid"
        ):
            raise ValueError("scheduled native probe is not wholly valid in its bound segment")
        if self.frequency_reference.receiver_id != str(self.iq.receiver_ids[0]):
            raise ValueError("scheduled native probe frequency reference changed receiver")


@dataclass(frozen=True, slots=True)
class NativeScheduledProbeDetection:
    """Lightweight retained mapping after the bounded probe IQ is released."""

    opportunity_index: int
    coarse_window_index: int
    continuity_segment_index: int
    global_device_sample_start: int
    segment_local_sample_start: int
    detection: PilotProbeDetection
    primary_qam_result: PilotQamResult | None = None
    qam_capture_complete: bool = False

    def __post_init__(self) -> None:
        if (
            self.opportunity_index < 0
            or self.coarse_window_index < 0
            or self.continuity_segment_index < 0
            or self.global_device_sample_start < 0
            or self.segment_local_sample_start < 0
            or self.detection.sample_start != self.segment_local_sample_start
        ):
            raise ValueError("scheduled pilot detection changed its opportunity coordinates")


@dataclass(frozen=True, slots=True)
class NativePrimaryProbeOutcome:
    """One detector result and the QAM computation from its primary candidate."""

    detection: PilotProbeDetection
    primary_qam_result: PilotQamResult | None
    qam_capture_complete: bool = True

    def __post_init__(self) -> None:
        if self.qam_capture_complete and (self.detection.local_epoch_sample is not None) != (
            self.primary_qam_result is not None
        ):
            raise ValueError("native primary QAM outcome disagrees with pilot detection")


NativeExplicitPilotDetector = Callable[
    [NativeScheduledProbeInput, TrajectoryFeedbackConfig, StarlinkEdge],
    PilotProbeDetection,
]
NativeExplicitPilotOutcomeDetector = Callable[
    [NativeScheduledProbeInput, TrajectoryFeedbackConfig, StarlinkEdge],
    NativePrimaryProbeOutcome,
]


@dataclass(frozen=True, slots=True)
class NativeSegmentLocalScience:
    """In-process legacy-kernel results in one segment-local coordinate space.

    None of these nested objects is a native persisted product.  In particular,
    their sample starts and times are relative to ``device_sample_start`` in the
    enclosing :class:`NativeStatefulSegmentResult`.
    """

    segment_path_binding_digest: Sha256Digest
    pilot_scan_digest: Sha256Digest
    raw_trajectory_bank_digest: Sha256Digest
    scheduled_outer_window_count: int
    detections: tuple[PilotProbeDetection, ...]
    residual_hough_bank: TrajectoryBankResult
    residual_hough_representatives: tuple[tuple[str, PolynomialTrajectory], ...]
    conditioned_hough_replay: tuple[dict[str, JsonValue], ...]
    cfo_alias_map: CfoAliasMapV2
    dealiased_trajectory_bank: DealiasedTrajectoryBankV4
    cfo_lift_replay: CfoLiftReplayV4
    final_trajectory_bank: FinalTrajectoryBankV3
    kalman_tracking: StandardKalmanTrackingV1
    pilot_doppler_segments: StandardPilotDopplerSegmentsV2
    pilot_phase_config: PilotPhaseLockletConfig
    pilot_phase_locklets: tuple[PilotPhaseLockletResult, ...]
    primary_probe_outcomes: tuple[NativePrimaryProbeOutcome, ...] = ()

    def __post_init__(self) -> None:
        if self.scheduled_outer_window_count <= 0:
            raise ValueError("segment-local science requires a positive outer-window count")
        starts = tuple(item.sample_start for item in self.detections)
        if starts != tuple(sorted(set(starts))):
            raise ValueError("segment-local pilot detections must be unique and ordered")
        if (
            self.cfo_alias_map.pilot_scan_digest != self.pilot_scan_digest
            or self.cfo_alias_map.raw_trajectory_bank_digest != self.raw_trajectory_bank_digest
            or self.dealiased_trajectory_bank.alias_map_digest != self.cfo_alias_map.content_digest
            or self.dealiased_trajectory_bank.raw_trajectory_bank_digest
            != self.raw_trajectory_bank_digest
            or self.cfo_lift_replay.path_input_binding_digest != self.segment_path_binding_digest
            or self.cfo_lift_replay.pilot_scan_digest != self.pilot_scan_digest
            or self.cfo_lift_replay.dealiased_bank_digest
            != self.dealiased_trajectory_bank.content_digest
            or self.final_trajectory_bank.dealiased_bank_digest
            != self.dealiased_trajectory_bank.content_digest
            or self.final_trajectory_bank.lift_replay_digest != self.cfo_lift_replay.content_digest
            or self.kalman_tracking.path_input_binding_digest != self.segment_path_binding_digest
            or self.kalman_tracking.pilot_scan_digest != self.pilot_scan_digest
            or self.kalman_tracking.dealiased_bank_digest
            != self.dealiased_trajectory_bank.content_digest
            or self.kalman_tracking.final_trajectory_bank_digest
            != self.final_trajectory_bank.content_digest
            or self.pilot_doppler_segments.path_input_binding_digest
            != self.segment_path_binding_digest
            or self.pilot_doppler_segments.pilot_scan_digest != self.pilot_scan_digest
            or self.pilot_doppler_segments.dealiased_bank_digest
            != self.dealiased_trajectory_bank.content_digest
            or self.pilot_doppler_segments.final_trajectory_bank_digest
            != self.final_trajectory_bank.content_digest
            or self.pilot_doppler_segments.kalman_tracking_digest
            != self.kalman_tracking.content_digest
        ):
            raise ValueError("segment-local stateful kernel authority does not close")
        if len(self.pilot_phase_locklets) != len(self.pilot_doppler_segments.segments):
            raise ValueError("segment-local phase evidence is not aligned to V2 locklets")
        if (
            self.primary_probe_outcomes
            and tuple(item.detection for item in self.primary_probe_outcomes) != self.detections
        ):
            raise ValueError("native primary QAM outcomes changed pilot detection order")


@dataclass(frozen=True, slots=True)
class NativeStatefulSegmentResult:
    """One authoritative reset boundary and its optional local computation."""

    segment: ContinuitySegmentV1
    continuity_segment_index: int
    device_sample_start: int
    device_sample_stop: int
    disposition: NativeSegmentExecutionDisposition
    local_science: NativeSegmentLocalScience | None

    def __post_init__(self) -> None:
        if (
            self.continuity_segment_index != self.segment.segment_index
            or self.device_sample_start != self.segment.device_sample_start
            or self.device_sample_stop != self.segment.device_sample_stop
        ):
            raise ValueError("stateful segment result changed authoritative global bounds")
        analyzed = self.disposition is NativeSegmentExecutionDisposition.ANALYZED
        if analyzed != (self.local_science is not None):
            raise ValueError("stateful segment disposition disagrees with numerical output")
        if (self.disposition is NativeSegmentExecutionDisposition.EMPTY_TERMINAL) != (
            self.segment.observed_sample_count == 0
        ):
            raise ValueError("empty stateful disposition disagrees with segment support")

    def to_global_device_sample(self, local_sample: int) -> int:
        """Map a nested kernel coordinate onto the recording device axis."""

        if not 0 <= local_sample <= self.segment.observed_sample_count:
            raise ValueError("segment-local sample lies outside authoritative support")
        return self.device_sample_start + local_sample

    def to_global_time_s(self, local_time_s: float, *, sample_rate_hz: int) -> float:
        """Map a finite segment-local time onto the recording device-time axis."""

        if sample_rate_hz <= 0 or not math.isfinite(local_time_s) or local_time_s < 0:
            raise ValueError("segment-local time mapping is invalid")
        maximum = self.segment.observed_sample_count / sample_rate_hz
        if local_time_s > maximum and not math.isclose(local_time_s, maximum, abs_tol=1e-12):
            raise ValueError("segment-local time lies outside authoritative support")
        return self.device_sample_start / sample_rate_hz + local_time_s


@dataclass(frozen=True, slots=True)
class StandardNativeStatefulResult:
    """Closed in-process result covering every authoritative continuity segment."""

    path_input_binding_digest: Sha256Digest
    validity_inventory_digest: Sha256Digest
    sample_rate_hz: int
    logical_sample_count: int
    maximum_outer_window_count: int
    analyzed_outer_window_count: int
    segments: tuple[NativeStatefulSegmentResult, ...]
    schedule_authority: NativeStatefulScheduleAuthority = (
        NativeStatefulScheduleAuthority.SEGMENT_LOCAL_ZERO_V1
    )
    probe_schedule_digest: Sha256Digest | None = None
    qam_probe_evidence: tuple[NativeQamProbeEvidenceV1, ...] = ()

    def __post_init__(self) -> None:
        if (
            self.sample_rate_hz <= 0
            or self.logical_sample_count <= 0
            or self.maximum_outer_window_count <= 0
            or not 0 <= self.analyzed_outer_window_count <= self.maximum_outer_window_count
            or not self.segments
        ):
            raise ValueError("native stateful result geometry is invalid")
        if tuple(item.continuity_segment_index for item in self.segments) != tuple(
            range(len(self.segments))
        ):
            raise ValueError("native stateful segment results are not canonical")
        if self.segments[0].device_sample_start != 0:
            raise ValueError("native stateful segments do not begin at the logical origin")
        for previous, current in zip(self.segments, self.segments[1:], strict=False):
            if current.device_sample_start < previous.device_sample_stop:
                raise ValueError("native stateful segment results overlap or regress")
        if self.segments[-1].device_sample_stop != self.logical_sample_count:
            raise ValueError("native stateful segments do not close the logical span")
        analyzed = sum(
            item.local_science.scheduled_outer_window_count
            for item in self.segments
            if item.local_science is not None
        )
        if analyzed != self.analyzed_outer_window_count:
            raise ValueError("native stateful outer-window accounting does not close")
        if (
            self.schedule_authority is NativeStatefulScheduleAuthority.GLOBAL_PROBE_SCHEDULE_V3
        ) != (self.probe_schedule_digest is not None):
            raise ValueError("native stateful result only binds a digest for a global schedule")
        qam_indexes = tuple(item.opportunity_index for item in self.qam_probe_evidence)
        if qam_indexes != tuple(sorted(set(qam_indexes))):
            raise ValueError("native stateful QAM evidence is not unique and ordered")


NativeSegmentScienceExecutor = Callable[
    [
        NativeSegmentKernelInput,
        StandardPathInputBindV4,
        ReceiverStandardConfig,
        StarlinkEdge,
        int,
    ],
    NativeSegmentLocalScience,
]


class StandardNativeStatefulRunner:
    """Run fresh stateful science per segment and poison on any failed campaign."""

    def __init__(
        self,
        config: ReceiverStandardConfig | None = None,
        *,
        segment_executor: NativeSegmentScienceExecutor | None = None,
        probe_detector: NativeExplicitPilotDetector | None = None,
        probe_outcome_detector: NativeExplicitPilotOutcomeDetector | None = None,
    ) -> None:
        if probe_detector is not None and probe_outcome_detector is not None:
            raise ValueError("configure either a legacy probe detector or a QAM-aware detector")
        self._config = config or ReceiverStandardConfig()
        self._segment_executor = segment_executor or _run_segment_local_science
        if probe_outcome_detector is not None:
            self._probe_outcome_detector = probe_outcome_detector
        elif probe_detector is not None:
            self._probe_outcome_detector = lambda item, feedback, edge: NativePrimaryProbeOutcome(
                probe_detector(item, feedback, edge),
                None,
                False,
            )
        else:
            self._probe_outcome_detector = detect_standard_native_probe_outcome
        self._lock = threading.Lock()
        self._running = False
        self._poisoned = False

    @property
    def poisoned(self) -> bool:
        with self._lock:
            return self._poisoned

    def run(
        self,
        reader: ValidityAwareIqReader,
        binding: StandardPathInputBindV4,
        *,
        edge: StarlinkEdge,
        qam_schedule: StandardProbeScheduleV3 | None = None,
    ) -> StandardNativeStatefulResult:
        """Run independently on each segment; never return partial failed output."""

        return self._guarded(
            lambda: self._run(
                reader,
                binding,
                edge=StarlinkEdge(edge),
                qam_schedule=qam_schedule,
            )
        )

    def run_global_probe_schedule(
        self,
        reader: ValidityAwareIqReader,
        binding: StandardPathInputBindV4,
        schedule: StandardProbeScheduleV3,
        *,
        edge: StarlinkEdge,
        capture_qam: bool = False,
    ) -> StandardNativeStatefulResult:
        """Execute only persisted, wholly-valid global opportunities per reset segment."""

        return self._guarded(
            lambda: self._run_global_probe_schedule(
                reader,
                binding,
                schedule,
                edge=StarlinkEdge(edge),
                capture_qam=capture_qam,
            )
        )

    def _guarded(
        self,
        function: Callable[[], StandardNativeStatefulResult],
    ) -> StandardNativeStatefulResult:
        with self._lock:
            if self._poisoned:
                raise RuntimeError("native stateful runner is poisoned; construct a new runner")
            if self._running:
                raise RuntimeError("native stateful runner is already running")
            self._running = True
        try:
            return function()
        except BaseException:
            with self._lock:
                self._poisoned = True
            raise
        finally:
            with self._lock:
                self._running = False

    def _run(
        self,
        reader: ValidityAwareIqReader,
        binding: StandardPathInputBindV4,
        *,
        edge: StarlinkEdge,
        qam_schedule: StandardProbeScheduleV3 | None,
    ) -> StandardNativeStatefulResult:
        validate_standard_native_source(reader, binding)
        if edge != StarlinkEdge(binding.starlink_edge):
            raise ValueError("native stateful edge differs from the V4 path binding")
        require_receiver_standard_sample_rate(
            self._config,
            sample_rate_hz=reader.sample_rate_hz,
        )
        segment_inputs = StandardNativeWindowAdapter(reader).segment_inputs
        if tuple(item.segment for item in segment_inputs) != binding.validity_inventory.segments:
            raise ValueError("native stateful segment inventory changed after source validation")

        remaining = self._config.feedback.maximum_outer_windows
        analyzed = 0
        results: list[NativeStatefulSegmentResult] = []
        for segment_input in segment_inputs:
            segment = segment_input.segment
            if segment.observed_sample_count == 0:
                disposition = NativeSegmentExecutionDisposition.EMPTY_TERMINAL
                local_science = None
            else:
                available = segment.observed_sample_count // reader.sample_rate_hz
                if available == 0:
                    disposition = NativeSegmentExecutionDisposition.NO_COMPLETE_OUTER_WINDOW
                    local_science = None
                elif remaining == 0:
                    disposition = NativeSegmentExecutionDisposition.OUTER_WINDOW_BUDGET_EXHAUSTED
                    local_science = None
                else:
                    allocated = min(available, remaining)
                    local_science = self._segment_executor(
                        segment_input,
                        binding,
                        self._config,
                        edge,
                        allocated,
                    )
                    if local_science.scheduled_outer_window_count != allocated:
                        raise ValueError(
                            "segment executor changed its allocated outer-window count"
                        )
                    disposition = NativeSegmentExecutionDisposition.ANALYZED
                    remaining -= allocated
                    analyzed += allocated
            results.append(
                NativeStatefulSegmentResult(
                    segment=segment,
                    continuity_segment_index=segment.segment_index,
                    device_sample_start=segment.device_sample_start,
                    device_sample_stop=segment.device_sample_stop,
                    disposition=disposition,
                    local_science=local_science,
                )
            )
        result = StandardNativeStatefulResult(
            path_input_binding_digest=binding.binding_digest,
            validity_inventory_digest=binding.validity_inventory.inventory_digest,
            sample_rate_hz=binding.sample_rate_hz,
            logical_sample_count=binding.logical_sample_count,
            maximum_outer_window_count=self._config.feedback.maximum_outer_windows,
            analyzed_outer_window_count=analyzed,
            segments=tuple(results),
        )
        if qam_schedule is None:
            return result
        if not stateful_global_schedule_is_publishable(binding):
            raise ValueError("local-zero QAM closure is only valid for a lossless path")
        _validate_global_stateful_schedule(qam_schedule, binding, self._config)
        return replace(
            result,
            qam_probe_evidence=_build_qam_probe_evidence(
                qam_schedule,
                result.segments,
            ),
        )

    def _run_global_probe_schedule(
        self,
        reader: ValidityAwareIqReader,
        binding: StandardPathInputBindV4,
        schedule: StandardProbeScheduleV3,
        *,
        edge: StarlinkEdge,
        capture_qam: bool,
    ) -> StandardNativeStatefulResult:
        validate_standard_native_source(reader, binding)
        if edge != StarlinkEdge(binding.starlink_edge):
            raise ValueError("native stateful edge differs from the V4 path binding")
        require_receiver_standard_sample_rate(
            self._config,
            sample_rate_hz=reader.sample_rate_hz,
        )
        if stateful_global_schedule_is_publishable(binding):
            raise ValueError("lossless stateful IQ must retain the byte-stable legacy path")
        _validate_global_stateful_schedule(schedule, binding, self._config)
        adapter = StandardNativeWindowAdapter(reader)
        segment_inputs = adapter.segment_inputs
        if tuple(item.segment for item in segment_inputs) != binding.validity_inventory.segments:
            raise ValueError("native stateful segment inventory changed after source validation")

        detected = _detect_global_probe_schedule(
            adapter,
            schedule,
            self._config.feedback,
            edge=edge,
            detector=self._probe_outcome_detector,
            frequency_reference=_path_frequency_reference(binding, self._config.feedback),
        )
        if len(detected) != schedule.accounting.valid_count:
            raise ValueError("global stateful detection did not close valid opportunity accounting")
        # One canonical coarse window can contribute valid probes to more than one
        # continuity segment.  The segment-local science rows therefore account
        # *memberships*, not distinct global coarse windows.  Their closed upper
        # bound is the number of valid persisted probe opportunities: every
        # nonempty (segment, coarse-window) membership contains at least one such
        # probe.  Keep the scientific schedule capped by the reviewed feedback
        # policy while using this independently derived bound for V2 membership
        # accounting.
        segment_membership_limit = max(1, schedule.accounting.valid_count)
        detected_by_segment: dict[int, list[NativeScheduledProbeDetection]] = {}
        for item in detected:
            detected_by_segment.setdefault(item.continuity_segment_index, []).append(item)

        analyzed = 0
        results: list[NativeStatefulSegmentResult] = []
        for segment_input in segment_inputs:
            segment = segment_input.segment
            selected = tuple(detected_by_segment.pop(segment.segment_index, ()))
            if segment.observed_sample_count == 0:
                if selected:
                    raise ValueError("empty stateful segment received a global probe")
                disposition = NativeSegmentExecutionDisposition.EMPTY_TERMINAL
                local_science = None
            elif not selected:
                disposition = NativeSegmentExecutionDisposition.NO_VALID_GLOBAL_PROBE
                local_science = None
            else:
                outer_window_count = len({item.coarse_window_index for item in selected})
                if analyzed + outer_window_count > segment_membership_limit:
                    raise ValueError(
                        "global schedule segment memberships exceed valid probe authority"
                    )
                local_science = _run_segment_global_probe_science(
                    segment_input,
                    binding,
                    self._config,
                    edge,
                    selected,
                    outer_window_count,
                )
                disposition = NativeSegmentExecutionDisposition.ANALYZED
                analyzed += outer_window_count
            results.append(
                NativeStatefulSegmentResult(
                    segment=segment,
                    continuity_segment_index=segment.segment_index,
                    device_sample_start=segment.device_sample_start,
                    device_sample_stop=segment.device_sample_stop,
                    disposition=disposition,
                    local_science=local_science,
                )
            )
        if detected_by_segment:
            raise ValueError("global stateful detections reference an unknown continuity segment")
        result = StandardNativeStatefulResult(
            path_input_binding_digest=binding.binding_digest,
            validity_inventory_digest=binding.validity_inventory.inventory_digest,
            sample_rate_hz=binding.sample_rate_hz,
            logical_sample_count=binding.logical_sample_count,
            maximum_outer_window_count=segment_membership_limit,
            analyzed_outer_window_count=analyzed,
            segments=tuple(results),
            schedule_authority=NativeStatefulScheduleAuthority.GLOBAL_PROBE_SCHEDULE_V3,
            probe_schedule_digest=schedule.schedule_digest,
        )
        if not capture_qam:
            return result
        return replace(
            result,
            qam_probe_evidence=_build_qam_probe_evidence(
                schedule,
                result.segments,
            ),
        )


def stateful_global_schedule_is_publishable(binding: StandardPathInputBindV4) -> bool:
    """Return whether segment-local zero equals the canonical global origin.

    The current legacy kernels construct their one-second/probe schedules from
    reader-local zero.  They are therefore publishable only when the source is
    one lossless segment spanning the complete logical device axis.
    """

    segments = binding.validity_inventory.segments
    return (
        binding.missing_sample_count == 0
        and len(segments) == 1
        and segments[0].device_sample_start == 0
        and segments[0].device_sample_stop == binding.logical_sample_count
    )


def _path_frequency_reference(
    binding: StandardPathInputBindV4,
    feedback: TrajectoryFeedbackConfig,
) -> ReceiverFrequencyCalibration:
    return compile_pilot_search_geometry(
        receiver_id=binding.receiver_id,
        starlink_channel=binding.starlink_channel,
        edge=binding.starlink_edge,
        tuned_center_frequency_hz=binding.tuned_center_frequency_hz,
        sample_rate_hz=binding.sample_rate_hz,
        rf_bandwidth_hz=binding.rf_bandwidth_hz,
        residual_cfo_min_hz=feedback.cfo_search_min_hz,
        residual_cfo_max_hz=feedback.cfo_search_max_hz,
    ).frequency_reference


def _validate_global_stateful_schedule(
    schedule: StandardProbeScheduleV3 | StandardProbeScheduleV4,
    binding: StandardPathInputBindV4 | StandardPathInputBindV5,
    config: ReceiverStandardConfig,
) -> None:
    feedback = config.feedback
    expected_source = (
        StandardNativeSourceV2.from_path_binding(binding)
        if isinstance(binding, StandardPathInputBindV5)
        else StandardNativeSourceV1.from_path_binding(binding)
    )
    if schedule.source != expected_source:
        raise ValueError("global stateful schedule changed path source authority")
    if (
        schedule.coarse_window_ms != 1_000
        or schedule.subwindow_ms != feedback.subwindow_ms
        or schedule.probe_ms != feedback.probe_ms
        or schedule.probe_offsets_ms != feedback.probe_offsets_ms
        or schedule.maximum_coarse_windows != feedback.maximum_outer_windows
    ):
        raise ValueError("global stateful schedule disagrees with numerical configuration")


def _detect_global_probe_schedule(
    adapter: StandardNativeWindowAdapter,
    schedule: StandardProbeScheduleV3,
    config: TrajectoryFeedbackConfig,
    *,
    edge: StarlinkEdge,
    detector: NativeExplicitPilotOutcomeDetector,
    frequency_reference: ReceiverFrequencyCalibration,
) -> tuple[NativeScheduledProbeDetection, ...]:
    """Detect a bounded number of exact windows without retaining their IQ corpus."""

    validate_trajectory_feedback_config(config)
    segments = {item.segment.segment_index: item.segment for item in adapter.segment_inputs}
    maximum_pending = max(1, config.maximum_workers * 2)
    completed: dict[int, NativeScheduledProbeDetection] = {}
    pending: dict[Future[NativePrimaryProbeOutcome], NativeScheduledProbeInput] = {}

    def harvest(finished: set[Future[NativePrimaryProbeOutcome]]) -> None:
        for future in finished:
            item = pending.pop(future)
            outcome = future.result()
            if not isinstance(outcome, NativePrimaryProbeOutcome):
                raise TypeError("native explicit pilot detector returned the wrong result type")
            detection = outcome.detection
            opportunity = item.opportunity.probe
            retained = NativeScheduledProbeDetection(
                opportunity_index=item.opportunity_index,
                coarse_window_index=opportunity.coarse_window_index,
                continuity_segment_index=item.continuity_segment_index,
                global_device_sample_start=item.global_device_sample_start,
                segment_local_sample_start=item.segment_local_sample_start,
                detection=detection,
                primary_qam_result=outcome.primary_qam_result,
                qam_capture_complete=outcome.qam_capture_complete,
            )
            if item.opportunity_index in completed:
                raise ValueError("global stateful detector repeated an opportunity")
            completed[item.opportunity_index] = retained

    with ThreadPoolExecutor(max_workers=config.maximum_workers) as executor:
        for opportunity, iq in adapter.iter_valid_probe_windows(schedule):
            segment = segments.get(iq.continuity_segment_index)
            if segment is None:
                raise ValueError("valid global probe references an unknown segment")
            item = NativeScheduledProbeInput(
                opportunity_index=iq.opportunity_index,
                opportunity=opportunity,
                segment=segment,
                iq=iq,
                continuity_segment_index=iq.continuity_segment_index,
                global_device_sample_start=iq.global_device_sample_start,
                global_device_sample_stop=iq.global_device_sample_stop,
                segment_local_sample_start=(
                    iq.global_device_sample_start - segment.device_sample_start
                ),
                frequency_reference=frequency_reference,
            )
            pending[executor.submit(detector, item, config, edge)] = item
            if len(pending) >= maximum_pending:
                finished, _ = wait(pending, return_when=FIRST_COMPLETED)
                harvest(finished)
        while pending:
            finished, _ = wait(pending, return_when=FIRST_COMPLETED)
            harvest(finished)
    return tuple(completed[index] for index in sorted(completed))


def detect_standard_native_probe(
    item: NativeScheduledProbeInput,
    config: TrajectoryFeedbackConfig,
    edge: StarlinkEdge,
) -> PilotProbeDetection:
    """Run the unchanged pilot/QAM detector on one explicit global opportunity."""

    if len(item.iq.receiver_ids) != 1:
        raise ValueError("native explicit pilot detection requires one receiver")
    expected_probe_samples = item.iq.sample_rate_hz * config.probe_ms
    if expected_probe_samples % 1_000 or expected_probe_samples // 1_000 != item.iq.sample_count:
        raise ValueError("native explicit pilot window disagrees with configured duration")
    acquisition = SymbolwiseAcquisitionConfig(
        residual_cfo_min_hz=config.cfo_search_min_hz,
        residual_cfo_max_hz=config.cfo_search_max_hz,
        coarse_cfo_step_hz=config.coarse_cfo_step_hz,
        fine_cfo_radius_hz=config.fine_cfo_radius_hz,
        fine_cfo_step_hz=config.fine_cfo_step_hz,
        conditioned_cfo_radius_hz=config.conditioned_cfo_radius_hz,
        conditioned_cfo_step_hz=config.conditioned_cfo_step_hz,
        retained_candidate_count=config.retained_candidate_count,
        candidate_epoch_separation_samples=config.candidate_epoch_separation_samples,
        candidate_cfo_separation_hz=config.candidate_cfo_separation_hz,
        maximum_probe_samples=item.iq.sample_count,
    )
    return detect_pilot_method_candidates(
        _native_window_complex_samples(item.iq),
        item.iq.sample_rate_hz,
        sample_start=item.segment_local_sample_start,
        calibration=item.frequency_reference,
        acquisition_config=acquisition,
        edge=edge,
        maximum_scored_candidates=config.maximum_scored_candidates_per_probe,
        glrt_size=config.glrt_size,
    )


def detect_standard_native_probe_outcome(
    item: NativeScheduledProbeInput,
    config: TrajectoryFeedbackConfig,
    edge: StarlinkEdge,
) -> NativePrimaryProbeOutcome:
    """Retain QAM from the exact primary-candidate call for one valid probe."""

    capture = NativePrimaryQamCapture()
    detection = _detect_standard_native_probe(item, config, edge, qam_capture=capture)
    return NativePrimaryProbeOutcome(detection, capture.result)


def _detect_standard_native_probe(
    item: NativeScheduledProbeInput,
    config: TrajectoryFeedbackConfig,
    edge: StarlinkEdge,
    *,
    qam_capture: NativePrimaryQamCapture,
) -> PilotProbeDetection:
    """QAM-aware implementation sharing the public detector's exact configuration."""

    if len(item.iq.receiver_ids) != 1:
        raise ValueError("native explicit pilot detection requires one receiver")
    expected_probe_samples = item.iq.sample_rate_hz * config.probe_ms
    if expected_probe_samples % 1_000 or expected_probe_samples // 1_000 != item.iq.sample_count:
        raise ValueError("native explicit pilot window disagrees with configured duration")
    acquisition = SymbolwiseAcquisitionConfig(
        residual_cfo_min_hz=config.cfo_search_min_hz,
        residual_cfo_max_hz=config.cfo_search_max_hz,
        coarse_cfo_step_hz=config.coarse_cfo_step_hz,
        fine_cfo_radius_hz=config.fine_cfo_radius_hz,
        fine_cfo_step_hz=config.fine_cfo_step_hz,
        conditioned_cfo_radius_hz=config.conditioned_cfo_radius_hz,
        conditioned_cfo_step_hz=config.conditioned_cfo_step_hz,
        retained_candidate_count=config.retained_candidate_count,
        candidate_epoch_separation_samples=config.candidate_epoch_separation_samples,
        candidate_cfo_separation_hz=config.candidate_cfo_separation_hz,
        maximum_probe_samples=item.iq.sample_count,
    )
    return detect_pilot_method_candidates(
        _native_window_complex_samples(item.iq),
        item.iq.sample_rate_hz,
        sample_start=item.segment_local_sample_start,
        calibration=item.frequency_reference,
        acquisition_config=acquisition,
        edge=edge,
        maximum_scored_candidates=config.maximum_scored_candidates_per_probe,
        glrt_size=config.glrt_size,
        primary_qam_observer=qam_capture,
    )


def _native_window_complex_samples(iq: NativeWindowIqReader) -> np.ndarray:
    parts = tuple(
        (block.samples[:, 0, 0].astype(np.float64) + 1j * block.samples[:, 0, 1].astype(np.float64))
        / 32_768.0
        for block in iq.iter_blocks(block_samples=min(iq.sample_count, 2**20))
    )
    values = np.ascontiguousarray(np.concatenate(parts))
    if values.shape != (iq.sample_count,):
        raise ValueError("native explicit pilot reader did not close its requested support")
    return values


def _build_qam_probe_evidence(
    schedule: StandardProbeScheduleV3,
    segments: tuple[NativeStatefulSegmentResult, ...],
) -> tuple[NativeQamProbeEvidenceV1, ...]:
    """Close same-call QAM outcomes against every valid persisted opportunity."""

    opportunities_by_start = {
        item.probe.sample_start: (index, item) for index, item in enumerate(schedule.opportunities)
    }
    if len(opportunities_by_start) != len(schedule.opportunities):
        raise ValueError("native probe schedule repeated a global sample start")
    evidence: dict[int, NativeQamProbeEvidenceV1] = {}
    for segment_result in segments:
        science = segment_result.local_science
        if science is None:
            continue
        if tuple(item.detection for item in science.primary_probe_outcomes) != science.detections:
            raise ValueError("native stateful science lacks same-call QAM closure")
        for outcome in science.primary_probe_outcomes:
            global_start = segment_result.device_sample_start + outcome.detection.sample_start
            resolved = opportunities_by_start.get(global_start)
            if resolved is None:
                raise ValueError("native QAM outcome is outside the persisted probe schedule")
            opportunity_index, opportunity = resolved
            if opportunity_index in evidence:
                raise ValueError("native QAM outcome repeated a persisted opportunity")
            if (
                outcome.detection.local_epoch_sample is not None
                and not outcome.qam_capture_complete
            ):
                raise ValueError("complete native detection lacks same-call QAM capture proof")
            evidence[opportunity_index] = build_native_qam_probe_evidence(
                opportunity_index=opportunity_index,
                opportunity=opportunity,
                continuity_segment_device_sample_start=segment_result.device_sample_start,
                detection=outcome.detection,
                qam_result=outcome.primary_qam_result,
            )
    valid_indexes = tuple(
        index
        for index, item in enumerate(schedule.opportunities)
        if item.validity.disposition.value == "valid"
    )
    if tuple(sorted(evidence)) != valid_indexes:
        raise ValueError("native same-call QAM evidence does not close every valid probe")
    return tuple(evidence[index] for index in valid_indexes)


def build_standard_native_stateful_path(
    result: StandardNativeStatefulResult,
    binding: StandardPathInputBindV4,
    config: ReceiverStandardConfig,
    *,
    edge: StarlinkEdge,
) -> StandardNativeStatefulPathV1:
    """Rebind one lossless in-process campaign to its persisted native major."""

    if not stateful_global_schedule_is_publishable(binding):
        raise ValueError(
            "segment-local stateful schedules are not publishable for gapped/boundary IQ"
        )
    if (
        result.path_input_binding_digest != binding.binding_digest
        or result.validity_inventory_digest != binding.validity_inventory.inventory_digest
        or result.sample_rate_hz != binding.sample_rate_hz
        or result.logical_sample_count != binding.logical_sample_count
        or tuple(item.segment for item in result.segments) != binding.validity_inventory.segments
    ):
        raise ValueError("native stateful result disagrees with path input authority")

    segments = tuple(_persist_stateful_segment(item) for item in result.segments)
    values = {
        "schema_version": 1,
        "algorithm_version": "standard-native-stateful-path-v1",
        "source": StandardNativeSourceV1.from_path_binding(binding).model_dump(mode="json"),
        "starlink_edge": StarlinkEdge(edge).value,
        "science_configuration_digest": receiver_standard_configuration_digest(config),
        "stateful_science_status": "complete",
        "maximum_outer_window_count": result.maximum_outer_window_count,
        "analyzed_outer_window_count": result.analyzed_outer_window_count,
        "segments": tuple(item.model_dump(mode="json") for item in segments),
        "native_evidence_only": True,
        "current_eligible": False,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    return StandardNativeStatefulPathV1.model_validate(
        {**values, "stateful_path_digest": canonical_digest(values)}
    )


def build_standard_native_stateful_path_v2(
    result: StandardNativeStatefulResult,
    binding: StandardPathInputBindV4,
    config: ReceiverStandardConfig,
    *,
    edge: StarlinkEdge,
    schedule: StandardProbeScheduleV3 | None = None,
) -> StandardNativeStatefulPathV2:
    """Rebind one schedule-proven campaign to the additive stateful V2 major."""

    require_receiver_standard_sample_rate(config, sample_rate_hz=binding.sample_rate_hz)
    lossless = stateful_global_schedule_is_publishable(binding)
    if lossless:
        if (
            result.schedule_authority is not NativeStatefulScheduleAuthority.SEGMENT_LOCAL_ZERO_V1
            or schedule is not None
        ):
            raise ValueError("lossless native stateful V2 publication changed schedule authority")
        stateful_science_status = "complete"
    else:
        if (
            result.schedule_authority
            is not NativeStatefulScheduleAuthority.GLOBAL_PROBE_SCHEDULE_V3
            or schedule is None
            or result.probe_schedule_digest != schedule.schedule_digest
        ):
            raise ValueError("gapped native stateful V2 publication lacks global schedule proof")
        _validate_global_stateful_schedule(schedule, binding, config)
        stateful_science_status = "partial_coverage"
    if (
        result.path_input_binding_digest != binding.binding_digest
        or result.validity_inventory_digest != binding.validity_inventory.inventory_digest
        or result.sample_rate_hz != binding.sample_rate_hz
        or result.logical_sample_count != binding.logical_sample_count
        or tuple(item.segment for item in result.segments) != binding.validity_inventory.segments
    ):
        raise ValueError("native stateful V2 result disagrees with path input authority")

    segments = tuple(_persist_stateful_segment_v2(item) for item in result.segments)
    values = {
        "schema_version": 2,
        "algorithm_version": "standard-native-stateful-path-v2",
        "source": StandardNativeSourceV1.from_path_binding(binding).model_dump(mode="json"),
        "starlink_edge": StarlinkEdge(edge).value,
        "science_configuration_digest": receiver_standard_configuration_digest(config),
        "stateful_science_status": stateful_science_status,
        "maximum_outer_window_count": result.maximum_outer_window_count,
        "analyzed_outer_window_count": result.analyzed_outer_window_count,
        "segments": tuple(item.model_dump(mode="json") for item in segments),
        "native_evidence_only": True,
        "current_eligible": False,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    return StandardNativeStatefulPathV2.model_validate(
        {**values, "stateful_path_digest": canonical_digest(values)}
    )


def build_standard_native_stateful_path_v3(
    result: StandardNativeStatefulResult,
    binding: StandardPathInputBindV5,
    config: ReceiverStandardConfig,
    *,
    edge: StarlinkEdge,
    schedule: StandardProbeScheduleV4 | None = None,
) -> StandardNativeStatefulPathV3:
    """Rebind a wideband campaign to the additive source-V2 stateful major."""

    require_receiver_standard_sample_rate(config, sample_rate_hz=binding.sample_rate_hz)
    lossless = stateful_global_schedule_is_publishable(binding)
    if lossless:
        if (
            result.schedule_authority is not NativeStatefulScheduleAuthority.SEGMENT_LOCAL_ZERO_V1
            or schedule is not None
        ):
            raise ValueError("lossless native stateful V3 publication changed schedule authority")
        stateful_science_status = "complete"
    else:
        if (
            result.schedule_authority
            is not NativeStatefulScheduleAuthority.GLOBAL_PROBE_SCHEDULE_V3
            or schedule is None
            or result.probe_schedule_digest != schedule.schedule_digest
        ):
            raise ValueError("gapped native stateful V3 publication lacks global schedule proof")
        _validate_global_stateful_schedule(schedule, binding, config)
        stateful_science_status = "partial_coverage"
    if (
        result.path_input_binding_digest != binding.binding_digest
        or result.validity_inventory_digest != binding.validity_inventory.inventory_digest
        or result.sample_rate_hz != binding.sample_rate_hz
        or result.logical_sample_count != binding.logical_sample_count
        or tuple(item.segment for item in result.segments) != binding.validity_inventory.segments
    ):
        raise ValueError("native stateful V3 result disagrees with path input authority")
    segments = tuple(_persist_stateful_segment_v2(item) for item in result.segments)
    values = {
        "schema_version": 3,
        "algorithm_version": "standard-native-stateful-path-v3",
        "source": StandardNativeSourceV2.from_path_binding(binding).model_dump(mode="json"),
        "starlink_edge": StarlinkEdge(edge).value,
        "science_configuration_digest": receiver_standard_configuration_digest(config),
        "stateful_science_status": stateful_science_status,
        "maximum_outer_window_count": result.maximum_outer_window_count,
        "analyzed_outer_window_count": result.analyzed_outer_window_count,
        "segments": tuple(item.model_dump(mode="json") for item in segments),
        "native_evidence_only": True,
        "current_eligible": False,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    return StandardNativeStatefulPathV3.model_validate(
        {**values, "stateful_path_digest": canonical_digest(values)}
    )


def build_unavailable_standard_native_stateful_path(
    binding: StandardPathInputBindV4,
    config: ReceiverStandardConfig,
    *,
    edge: StarlinkEdge,
) -> StandardNativeStatefulPathV1:
    """Close all gapped segments without claiming a shifted local schedule."""

    if stateful_global_schedule_is_publishable(binding):
        raise ValueError("lossless native stateful IQ must execute its global schedule")
    segments = tuple(
        _persist_unavailable_stateful_segment(segment)
        for segment in binding.validity_inventory.segments
    )
    values = {
        "schema_version": 1,
        "algorithm_version": "standard-native-stateful-path-v1",
        "source": StandardNativeSourceV1.from_path_binding(binding).model_dump(mode="json"),
        "starlink_edge": StarlinkEdge(edge).value,
        "science_configuration_digest": receiver_standard_configuration_digest(config),
        "stateful_science_status": "unavailable_global_schedule",
        "maximum_outer_window_count": config.feedback.maximum_outer_windows,
        "analyzed_outer_window_count": 0,
        "segments": tuple(item.model_dump(mode="json") for item in segments),
        "native_evidence_only": True,
        "current_eligible": False,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    return StandardNativeStatefulPathV1.model_validate(
        {**values, "stateful_path_digest": canonical_digest(values)}
    )


def build_unavailable_standard_native_stateful_path_v2(
    binding: StandardPathInputBindV4,
    config: ReceiverStandardConfig,
    *,
    edge: StarlinkEdge,
) -> StandardNativeStatefulPathV2:
    """Close a gapped V2 path when no canonical global schedule was executed."""

    require_receiver_standard_sample_rate(config, sample_rate_hz=binding.sample_rate_hz)
    if stateful_global_schedule_is_publishable(binding):
        raise ValueError("lossless native stateful IQ must execute its global schedule")
    segments = tuple(
        _persist_unavailable_stateful_segment_v2(segment)
        for segment in binding.validity_inventory.segments
    )
    values = {
        "schema_version": 2,
        "algorithm_version": "standard-native-stateful-path-v2",
        "source": StandardNativeSourceV1.from_path_binding(binding).model_dump(mode="json"),
        "starlink_edge": StarlinkEdge(edge).value,
        "science_configuration_digest": receiver_standard_configuration_digest(config),
        "stateful_science_status": "unavailable_global_schedule",
        "maximum_outer_window_count": config.feedback.maximum_outer_windows,
        "analyzed_outer_window_count": 0,
        "segments": tuple(item.model_dump(mode="json") for item in segments),
        "native_evidence_only": True,
        "current_eligible": False,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    return StandardNativeStatefulPathV2.model_validate(
        {**values, "stateful_path_digest": canonical_digest(values)}
    )


def _persist_stateful_segment(result: NativeStatefulSegmentResult) -> NativeStatefulSegmentV1:
    local_science = (
        None
        if result.local_science is None
        else _persist_segment_local_science(result.local_science)
    )
    values = {
        "schema_version": 1,
        "continuity_segment": result.segment.model_dump(mode="json"),
        "continuity_segment_index": result.continuity_segment_index,
        "global_device_sample_start": result.device_sample_start,
        "global_device_sample_stop": result.device_sample_stop,
        "disposition": result.disposition.value,
        "local_science": (None if local_science is None else local_science.model_dump(mode="json")),
    }
    return NativeStatefulSegmentV1.model_validate(
        {**values, "segment_digest": canonical_digest(values)}
    )


def _persist_stateful_segment_v2(result: NativeStatefulSegmentResult) -> NativeStatefulSegmentV2:
    local_science = (
        None
        if result.local_science is None
        else _persist_segment_local_science(result.local_science)
    )
    values = {
        "schema_version": 2,
        "continuity_segment": result.segment.model_dump(mode="json"),
        "continuity_segment_index": result.continuity_segment_index,
        "global_device_sample_start": result.device_sample_start,
        "global_device_sample_stop": result.device_sample_stop,
        "disposition": result.disposition.value,
        "local_science": (None if local_science is None else local_science.model_dump(mode="json")),
    }
    return NativeStatefulSegmentV2.model_validate(
        {**values, "segment_digest": canonical_digest(values)}
    )


def _persist_unavailable_stateful_segment(
    segment: ContinuitySegmentV1,
) -> NativeStatefulSegmentV1:
    disposition = (
        NativeStatefulSegmentDispositionV1.EMPTY_TERMINAL
        if segment.observed_sample_count == 0
        else NativeStatefulSegmentDispositionV1.GLOBAL_SCHEDULE_UNAVAILABLE
    )
    values = {
        "schema_version": 1,
        "continuity_segment": segment.model_dump(mode="json"),
        "continuity_segment_index": segment.segment_index,
        "global_device_sample_start": segment.device_sample_start,
        "global_device_sample_stop": segment.device_sample_stop,
        "disposition": disposition.value,
        "local_science": None,
    }
    return NativeStatefulSegmentV1.model_validate(
        {**values, "segment_digest": canonical_digest(values)}
    )


def _persist_unavailable_stateful_segment_v2(
    segment: ContinuitySegmentV1,
) -> NativeStatefulSegmentV2:
    disposition = (
        NativeStatefulSegmentDispositionV2.EMPTY_TERMINAL
        if segment.observed_sample_count == 0
        else NativeStatefulSegmentDispositionV2.GLOBAL_SCHEDULE_UNAVAILABLE
    )
    values = {
        "schema_version": 2,
        "continuity_segment": segment.model_dump(mode="json"),
        "continuity_segment_index": segment.segment_index,
        "global_device_sample_start": segment.device_sample_start,
        "global_device_sample_stop": segment.device_sample_stop,
        "disposition": disposition.value,
        "local_science": None,
    }
    return NativeStatefulSegmentV2.model_validate(
        {**values, "segment_digest": canonical_digest(values)}
    )


def _persist_segment_local_science(
    science: NativeSegmentLocalScience,
) -> NativeSegmentLocalScienceV1:
    detections = tuple(
        NativePilotProbeDetectionV1.model_validate(asdict(item)) for item in science.detections
    )
    raw_bank = NativeRawTrajectoryBankV1.model_validate(asdict(science.residual_hough_bank))
    representatives = tuple(
        NativeTrajectoryRepresentativeV1.model_validate(
            {"family_id": family_id, "trajectory": asdict(trajectory)}
        )
        for family_id, trajectory in science.residual_hough_representatives
    )
    replay = tuple(
        NativeConditionedHoughReplayRowV1.model_validate(item)
        for item in science.conditioned_hough_replay
    )
    values = {
        "schema_version": 1,
        "coordinate_basis": "segment-local-device-axis-v1",
        "segment_path_binding_digest": science.segment_path_binding_digest,
        "pilot_scan_digest": science.pilot_scan_digest,
        "raw_trajectory_bank_digest": science.raw_trajectory_bank_digest,
        "scheduled_outer_window_count": science.scheduled_outer_window_count,
        "detections": tuple(item.model_dump(mode="json") for item in detections),
        "residual_hough_bank": raw_bank.model_dump(mode="json"),
        "residual_hough_representatives": tuple(
            item.model_dump(mode="json") for item in representatives
        ),
        "conditioned_hough_replay": tuple(item.model_dump(mode="json") for item in replay),
        "cfo_alias_map": science.cfo_alias_map.model_dump(mode="json"),
        "dealiased_trajectory_bank": science.dealiased_trajectory_bank.model_dump(mode="json"),
        "cfo_lift_replay": science.cfo_lift_replay.model_dump(mode="json"),
        "final_trajectory_bank": science.final_trajectory_bank.model_dump(mode="json"),
        "kalman_tracking": science.kalman_tracking.model_dump(mode="json"),
        "pilot_doppler_segments": science.pilot_doppler_segments.model_dump(mode="json"),
    }
    return NativeSegmentLocalScienceV1.model_validate(
        {**values, "science_digest": canonical_digest(values)}
    )


def _run_segment_local_science(
    segment_input: NativeSegmentKernelInput,
    binding: StandardPathInputBindV4,
    config: ReceiverStandardConfig,
    edge: StarlinkEdge,
    outer_window_limit: int,
) -> NativeSegmentLocalScience:
    """Execute the existing pure kernels inside one contiguous local reader."""

    iq = segment_input.iq
    if iq is None or outer_window_limit <= 0:
        raise ValueError("segment-local science requires nonempty IQ and a positive budget")
    require_receiver_standard_sample_rate(config, sample_rate_hz=iq.sample_rate_hz)
    feedback = replace(config.feedback, maximum_outer_windows=outer_window_limit)
    primary_outcomes: list[NativePrimaryProbeOutcome] = []
    outcome_lock = threading.Lock()

    def retain_primary_qam(
        detection: PilotProbeDetection,
        qam_result: PilotQamResult | None,
    ) -> None:
        outcome = NativePrimaryProbeOutcome(detection, qam_result)
        with outcome_lock:
            primary_outcomes.append(outcome)

    detections = scan_pilot_detections(
        iq,
        feedback,
        edge=edge,
        primary_qam_detection_observer=retain_primary_qam,
        frequency_reference=_path_frequency_reference(binding, feedback),
    )
    ordered_primary_outcomes = tuple(
        sorted(primary_outcomes, key=lambda item: item.detection.sample_start)
    )
    if (
        ordered_primary_outcomes
        and tuple(item.detection for item in ordered_primary_outcomes) != detections
    ):
        raise ValueError("segment-local QAM observation changed pilot scan ordering")
    bank, representatives = fit_residual_hough_pilot_trajectories(
        detections,
        feedback,
        config.segmentation,
    )
    observations = trajectory_observations(detections)
    if representatives:
        alias_spacing_hz = config.segmentation.initial_hough.alias_spacing_hz
        half_usable_hz = min(binding.sample_rate_hz, binding.rf_bandwidth_hz) / 2.0
        alias_resolution = resolve_hough_replay_alias_indices_by_native_replay(
            iq,
            detections,
            representatives,
            observations,
            feedback,
            edge=edge,
            alias_spacing_hz=alias_spacing_hz,
            gate_config=config.replay_gate,
            usable_baseband_min_hz=-half_usable_hz,
            usable_baseband_max_hz=half_usable_hz,
        )
        alias_indices = alias_resolution.alias_indices
        replay_representatives = tuple(
            item for item in representatives if item[1].trajectory_id in alias_indices
        )
        conditioned_replay = (
            replay_pilot_trajectories_with_conditioned_scores(
                iq,
                detections,
                replay_representatives,
                feedback,
                edge=edge,
                alias_indices=alias_indices,
                alias_spacing_hz=alias_spacing_hz,
                association_gate_hz=config.trajectory_accounting.association_gate_hz,
            )
            if replay_representatives
            else ()
        )
    else:
        conditioned_replay = ()

    configuration_digest = receiver_standard_configuration_digest(config)
    segment_path_binding_digest = canonical_digest(
        {
            "kind": "standard-native-segment-local-binding-v1",
            "path_input_binding_digest": binding.binding_digest,
            "validity_inventory_digest": binding.validity_inventory.inventory_digest,
            "segment": segment_input.segment.model_dump(mode="json"),
            "science_configuration_digest": configuration_digest,
            "effective_maximum_outer_windows": outer_window_limit,
        }
    )
    pilot_scan_digest = canonical_digest(
        {
            "kind": "standard-native-segment-local-pilot-scan-v1",
            "segment_path_binding_digest": segment_path_binding_digest,
            "detections": [asdict(item) for item in detections],
        }
    )
    raw_bank_digest = canonical_digest(
        {
            "kind": "standard-native-segment-local-residual-hough-bank-v1",
            "segment_path_binding_digest": segment_path_binding_digest,
            "pilot_scan_digest": pilot_scan_digest,
            "bank": asdict(bank),
        }
    )
    alias_map = build_cfo_alias_map(
        bank,
        representatives,
        pilot_scan_digest=pilot_scan_digest,
        raw_bank_digest=raw_bank_digest,
        config=config.dealias,
    )
    canonical_bank = fit_huber_linear_dealiased_trajectories(
        observations,
        representatives,
        alias_map,
        raw_bank_digest=raw_bank_digest,
        config=config.dealias,
        seeded_em_config=config.seeded_alias_em,
        huber_config=config.huber_linear,
    )
    replay_gate = config.replay_gate
    if canonical_bank.branches:
        lift_replay = replay_observed_cfo_lifts_v4(
            iq,
            detections,
            canonical_bank,
            feedback,
            edge=edge,
            path_input_binding_digest=segment_path_binding_digest,
            pilot_scan_digest=pilot_scan_digest,
            dealias_config=config.dealias,
            gate_config=replay_gate,
        )
    else:
        lift_replay = classify_observed_lift_replay_v4(
            (),
            (),
            source_lift_count=0,
            path_input_binding_digest=segment_path_binding_digest,
            pilot_scan_digest=pilot_scan_digest,
            canonical_bank=canonical_bank,
            gate_config=replay_gate,
        )
    final_bank = select_final_trajectories_v3(
        canonical_bank,
        lift_replay,
        config=config.dealias,
    )
    kalman = build_standard_kalman_tracking(
        iq,
        path_input_binding_digest=segment_path_binding_digest,
        pilot_scan_digest=pilot_scan_digest,
        detections=detections,
        canonical_bank=canonical_bank,
        final_bank=final_bank,
        feedback_config=feedback,
        config=config.kalman,
        edge=edge,
    )
    doppler_bundle = build_standard_pilot_doppler_segments_bundle_v3(
        iq,
        path_input_binding_digest=segment_path_binding_digest,
        pilot_scan_digest=pilot_scan_digest,
        detections=detections,
        canonical_bank=canonical_bank,
        final_bank=final_bank,
        kalman_tracking=kalman,
        config=config.pilot_doppler_segments,
        edge=edge,
    )
    return NativeSegmentLocalScience(
        segment_path_binding_digest=segment_path_binding_digest,
        pilot_scan_digest=pilot_scan_digest,
        raw_trajectory_bank_digest=raw_bank_digest,
        scheduled_outer_window_count=outer_window_limit,
        detections=detections,
        residual_hough_bank=bank,
        residual_hough_representatives=representatives,
        conditioned_hough_replay=conditioned_replay,
        cfo_alias_map=alias_map,
        dealiased_trajectory_bank=canonical_bank,
        cfo_lift_replay=lift_replay,
        final_trajectory_bank=final_bank,
        kalman_tracking=kalman,
        pilot_doppler_segments=doppler_bundle.legacy_v2,
        pilot_phase_config=doppler_bundle.phase_config,
        pilot_phase_locklets=doppler_bundle.phase_locklets,
        primary_probe_outcomes=ordered_primary_outcomes,
    )


def _run_segment_global_probe_science(
    segment_input: NativeSegmentKernelInput,
    binding: StandardPathInputBindV4,
    config: ReceiverStandardConfig,
    edge: StarlinkEdge,
    scheduled: tuple[NativeScheduledProbeDetection, ...],
    outer_window_count: int,
) -> NativeSegmentLocalScience:
    """Execute one reset-local chain from persisted global probe opportunities."""

    iq = segment_input.iq
    segment = segment_input.segment
    if iq is None or outer_window_count <= 0 or not scheduled:
        raise ValueError("global-probe segment science requires nonempty scheduled IQ")
    require_receiver_standard_sample_rate(config, sample_rate_hz=iq.sample_rate_hz)
    if tuple(item.opportunity_index for item in scheduled) != tuple(
        sorted(item.opportunity_index for item in scheduled)
    ):
        raise ValueError("global-probe segment opportunities are not ordered")
    if any(
        item.continuity_segment_index != segment.segment_index
        or item.global_device_sample_start
        != segment.device_sample_start + item.segment_local_sample_start
        or item.global_device_sample_start < segment.device_sample_start
        or item.global_device_sample_start >= segment.device_sample_stop
        for item in scheduled
    ):
        raise ValueError("global-probe segment execution crossed a reset boundary")
    detections = tuple(item.detection for item in scheduled)
    starts = tuple(item.sample_start for item in detections)
    if starts != tuple(sorted(set(starts))):
        raise ValueError("global-probe detections are not unique and segment-local")

    feedback = replace(config.feedback, maximum_outer_windows=outer_window_count)
    bank, representatives = fit_residual_hough_pilot_trajectories(
        detections,
        feedback,
        config.segmentation,
    )
    observations = trajectory_observations(detections)
    probe_samples = binding.sample_rate_hz * feedback.probe_ms // 1_000
    if representatives:
        alias_spacing_hz = config.segmentation.initial_hough.alias_spacing_hz
        half_usable_hz = min(binding.sample_rate_hz, binding.rf_bandwidth_hz) / 2.0
        alias_resolution = resolve_hough_replay_alias_indices_by_native_replay(
            iq,
            detections,
            representatives,
            observations,
            feedback,
            edge=edge,
            alias_spacing_hz=alias_spacing_hz,
            gate_config=config.replay_gate,
            usable_baseband_min_hz=-half_usable_hz,
            usable_baseband_max_hz=half_usable_hz,
            probe_samples=probe_samples,
        )
        alias_indices = alias_resolution.alias_indices
        replay_representatives = tuple(
            item for item in representatives if item[1].trajectory_id in alias_indices
        )
        conditioned_replay = (
            replay_pilot_trajectories_at_detection_windows_with_conditioned_scores(
                iq,
                detections,
                replay_representatives,
                feedback,
                edge=edge,
                alias_indices=alias_indices,
                alias_spacing_hz=alias_spacing_hz,
                association_gate_hz=config.trajectory_accounting.association_gate_hz,
                probe_samples=probe_samples,
            )
            if replay_representatives
            else ()
        )
    else:
        conditioned_replay = ()

    configuration_digest = receiver_standard_configuration_digest(config)
    segment_path_binding_digest = canonical_digest(
        {
            "kind": "standard-native-segment-local-binding-v1",
            "path_input_binding_digest": binding.binding_digest,
            "validity_inventory_digest": binding.validity_inventory.inventory_digest,
            "segment": segment.model_dump(mode="json"),
            "science_configuration_digest": configuration_digest,
            "effective_maximum_outer_windows": outer_window_count,
        }
    )
    pilot_scan_digest = canonical_digest(
        {
            "kind": "standard-native-segment-local-pilot-scan-v1",
            "segment_path_binding_digest": segment_path_binding_digest,
            "detections": [asdict(item) for item in detections],
        }
    )
    raw_bank_digest = canonical_digest(
        {
            "kind": "standard-native-segment-local-residual-hough-bank-v1",
            "segment_path_binding_digest": segment_path_binding_digest,
            "pilot_scan_digest": pilot_scan_digest,
            "bank": asdict(bank),
        }
    )
    alias_map = build_cfo_alias_map(
        bank,
        representatives,
        pilot_scan_digest=pilot_scan_digest,
        raw_bank_digest=raw_bank_digest,
        config=config.dealias,
    )
    canonical_bank = fit_huber_linear_dealiased_trajectories(
        observations,
        representatives,
        alias_map,
        raw_bank_digest=raw_bank_digest,
        config=config.dealias,
        seeded_em_config=config.seeded_alias_em,
        huber_config=config.huber_linear,
    )
    replay_gate = config.replay_gate
    lift_replay = _replay_observed_cfo_lifts_at_global_probe_windows(
        iq,
        detections,
        canonical_bank,
        feedback,
        edge=edge,
        path_input_binding_digest=segment_path_binding_digest,
        pilot_scan_digest=pilot_scan_digest,
        config=config,
        probe_samples=probe_samples,
        replay_gate=replay_gate,
    )
    final_bank = select_final_trajectories_v3(
        canonical_bank,
        lift_replay,
        config=config.dealias,
    )
    kalman = _build_standard_kalman_tracking_at_global_probe_windows(
        iq,
        path_input_binding_digest=segment_path_binding_digest,
        pilot_scan_digest=pilot_scan_digest,
        detections=detections,
        canonical_bank=canonical_bank,
        final_bank=final_bank,
        probe_samples=probe_samples,
        config=config,
        edge=edge,
    )
    doppler_bundle = build_standard_pilot_doppler_segments_bundle_v3(
        iq,
        path_input_binding_digest=segment_path_binding_digest,
        pilot_scan_digest=pilot_scan_digest,
        detections=detections,
        canonical_bank=canonical_bank,
        final_bank=final_bank,
        kalman_tracking=kalman,
        config=config.pilot_doppler_segments,
        edge=edge,
    )
    return NativeSegmentLocalScience(
        segment_path_binding_digest=segment_path_binding_digest,
        pilot_scan_digest=pilot_scan_digest,
        raw_trajectory_bank_digest=raw_bank_digest,
        scheduled_outer_window_count=outer_window_count,
        detections=detections,
        residual_hough_bank=bank,
        residual_hough_representatives=representatives,
        conditioned_hough_replay=conditioned_replay,
        cfo_alias_map=alias_map,
        dealiased_trajectory_bank=canonical_bank,
        cfo_lift_replay=lift_replay,
        final_trajectory_bank=final_bank,
        kalman_tracking=kalman,
        pilot_doppler_segments=doppler_bundle.legacy_v2,
        pilot_phase_config=doppler_bundle.phase_config,
        pilot_phase_locklets=doppler_bundle.phase_locklets,
        primary_probe_outcomes=tuple(
            NativePrimaryProbeOutcome(
                item.detection,
                item.primary_qam_result,
                item.qam_capture_complete,
            )
            for item in scheduled
        ),
    )


def _replay_observed_cfo_lifts_at_global_probe_windows(
    iq: ContinuitySegmentIqReader,
    detections: tuple[PilotProbeDetection, ...],
    canonical_bank: DealiasedTrajectoryBankV4,
    feedback: TrajectoryFeedbackConfig,
    *,
    edge: StarlinkEdge,
    path_input_binding_digest: Sha256Digest,
    pilot_scan_digest: Sha256Digest,
    config: ReceiverStandardConfig,
    probe_samples: int,
    replay_gate: Any,
) -> CfoLiftReplayV4:
    candidates, source_count = _observed_lift_candidates_v2(
        canonical_bank,
        config.dealias,
        replay_gate,
    )
    representatives = tuple(
        (canonical_digest({"replay_trajectory_id": item.replay_trajectory_id}), item.trajectory)
        for item in candidates
    )
    raw_rows = (
        replay_pilot_trajectories_at_detection_windows_with_conditioned_scores(
            iq,
            detections,
            representatives,
            feedback,
            edge=edge,
            alias_indices={item.trajectory.trajectory_id: 0 for item in candidates},
            alias_spacing_hz=config.dealias.alias_spacing_hz,
            association_gate_hz=config.trajectory_accounting.association_gate_hz,
            probe_samples=probe_samples,
        )
        if representatives
        else ()
    )
    return classify_observed_lift_replay_v4(
        candidates,
        tuple(dict(item) for item in raw_rows),
        source_lift_count=source_count,
        path_input_binding_digest=path_input_binding_digest,
        pilot_scan_digest=pilot_scan_digest,
        canonical_bank=canonical_bank,
        gate_config=replay_gate,
    )


def _build_standard_kalman_tracking_at_global_probe_windows(
    iq: ContinuitySegmentIqReader,
    *,
    path_input_binding_digest: Sha256Digest,
    pilot_scan_digest: Sha256Digest,
    detections: tuple[PilotProbeDetection, ...],
    canonical_bank: DealiasedTrajectoryBankV4,
    final_bank: FinalTrajectoryBankV3,
    probe_samples: int,
    config: ReceiverStandardConfig,
    edge: StarlinkEdge,
) -> StandardKalmanTrackingV1:
    """Reuse frame/Kalman kernels while reading only explicit local probe starts."""

    kalman_config = config.kalman
    selected = tuple(sorted(final_bank.trajectories, key=lambda item: item.trajectory_id))[
        : kalman_config.maximum_tracks
    ]
    model_by_track = {
        item.trajectory_id: PolynomialFrequencyModel(
            item.reference_time_s,
            tuple(item.absolute_coefficients_hz),
        )
        for item in selected
    }
    raw_source_by_id = raw_candidate_sources(detections)
    canonical_by_id = {item.observation_id: item for item in canonical_bank.observations}
    sources_by_probe: dict[int, list[tuple[str, Any]]] = {}
    track_by_id = {item.trajectory_id: item for item in selected}
    for track in selected:
        seen_probes: set[int] = set()
        for canonical_id in track.observation_ids:
            canonical = canonical_by_id.get(canonical_id)
            if canonical is None:
                continue
            source = next(
                (
                    raw_source_by_id[source_id]
                    for source_id in canonical.source_observation_ids
                    if source_id in raw_source_by_id
                ),
                None,
            )
            if source is None or source.detection_sample_start in seen_probes:
                continue
            seen_probes.add(source.detection_sample_start)
            sources_by_probe.setdefault(source.detection_sample_start, []).append(
                (track.trajectory_id, source)
            )

    raw_by_track: dict[str, list[Any]] = {item.trajectory_id: [] for item in selected}
    source_frame_counts = {item.trajectory_id: 0 for item in selected}
    for probe_start, samples in _iter_explicit_segment_probe_samples(
        iq,
        tuple(sorted(sources_by_probe)),
        probe_samples,
    ):
        for trajectory_id, source in sources_by_probe[probe_start]:
            track = track_by_id[trajectory_id]
            measured = extract_probe_frame_measurements(
                samples,
                probe_sample_start=probe_start,
                local_epoch_sample=source.local_epoch_sample,
                sample_rate_hz=iq.sample_rate_hz,
                model=model_by_track[trajectory_id],
                edge=edge,
                pilot_symbol_count=kalman_config.pilot_symbol_count,
                start_time_s=track.start_s,
                end_time_s=track.end_s,
            )
            source_frame_counts[trajectory_id] += len(measured)
            remaining = kalman_config.maximum_source_frames_per_track - len(
                raw_by_track[trajectory_id]
            )
            if remaining > 0:
                raw_by_track[trajectory_id].extend(measured[:remaining])

    tracks = tuple(
        _build_track(
            track,
            tuple(raw_by_track[track.trajectory_id]),
            source_frame_count=source_frame_counts[track.trajectory_id],
            sample_rate_hz=iq.sample_rate_hz,
            model=model_by_track[track.trajectory_id],
            config=kalman_config,
        )
        for track in selected
    )
    has_complete = any(item.status is StandardScientificStatus.COMPLETE for item in tracks)
    truncated = len(final_bank.trajectories) > len(selected) or any(
        item.truncated_frame_count for item in tracks
    )
    status = (
        StandardScientificStatus.PARTIAL
        if has_complete and truncated
        else StandardScientificStatus.COMPLETE
        if has_complete
        else StandardScientificStatus.INSUFFICIENT_DATA
        if selected
        else StandardScientificStatus.NO_RESULT
    )
    reason = (
        "five-state known-pilot frame tracking completed with bounded truncation"
        if status is StandardScientificStatus.PARTIAL
        else "five-state known-pilot frame tracking completed"
        if status is StandardScientificStatus.COMPLETE
        else "final trajectories had too few known-pilot frames for Kalman tracking"
        if selected
        else "no final CFO trajectory was available for Kalman tracking"
    )
    document: dict[str, Any] = {
        "path_input_binding_digest": path_input_binding_digest,
        "pilot_scan_digest": pilot_scan_digest,
        "dealiased_bank_digest": canonical_bank.content_digest,
        "final_trajectory_bank_digest": final_bank.content_digest,
        "config": kalman_config.model_dump(mode="json"),
        "config_digest": kalman_config.digest,
        "source_track_count": len(final_bank.trajectories),
        "returned_track_count": len(tracks),
        "truncated_track_count": len(final_bank.trajectories) - len(tracks),
        "tracks": [item.model_dump(mode="json") for item in tracks],
        "status": status,
        "reason": reason,
        "candidate_only": True,
        "known_pilots_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    identity = {
        "schema_version": 1,
        "algorithm_version": "standard-kalman-tracking-v1",
        **document,
    }
    return StandardKalmanTrackingV1.model_validate(
        {**document, "content_digest": canonical_digest(identity)}
    )


def _iter_explicit_segment_probe_samples(
    iq: ContinuitySegmentIqReader,
    sample_starts: tuple[int, ...],
    probe_samples: int,
) -> Iterable[tuple[int, np.ndarray]]:
    if sample_starts != tuple(sorted(set(sample_starts))):
        raise ValueError("explicit segment probe starts must be unique and ordered")
    if probe_samples <= 0 or any(
        start < 0 or start + probe_samples > iq.sample_count for start in sample_starts
    ):
        raise ValueError("explicit segment probe support escaped its continuity segment")
    if not sample_starts:
        return
    pending = np.empty(0, dtype=np.complex128)
    pending_start = 0
    expected_start = 0
    start_index = 0
    for block in iq.iter_blocks(block_samples=2**20):
        block_start = block.metadata.session_sample_start
        if block_start != expected_start:
            raise ValueError("explicit segment probe reader is not contiguous")
        expected_start += block.metadata.sample_count
        values = (
            block.samples[:, 0, 0].astype(np.float64)
            + 1j * block.samples[:, 0, 1].astype(np.float64)
        ) / 32_768.0
        if not pending.size:
            pending_start = block_start
        elif block_start != pending_start + len(pending):
            raise ValueError("explicit segment probe buffer became discontinuous")
        pending = np.concatenate((pending, values))
        pending_end = pending_start + len(pending)
        while start_index < len(sample_starts):
            sample_start = sample_starts[start_index]
            if sample_start + probe_samples > pending_end:
                break
            if sample_start < pending_start:
                raise ValueError("explicit segment probe reader discarded requested support")
            offset = sample_start - pending_start
            yield sample_start, np.ascontiguousarray(pending[offset : offset + probe_samples])
            start_index += 1
        if start_index == len(sample_starts):
            return
        next_start = sample_starts[start_index]
        drop = min(max(next_start - pending_start, 0), len(pending))
        if drop:
            pending = pending[drop:]
            pending_start += drop
    raise ValueError("explicit segment probe reader did not reach every requested start")
