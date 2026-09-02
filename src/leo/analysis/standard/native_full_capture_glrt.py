"""Gap-aware full-capture GLRT orchestration for Standard-native evidence."""

from __future__ import annotations

import math
import threading
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from leo.analysis.standard.full_capture_glrt20ms import (
    WindowResult,
    _acquisition_config,
    _analyze_window,
    _constant_rate,
    _hough_tracks,
    _run_parallel,
)
from leo.analysis.standard.native_runner import validate_standard_native_source
from leo.analysis.standard.native_windows import (
    NativeWindowDecision,
    NativeWindowIqReader,
    StandardNativeWindowAdapter,
    native_opportunity_accounting,
    native_window_evidence,
)
from leo.analysis.standard.runner import ReceiverStandardConfig
from leo.analysis.starlink.pilot_search_geometry import compile_pilot_search_geometry
from leo.contracts.digests import canonical_digest
from leo.contracts.standard_native import StandardNativeSourceV1, StandardNativeSourceV2
from leo.contracts.standard_native_glrt import (
    NativeFullCaptureGlrtConstantRateV1,
    NativeFullCaptureGlrtHoughTrackV1,
    NativeFullCaptureGlrtHoughV1,
    NativeFullCaptureGlrtOpportunityV1,
    NativeFullCaptureGlrtSegmentDispositionV1,
    NativeFullCaptureGlrtSegmentV1,
    NativeFullCaptureGlrtTrackObservationV1,
    NativeFullCaptureGlrtWindowV1,
    StandardNativeFullCaptureGlrt20msV1,
    StandardNativeFullCaptureGlrt20msV2,
)
from leo.contracts.standard_native_glrt_fractional import (
    FRACTIONAL_GLRT_EPOCH_OFFSETS_V1,
    NativeGlrtFractionalEpochRefinementV1,
    NativeGlrtFractionalEpochStatusV1,
    StandardNativeGlrtFractionalEpochV1,
)
from leo.contracts.standard_pipeline import StandardPathInputBindV4, StandardPathInputBindV5
from leo.contracts.states import StarlinkEdge
from leo.pipeline.validity import ValidityAwareIqReader

NativeFullCaptureWindowKernel = Callable[[int, int, np.ndarray], WindowResult]
NativeFullCaptureSegmentKernel = Callable[
    [tuple[WindowResult, ...]],
    tuple[dict[str, Any], dict[str, Any] | None],
]


@dataclass(frozen=True, slots=True)
class StandardNativeFullCaptureGlrtEvidence:
    """Existing GLRT product plus additive fractional timing evidence."""

    full_capture: StandardNativeFullCaptureGlrt20msV1 | StandardNativeFullCaptureGlrt20msV2
    fractional_epoch: StandardNativeGlrtFractionalEpochV1 | None


def native_full_capture_glrt_configuration_digest(config: ReceiverStandardConfig) -> str:
    """Bind exactly the numerical configuration consumed by this slice."""

    return canonical_digest(
        {
            "algorithm_version": "standard-native-full-capture-glrt20ms-v1",
            "full_capture_glrt20ms": asdict(config.full_capture_glrt20ms),
            "trajectory_feedback": asdict(config.feedback),
            "residual_hough_segmentation": config.segmentation.model_dump(mode="json"),
            "cfo_dealias": config.dealias.model_dump(mode="json"),
            "seeded_alias_em": config.seeded_alias_em.model_dump(mode="json"),
            "huber_linear": config.huber_linear.model_dump(mode="json"),
        }
    )


