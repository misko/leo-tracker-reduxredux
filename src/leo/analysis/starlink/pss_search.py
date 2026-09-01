"""Hierarchical, rate-generic acquisition around the pure PSS timing kernel.

This module deliberately knows nothing about storage, Standard products, GLRT,
or capture orchestration.  Callers supply one continuous IQ block, an explicit
spectral projection, and an explicit acquisition bank.  The returned evidence
retains whether a search was blind or externally conditioned.
"""

from __future__ import annotations

import hashlib
import itertools
import math
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import numpy.typing as npt

from leo.analysis.starlink.pss_timing import (
    PssEpochCandidate,
    PssFrameTimingResult,
    PssFrameWindow,
    PssTimingSearchConfig,
    search_pss_frame_timing,
)
from leo.analysis.starlink.templates import FRAME_RATE_HZ


class PssSearchOrigin(StrEnum):
    """Scientific provenance of one acquisition hypothesis."""

    INDEPENDENT_BLIND = "independent_blind"
    GLRT_CONDITIONED = "glrt_conditioned"


@dataclass(frozen=True, slots=True)
class PssProjection:
    """One exact native-IQ to PSS-search coordinate transform."""

    projection_id: str
    input_sample_rate_hz: int
    output_sample_rate_hz: int
    input_center_frequency_hz: float
    output_center_frequency_hz: float
    channel_reference_hz: float
    decimation_factor: int
    edge_trim_output_samples: int

    @property
    def slice_center_offset_hz(self) -> float:
        return self.output_center_frequency_hz - self.channel_reference_hz

    @property
    def input_translation_hz(self) -> float:
        return self.output_center_frequency_hz - self.input_center_frequency_hz

    def __post_init__(self) -> None:
        numerical = (
            self.input_center_frequency_hz,
            self.output_center_frequency_hz,
            self.channel_reference_hz,
        )
        if not self.projection_id or not all(math.isfinite(value) for value in numerical):
            raise ValueError("PSS projection identity and frequencies must be finite")
        integer_values = (
            self.input_sample_rate_hz,
            self.output_sample_rate_hz,
            self.decimation_factor,
            self.edge_trim_output_samples,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) for value in integer_values):
            raise TypeError("PSS projection sample geometry must be integral")
        if min(self.input_sample_rate_hz, self.output_sample_rate_hz) <= 0:
            raise ValueError("PSS projection sample rates must be positive")
        if self.decimation_factor < 1 or self.edge_trim_output_samples < 0:
            raise ValueError("PSS projection decimation and trim are invalid")
        if self.input_sample_rate_hz != self.output_sample_rate_hz * self.decimation_factor:
            raise ValueError("PSS projection sample rates do not close the decimation factor")
        if self.decimation_factor == 1 and not math.isclose(
            self.input_center_frequency_hz,
            self.output_center_frequency_hz,
            abs_tol=1e-9,
        ):
            raise ValueError("an undecimated PSS projection cannot translate the capture")


@dataclass(frozen=True, slots=True)
class PssProjectedBlock:
    """One continuous projected block with an exact native-axis mapping."""

    projection: PssProjection
    samples: npt.NDArray[np.complex64]
    continuity_segment_index: int
    input_device_sample_start: int
    input_device_sample_stop: int
    output_device_sample_start: int

    @property
    def center_time_s(self) -> float:
        return (
            (self.input_device_sample_start + self.input_device_sample_stop)
            / 2
            / self.projection.input_sample_rate_hz
        )


