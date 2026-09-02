"""Validity-safe PSS acquisition for the existing Standard-native path stage."""

from __future__ import annotations

import concurrent.futures
import math
from dataclasses import asdict, dataclass, field

import numpy as np

from leo.analysis.standard.native_runner import validate_standard_native_source
from leo.analysis.starlink.pss_search import (
    PssBankMode,
    PssBankSearchConfig,
    PssBankSearchResult,
    PssProjectedBlock,
    PssProjection,
    PssSearchOrigin,
    PssSearchTarget,
    PssTimingTrack,
    PssTrackAssociationConfig,
    associate_pss_timing_tracks,
    compile_pss_projection,
    fit_pss_timing_track,
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
_MAX_DEVICE_READ_SAMPLES = 1_048_576


def _production_blind_anchor_bank() -> PssBankSearchConfig:
    """Return the bounded PSS-only acquisition bank used at native rate."""

    return PssBankSearchConfig(
        coarse_frequency_offsets_hz=tuple(
            float(value) for value in range(-1_200_000, 1_200_001, 200_000)
        ),
        fine_frequency_radius_hz=0.0,
    )


def _production_tracking_bank() -> PssBankSearchConfig:
    """Return the three-hypothesis bank used after a PSS-only lock."""

    return PssBankSearchConfig(
        coarse_frequency_offsets_hz=(0.0,),
        fine_frequency_radius_hz=0.0,
        fine_frequency_step_hz=100_000.0,
    )


@dataclass(frozen=True, slots=True)
class StandardNativePssConfig:
    """Release-bound PSS policy shared by every reviewed native rate."""

    maximum_block_duration_s: float = 0.125
    block_overlap_duration_s: float = 0.0625
    maximum_input_block_samples: int = 4_194_304
    canonical_projection_sample_rate_hz: int = 25_000_000
    projection_edge_trim_output_samples: int = 64
    timing: PssTimingSearchConfig = field(default_factory=PssTimingSearchConfig)
    blind_bank: PssBankSearchConfig = field(default_factory=_production_blind_anchor_bank)
    tracking_bank: PssBankSearchConfig = field(default_factory=_production_tracking_bank)
    association: PssTrackAssociationConfig = field(default_factory=PssTrackAssociationConfig)
    blind_anchor_stride_s: float = 0.5
    tracking_frequency_half_width_hz: float = 100_000.0
    maximum_parallel_searches: int = 8
    maximum_refined_tracks: int = 1
    glrt_conditioning_enabled: bool = False
    glrt_bootstrap_minimum_pairs: int = 3
    glrt_timing_radius_s: float = 2.0e-6
    glrt_frequency_half_width_hz: float = 75_000.0

    def __post_init__(self) -> None:
        numerical = (
            self.maximum_block_duration_s,
            self.blind_anchor_stride_s,
            self.tracking_frequency_half_width_hz,
            self.glrt_timing_radius_s,
            self.glrt_frequency_half_width_hz,
        )
        if not all(math.isfinite(value) and value > 0 for value in numerical):
            raise ValueError("native PSS search bounds must be finite and positive")
        if (
            not math.isfinite(self.block_overlap_duration_s)
            or not 0 <= self.block_overlap_duration_s < self.maximum_block_duration_s
        ):
            raise ValueError("native PSS block overlap must be finite and shorter than a block")
        if (
            self.canonical_projection_sample_rate_hz <= 0
            or self.maximum_input_block_samples <= 0
            or self.projection_edge_trim_output_samples < 0
            or not 1 <= self.maximum_parallel_searches <= 16
            or not 1 <= self.maximum_refined_tracks <= self.association.maximum_tracks
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
        full_capture_glrt: StandardNativeFullCaptureGlrt20msV2 | None = None,
    ) -> StandardNativePssFrameTimingV1:
        validate_standard_native_source(reader, binding)
        source = StandardNativeSourceV2.from_path_binding(binding)
        if full_capture_glrt is not None and full_capture_glrt.source != source:
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
        blind_rows, projected_by_block, independent_tracks = self._blind_blocks(
            reader,
            binding,
            projection,
        )
        conditioned_rows: tuple[tuple[object, PssBankSearchResult], ...] = ()
        if config.glrt_conditioning_enabled and full_capture_glrt is not None:
            conditioned_rows = self._conditioned_blocks(
                projected_by_block,
                blind_rows,
                full_capture_glrt,
            )
        all_rows = (*blind_rows, *conditioned_rows)
        all_modes = tuple(mode for _block, result in all_rows for mode in result.modes)
        conditioned_tracks = tuple(
            track
            for track in associate_pss_timing_tracks(
                tuple(
                    mode for mode in all_modes if mode.origin is PssSearchOrigin.GLRT_CONDITIONED
                ),
                config=config.association,
            )
        )
        tracks = (*independent_tracks, *conditioned_tracks)
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
        tuple[PssTimingTrack, ...],
    ]:
        config = self._config
        maximum_samples = min(
            config.maximum_input_block_samples,
            max(1, round(config.maximum_block_duration_s * binding.sample_rate_hz)),
        )
        stride_samples = max(
            1,
            round(
                (config.maximum_block_duration_s - config.block_overlap_duration_s)
                * binding.sample_rate_hz
            ),
        )
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
                stride_samples=stride_samples,
                minimum_samples=minimum_input_samples,
            )
        )
        anchor_stride_samples = round(config.blind_anchor_stride_s * binding.sample_rate_hz)
        anchors: list[tuple[int, tuple[int, int, int], PssSearchTarget | None]] = []
        last_anchor_by_segment: dict[int, int] = {}
        for block_index, block in enumerate(blocks):
            segment_index, start, _count = block
            previous = last_anchor_by_segment.get(segment_index)
            if previous is None or start - previous >= anchor_stride_samples:
                anchors.append((block_index, block, None))
                last_anchor_by_segment[segment_index] = start
        anchor_rows = self._search_blocks(
            reader,
            binding,
            projection,
            tuple(anchors),
            bank=config.blind_bank,
        )
        anchor_modes = tuple(mode for _block, result in anchor_rows for mode in result.modes)
        anchor_tracks = associate_pss_timing_tracks(anchor_modes, config=config.association)
        if not anchor_tracks:
            return (
                anchor_rows,
                {result.block_index: block for block, result in anchor_rows},
                (),
            )

        modes_by_id = {item.mode_id: item for item in anchor_modes}
        period_s = 1.0 / FRAME_RATE_HZ
        refined_rows: list[tuple[object, PssBankSearchResult]] = []
        refined_tracks: list[PssTimingTrack] = []
        selected_tracks = tuple(
            sorted(
                anchor_tracks,
                key=lambda item: (
                    -len(item.mode_ids),
                    -(item.time_stop_s - item.time_start_s),
                    item.rms_residual_s,
                    item.track_id,
                ),
            )[: config.maximum_refined_tracks]
        )
        for track_ordinal, track in enumerate(selected_tracks, start=1):
            source_modes = tuple(modes_by_id[item] for item in track.mode_ids)
            frequency_center_hz = float(
                np.median([item.nominal_frequency_offset_hz for item in source_modes])
            )
            requests: list[tuple[int, tuple[int, int, int], PssSearchTarget | None]] = []
            for block_index, block in enumerate(blocks):
                _segment_index, start, count = block
                center_time_s = (start + count / 2) / binding.sample_rate_hz
                if not track.time_start_s <= center_time_s <= track.time_stop_s:
                    continue
                predicted_phase_s = (
                    float(
                        np.polyval(
                            track.coefficients_descending_s,
                            center_time_s - track.time_origin_s,
                        )
                    )
                    % period_s
                )
                requests.append(
                    (
                        track_ordinal * len(blocks) + block_index,
                        block,
                        PssSearchTarget(
                            origin=PssSearchOrigin.INDEPENDENT_BLIND,
                            frequency_center_hz=frequency_center_hz,
                            frequency_half_width_hz=config.tracking_frequency_half_width_hz,
                            predicted_frame_phase_s=predicted_phase_s,
                            frame_phase_radius_s=config.association.phase_inlier_radius_s,
                        ),
                    )
                )
            track_rows = self._search_blocks(
                reader,
                binding,
                projection,
                tuple(requests),
                bank=config.tracking_bank,
            )
            refined_rows.extend(track_rows)
            selected_modes: list[PssBankMode] = []
            for _raw_block, result in track_rows:
                if not result.modes:
                    continue
                selected_modes.append(
                    max(
                        result.modes,
                        key=lambda item: (
                            item.candidate.robust_z,
                            item.candidate.peak_to_median,
                            -abs(item.nominal_frequency_offset_hz - frequency_center_hz),
                            item.mode_id,
                        ),
                    )
                )
            if len(selected_modes) < config.association.minimum_block_count:
                continue
            refined = fit_pss_timing_track(tuple(selected_modes))
            if (
                refined.time_stop_s - refined.time_start_s >= config.association.minimum_span_s
                and refined.maximum_absolute_residual_s <= config.association.phase_inlier_radius_s
            ):
                refined_tracks.append(refined)

        rows = (*anchor_rows, *refined_rows)
        projected_by_block = {result.block_index: block for block, result in anchor_rows}
        tracks = (*refined_tracks, *anchor_tracks) if refined_tracks else anchor_tracks
        return rows, projected_by_block, tracks

    def _search_blocks(
        self,
        reader: ValidityAwareIqReader,
        binding: StandardPathInputBindV5,
        projection: PssProjection,
        requests: tuple[
            tuple[int, tuple[int, int, int], PssSearchTarget | None],
            ...,
        ],
        *,
        bank: PssBankSearchConfig,
    ) -> tuple[tuple[object, PssBankSearchResult], ...]:
        """Read serially and search a bounded number of blocks concurrently."""

        if not requests:
            return ()
        results: dict[int, tuple[object, PssBankSearchResult]] = {}
        pending: dict[concurrent.futures.Future[PssBankSearchResult], object] = {}
        previous_projected: PssProjectedBlock | None = None
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self._config.maximum_parallel_searches,
            thread_name_prefix="native-pss",
        ) as executor:
            for block_index, (segment_index, start, count), target in requests:
                projected = self._read_projected_continuation(
                    reader,
                    binding,
                    projection,
                    segment_index=segment_index,
                    start=start,
                    count=count,
                    previous=previous_projected,
                )
                previous_projected = projected
                future = executor.submit(
                    search_pss_frame_timing_bank,
                    projected,
                    block_index=block_index,
                    target=target,
                    bank_config=bank,
                    timing_config=self._config.timing,
                )
                pending[future] = projected
                if len(pending) >= self._config.maximum_parallel_searches:
                    self._collect_completed_searches(pending, results, wait_for_one=True)
            while pending:
                self._collect_completed_searches(pending, results, wait_for_one=True)
        return tuple(results[index] for index in sorted(results))

    @staticmethod
    def _collect_completed_searches(
        pending: dict[concurrent.futures.Future[PssBankSearchResult], object],
        results: dict[int, tuple[object, PssBankSearchResult]],
        *,
        wait_for_one: bool,
    ) -> None:
        return_when = (
            concurrent.futures.FIRST_COMPLETED if wait_for_one else concurrent.futures.ALL_COMPLETED
        )
        completed, _ = concurrent.futures.wait(tuple(pending), return_when=return_when)
        for future in completed:
            projected = pending.pop(future)
            result = future.result()
            results[result.block_index] = projected, result

    @staticmethod
    def _read_projected_continuation(
        reader: ValidityAwareIqReader,
        binding: StandardPathInputBindV5,
        projection: PssProjection,
        *,
        segment_index: int,
        start: int,
        count: int,
        previous: PssProjectedBlock | None,
    ) -> PssProjectedBlock:
        overlap = 0
        if (
            previous is not None
            and projection.decimation_factor == 1
            and previous.continuity_segment_index == segment_index
            and previous.input_device_sample_start < start < previous.input_device_sample_stop
            and start + count > previous.input_device_sample_stop
        ):
            overlap = previous.input_device_sample_stop - start
        read_start = start + overlap
        read_count = count - overlap
        chunks: list[np.ndarray] = []
        cursor = read_start
        remaining = read_count
        while remaining:
            chunk_count = min(remaining, _MAX_DEVICE_READ_SAMPLES)
            span = reader.read_device_span(cursor, chunk_count)
            if (
                span.device_sample_start != cursor
                or span.sample_count != chunk_count
                or span.receiver_ids != (binding.receiver_id,)
            ):
                raise ValueError("native PSS block returned a foreign device-axis span")
            if not np.all(span.valid_samples) or not np.all(
                span.continuity_segment_ids == segment_index
            ):
                raise ValueError("native PSS block escaped its authoritative continuity segment")
            chunks.append(
                np.asarray(
                    span.samples[:, 0, 0].astype(np.float32)
                    + 1j * span.samples[:, 0, 1].astype(np.float32),
                    dtype=np.complex64,
                )
            )
            cursor += chunk_count
            remaining -= chunk_count
        new_values = (
            chunks[0]
            if len(chunks) == 1
            else np.concatenate(chunks).astype(np.complex64, copy=False)
        )
        if overlap:
            assert previous is not None
            values = np.concatenate(
                (
                    previous.samples[-overlap:],
                    new_values,
                )
            ).astype(np.complex64, copy=False)
        else:
            values = new_values
        return project_pss_block(
            values,
            projection,
            input_device_sample_start=start,
            continuity_segment_index=segment_index,
        )

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
    stride_samples: int,
    minimum_samples: int,
) -> tuple[tuple[int, int, int], ...]:
    """Place only complete overlapping windows inside one continuity segment."""

    if maximum_samples < minimum_samples or minimum_samples <= 0:
        raise ValueError("PSS continuity block bounds are invalid")
    if not 0 < stride_samples <= maximum_samples:
        raise ValueError("native PSS block stride must be in (0, block size]")
    if sample_count < maximum_samples:
        return ()
    block_count = 1 + (sample_count - maximum_samples) // stride_samples
    return tuple(
        (
            segment_index,
            device_sample_start + block_index * stride_samples,
            maximum_samples,
        )
        for block_index in range(block_count)
    )


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