class StandardNativeFullCaptureGlrtRunner:
    """Analyze all and only valid global windows; poison on any failed run."""

    def __init__(
        self,
        config: ReceiverStandardConfig | None = None,
        *,
        block_samples: int = 262_144,
        window_kernel: NativeFullCaptureWindowKernel | None = None,
        segment_kernel: NativeFullCaptureSegmentKernel | None = None,
    ) -> None:
        if not 0 < block_samples <= 1_048_576:
            raise ValueError("native full-capture GLRT block size is outside the reviewed bound")
        self._config = config or ReceiverStandardConfig()
        full_capture = self._config.full_capture_glrt20ms
        if not full_capture.enabled or (full_capture.window_ms, full_capture.stride_ms) != (20, 10):
            raise ValueError("Standard-native requires the enabled canonical 20ms/10ms GLRT")
        self._block_samples = block_samples
        self._window_kernel = window_kernel
        self._segment_kernel = segment_kernel
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
        binding: StandardPathInputBindV4 | StandardPathInputBindV5,
        *,
        edge: StarlinkEdge,
    ) -> StandardNativeFullCaptureGlrt20msV1 | StandardNativeFullCaptureGlrt20msV2:
        """Return one complete persisted result, or poison without partial output."""

        return self._execute(reader, binding, edge=StarlinkEdge(edge)).full_capture

    def run_evidence(
        self,
        reader: ValidityAwareIqReader,
        binding: StandardPathInputBindV5,
        *,
        edge: StarlinkEdge,
    ) -> StandardNativeFullCaptureGlrtEvidence:
        """Return the current full-capture result and fractional timing companion."""

        result = self._execute(reader, binding, edge=StarlinkEdge(edge))
        if result.fractional_epoch is None:
            raise ValueError("V5 native GLRT did not produce fractional epoch evidence")
        return result

    def _execute(
        self,
        reader: ValidityAwareIqReader,
        binding: StandardPathInputBindV4 | StandardPathInputBindV5,
        *,
        edge: StarlinkEdge,
    ) -> StandardNativeFullCaptureGlrtEvidence:

        with self._lock:
            if self._poisoned:
                raise RuntimeError("native full-capture GLRT runner is poisoned")
            if self._running:
                raise RuntimeError("native full-capture GLRT runner is already running")
            self._running = True
        try:
            return self._run(reader, binding, edge=edge)
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
        binding: StandardPathInputBindV4 | StandardPathInputBindV5,
        *,
        edge: StarlinkEdge,
    ) -> StandardNativeFullCaptureGlrtEvidence:
        validate_standard_native_source(reader, binding)
        if edge is not binding.starlink_edge:
            raise ValueError("native full-capture GLRT edge differs from the V4 path binding")
        adapter = StandardNativeWindowAdapter(reader)
        decisions = adapter.full_capture_glrt20ms_schedule(window_ms=20, stride_ms=10)
        config = self._config
        full_capture = config.full_capture_glrt20ms
        window_samples = binding.sample_rate_hz * 20 // 1_000
        stride_samples = binding.sample_rate_hz * 10 // 1_000
        acquisition = _acquisition_config(window_samples, config.feedback)
        effective_window_kernel = self._window_kernel
        if effective_window_kernel is None:
            search_geometry = compile_pilot_search_geometry(
                receiver_id=binding.receiver_id,
                starlink_channel=binding.starlink_channel,
                edge=edge,
                tuned_center_frequency_hz=binding.tuned_center_frequency_hz,
                sample_rate_hz=binding.sample_rate_hz,
                rf_bandwidth_hz=binding.rf_bandwidth_hz,
                residual_cfo_min_hz=config.feedback.cfo_search_min_hz,
                residual_cfo_max_hz=config.feedback.cfo_search_max_hz,
            )

            def effective_window_kernel(
                index: int, start: int, samples: np.ndarray
            ) -> WindowResult:
                return _analyze_window(
                    index,
                    start,
                    samples,
                    sample_rate_hz=binding.sample_rate_hz,
                    edge=edge,
                    acquisition_config=acquisition,
                    glrt_size=config.feedback.glrt_size,
                    margin_gate=full_capture.margin_gate,
                    frequency_reference=search_geometry.frequency_reference,
                    refine_fractional_epoch=isinstance(binding, StandardPathInputBindV5),
                )

        rows = _run_parallel(
            _kernel_windows(
                adapter,
                decisions,
                receiver_id=binding.receiver_id,
                block_samples=self._block_samples,
            ),
            effective_window_kernel,
            workers=full_capture.maximum_workers,
        )
        decision_by_index = {item.request.opportunity_index: item for item in decisions}
        if len(rows) != sum(item.eligible for item in decisions):
            raise ValueError("native full-capture GLRT lost an eligible global opportunity")
        rows_by_segment: dict[int, list[WindowResult]] = {
            segment.segment_index: [] for segment in binding.validity_inventory.segments
        }
        for row in rows:
            decision = decision_by_index.get(row.probe_index)
            if (
                decision is None
                or not decision.eligible
                or row.sample_start != decision.request.device_sample_start
            ):
                raise ValueError("native GLRT kernel changed its global opportunity identity")
            segment_index = decision.classification.continuity_segment_index
            assert segment_index is not None
            rows_by_segment[segment_index].append(row)

        effective_segment_kernel = self._segment_kernel
        if effective_segment_kernel is None:

            def effective_segment_kernel(
                segment_rows: tuple[WindowResult, ...],
            ) -> tuple[dict[str, Any], dict[str, Any] | None]:
                return (
                    _hough_tracks(
                        segment_rows,
                        feedback=config.feedback,
                        segmentation=config.segmentation,
                        dealias=config.dealias,
                        seeded_alias_em=config.seeded_alias_em,
                        huber_linear=config.huber_linear,
                    ),
                    _constant_rate(
                        segment_rows,
                        line_rms_reference_hz=full_capture.line_rms_reference_hz,
                    ),
                )

        segment_results: list[NativeFullCaptureGlrtSegmentV1] = []
        for segment in binding.validity_inventory.segments:
            segment_rows = tuple(rows_by_segment[segment.segment_index])
            windows = tuple(
                _persist_window(
                    row,
                    decision_by_index[row.probe_index],
                )
                for row in segment_rows
            )
            if windows:
                hough_document, rate_document = effective_segment_kernel(segment_rows)
                hough = _persist_hough(hough_document, windows, binding.sample_rate_hz)
                constant_rate = _persist_constant_rate(
                    rate_document,
                    windows,
                    binding.sample_rate_hz,
                    line_rms_reference_hz=full_capture.line_rms_reference_hz,
                )
                disposition = NativeFullCaptureGlrtSegmentDispositionV1.ANALYZED
            else:
                hough = _empty_hough()
                constant_rate = None
                disposition = (
                    NativeFullCaptureGlrtSegmentDispositionV1.EMPTY_TERMINAL
                    if segment.observed_sample_count == 0
                    else NativeFullCaptureGlrtSegmentDispositionV1.NO_VALID_WINDOWS
                )
            segment_values = {
                "continuity_segment": segment.model_dump(mode="json"),
                "disposition": disposition.value,
                "valid_opportunity_indexes": tuple(item.opportunity_index for item in windows),
                "windows": tuple(item.model_dump(mode="json") for item in windows),
                "hough": hough.model_dump(mode="json"),
                "constant_rate": (
                    None if constant_rate is None else constant_rate.model_dump(mode="json")
                ),
            }
            segment_results.append(
                NativeFullCaptureGlrtSegmentV1.model_validate(
                    {
                        **segment_values,
                        "segment_digest": canonical_digest({"schema_version": 1, **segment_values}),
                    }
                )
            )

        opportunities = tuple(
            NativeFullCaptureGlrtOpportunityV1(
                opportunity_index=decision.request.opportunity_index,
                validity=native_window_evidence(decision.classification),
            )
            for decision in decisions
        )
        passing = sum(item.passed_margin_gate for item in rows)
        accounting = native_opportunity_accounting(
            decisions,
            analyzed_count=len(rows),
            passing_count=passing,
        )
        source = (
            StandardNativeSourceV2.from_path_binding(binding)
            if isinstance(binding, StandardPathInputBindV5)
            else StandardNativeSourceV1.from_path_binding(binding)
        )
        wideband = isinstance(source, StandardNativeSourceV2)
        schedule_values = {
            "kind": "standard-native-full-capture-glrt20ms-schedule-v1",
            "path_input_binding_digest": source.path_input_binding_digest,
            "validity_inventory_digest": source.validity_inventory_digest,
            "sample_rate_hz": source.sample_rate_hz,
            "logical_sample_count": source.logical_sample_count,
            "window_samples": window_samples,
            "stride_samples": stride_samples,
            "opportunities": tuple(item.model_dump(mode="json") for item in opportunities),
        }
        segment_documents = tuple(item.model_dump(mode="json") for item in segment_results)
        values = {
            "source": source.model_dump(mode="json"),
            "starlink_edge": edge.value,
            "science_configuration_digest": native_full_capture_glrt_configuration_digest(config),
            "window_samples": window_samples,
            "stride_samples": stride_samples,
            "opportunities": tuple(item.model_dump(mode="json") for item in opportunities),
            "accounting": accounting.model_dump(mode="json"),
            "schedule_digest": canonical_digest(schedule_values),
            "segments": segment_documents,
            "segment_results_digest": canonical_digest(segment_documents),
            "native_evidence_only": True,
            "current_eligible": False,
            "candidate_only": True,
            "specificity_claimed": False,
            "payload_decoded": False,
        }
        document = {
            "schema_version": 2 if wideband else 1,
            "algorithm_version": (
                "standard-native-full-capture-glrt20ms-v2"
                if wideband
                else "standard-native-full-capture-glrt20ms-v1"
            ),
            "window_ms": 20,
            "stride_ms": 10,
            **values,
        }
        product_type = (
            StandardNativeFullCaptureGlrt20msV2 if wideband else StandardNativeFullCaptureGlrt20msV1
        )
        full_capture_result = product_type.model_validate(
            {**document, "result_digest": canonical_digest(document)}
        )
        fractional_epoch = (
            _persist_fractional_epoch(
                rows,
                decision_by_index,
                source,
                full_capture_result,
            )
            if isinstance(source, StandardNativeSourceV2)
            and isinstance(full_capture_result, StandardNativeFullCaptureGlrt20msV2)
            else None
        )
        return StandardNativeFullCaptureGlrtEvidence(full_capture_result, fractional_epoch)