@dataclass(frozen=True, slots=True)
class PssBankSearchConfig:
    """Bounded coarse-to-fine CFO and mode-retention policy."""

    coarse_frequency_offsets_hz: tuple[float, ...] = tuple(
        float(value) for value in range(-1_200_000, 1_200_001, 100_000)
    )
    fine_frequency_radius_hz: float = 50_000.0
    fine_frequency_step_hz: float = 25_000.0
    mode_phase_deduplication_radius_s: float = 2.0e-6
    mode_frequency_deduplication_radius_hz: float = 75_000.0
    strong_window_peak_to_median: float = 5.0
    maximum_raw_modes: int = 256
    maximum_coarse_refinement_centers: int = 4
    minimum_coarse_refinement_robust_z: float = 4.0

    def __post_init__(self) -> None:
        values = (
            *self.coarse_frequency_offsets_hz,
            self.fine_frequency_radius_hz,
            self.fine_frequency_step_hz,
            self.mode_phase_deduplication_radius_s,
            self.mode_frequency_deduplication_radius_hz,
            self.strong_window_peak_to_median,
            self.minimum_coarse_refinement_robust_z,
        )
        if not self.coarse_frequency_offsets_hz or not all(
            math.isfinite(value) for value in values
        ):
            raise ValueError("PSS bank search values must be finite and nonempty")
        if len(set(self.coarse_frequency_offsets_hz)) != len(self.coarse_frequency_offsets_hz):
            raise ValueError("PSS coarse CFO bank must be unique")
        if self.fine_frequency_radius_hz < 0 or self.fine_frequency_step_hz <= 0:
            raise ValueError("PSS fine CFO search geometry is invalid")
        if (
            self.mode_phase_deduplication_radius_s <= 0
            or self.mode_frequency_deduplication_radius_hz < 0
        ):
            raise ValueError("PSS mode deduplication geometry is invalid")
        if (
            self.strong_window_peak_to_median <= 1
            or self.maximum_raw_modes < 1
            or self.maximum_coarse_refinement_centers < 1
            or self.minimum_coarse_refinement_robust_z <= 0
        ):
            raise ValueError("PSS bank retention policy is invalid")


@dataclass(frozen=True, slots=True)
class PssSearchTarget:
    """Optional externally compiled target passed through a narrow port."""

    origin: PssSearchOrigin
    frequency_center_hz: float | None = None
    frequency_half_width_hz: float | None = None
    predicted_frame_phase_s: float | None = None
    frame_phase_radius_s: float | None = None
    source_digest: str | None = None

    def __post_init__(self) -> None:
        optional = (
            self.frequency_center_hz,
            self.frequency_half_width_hz,
            self.predicted_frame_phase_s,
            self.frame_phase_radius_s,
        )
        if any(value is not None and not math.isfinite(value) for value in optional):
            raise ValueError("PSS target values must be finite")
        frequency_pair = (
            self.frequency_center_hz is not None,
            self.frequency_half_width_hz is not None,
        )
        timing_pair = (
            self.predicted_frame_phase_s is not None,
            self.frame_phase_radius_s is not None,
        )
        if frequency_pair[0] != frequency_pair[1] or timing_pair[0] != timing_pair[1]:
            raise ValueError("PSS target centers and radii must be supplied together")
        if self.frequency_half_width_hz is not None and self.frequency_half_width_hz < 0:
            raise ValueError("PSS target CFO radius must be nonnegative")
        if self.frame_phase_radius_s is not None and self.frame_phase_radius_s <= 0:
            raise ValueError("PSS target timing radius must be positive")
        if self.origin is PssSearchOrigin.INDEPENDENT_BLIND and self.source_digest is not None:
            raise ValueError("independent PSS search cannot carry conditioned lineage")
        if self.origin is PssSearchOrigin.GLRT_CONDITIONED and not self.source_digest:
            raise ValueError("conditioned PSS target requires an upstream source digest")


@dataclass(frozen=True, slots=True)
class PssBankMode:
    """One qualified and locally refined mode from a true CFO hypothesis."""

    mode_id: str
    block_index: int
    continuity_segment_index: int
    projection_id: str
    origin: PssSearchOrigin
    source_digest: str | None
    center_time_s: float
    nominal_frequency_offset_hz: float
    candidate: PssEpochCandidate
    median_frame_phase_s: float
    window_count: int
    strong_window_count: int
    windows: tuple[PssFrameWindow, ...]


