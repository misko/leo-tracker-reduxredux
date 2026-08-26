"""Segment-local orchestration for additive Standard-native stateful science.

The published Standard contracts remain unchanged.  This module deliberately
returns ordinary frozen dataclasses, not persisted contract models: the legacy
kernel products nested below use segment-local sample coordinates and must be
rebound to additive native contract majors before publication.

Every numerical chain receives exactly one contiguous segment reader.  Pilot
scanning, residual-Hough fitting, CFO de-aliasing and replay, Kalman tracking,
and pilot Doppler therefore start from fresh state at every authoritative
continuity boundary.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from enum import StrEnum

from pydantic import JsonValue

from leo.analysis.standard.native_runner import validate_standard_native_source
from leo.analysis.standard.native_windows import (
    NativeSegmentKernelInput,
    StandardNativeWindowAdapter,
)
from leo.analysis.standard.runner import (
    ReceiverStandardConfig,
    receiver_standard_configuration_digest,
)
from leo.analysis.starlink.cfo_dealias import (
    build_cfo_alias_map,
    classify_observed_lift_replay_v4,
    fit_huber_linear_dealiased_trajectories,
    replay_observed_cfo_lifts_v4,
    select_final_trajectories_v3,
)
from leo.analysis.starlink.kalman_tracking import build_standard_kalman_tracking
from leo.analysis.starlink.pilot_doppler_segments import (
    build_standard_pilot_doppler_segments_v2,
)
from leo.analysis.starlink.pilot_methods import PilotProbeDetection
from leo.analysis.starlink.trajectories import PolynomialTrajectory, TrajectoryBankResult
from leo.analysis.starlink.trajectory_feedback import (
    fit_residual_hough_pilot_trajectories,
    infer_hough_replay_alias_indices,
    replay_pilot_trajectories_with_conditioned_scores,
    scan_pilot_detections,
    trajectory_observations,
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
from leo.contracts.standard_native import StandardNativeSourceV1
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
from leo.contracts.standard_pipeline import StandardPathInputBindV4
from leo.contracts.states import StarlinkEdge
from leo.contracts.validity import ContinuitySegmentV1
from leo.pipeline.validity import ValidityAwareIqReader


class NativeSegmentExecutionDisposition(StrEnum):
    """Truthful reason a continuity segment did or did not enter the chain."""

    ANALYZED = "analyzed"
    EMPTY_TERMINAL = "empty_terminal"
    NO_COMPLETE_OUTER_WINDOW = "no_complete_outer_window"
    OUTER_WINDOW_BUDGET_EXHAUSTED = "outer_window_budget_exhausted"


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
    ) -> None:
        self._config = config or ReceiverStandardConfig()
        self._segment_executor = segment_executor or _run_segment_local_science
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
    ) -> StandardNativeStatefulResult:
        """Run independently on each segment; never return partial failed output."""

        with self._lock:
            if self._poisoned:
                raise RuntimeError("native stateful runner is poisoned; construct a new runner")
            if self._running:
                raise RuntimeError("native stateful runner is already running")
            self._running = True
        try:
            return self._run(reader, binding, edge=StarlinkEdge(edge))
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
    ) -> StandardNativeStatefulResult:
        validate_standard_native_source(reader, binding)
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
        return StandardNativeStatefulResult(
            path_input_binding_digest=binding.binding_digest,
            validity_inventory_digest=binding.validity_inventory.inventory_digest,
            sample_rate_hz=binding.sample_rate_hz,
            logical_sample_count=binding.logical_sample_count,
            maximum_outer_window_count=self._config.feedback.maximum_outer_windows,
            analyzed_outer_window_count=analyzed,
            segments=tuple(results),
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
    feedback = replace(config.feedback, maximum_outer_windows=outer_window_limit)
    detections = scan_pilot_detections(iq, feedback, edge=edge)
    bank, representatives = fit_residual_hough_pilot_trajectories(
        detections,
        feedback,
        config.segmentation,
    )
    observations = trajectory_observations(detections)
    if representatives:
        alias_spacing_hz = config.segmentation.initial_hough.alias_spacing_hz
        alias_indices = infer_hough_replay_alias_indices(
            representatives,
            observations,
            alias_spacing_hz=alias_spacing_hz,
        )
        conditioned_replay = replay_pilot_trajectories_with_conditioned_scores(
            iq,
            detections,
            representatives,
            feedback,
            edge=edge,
            alias_indices=alias_indices,
            alias_spacing_hz=alias_spacing_hz,
            association_gate_hz=config.trajectory_accounting.association_gate_hz,
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
    replay_gate = (
        config.replay_gate
        if config.replay_gate.sample_rate_hz == iq.sample_rate_hz
        else config.replay_gate.model_copy(update={"sample_rate_hz": iq.sample_rate_hz})
    )
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
    doppler = build_standard_pilot_doppler_segments_v2(
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
        pilot_doppler_segments=doppler,
    )