def _persist_fractional_epoch(
    rows: tuple[WindowResult, ...],
    decisions: dict[int, NativeWindowDecision],
    source: StandardNativeSourceV2,
    full_capture: StandardNativeFullCaptureGlrt20msV2,
) -> StandardNativeGlrtFractionalEpochV1:
    """Seal passing-window fractional peaks without changing integer evidence."""

    refinements: list[NativeGlrtFractionalEpochRefinementV1] = []
    for row in rows:
        if not row.passed_margin_gate:
            continue
        decision = decisions[row.probe_index]
        segment_index = decision.classification.continuity_segment_index
        if (
            segment_index is None
            or row.epoch_sample is None
            or row.acquired_cfo_hz is None
            or row.glrt_exact_score is None
        ):
            raise ValueError("passing native GLRT window lacks fractional refinement inputs")
        try:
            status = NativeGlrtFractionalEpochStatusV1(row.fractional_epoch_status)
        except ValueError as error:
            raise ValueError("passing native GLRT window was not fractionally evaluated") from error
        if status not in {
            NativeGlrtFractionalEpochStatusV1.COMPLETE,
            NativeGlrtFractionalEpochStatusV1.UNBRACKETED,
            NativeGlrtFractionalEpochStatusV1.UNAVAILABLE,
        }:
            raise ValueError("passing native GLRT window was not fractionally evaluated")
        integer_global = decision.request.device_sample_start + row.epoch_sample
        score_grid = (
            None
            if status is NativeGlrtFractionalEpochStatusV1.UNAVAILABLE
            else tuple(row.fractional_epoch_exact_score_grid)
        )
        fractional_global = (
            None
            if row.fractional_epoch_offset_samples is None
            else integer_global + row.fractional_epoch_offset_samples
        )
        refinement_values = {
            "opportunity_index": row.probe_index,
            "continuity_segment_index": segment_index,
            "integer_global_epoch_device_sample": integer_global,
            "acquired_cfo_hz": row.acquired_cfo_hz,
            "integer_exact_score": row.glrt_exact_score,
            "status": status.value,
            "exact_score_grid": score_grid,
            "fractional_epoch_offset_samples": row.fractional_epoch_offset_samples,
            "fractional_global_epoch_device_sample": fractional_global,
        }
        refinements.append(
            NativeGlrtFractionalEpochRefinementV1.model_validate(
                {
                    **refinement_values,
                    "refinement_digest": canonical_digest(
                        {"schema_version": 1, **refinement_values}
                    ),
                }
            )
        )
    statuses = tuple(item.status for item in refinements)
    product_values = {
        "source": source.model_dump(mode="json"),
        "source_glrt_product_digest": canonical_digest(full_capture.model_dump(mode="json")),
        "source_glrt_result_digest": full_capture.result_digest,
        "configuration_digest": canonical_digest(
            {
                "algorithm_version": "standard-native-glrt-fractional-epoch-v1",
                "source_glrt_configuration_digest": full_capture.science_configuration_digest,
                "score_definition": "conditioned-exact-glrt64-at-fixed-acquired-cfo",
                "interpolation_method": "three-cell-log-parabola-v1",
                "score_grid_offsets_samples": FRACTIONAL_GLRT_EPOCH_OFFSETS_V1,
                "selection_policy": "persisted-margin-pass-windows-only",
            }
        ),
        "starlink_edge": full_capture.starlink_edge.value,
        "score_grid_offsets_samples": FRACTIONAL_GLRT_EPOCH_OFFSETS_V1,
        "refinement_count": len(refinements),
        "complete_count": statuses.count(NativeGlrtFractionalEpochStatusV1.COMPLETE),
        "unbracketed_count": statuses.count(NativeGlrtFractionalEpochStatusV1.UNBRACKETED),
        "unavailable_count": statuses.count(NativeGlrtFractionalEpochStatusV1.UNAVAILABLE),
        "refinements": tuple(item.model_dump(mode="json") for item in refinements),
        "limitations": (
            "Only persisted GLRT margin-pass windows are refined; detection is unchanged.",
            "The acquired CFO and edge hypothesis remain fixed during timing refinement.",
            "The fractional peak is a three-cell log-parabolic interpolation of integer "
            "exact-score evaluations, not a fractionally shifted template correlation.",
            "Overlapping 20 ms windows are statistically dependent at the 10 ms stride.",
            "Candidate evidence does not establish Starlink or satellite identity.",
        ),
        "native_evidence_only": True,
        "current_eligible": False,
        "candidate_only": True,
    }
    document = {
        "schema_version": 1,
        "algorithm_version": "standard-native-glrt-fractional-epoch-v1",
        "score_definition": "conditioned-exact-glrt64-at-fixed-acquired-cfo",
        "interpolation_method": "three-cell-log-parabola-v1",
        "selection_policy": "persisted-margin-pass-windows-only",
        **product_values,
    }
    return StandardNativeGlrtFractionalEpochV1.model_validate(
        {**document, "result_digest": canonical_digest(document)}
    )