@dataclass(frozen=True, slots=True)
class PssBankSearchResult:
    """Complete accounting for one block/projection acquisition bank."""

    block_index: int
    projection_id: str
    origin: PssSearchOrigin
    source_digest: str | None
    searched_frequency_offsets_hz: tuple[float, ...]
    complete_hypothesis_count: int
    no_result_hypothesis_count: int
    insufficient_hypothesis_count: int
    raw_mode_count: int
    modes: tuple[PssBankMode, ...]


@dataclass(frozen=True, slots=True)
class PssTimingTrack:
    """One independently associated circular-frame timing trajectory."""

    track_id: str
    origin: PssSearchOrigin
    mode_ids: tuple[str, ...]
    time_origin_s: float
    coefficients_descending_s: tuple[float, float, float]
    time_start_s: float
    time_stop_s: float
    rms_residual_s: float
    maximum_absolute_residual_s: float
    residuals_s: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class PssTrackAssociationConfig:
    minimum_block_count: int = 6
    minimum_span_s: float = 2.0
    maximum_tracks: int = 8
    phase_inlier_radius_s: float = 2.0e-6
    maximum_cfo_deviation_hz: float = 150_000.0
    maximum_seed_modes: int = 96

    def __post_init__(self) -> None:
        numeric = (
            self.minimum_span_s,
            self.phase_inlier_radius_s,
            self.maximum_cfo_deviation_hz,
        )
        if not all(math.isfinite(value) for value in numeric):
            raise ValueError("PSS association values must be finite")
        if self.minimum_block_count < 3 or self.maximum_tracks < 1 or self.maximum_seed_modes < 3:
            raise ValueError("PSS association count bounds are invalid")
        if min(numeric) <= 0:
            raise ValueError("PSS association gates must be positive")


def compile_pss_projection(
    *,
    input_sample_rate_hz: int,
    input_center_frequency_hz: float,
    rf_bandwidth_hz: int,
    target_center_frequency_hz: float,
    channel_reference_hz: float,
    canonical_output_sample_rate_hz: int = 2_500_000,
    edge_trim_output_samples: int = 64,
) -> PssProjection:
    """Compile one deterministic native or integer-decimated PSS projection."""

    integer_values = (input_sample_rate_hz, rf_bandwidth_hz, canonical_output_sample_rate_hz)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in integer_values):
        raise TypeError("PSS projection compilation requires integer sample geometry")
    if min(integer_values) <= 0:
        raise ValueError("PSS projection compilation requires positive sample geometry")
    usable_half_width = min(input_sample_rate_hz, rf_bandwidth_hz) / 2.0
    direct = input_sample_rate_hz <= canonical_output_sample_rate_hz
    if direct:
        output_rate = input_sample_rate_hz
        output_center = float(input_center_frequency_hz)
        factor = 1
        trim = 0
    else:
        if input_sample_rate_hz % canonical_output_sample_rate_hz:
            raise ValueError("PSS canonical projection requires an integral decimation factor")
        output_rate = canonical_output_sample_rate_hz
        output_center = float(target_center_frequency_hz)
        factor = input_sample_rate_hz // output_rate
        trim = edge_trim_output_samples
        lower = output_center - output_rate / 2
        upper = output_center + output_rate / 2
        available_lower = input_center_frequency_hz - usable_half_width
        available_upper = input_center_frequency_hz + usable_half_width
        if lower < available_lower or upper > available_upper:
            raise ValueError("PSS target projection is outside the usable capture passband")
    identity = (
        f"pss-projection-v1:{input_sample_rate_hz}:{output_rate}:"
        f"{input_center_frequency_hz:.9f}:{output_center:.9f}:{channel_reference_hz:.9f}"
    )
    return PssProjection(
        projection_id=f"sha256:{hashlib.sha256(identity.encode()).hexdigest()}",
        input_sample_rate_hz=input_sample_rate_hz,
        output_sample_rate_hz=output_rate,
        input_center_frequency_hz=float(input_center_frequency_hz),
        output_center_frequency_hz=output_center,
        channel_reference_hz=float(channel_reference_hz),
        decimation_factor=factor,
        edge_trim_output_samples=trim,
    )


