"""Validity-safe PSS acquisition for the existing Standard-native path stage."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np

from leo.analysis.standard.native_runner import validate_standard_native_source
from leo.analysis.starlink.pss_search import (
    PssBankMode,
    PssBankSearchConfig,
    PssBankSearchResult,
    PssProjection,
    PssSearchOrigin,
    PssSearchTarget,
    PssTimingTrack,
    PssTrackAssociationConfig,
    associate_pss_timing_tracks,
    compile_pss_projection,
    project_pss_block,
    search_pss_frame_timing_bank,
)
from leo.analysis.starlink.pss_timing import PssTimingSearchConfig, pss_subband_template
from leo.analysis.starlink.templates import FRAME_RATE_HZ
from leo.contracts.digests import canonical_digest
from leo.contracts.standard_native import StandardNativeSourceV2
from leo.contracts.standard_native_glrt import (
    NativeFullCaptureGlrtWindowV1,
    StandardNativeFullCaptureGlrt20msV2,
)
from leo.contracts.standard_native_pss import (
    NativePssAccountingV1,
    NativePssBlockDispositionV1,
    NativePssModeV1,
    NativePssProjectionV1,
    NativePssSearchBlockV1,
    NativePssSearchOriginV1,
    NativePssTimingTrackV1,
    StandardNativePssFrameTimingV1,
)
from leo.contracts.standard_pipeline import StandardPathInputBindV5
from leo.contracts.starlink_frequency import (
    STARLINK_CHANNEL_OCCUPIED_BANDWIDTH_HZ,
    starlink_channel_if_bounds_hz,
    starlink_edge_if_center_frequency_hz,
)
from leo.contracts.states import StarlinkEdge
from leo.pipeline.validity import ValidityAwareIqReader

_PSS_HALF_BIN_HZ = STARLINK_CHANNEL_OCCUPIED_BANDWIDTH_HZ / 2048.0


@dataclass(frozen=True, slots=True)
class StandardNativePssConfig:
    """Release-bound PSS policy shared by every reviewed native rate."""

    maximum_block_duration_s: float = 0.25
    canonical_projection_sample_rate_hz: int = 2_500_000
    projection_edge_trim_output_samples: int = 64
    timing: PssTimingSearchConfig = field(default_factory=PssTimingSearchConfig)
    blind_bank: PssBankSearchConfig = field(default_factory=PssBankSearchConfig)
    association: PssTrackAssociationConfig = field(default_factory=PssTrackAssociationConfig)
    glrt_conditioning_enabled: bool = True
    glrt_bootstrap_minimum_pairs: int = 3
    glrt_timing_radius_s: float = 2.0e-6
    glrt_frequency_half_width_hz: float = 75_000.0

    def __post_init__(self) -> None:
        numerical = (
            self.maximum_block_duration_s,
            self.glrt_timing_radius_s,
            self.glrt_frequency_half_width_hz,
        )
        if not all(math.isfinite(value) and value > 0 for value in numerical):
            raise ValueError("native PSS search bounds must be finite and positive")
        if (
            self.canonical_projection_sample_rate_hz <= 0
            or self.projection_edge_trim_output_samples < 0
            or self.glrt_bootstrap_minimum_pairs < 1
        ):
            raise ValueError("native PSS search count bounds are invalid")


def standard_native_pss_configuration_digest(config: StandardNativePssConfig) -> str:
    return canonical_digest(
        {
            "algorithm_version": "standard-native-pss-frame-timing-v1",
            "configuration": asdict(config),
        }
    )


def starlink_pss_channel_reference_hz(
    channel: int,
    edge: StarlinkEdge | str,
) -> float:
    """Return the published edge-dependent PSS half-bin channel reference."""

    selected_edge = StarlinkEdge(edge)
    lower, upper = starlink_channel_if_bounds_hz(channel)
    midpoint = (lower + upper) / 2.0
    return midpoint + (
        -_PSS_HALF_BIN_HZ if selected_edge is StarlinkEdge.LOWER else _PSS_HALF_BIN_HZ
    )


class StandardNativePssRunner:
    """Run mandatory blind PSS plus optional, explicitly conditioned follow-up."""

    def __init__(self, config: StandardNativePssConfig | None = None) -> None:
        self._config = config or StandardNativePssConfig()

    def run(
        self,
        reader: ValidityAwareIqReader,
        binding: StandardPathInputBindV5,
        *,
        full_capture_glrt: StandardNativeFullCaptureGlrt20msV2,
    ) -> StandardNativePssFrameTimingV1:
        validate_standard_native_source(reader, binding)
        source = StandardNativeSourceV2.from_path_binding(binding)
        if full_capture_glrt.source != source:
            raise ValueError("native PSS GLRT source differs from the exact path binding")
        config = self._config
        reference_hz = starlink_pss_channel_reference_hz(
            binding.starlink_channel,
            binding.starlink_edge,
        )
        target_center_hz = float(
            starlink_edge_if_center_frequency_hz(
                binding.starlink_channel,
                binding.starlink_edge,
            )
        )
        canonical_rate = (
            config.canonical_projection_sample_rate_hz
            if binding.sample_rate_hz % config.canonical_projection_sample_rate_hz == 0
            else binding.sample_rate_hz
        )
        projection = compile_pss_projection(
            input_sample_rate_hz=binding.sample_rate_hz,
            input_center_frequency_hz=float(binding.tuned_center_frequency_hz),
            rf_bandwidth_hz=binding.rf_bandwidth_hz,
            target_center_frequency_hz=target_center_hz,
            channel_reference_hz=reference_hz,
            canonical_output_sample_rate_hz=canonical_rate,
            edge_trim_output_samples=config.projection_edge_trim_output_samples,
        )
        blind_rows, projected_by_block = self._blind_blocks(reader, binding, projection)
        conditioned_rows: tuple[tuple[object, PssBankSearchResult], ...] = ()
        if config.glrt_conditioning_enabled:
            conditioned_rows = self._conditioned_blocks(
                projected_by_block,
                blind_rows,
                full_capture_glrt,
            )
        all_rows = (*blind_rows, *conditioned_rows)
        all_modes = tuple(mode for _block, result in all_rows for mode in result.modes)
        tracks = tuple(
            track
            for origin in PssSearchOrigin
            for track in associate_pss_timing_tracks(
                tuple(mode for mode in all_modes if mode.origin is origin),
                config=config.association,
            )
        )
        return _build_contract(
            source=source,
            edge=binding.starlink_edge,
            channel_reference_hz=reference_hz,
            config=config,
            projection=projection,
            rows=all_rows,
            modes=all_modes,
            tracks=tracks,
        )

    def _blind_blocks(
        self,
        reader: ValidityAwareIqReader,
        binding: StandardPathInputBindV5,
        projection: PssProjection,
    ) -> tuple[
        tuple[tuple[object, PssBankSearchResult], ...],
        dict[int, object],
    ]:
        config = self._config
        maximum_samples = max(1, round(config.maximum_block_duration_s * binding.sample_rate_hz))
        template = pss_subband_template(
            projection.output_sample_rate_hz,
            slice_center_offset_hz=projection.slice_center_offset_hz,
        )
        minimum_output_samples = (
            math.ceil(config.timing.minimum_frame_support * projection.output_sample_rate_hz / 750)
            + template.size
            + 2 * projection.edge_trim_output_samples
        )
        minimum_input_samples = minimum_output_samples * projection.decimation_factor
        blocks = tuple(
            block
            for segment in binding.validity_inventory.segments
            for block in _continuity_blocks(
                segment_index=segment.segment_index,
                device_sample_start=segment.device_sample_start,
                sample_count=segment.observed_sample_count,
                maximum_samples=maximum_samples,
                minimum_samples=minimum_input_samples,
            )
        )
        rows: list[tuple[object, PssBankSearchResult]] = []
        projected_by_block: dict[int, object] = {}
        for block_index, (segment_index, start, count) in enumerate(blocks):
            span = reader.read_device_span(start, count)
            if span.receiver_ids != (binding.receiver_id,):
                raise ValueError("native PSS block returned a foreign receiver inventory")
            if not np.all(span.valid_samples) or not np.all(
                span.continuity_segment_ids == segment_index
            ):
                raise ValueError("native PSS block escaped its authoritative continuity segment")
            values = np.asarray(
                span.samples[:, 0, 0].astype(np.float32)
                + 1j * span.samples[:, 0, 1].astype(np.float32),
                dtype=np.complex64,
            )
            projected = project_pss_block(
                values,
                projection,
                input_device_sample_start=start,
                continuity_segment_index=segment_index,
            )
            result = search_pss_frame_timing_bank(
                projected,
                block_index=block_index,
                bank_config=config.blind_bank,
                timing_config=config.timing,
            )
            rows.append((projected, result))
            projected_by_block[block_index] = projected
        return tuple(rows), projected_by_block

    def _conditioned_blocks(
        self,
        projected_by_block: dict[int, object],
        blind_rows: tuple[tuple[object, PssBankSearchResult], ...],
        glrt: StandardNativeFullCaptureGlrt20msV2,
    ) -> tuple[tuple[object, PssBankSearchResult], ...]:
        from leo.analysis.starlink.pss_search import PssProjectedBlock

        windows = tuple(
            window
            for segment in glrt.segments
            for window in segment.windows
            if window.passed_margin_gate
            and window.global_epoch_device_sample is not None
            and window.tracking_cfo_hz is not None
        )
        if not windows:
            return ()
        glrt_by_block: dict[int, NativeFullCaptureGlrtWindowV1] = {}
        for block_index, raw_block in projected_by_block.items():
            if not isinstance(raw_block, PssProjectedBlock):
                continue
            window = _best_glrt_window(raw_block, windows)
            if window is not None:
                glrt_by_block[block_index] = window
        offsets: list[float] = []
        period_s = 1.0 / FRAME_RATE_HZ
        for _block, result in blind_rows:
            window = glrt_by_block.get(result.block_index)
            if window is None:
                continue
            epoch_sample = window.global_epoch_device_sample
            tracking_cfo_hz = window.tracking_cfo_hz
            if epoch_sample is None or tracking_cfo_hz is None:
                raise ValueError("selected native GLRT PSS target is incomplete")
            predicted_phase_s = (epoch_sample / glrt.source.sample_rate_hz) % period_s
            aligned = tuple(
                mode
                for mode in result.modes
                if _circular_distance(mode.median_frame_phase_s, predicted_phase_s, period_s)
                <= self._config.glrt_timing_radius_s
            )
            if aligned:
                best = min(
                    aligned,
                    key=lambda item: _circular_distance(
                        item.median_frame_phase_s,
                        predicted_phase_s,
                        period_s,
                    ),
                )
                offsets.append(best.nominal_frequency_offset_hz - float(tracking_cfo_hz))
        if len(offsets) < self._config.glrt_bootstrap_minimum_pairs:
            return ()
        intercept_hz = float(np.median(offsets))
        output: list[tuple[object, PssBankSearchResult]] = []
        for block_index, raw_block in sorted(projected_by_block.items()):
            if not isinstance(raw_block, PssProjectedBlock):
                raise TypeError("native PSS projected-block inventory changed type")
            window = glrt_by_block.get(block_index)
            if window is None:
                continue
            epoch_sample = window.global_epoch_device_sample
            tracking_cfo_hz = window.tracking_cfo_hz
            if epoch_sample is None or tracking_cfo_hz is None:
                raise ValueError("selected native GLRT PSS target is incomplete")
            predicted_phase_s = (epoch_sample / glrt.source.sample_rate_hz) % period_s
            target = PssSearchTarget(
                origin=PssSearchOrigin.GLRT_CONDITIONED,
                frequency_center_hz=float(tracking_cfo_hz) + intercept_hz,
                frequency_half_width_hz=self._config.glrt_frequency_half_width_hz,
                predicted_frame_phase_s=predicted_phase_s,
                frame_phase_radius_s=self._config.glrt_timing_radius_s,
                source_digest=glrt.result_digest,
            )
            output.append(
                (
                    raw_block,
                    search_pss_frame_timing_bank(
                        raw_block,
                        block_index=block_index,
                        target=target,
                        bank_config=self._config.blind_bank,
                        timing_config=self._config.timing,
                    ),
                )
            )
        return tuple(output)


def build_empty_standard_native_pss(
    binding: StandardPathInputBindV5,
    *,
    config: StandardNativePssConfig | None = None,
) -> StandardNativePssFrameTimingV1:
    """Build a deterministic empty result for isolated analyzer tests."""

    policy = config or StandardNativePssConfig()
    reference_hz = starlink_pss_channel_reference_hz(
        binding.starlink_channel,
        binding.starlink_edge,
    )
    canonical_rate = (
        policy.canonical_projection_sample_rate_hz
        if binding.sample_rate_hz % policy.canonical_projection_sample_rate_hz == 0
        else binding.sample_rate_hz
    )
    projection = compile_pss_projection(
        input_sample_rate_hz=binding.sample_rate_hz,
        input_center_frequency_hz=float(binding.tuned_center_frequency_hz),
        rf_bandwidth_hz=binding.rf_bandwidth_hz,
        target_center_frequency_hz=float(
            starlink_edge_if_center_frequency_hz(
                binding.starlink_channel,
                binding.starlink_edge,
            )
        ),
        channel_reference_hz=reference_hz,
        canonical_output_sample_rate_hz=canonical_rate,
        edge_trim_output_samples=policy.projection_edge_trim_output_samples,
    )
    return _build_contract(
        source=StandardNativeSourceV2.from_path_binding(binding),
        edge=binding.starlink_edge,
        channel_reference_hz=reference_hz,
        config=policy,
        projection=projection,
        rows=(),
        modes=(),
        tracks=(),
    )


def _continuity_blocks(
    *,
    segment_index: int,
    device_sample_start: int,
    sample_count: int,
    maximum_samples: int,
    minimum_samples: int,
) -> tuple[tuple[int, int, int], ...]:
    output: list[tuple[int, int, int]] = []
    cursor = device_sample_start
    remaining = sample_count
    while remaining >= minimum_samples:
        count = min(remaining, maximum_samples)
        trailing = remaining - count
        if 0 < trailing < minimum_samples:
            count = remaining
        output.append((segment_index, cursor, count))
        cursor += count
        remaining -= count
    return tuple(output)


def _best_glrt_window(
    block: object,
    windows: tuple[object, ...],
) -> NativeFullCaptureGlrtWindowV1 | None:
    from leo.analysis.starlink.pss_search import PssProjectedBlock

    if not isinstance(block, PssProjectedBlock):
        raise TypeError("native PSS GLRT targeting received a foreign block")
    overlapping = tuple(
        item
        for item in windows
        if isinstance(item, NativeFullCaptureGlrtWindowV1)
        and item.continuity_segment_index == block.continuity_segment_index
        and item.global_device_sample_start < block.input_device_sample_stop
        and item.global_device_sample_stop > block.input_device_sample_start
    )
    return max(
        overlapping,
        key=lambda item: (
            -math.inf if item.glrt_margin is None else item.glrt_margin,
            -item.opportunity_index,
        ),
        default=None,
    )


def _build_contract(
    *,
    source: StandardNativeSourceV2,
    edge: StarlinkEdge,
    channel_reference_hz: float,
    config: StandardNativePssConfig,
    projection: PssProjection,
    rows: tuple[tuple[object, PssBankSearchResult], ...],
    modes: tuple[PssBankMode, ...],
    tracks: tuple[PssTimingTrack, ...],
) -> StandardNativePssFrameTimingV1:
    from leo.analysis.starlink.pss_search import PssProjectedBlock

    projection_values = {
        "projection_id": projection.projection_id,
        "input_sample_rate_hz": projection.input_sample_rate_hz,
        "output_sample_rate_hz": projection.output_sample_rate_hz,
        "input_center_frequency_hz": projection.input_center_frequency_hz,
        "output_center_frequency_hz": projection.output_center_frequency_hz,
        "channel_reference_hz": projection.channel_reference_hz,
        "slice_center_offset_hz": projection.slice_center_offset_hz,
        "decimation_factor": projection.decimation_factor,
        "edge_trim_output_samples": projection.edge_trim_output_samples,
    }
    projection_contract = NativePssProjectionV1.model_validate(
        {
            **projection_values,
            "projection_digest": canonical_digest({"schema_version": 1, **projection_values}),
        }
    )
    mode_contracts = tuple(
        sorted((_mode_contract(item) for item in modes), key=lambda item: item.mode_id)
    )
    block_contracts: list[NativePssSearchBlockV1] = []
    for raw_block, result in rows:
        if not isinstance(raw_block, PssProjectedBlock):
            raise TypeError("native PSS contract builder received a foreign projected block")
        origin = NativePssSearchOriginV1(result.origin.value)
        source_digest = result.source_digest
        if origin is NativePssSearchOriginV1.GLRT_CONDITIONED and source_digest is None:
            raise ValueError("conditioned native PSS empty block lost its source digest")
        values = {
            "block_index": result.block_index,
            "continuity_segment_index": raw_block.continuity_segment_index,
            "projection_id": result.projection_id,
            "origin": origin.value,
            "source_digest": source_digest,
            "input_device_sample_start": raw_block.input_device_sample_start,
            "input_device_sample_stop": raw_block.input_device_sample_stop,
            "output_device_sample_start": raw_block.output_device_sample_start,
            "output_sample_count": len(raw_block.samples),
            "searched_frequency_offsets_hz": result.searched_frequency_offsets_hz,
            "complete_hypothesis_count": result.complete_hypothesis_count,
            "no_result_hypothesis_count": result.no_result_hypothesis_count,
            "insufficient_hypothesis_count": result.insufficient_hypothesis_count,
            "raw_mode_count": result.raw_mode_count,
            "retained_mode_ids": tuple(sorted(item.mode_id for item in result.modes)),
            "disposition": (
                NativePssBlockDispositionV1.ANALYZED_CANDIDATE.value
                if result.modes
                else (
                    NativePssBlockDispositionV1.INSUFFICIENT.value
                    if result.insufficient_hypothesis_count
                    == len(result.searched_frequency_offsets_hz)
                    else NativePssBlockDispositionV1.ANALYZED_NO_CANDIDATE.value
                )
            ),
        }
        block_contracts.append(
            NativePssSearchBlockV1.model_validate(
                {**values, "block_digest": canonical_digest({"schema_version": 1, **values})}
            )
        )
    blocks = tuple(sorted(block_contracts, key=lambda item: (item.origin.value, item.block_index)))
    track_contracts = tuple(
        sorted((_track_contract(item) for item in tracks), key=lambda item: item.track_id)
    )
    dispositions = tuple(item.disposition for item in blocks)
    accounting = NativePssAccountingV1(
        blind_block_count=sum(
            item.origin is NativePssSearchOriginV1.INDEPENDENT_BLIND for item in blocks
        ),
        conditioned_block_count=sum(
            item.origin is NativePssSearchOriginV1.GLRT_CONDITIONED for item in blocks
        ),
        candidate_block_count=dispositions.count(NativePssBlockDispositionV1.ANALYZED_CANDIDATE),
        no_candidate_block_count=dispositions.count(
            NativePssBlockDispositionV1.ANALYZED_NO_CANDIDATE
        ),
        insufficient_block_count=dispositions.count(NativePssBlockDispositionV1.INSUFFICIENT),
        raw_mode_count=sum(item.raw_mode_count for item in blocks),
        retained_mode_count=len(mode_contracts),
        track_count=len(track_contracts),
        refined_window_count=sum(item.window_count for item in mode_contracts),
        strong_window_count=sum(item.strong_window_count for item in mode_contracts),
    )
    values = {
        "schema_version": 1,
        "algorithm_version": "standard-native-pss-frame-timing-v1",
        "source": source.model_dump(mode="json"),
        "starlink_edge": edge.value,
        "channel_reference_hz": channel_reference_hz,
        "science_configuration_digest": standard_native_pss_configuration_digest(config),
        "projections": (projection_contract.model_dump(mode="json"),),
        "blocks": tuple(item.model_dump(mode="json") for item in blocks),
        "modes": tuple(item.model_dump(mode="json") for item in mode_contracts),
        "tracks": tuple(item.model_dump(mode="json") for item in track_contracts),
        "accounting": accounting.model_dump(mode="json"),
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
        "absolute_carrier_phase_resolved": False,
    }
    return StandardNativePssFrameTimingV1.model_validate(
        {**values, "result_digest": canonical_digest(values)}
    )


def _mode_contract(mode: PssBankMode) -> NativePssModeV1:
    values = {
        "mode_id": mode.mode_id,
        "block_index": mode.block_index,
        "continuity_segment_index": mode.continuity_segment_index,
        "projection_id": mode.projection_id,
        "origin": mode.origin.value,
        "source_digest": mode.source_digest,
        "center_time_s": mode.center_time_s,
        "frame_phase_s": mode.median_frame_phase_s,
        "nominal_frequency_offset_hz": mode.nominal_frequency_offset_hz,
        "selected_frequency_offset_hz": mode.candidate.frequency_offset_hz,
        "folded_score": mode.candidate.folded_score,
        "folded_median": mode.candidate.folded_median,
        "peak_to_median": mode.candidate.peak_to_median,
        "robust_z": mode.candidate.robust_z,
        "frame_support": mode.candidate.frame_support,
        "window_count": mode.window_count,
        "strong_window_count": mode.strong_window_count,
    }
    return NativePssModeV1.model_validate(
        {**values, "mode_digest": canonical_digest({"schema_version": 1, **values})}
    )


def _track_contract(track: PssTimingTrack) -> NativePssTimingTrackV1:
    values = {
        "track_id": track.track_id,
        "origin": track.origin.value,
        "mode_ids": track.mode_ids,
        "time_origin_s": track.time_origin_s,
        "coefficients_descending_s": track.coefficients_descending_s,
        "time_start_s": track.time_start_s,
        "time_stop_s": track.time_stop_s,
        "rms_residual_us": track.rms_residual_s * 1e6,
        "maximum_absolute_residual_us": track.maximum_absolute_residual_s * 1e6,
        "residuals_us": tuple(value * 1e6 for value in track.residuals_s),
    }
    return NativePssTimingTrackV1.model_validate(
        {**values, "track_digest": canonical_digest({"schema_version": 1, **values})}
    )


def _circular_distance(left: float, right: float, period: float) -> float:
    return abs((left - right + period / 2) % period - period / 2)