def _kernel_windows(
    adapter: StandardNativeWindowAdapter,
    decisions: tuple[NativeWindowDecision, ...],
    *,
    receiver_id: int,
    block_samples: int,
) -> Iterable[tuple[int, int, np.ndarray]]:
    for decision, iq in adapter.iter_valid_windows(decisions, block_samples=block_samples):
        yield (
            decision.request.opportunity_index,
            decision.request.device_sample_start,
            _complex_window(iq, receiver_id=receiver_id, block_samples=block_samples),
        )


def _complex_window(
    iq: NativeWindowIqReader,
    *,
    receiver_id: int,
    block_samples: int,
) -> np.ndarray:
    try:
        receiver_column = iq.receiver_ids.index(receiver_id)
    except ValueError as error:
        raise ValueError("native GLRT receiver is absent from a valid window") from error
    blocks = tuple(iq.iter_blocks(block_samples=block_samples))
    if not blocks:
        raise ValueError("native GLRT valid window returned no IQ")
    samples = (
        np.concatenate(
            tuple(
                block.samples[:, receiver_column, 0].astype(np.float64)
                + 1j * block.samples[:, receiver_column, 1].astype(np.float64)
                for block in blocks
            )
        )
        / 32_768.0
    )
    if len(samples) != iq.sample_count:
        raise ValueError("native GLRT numerical window did not close its support")
    return np.ascontiguousarray(samples)