def project_pss_block(
    samples: npt.ArrayLike,
    projection: PssProjection,
    *,
    input_device_sample_start: int,
    continuity_segment_index: int,
) -> PssProjectedBlock:
    """Translate and ideal-bandlimit one block without crossing its boundary."""

    values = np.asarray(samples, dtype=np.complex64)
    if values.ndim != 1 or not values.size or not np.all(np.isfinite(values)):
        raise ValueError("PSS projection requires finite one-dimensional complex IQ")
    if (
        isinstance(input_device_sample_start, bool)
        or not isinstance(input_device_sample_start, int)
        or input_device_sample_start < 0
        or isinstance(continuity_segment_index, bool)
        or not isinstance(continuity_segment_index, int)
        or continuity_segment_index < 0
    ):
        raise ValueError("PSS projection requires nonnegative integral device coordinates")
    factor = projection.decimation_factor
    leading = (-input_device_sample_start) % factor
    usable_count = (values.size - leading) // factor * factor
    if usable_count <= 0:
        raise ValueError("PSS projection block has no decimation-aligned IQ")
    native_start = input_device_sample_start + leading
    aligned = values[leading : leading + usable_count]
    if factor == 1:
        reduced = np.ascontiguousarray(aligned)
    else:
        absolute_samples = native_start + np.arange(usable_count, dtype=np.float64)
        translated = aligned * np.exp(
            -2j
            * np.pi
            * projection.input_translation_hz
            * absolute_samples
            / projection.input_sample_rate_hz
        )
        reduced = _fft_decimate(translated, factor)
        trim = projection.edge_trim_output_samples
        if reduced.size <= 2 * trim:
            raise ValueError("PSS projected block is shorter than its deterministic edge trim")
        reduced = reduced[trim:-trim]
        native_start += trim * factor
        usable_count -= 2 * trim * factor
    native_stop = native_start + usable_count
    return PssProjectedBlock(
        projection=projection,
        samples=np.asarray(reduced, dtype=np.complex64),
        continuity_segment_index=continuity_segment_index,
        input_device_sample_start=native_start,
        input_device_sample_stop=native_stop,
        output_device_sample_start=native_start // factor,
    )