def _persist_window(
    row: WindowResult,
    decision: NativeWindowDecision,
) -> NativeFullCaptureGlrtWindowV1:
    segment_index = decision.classification.continuity_segment_index
    if segment_index is None:
        raise ValueError("native GLRT result is not bound to one continuity segment")
    start = decision.request.device_sample_start
    stop = decision.request.device_sample_stop
    values = {
        "opportunity_index": decision.request.opportunity_index,
        "continuity_segment_index": segment_index,
        "global_device_sample_start": start,
        "global_device_sample_stop": stop,
        "global_start_time_s": row.start_time_s,
        "global_center_time_s": row.center_time_s,
        "global_end_time_s": row.end_time_s,
        "acquisition_status": row.acquisition_status,
        "candidate_count": row.candidate_count,
        "best_candidate_rank": row.best_candidate_rank,
        "global_epoch_device_sample": (
            None if row.epoch_sample is None else start + row.epoch_sample
        ),
        "acquired_cfo_hz": row.acquired_cfo_hz,
        "residual_cfo_hz": row.residual_cfo_hz,
        "tracking_cfo_hz": row.tracking_cfo_hz,
        "glrt_exact_score": row.glrt_exact_score,
        "glrt_control_score": row.glrt_control_score,
        "glrt_margin": row.glrt_margin,
        "passed_margin_gate": row.passed_margin_gate,
        "lattice_frame_count": row.lattice_frame_count,
        "measured_frame_count": row.measured_frame_count,
        "robust_line_available": row.robust_line_available,
        "global_robust_reference_time_s": row.robust_reference_time_s,
        "robust_cfo_at_reference_hz": row.robust_cfo_at_reference_hz,
        "robust_slope_hz_s": row.robust_slope_hz_s,
        "robust_slope_sigma_hz_s": row.robust_slope_sigma_hz_s,
        "robust_residual_rms_hz": row.robust_residual_rms_hz,
        "robust_median_absolute_residual_hz": row.robust_median_absolute_residual_hz,
        "robust_mad_scale_hz": row.robust_mad_scale_hz,
        "robust_outlier_count": row.robust_outlier_count,
        "robust_converged": row.robust_converged,
        "reason": row.reason,
    }
    return NativeFullCaptureGlrtWindowV1.model_validate(
        {
            **values,
            "window_digest": canonical_digest({"schema_version": 1, **values}),
        }
    )