def search_pss_frame_timing_bank(
    block: PssProjectedBlock,
    *,
    block_index: int,
    target: PssSearchTarget | None = None,
    bank_config: PssBankSearchConfig | None = None,
    timing_config: PssTimingSearchConfig | None = None,
) -> PssBankSearchResult:
    """Run true epoch acquisition at every coarse and retained fine CFO."""

    policy = bank_config or PssBankSearchConfig()
    selected_target = target or PssSearchTarget(PssSearchOrigin.INDEPENDENT_BLIND)
    sample_rate_hz = float(block.projection.output_sample_rate_hz)
    if selected_target.frequency_center_hz is None:
        coarse = policy.coarse_frequency_offsets_hz
    else:
        assert selected_target.frequency_half_width_hz is not None
        coarse = _centered_bank(
            selected_target.frequency_center_hz,
            selected_target.frequency_half_width_hz,
            policy.fine_frequency_step_hz,
        )
    hypotheses = [
        value for value in coarse if abs(value) < block.projection.output_sample_rate_hz / 2
    ]
    if not hypotheses:
        raise ValueError("PSS acquisition bank has no hypothesis inside projected Nyquist")
    results: dict[float, tuple[PssFrameTimingResult, tuple[PssBankMode, ...]]] = {}
    for frequency_offset_hz in hypotheses:
        result = search_pss_frame_timing(
            block.samples,
            sample_rate_hz,
            global_device_sample_start=block.output_device_sample_start,
            continuity_segment_index=block.continuity_segment_index,
            slice_center_offset_hz=block.projection.slice_center_offset_hz,
            nominal_frequency_offset_hz=frequency_offset_hz,
            frequency_offsets_hz=(frequency_offset_hz,),
            config=timing_config,
        )
        modes = _result_modes(
            result,
            block=block,
            block_index=block_index,
            origin=selected_target.origin,
            source_digest=selected_target.source_digest,
            strong_window_threshold=policy.strong_window_peak_to_median,
            predicted_frame_phase_s=selected_target.predicted_frame_phase_s,
            frame_phase_radius_s=selected_target.frame_phase_radius_s,
        )
        results[frequency_offset_hz] = result, modes

    refinement_centers = tuple(
        frequency
        for score, frequency in sorted(
            (
                (
                    max(
                        (candidate.robust_z for candidate in result.candidates),
                        default=-math.inf,
                    ),
                    frequency,
                )
                for frequency, (result, _modes) in results.items()
            ),
            key=lambda item: (-item[0], item[1]),
        )[: policy.maximum_coarse_refinement_centers]
        if score >= policy.minimum_coarse_refinement_robust_z
    )
    if selected_target.frequency_center_hz is None and policy.fine_frequency_radius_hz:
        fine = sorted(
            {
                candidate
                for center in refinement_centers
                for candidate in _centered_bank(
                    center,
                    policy.fine_frequency_radius_hz,
                    policy.fine_frequency_step_hz,
                )
                if abs(candidate) < block.projection.output_sample_rate_hz / 2
            }
            - set(results)
        )
        for frequency_offset_hz in fine:
            result = search_pss_frame_timing(
                block.samples,
                sample_rate_hz,
                global_device_sample_start=block.output_device_sample_start,
                continuity_segment_index=block.continuity_segment_index,
                slice_center_offset_hz=block.projection.slice_center_offset_hz,
                nominal_frequency_offset_hz=frequency_offset_hz,
                frequency_offsets_hz=(frequency_offset_hz,),
                config=timing_config,
            )
            results[frequency_offset_hz] = (
                result,
                _result_modes(
                    result,
                    block=block,
                    block_index=block_index,
                    origin=selected_target.origin,
                    source_digest=selected_target.source_digest,
                    strong_window_threshold=policy.strong_window_peak_to_median,
                    predicted_frame_phase_s=selected_target.predicted_frame_phase_s,
                    frame_phase_radius_s=selected_target.frame_phase_radius_s,
                ),
            )

    raw_modes = tuple(mode for _result, modes in results.values() for mode in modes)
    if len(raw_modes) > policy.maximum_raw_modes:
        raw_modes = tuple(
            sorted(raw_modes, key=lambda item: (-item.candidate.robust_z, item.mode_id))[
                : policy.maximum_raw_modes
            ]
        )
    modes = _deduplicate_modes(raw_modes, sample_rate_hz=sample_rate_hz, config=policy)
    status_values = tuple(str(result.status) for result, _modes in results.values())
    return PssBankSearchResult(
        block_index=block_index,
        projection_id=block.projection.projection_id,
        origin=selected_target.origin,
        source_digest=selected_target.source_digest,
        searched_frequency_offsets_hz=tuple(sorted(results)),
        complete_hypothesis_count=status_values.count("complete"),
        no_result_hypothesis_count=status_values.count("no_result"),
        insufficient_hypothesis_count=status_values.count("insufficient"),
        raw_mode_count=len(raw_modes),
        modes=modes,
    )


def associate_pss_timing_tracks(
    modes: tuple[PssBankMode, ...],
    *,
    config: PssTrackAssociationConfig | None = None,
) -> tuple[PssTimingTrack, ...]:
    """Associate circular frame phases without using GLRT or another receiver."""

    policy = config or PssTrackAssociationConfig()
    remaining = list(modes)
    tracks: list[PssTimingTrack] = []
    while len(remaining) >= policy.minimum_block_count and len(tracks) < policy.maximum_tracks:
        selected = _best_track_modes(tuple(remaining), policy)
        if len(selected) < policy.minimum_block_count:
            break
        track = _fit_track(selected)
        if (
            track.time_stop_s - track.time_start_s < policy.minimum_span_s
            or track.maximum_absolute_residual_s > policy.phase_inlier_radius_s
        ):
            break
        tracks.append(track)
        selected_ids = set(track.mode_ids)
        remaining = [item for item in remaining if item.mode_id not in selected_ids]
    return tuple(tracks)