def _persist_hough(
    document: dict[str, Any],
    windows: tuple[NativeFullCaptureGlrtWindowV1, ...],
    sample_rate_hz: int,
) -> NativeFullCaptureGlrtHoughV1:
    by_start = {item.global_device_sample_start: item for item in windows}
    tracks: list[NativeFullCaptureGlrtHoughTrackV1] = []
    raw_tracks = document.get("tracks")
    if not isinstance(raw_tracks, list):
        raise ValueError("native Hough kernel returned no exact track inventory")
    for raw_track in raw_tracks:
        if not isinstance(raw_track, dict) or not isinstance(raw_track.get("observations"), list):
            raise ValueError("native Hough kernel returned a malformed track")
        observations: list[NativeFullCaptureGlrtTrackObservationV1] = []
        for raw in raw_track["observations"]:
            if not isinstance(raw, dict):
                raise ValueError("native Hough kernel returned a malformed observation")
            time_s = float(raw["time_s"])
            sample = round(time_s * sample_rate_hz)
            window = by_start.get(sample)
            if window is None or not math.isclose(
                time_s,
                sample / sample_rate_hz,
                abs_tol=1e-12,
            ):
                raise ValueError("native Hough observation is not on a segment window")
            observations.append(
                NativeFullCaptureGlrtTrackObservationV1(
                    opportunity_index=window.opportunity_index,
                    global_device_sample=sample,
                    global_time_s=time_s,
                    raw_cfo_hz=float(raw["raw_cfo_hz"]),
                    alias_index=int(raw["alias_index"]),
                )
            )
        observations.sort(key=lambda item: item.opportunity_index)
        if not observations:
            raise ValueError("native Hough track has no observations")
        start_s = float(raw_track["start_s"])
        end_s = float(raw_track["end_s"])
        reference_s = float(raw_track["reference_time_s"])
        if not (
            math.isclose(start_s, observations[0].global_time_s, abs_tol=1e-12)
            and math.isclose(end_s, observations[-1].global_time_s, abs_tol=1e-12)
        ):
            raise ValueError("native Hough track support differs from its observations")
        values = {
            "track_label": str(raw_track["track_label"]),
            "global_device_sample_start": observations[0].global_device_sample,
            "global_device_sample_end": observations[-1].global_device_sample,
            "global_reference_device_sample": reference_s * sample_rate_hz,
            "global_start_time_s": start_s,
            "global_end_time_s": end_s,
            "global_reference_time_s": reference_s,
            "slope_hz_s": float(raw_track["slope_hz_s"]),
            "cfo_at_reference_hz": float(raw_track["cfo_at_reference_hz"]),
            "observation_count": int(raw_track["observation_count"]),
            "observations": tuple(item.model_dump(mode="json") for item in observations),
        }
        tracks.append(
            NativeFullCaptureGlrtHoughTrackV1.model_validate(
                {
                    **values,
                    "track_digest": canonical_digest({"schema_version": 1, **values}),
                }
            )
        )
    values = {
        "input_observation_count": int(document["input_observation_count"]),
        "raw_hough_track_count": int(document["raw_hough_track_count"]),
        "truncated_hough_track_count": int(document["truncated_hough_track_count"]),
        "published_track_count": int(document["published_track_count"]),
        "returned_observation_count": int(document["returned_observation_count"]),
        "tracks": tuple(item.model_dump(mode="json") for item in tracks),
    }
    return NativeFullCaptureGlrtHoughV1.model_validate(
        {
            **values,
            "hough_digest": canonical_digest({"schema_version": 1, **values}),
        }
    )