def _fft_decimate(values: npt.NDArray[np.complex64], factor: int) -> npt.NDArray[np.complex64]:
    output_count = values.size // factor
    spectrum = np.fft.fftshift(np.fft.fft(values))
    first = (values.size - output_count) // 2
    selected = spectrum[first : first + output_count]
    reduced = np.fft.ifft(np.fft.ifftshift(selected)) * output_count / values.size
    return np.asarray(reduced, dtype=np.complex64)


def _centered_bank(center_hz: float, radius_hz: float, step_hz: float) -> tuple[float, ...]:
    step_count = math.floor(radius_hz / step_hz + 1e-12)
    return tuple(float(center_hz + index * step_hz) for index in range(-step_count, step_count + 1))


def _result_modes(
    result: object,
    *,
    block: PssProjectedBlock,
    block_index: int,
    origin: PssSearchOrigin,
    source_digest: str | None,
    strong_window_threshold: float,
    predicted_frame_phase_s: float | None,
    frame_phase_radius_s: float | None,
) -> tuple[PssBankMode, ...]:
    from leo.analysis.starlink.pss_timing import PssFrameTimingResult

    if not isinstance(result, PssFrameTimingResult):
        raise TypeError("PSS bank received a foreign timing result")
    output: list[PssBankMode] = []
    period_s = 1.0 / FRAME_RATE_HZ
    for candidate in result.qualified_candidates:
        windows = tuple(
            item for item in result.windows if item.candidate_index == candidate.candidate_index
        )
        strong = tuple(
            item for item in windows if item.peak_to_local_median >= strong_window_threshold
        )
        selected = strong or windows
        if not selected:
            continue
        phases_s = np.asarray(
            [item.frame_phase_samples / result.sample_rate_hz for item in selected],
            dtype=float,
        )
        median_phase_s = float(np.median(phases_s)) % period_s
        if predicted_frame_phase_s is not None:
            assert frame_phase_radius_s is not None
            if _circular_distance(median_phase_s, predicted_frame_phase_s, period_s) > (
                frame_phase_radius_s
            ):
                continue
        identity = (
            f"pss-bank-mode-v1:{block.projection.projection_id}:{block_index}:"
            f"{origin.value}:{candidate.frequency_offset_hz:.9f}:{median_phase_s:.15f}:"
            f"{candidate.global_epoch_device_sample}"
        )
        output.append(
            PssBankMode(
                mode_id=f"sha256:{hashlib.sha256(identity.encode()).hexdigest()}",
                block_index=block_index,
                continuity_segment_index=block.continuity_segment_index,
                projection_id=block.projection.projection_id,
                origin=origin,
                source_digest=source_digest,
                center_time_s=block.center_time_s,
                nominal_frequency_offset_hz=candidate.frequency_offset_hz,
                candidate=candidate,
                median_frame_phase_s=median_phase_s,
                window_count=len(windows),
                strong_window_count=len(strong),
                windows=windows,
            )
        )
    return tuple(output)


def _deduplicate_modes(
    modes: tuple[PssBankMode, ...],
    *,
    sample_rate_hz: float,
    config: PssBankSearchConfig,
) -> tuple[PssBankMode, ...]:
    del sample_rate_hz
    period_s = 1.0 / FRAME_RATE_HZ
    retained: list[PssBankMode] = []
    for mode in sorted(
        modes,
        key=lambda item: (
            -item.candidate.robust_z,
            -item.candidate.peak_to_median,
            item.nominal_frequency_offset_hz,
            item.mode_id,
        ),
    ):
        duplicate = any(
            _circular_distance(
                mode.median_frame_phase_s,
                existing.median_frame_phase_s,
                period_s,
            )
            <= config.mode_phase_deduplication_radius_s
            and abs(mode.nominal_frequency_offset_hz - existing.nominal_frequency_offset_hz)
            <= config.mode_frequency_deduplication_radius_hz
            for existing in retained
        )
        if not duplicate:
            retained.append(mode)
    return tuple(sorted(retained, key=lambda item: (item.median_frame_phase_s, item.mode_id)))


def _best_track_modes(
    modes: tuple[PssBankMode, ...],
    config: PssTrackAssociationConfig,
) -> tuple[PssBankMode, ...]:
    candidates = tuple(
        sorted(modes, key=lambda item: (-item.candidate.robust_z, item.mode_id))[
            : config.maximum_seed_modes
        ]
    )
    period_s = 1.0 / FRAME_RATE_HZ
    best: tuple[PssBankMode, ...] = ()
    best_key = (0, 0.0, -math.inf)
    for seed in itertools.combinations(candidates, 3):
        if len({item.block_index for item in seed}) < 3:
            continue
        ordered = tuple(sorted(seed, key=lambda item: item.center_time_s))
        times = np.asarray([item.center_time_s for item in ordered])
        if times[-1] - times[0] < config.minimum_span_s:
            continue
        phases = np.asarray([item.median_frame_phase_s for item in ordered])
        unwrapped = np.unwrap(phases / period_s * 2 * np.pi) * period_s / (2 * np.pi)
        coefficients = np.polyfit(times - times.mean(), unwrapped, 2)
        predicted = np.polyval(
            coefficients, np.asarray([item.center_time_s for item in modes]) - times.mean()
        )
        by_block: dict[int, tuple[float, PssBankMode]] = {}
        cfo_center = float(np.median([item.nominal_frequency_offset_hz for item in ordered]))
        for item, prediction in zip(modes, predicted, strict=True):
            if abs(item.nominal_frequency_offset_hz - cfo_center) > config.maximum_cfo_deviation_hz:
                continue
            residual = _circular_residual(item.median_frame_phase_s, float(prediction), period_s)
            if abs(residual) > config.phase_inlier_radius_s:
                continue
            previous = by_block.get(item.block_index)
            if previous is None or (abs(residual), item.mode_id) < (
                abs(previous[0]),
                previous[1].mode_id,
            ):
                by_block[item.block_index] = residual, item
        selected = tuple(
            sorted((value[1] for value in by_block.values()), key=lambda item: item.center_time_s)
        )
        if not selected:
            continue
        span = selected[-1].center_time_s - selected[0].center_time_s
        rms = math.sqrt(sum(value[0] ** 2 for value in by_block.values()) / len(by_block))
        key = (len(selected), span, -rms)
        if key > best_key:
            best_key = key
            best = selected
    return best


def _fit_track(modes: tuple[PssBankMode, ...]) -> PssTimingTrack:
    ordered = tuple(sorted(modes, key=lambda item: item.center_time_s))
    times = np.asarray([item.center_time_s for item in ordered])
    phases = np.asarray([item.median_frame_phase_s for item in ordered])
    period_s = 1.0 / FRAME_RATE_HZ
    unwrapped = np.unwrap(phases / period_s * 2 * np.pi) * period_s / (2 * np.pi)
    origin = float(times.mean())
    coefficients = np.polyfit(times - origin, unwrapped, 2)
    fitted = np.polyval(coefficients, times - origin)
    residuals = np.asarray(
        [
            _circular_residual(value, prediction, period_s)
            for value, prediction in zip(phases, fitted, strict=True)
        ]
    )
    identity = "pss-track-v1:" + ":".join(item.mode_id for item in ordered)
    return PssTimingTrack(
        track_id=f"sha256:{hashlib.sha256(identity.encode()).hexdigest()}",
        origin=ordered[0].origin,
        mode_ids=tuple(item.mode_id for item in ordered),
        time_origin_s=origin,
        coefficients_descending_s=(
            float(coefficients[0]),
            float(coefficients[1]),
            float(coefficients[2]),
        ),
        time_start_s=float(times[0]),
        time_stop_s=float(times[-1]),
        rms_residual_s=float(np.sqrt(np.mean(residuals**2))),
        maximum_absolute_residual_s=float(np.max(np.abs(residuals))),
        residuals_s=tuple(float(value) for value in residuals),
    )


def _circular_distance(left: float, right: float, period: float) -> float:
    return abs(_circular_residual(left, right, period))


def _circular_residual(observed: float, predicted: float, period: float) -> float:
    return (observed - predicted + period / 2) % period - period / 2