def _empty_hough() -> NativeFullCaptureGlrtHoughV1:
    values = {
        "input_observation_count": 0,
        "raw_hough_track_count": 0,
        "truncated_hough_track_count": 0,
        "published_track_count": 0,
        "returned_observation_count": 0,
        "tracks": (),
    }
    return NativeFullCaptureGlrtHoughV1.model_validate(
        {
            **values,
            "hough_digest": canonical_digest({"schema_version": 1, **values}),
        }
    )


def _persist_constant_rate(
    document: dict[str, Any] | None,
    windows: tuple[NativeFullCaptureGlrtWindowV1, ...],
    sample_rate_hz: int,
    *,
    line_rms_reference_hz: float,
) -> NativeFullCaptureGlrtConstantRateV1 | None:
    if document is None:
        return None
    start_s = float(document["start_s"])
    end_s = float(document["end_s"])
    start_sample = round(start_s * sample_rate_hz)
    end_sample = round(end_s * sample_rate_hz)
    centers = {
        (item.global_device_sample_start + item.global_device_sample_stop) // 2 for item in windows
    }
    if (
        start_sample not in centers
        or end_sample not in centers
        or not math.isclose(start_s, start_sample / sample_rate_hz, abs_tol=1e-12)
        or not math.isclose(end_s, end_sample / sample_rate_hz, abs_tol=1e-12)
    ):
        raise ValueError("native constant-rate kernel escaped segment window centers")
    values = {
        "input_filter": str(document["input_filter"]),
        "point_count": int(document["point_count"]),
        "supporting_opportunity_indexes": tuple(
            item.opportunity_index
            for item in windows
            if item.passed_margin_gate
            and item.robust_line_available
            and item.robust_slope_hz_s is not None
            and abs(item.robust_slope_hz_s) <= 10_000.0
            and item.robust_residual_rms_hz is not None
            and item.robust_residual_rms_hz <= line_rms_reference_hz
        ),
        "global_center_sample_start": start_sample,
        "global_center_sample_end": end_sample,
        "global_start_time_s": start_s,
        "global_end_time_s": end_s,
        "constant_doppler_rate_hz_s": float(document["constant_doppler_rate_hz_s"]),
        "median_absolute_deviation_hz_s": float(document["median_absolute_deviation_hz_s"]),
    }
    return NativeFullCaptureGlrtConstantRateV1.model_validate(
        {
            **values,
            "summary_digest": canonical_digest({"schema_version": 1, **values}),
        }
    )
