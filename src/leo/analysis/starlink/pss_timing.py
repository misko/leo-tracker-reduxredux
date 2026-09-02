"""Rate-generic, infrastructure-blind Starlink PSS frame-timing search.

The published PSS construction is independently ported from Humphreys et al.,
IEEE TAES 2023, equations 35--37.  Reference repositories are numerical
oracles only and are never imported at runtime.

The search is deliberately candidate-only.  A strong folded PSS maximum is a
frame-timing hypothesis, not payload evidence, a satellite identity, or an
absolute carrier-phase measurement.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import numpy.typing as npt

from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.templates import FRAME_RATE_HZ

PSS_HEX_V1 = "C1B5D191024D3DC3F8EC52FAA16F3958"
PSS_NATIVE_SAMPLE_RATE_HZ = 240_000_000.0
PSS_NATIVE_SAMPLE_COUNT = 1056
PSS_NATIVE_TEMPLATE_SHA256 = "e950ec78f60f8d9d9f0f6d98fc9f17ae77ebed9ef224df38efe9545c8d5a21f7"
_PSS_RESAMPLE_LOBES = 10.0


@dataclass(frozen=True, slots=True)
class PssTimingSearchConfig:
    """Declared acquisition and per-frame timing policy."""

    minimum_frame_support: int = 4
    minimum_epoch_peak_to_median: float = 1.15
    minimum_epoch_robust_z: float = 6.0
    maximum_epoch_candidates: int = 8
    candidate_separation_symbols: float = 2.0
    local_search_radius_s: float = 2.0e-6
    fft_output_block_samples: int = 262_144

    def __post_init__(self) -> None:
        finite = (
            self.minimum_epoch_peak_to_median,
            self.minimum_epoch_robust_z,
            self.candidate_separation_symbols,
            self.local_search_radius_s,
        )
        if not all(math.isfinite(value) for value in finite):
            raise ValueError("PSS timing configuration values must be finite")
        if self.minimum_frame_support < 2:
            raise ValueError("PSS timing search requires at least two frames")
        if self.minimum_epoch_peak_to_median <= 1.0:
            raise ValueError("PSS epoch peak-to-median threshold must exceed one")
        if self.minimum_epoch_robust_z <= 0:
            raise ValueError("PSS epoch robust-z threshold must be positive")
        if self.maximum_epoch_candidates < 1:
            raise ValueError("PSS timing search requires at least one epoch candidate")
        if self.candidate_separation_symbols < 1.0:
            raise ValueError("PSS candidates must be separated by at least one symbol")
        if self.local_search_radius_s < 0:
            raise ValueError("PSS local search radius must be nonnegative")
        if self.fft_output_block_samples < 1024:
            raise ValueError("PSS FFT output blocks must contain at least 1024 samples")


@dataclass(frozen=True, slots=True)
class PssEpochCandidate:
    """One separated folded PSS timing mode."""

    candidate_index: int
    epoch_sample: int
    global_epoch_device_sample: int
    frame_phase_samples: float
    frequency_offset_hz: float
    folded_score: float
    folded_median: float
    peak_to_median: float
    robust_z: float
    frame_support: int
    qualified: bool


@dataclass(frozen=True, slots=True)
class PssFrameWindow:
    """One locally refined PSS opportunity on an accepted frame lattice."""

    candidate_index: int
    frame_index: int
    predicted_local_sample: int
    measured_local_sample: int
    global_device_sample: int
    fractional_global_device_sample: float
    fractional_timing_offset_samples: float
    frame_phase_samples: float
    frame_phase_cycles: float
    frequency_offset_hz: float
    normalized_match_power: float
    peak_to_local_median: float
    correlation_phase_cycles: float
    local_search_start_sample: int
    local_search_stop_sample: int


@dataclass(frozen=True, slots=True)
class PssFrameTimingResult:
    """Candidate-only PSS timing evidence for one continuity-safe IQ block."""

    status: NumericalStatus
    sample_rate_hz: float
    sample_count: int
    global_device_sample_start: int
    continuity_segment_index: int
    slice_center_offset_hz: float
    nominal_frequency_offset_hz: float
    searched_frequency_offsets_hz: tuple[float, ...]
    frame_period_samples: float
    template_sample_count: int
    template_sha256: str
    candidates: tuple[PssEpochCandidate, ...]
    windows: tuple[PssFrameWindow, ...]
    reason: str
    candidate_only: bool = True
    absolute_carrier_phase_resolved: bool = False

    @property
    def qualified_candidates(self) -> tuple[PssEpochCandidate, ...]:
        return tuple(candidate for candidate in self.candidates if candidate.qualified)


def pss_native_time_samples() -> npt.NDArray[np.complex64]:
    """Return the exact 1056 published PSS samples at 240 MS/s."""

    encoded = int(PSS_HEX_V1, 16)
    output = np.empty(PSS_NATIVE_SAMPLE_COUNT, dtype=np.complex64)
    for output_index, k in enumerate(range(-32, 1024)):
        position = k % 128
        cumulative = sum(2 * ((encoded >> bit) & 1) - 1 for bit in range(position + 1))
        phase_pi = (1.0 if k < 128 else 0.0) - 0.25 - 0.5 * cumulative
        output[output_index] = np.exp(1j * np.pi * phase_pi)
    digest = hashlib.sha256(np.asarray(output, dtype="<c8").tobytes(order="C")).hexdigest()
    if digest != PSS_NATIVE_TEMPLATE_SHA256:
        raise RuntimeError("published PSS construction changed unexpectedly")
    output.flags.writeable = False
    return output


@lru_cache(maxsize=64)
def _cached_pss_subband_template(
    sample_rate_hz: float,
    slice_center_offset_hz: float,
) -> npt.NDArray[np.complex64]:
    if not math.isfinite(sample_rate_hz) or not 0 < sample_rate_hz <= PSS_NATIVE_SAMPLE_RATE_HZ:
        raise ValueError("PSS sample rate must be finite and in (0, 240 MHz]")
    if not math.isfinite(slice_center_offset_hz):
        raise ValueError("PSS slice-center offset must be finite")
    if abs(slice_center_offset_hz) + sample_rate_hz / 2 > PSS_NATIVE_SAMPLE_RATE_HZ / 2:
        raise ValueError("PSS sampled passband lies outside the native 240 MHz channel")

    native = np.asarray(pss_native_time_samples(), dtype=np.complex128)
    native_time_s = np.arange(native.size, dtype=float) / PSS_NATIVE_SAMPLE_RATE_HZ
    translated = native * np.exp(-2j * np.pi * slice_center_offset_hz * native_time_s)

    ratio = sample_rate_hz / PSS_NATIVE_SAMPLE_RATE_HZ
    output_count = int(math.ceil(native.size * ratio - 1e-12))
    output_positions = np.arange(output_count, dtype=float) / ratio
    source_positions = np.arange(native.size, dtype=float)
    distance = output_positions[:, None] - source_positions[None, :]
    scaled = ratio * distance
    inside = np.abs(scaled) < _PSS_RESAMPLE_LOBES
    window = np.zeros_like(scaled)
    window[inside] = 0.5 * (1.0 + np.cos(np.pi * scaled[inside] / _PSS_RESAMPLE_LOBES))
    weights = ratio * np.sinc(scaled) * window
    output = np.asarray(weights @ translated, dtype=np.complex64)
    norm = float(np.linalg.norm(output))
    if not math.isfinite(norm) or norm <= 0:
        raise ValueError("PSS subband projection has no finite energy")
    output /= norm
    output.flags.writeable = False
    return output


def pss_subband_template(
    sample_rate_hz: float,
    *,
    slice_center_offset_hz: float,
) -> npt.NDArray[np.complex64]:
    """Return the unit-energy PSS projection visible in one complex passband."""

    return _cached_pss_subband_template(float(sample_rate_hz), float(slice_center_offset_hz)).copy()


def search_pss_frame_timing(
    samples: npt.ArrayLike,
    sample_rate_hz: float,
    *,
    global_device_sample_start: int,
    continuity_segment_index: int,
    slice_center_offset_hz: float,
    nominal_frequency_offset_hz: float,
    frequency_offsets_hz: tuple[float, ...] | None = None,
    config: PssTimingSearchConfig | None = None,
) -> PssFrameTimingResult:
    """Search one continuous IQ block and refine every accepted PSS frame.

    ``frequency_offsets_hz`` is an explicit receiver-relative bank used only
    after the blind epoch search.  The blind pass uses
    ``nominal_frequency_offset_hz`` so runtime scales with IQ length rather
    than with the number of supplied CFO hypotheses.
    """

    values = np.asarray(samples, dtype=np.complex64)
    policy = config or PssTimingSearchConfig()
    _validate_search_inputs(
        values,
        sample_rate_hz=sample_rate_hz,
        global_device_sample_start=global_device_sample_start,
        continuity_segment_index=continuity_segment_index,
        nominal_frequency_offset_hz=nominal_frequency_offset_hz,
    )
    offsets = _frequency_offsets(
        sample_rate_hz,
        nominal_frequency_offset_hz=nominal_frequency_offset_hz,
        frequency_offsets_hz=frequency_offsets_hz,
    )
    template = pss_subband_template(
        sample_rate_hz,
        slice_center_offset_hz=slice_center_offset_hz,
    )
    frame_period = sample_rate_hz / FRAME_RATE_HZ
    minimum_samples = math.ceil(policy.minimum_frame_support * frame_period) + len(template)
    template_digest = hashlib.sha256(
        np.asarray(template, dtype="<c8").tobytes(order="C")
    ).hexdigest()
    if values.size < minimum_samples:
        return PssFrameTimingResult(
            status=NumericalStatus.INSUFFICIENT,
            sample_rate_hz=float(sample_rate_hz),
            sample_count=int(values.size),
            global_device_sample_start=global_device_sample_start,
            continuity_segment_index=continuity_segment_index,
            slice_center_offset_hz=float(slice_center_offset_hz),
            nominal_frequency_offset_hz=float(nominal_frequency_offset_hz),
            searched_frequency_offsets_hz=offsets,
            frame_period_samples=float(frame_period),
            template_sample_count=len(template),
            template_sha256=template_digest,
            candidates=(),
            windows=(),
            reason="continuous IQ block contains fewer than the required complete frames",
        )

    nominal_template = _conditioned_template(template, nominal_frequency_offset_hz, sample_rate_hz)
    match_power = _normalized_match_power(
        values,
        nominal_template,
        output_block_samples=policy.fft_output_block_samples,
    )
    folded, _support = _fold_match_power(match_power, frame_period)
    folded_median = float(np.median(folded))
    folded_robust_sigma = 1.4826 * float(np.median(np.abs(folded - folded_median)))
    detection_threshold = max(
        folded_median * policy.minimum_epoch_peak_to_median,
        folded_median + policy.minimum_epoch_robust_z * folded_robust_sigma,
    )
    separated = _separated_epoch_indexes(
        folded,
        threshold=detection_threshold,
        minimum_separation=max(1, math.ceil(policy.candidate_separation_symbols * len(template))),
        maximum_candidates=policy.maximum_epoch_candidates,
    )

    if not separated:
        best = int(np.argmax(folded))
        separated = (best,)

    candidate_values: list[PssEpochCandidate] = []
    windows: list[PssFrameWindow] = []
    for candidate_index, epoch_sample in enumerate(separated):
        selected_frequency, _selected_score, selected_support = _refine_candidate_frequency(
            values,
            template,
            sample_rate_hz=sample_rate_hz,
            epoch_sample=epoch_sample,
            frame_period_samples=frame_period,
            frequency_offsets_hz=offsets,
        )
        nominal_score = float(folded[epoch_sample])
        peak_to_median = nominal_score / max(folded_median, np.finfo(float).tiny)
        robust_z = (nominal_score - folded_median) / max(folded_robust_sigma, np.finfo(float).tiny)
        qualified = (
            selected_support >= policy.minimum_frame_support
            and peak_to_median >= policy.minimum_epoch_peak_to_median
            and robust_z >= policy.minimum_epoch_robust_z
        )
        global_epoch = global_device_sample_start + epoch_sample
        candidate = PssEpochCandidate(
            candidate_index=candidate_index,
            epoch_sample=epoch_sample,
            global_epoch_device_sample=global_epoch,
            frame_phase_samples=float(global_epoch % frame_period),
            frequency_offset_hz=selected_frequency,
            folded_score=nominal_score,
            folded_median=folded_median,
            peak_to_median=peak_to_median,
            robust_z=robust_z,
            frame_support=selected_support,
            qualified=qualified,
        )
        candidate_values.append(candidate)
        if qualified:
            windows.extend(
                _measure_candidate_windows(
                    values,
                    template,
                    sample_rate_hz=sample_rate_hz,
                    global_device_sample_start=global_device_sample_start,
                    candidate=candidate,
                    frame_period_samples=frame_period,
                    local_search_radius_s=policy.local_search_radius_s,
                )
            )

    qualified_count = sum(candidate.qualified for candidate in candidate_values)
    status = NumericalStatus.COMPLETE if qualified_count else NumericalStatus.NO_RESULT
    reason = (
        f"{qualified_count} separated PSS timing mode(s) passed the candidate threshold"
        if qualified_count
        else "no separated PSS timing mode passed the candidate threshold"
    )
    return PssFrameTimingResult(
        status=status,
        sample_rate_hz=float(sample_rate_hz),
        sample_count=int(values.size),
        global_device_sample_start=global_device_sample_start,
        continuity_segment_index=continuity_segment_index,
        slice_center_offset_hz=float(slice_center_offset_hz),
        nominal_frequency_offset_hz=float(nominal_frequency_offset_hz),
        searched_frequency_offsets_hz=offsets,
        frame_period_samples=float(frame_period),
        template_sample_count=len(template),
        template_sha256=template_digest,
        candidates=tuple(candidate_values),
        windows=tuple(windows),
        reason=reason,
    )


def _validate_search_inputs(
    values: npt.NDArray[np.complex64],
    *,
    sample_rate_hz: float,
    global_device_sample_start: int,
    continuity_segment_index: int,
    nominal_frequency_offset_hz: float,
) -> None:
    if values.ndim != 1:
        raise ValueError("PSS search samples must be one-dimensional complex IQ")
    if not values.size or not np.all(np.isfinite(values)):
        raise ValueError("PSS search samples must be nonempty and finite")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("PSS sample rate must be finite and positive")
    if isinstance(global_device_sample_start, bool) or global_device_sample_start < 0:
        raise ValueError("PSS global device start must be a nonnegative integer")
    if not isinstance(global_device_sample_start, int):
        raise TypeError("PSS global device start must be an integer")
    if isinstance(continuity_segment_index, bool) or continuity_segment_index < 0:
        raise ValueError("PSS continuity segment index must be a nonnegative integer")
    if not isinstance(continuity_segment_index, int):
        raise TypeError("PSS continuity segment index must be an integer")
    if not math.isfinite(nominal_frequency_offset_hz):
        raise ValueError("PSS nominal frequency offset must be finite")


def _frequency_offsets(
    sample_rate_hz: float,
    *,
    nominal_frequency_offset_hz: float,
    frequency_offsets_hz: tuple[float, ...] | None,
) -> tuple[float, ...]:
    supplied = (
        (float(nominal_frequency_offset_hz),)
        if frequency_offsets_hz is None
        else tuple(float(value) for value in frequency_offsets_hz)
    )
    if not supplied or not all(math.isfinite(value) for value in supplied):
        raise ValueError("PSS frequency-offset bank must be nonempty and finite")
    if len(set(supplied)) != len(supplied):
        raise ValueError("PSS frequency-offset bank must be unique")
    if any(abs(value) >= sample_rate_hz / 2 for value in supplied):
        raise ValueError("PSS frequency offset must lie strictly inside complex Nyquist")
    return supplied


def _conditioned_template(
    template: npt.NDArray[np.complex64],
    frequency_offset_hz: float,
    sample_rate_hz: float,
) -> npt.NDArray[np.complex64]:
    time_s = np.arange(template.size, dtype=float) / sample_rate_hz
    return np.asarray(
        template * np.exp(2j * np.pi * frequency_offset_hz * time_s),
        dtype=np.complex64,
    )


def _normalized_match_power(
    values: npt.NDArray[np.complex64],
    template: npt.NDArray[np.complex64],
    *,
    output_block_samples: int,
) -> npt.NDArray[np.float64]:
    output_count = values.size - template.size + 1
    reversed_conjugate = np.conj(template[::-1])
    # The reviewed native-rate PSS templates are short (11 samples at
    # 2.5 MS/s and 110 samples at 25 MS/s).  Direct complex convolution is
    # materially faster than rebuilding overlap-save FFTs for this range and
    # produces the same correlation definition.
    if template.size <= 256:
        correlation = np.convolve(values, reversed_conjugate, mode="valid")
        power = np.square(np.abs(values), dtype=np.float64)
        cumulative = np.concatenate(([0.0], np.cumsum(power, dtype=np.float64)))
        energy = cumulative[template.size :] - cumulative[: -template.size]
        usable = energy > max(float(np.max(energy)), 0.0) * 1e-12
        output = np.zeros(output_count, dtype=np.float64)
        np.divide(
            np.square(np.abs(correlation), dtype=np.float64),
            energy,
            out=output,
            where=usable,
        )
        output.flags.writeable = False
        return output

    output = np.empty(output_count, dtype=np.float64)
    template_ffts: dict[int, npt.NDArray[np.complex128]] = {}
    for output_start in range(0, output_count, output_block_samples):
        count = min(output_block_samples, output_count - output_start)
        source = values[output_start : output_start + count + template.size - 1]
        convolution_count = source.size + template.size - 1
        fft_count = 1 << (convolution_count - 1).bit_length()
        template_fft = template_ffts.get(fft_count)
        if template_fft is None:
            template_fft = np.fft.fft(reversed_conjugate, fft_count)
            template_ffts[fft_count] = template_fft
        convolution = np.fft.ifft(np.fft.fft(source, fft_count) * template_fft)
        correlation = convolution[template.size - 1 : template.size - 1 + count]
        power = np.square(np.abs(source), dtype=np.float64)
        cumulative = np.concatenate(([0.0], np.cumsum(power, dtype=np.float64)))
        energy = cumulative[template.size :] - cumulative[: -template.size]
        usable = energy > max(float(np.max(energy)), 0.0) * 1e-12
        selected = output[output_start : output_start + count]
        selected.fill(0.0)
        np.divide(
            np.square(np.abs(correlation), dtype=np.float64),
            energy,
            out=selected,
            where=usable,
        )
    output.flags.writeable = False
    return output


def _fold_match_power(
    match_power: npt.NDArray[np.float64],
    frame_period_samples: float,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.int64]]:
    epoch_count = round(frame_period_samples)
    folded = np.zeros(epoch_count, dtype=float)
    support = np.zeros(epoch_count, dtype=np.int64)
    # Accumulate one complete frame at a time.  This is numerically
    # equivalent to constructing a tiny index vector for every possible
    # epoch, while replacing tens of thousands of Python iterations with at
    # most a few hundred vector operations.  Re-evaluating ``rint`` for every
    # frame preserves the exact fractional-period and ties-to-even behavior.
    epochs = np.arange(epoch_count, dtype=float)
    frame_count = math.ceil(match_power.size / frame_period_samples)
    for frame_index in range(frame_count):
        indexes = np.rint(epochs + frame_index * frame_period_samples).astype(np.int64)
        usable = indexes < match_power.size
        if not np.any(usable):
            continue
        folded[usable] += match_power[indexes[usable]]
        support[usable] += 1
    np.divide(folded, support, out=folded, where=support > 0)
    folded.flags.writeable = False
    support.flags.writeable = False
    return folded, support


def _separated_epoch_indexes(
    folded: npt.NDArray[np.float64],
    *,
    threshold: float,
    minimum_separation: int,
    maximum_candidates: int,
) -> tuple[int, ...]:
    selected: list[int] = []
    epoch_count = folded.size
    for raw_index in np.argsort(folded)[::-1]:
        index = int(raw_index)
        if folded[index] < threshold:
            break
        if any(
            min(abs(index - retained), epoch_count - abs(index - retained)) < minimum_separation
            for retained in selected
        ):
            continue
        selected.append(index)
        if len(selected) == maximum_candidates:
            break
    return tuple(selected)


def _projected_frame_starts(
    *,
    epoch_sample: int,
    frame_period_samples: float,
    sample_count: int,
    template_sample_count: int,
) -> npt.NDArray[np.int64]:
    frame_count = math.ceil((sample_count - epoch_sample) / frame_period_samples)
    starts = np.rint(
        epoch_sample + np.arange(frame_count, dtype=float) * frame_period_samples
    ).astype(np.int64)
    return starts[(starts >= 0) & (starts + template_sample_count <= sample_count)]


def _refine_candidate_frequency(
    values: npt.NDArray[np.complex64],
    template: npt.NDArray[np.complex64],
    *,
    sample_rate_hz: float,
    epoch_sample: int,
    frame_period_samples: float,
    frequency_offsets_hz: tuple[float, ...],
) -> tuple[float, float, int]:
    starts = _projected_frame_starts(
        epoch_sample=epoch_sample,
        frame_period_samples=frame_period_samples,
        sample_count=values.size,
        template_sample_count=template.size,
    )
    best_frequency = frequency_offsets_hz[0]
    best_score = -math.inf
    for frequency in frequency_offsets_hz:
        conditioned = _conditioned_template(template, frequency, sample_rate_hz)
        correlations = np.asarray(
            [np.vdot(conditioned, values[start : start + template.size]) for start in starts]
        )
        energy = np.asarray(
            [
                np.vdot(
                    values[start : start + template.size], values[start : start + template.size]
                ).real
                for start in starts
            ],
            dtype=float,
        )
        scores = np.zeros(starts.size, dtype=float)
        np.divide(np.abs(correlations) ** 2, energy, out=scores, where=energy > 0)
        score = float(np.mean(scores)) if scores.size else 0.0
        if score > best_score:
            best_frequency = frequency
            best_score = score
    return float(best_frequency), float(best_score), int(starts.size)


def _measure_candidate_windows(
    values: npt.NDArray[np.complex64],
    template: npt.NDArray[np.complex64],
    *,
    sample_rate_hz: float,
    global_device_sample_start: int,
    candidate: PssEpochCandidate,
    frame_period_samples: float,
    local_search_radius_s: float,
) -> tuple[PssFrameWindow, ...]:
    starts = _projected_frame_starts(
        epoch_sample=candidate.epoch_sample,
        frame_period_samples=frame_period_samples,
        sample_count=values.size,
        template_sample_count=template.size,
    )
    radius = math.ceil(local_search_radius_s * sample_rate_hz)
    conditioned = _conditioned_template(template, candidate.frequency_offset_hz, sample_rate_hz)
    output: list[PssFrameWindow] = []
    for frame_index, predicted in enumerate(starts):
        search_start = int(predicted) - radius
        search_stop = int(predicted) + radius + 1
        if search_start < 0 or search_stop + template.size - 1 > values.size:
            # Never publish a timing estimate whose local matched-filter
            # aperture was truncated by this analysis block. Overlapping
            # blocks provide an interior copy of boundary opportunities.
            continue
        scores, correlations = _local_match_scores(
            values,
            conditioned,
            search_start=search_start,
            search_stop=search_stop,
        )
        best_index = int(np.argmax(scores))
        fractional = _parabolic_log_peak(scores, best_index)
        measured = search_start + best_index
        fractional_local = measured + fractional
        fractional_global = global_device_sample_start + fractional_local
        frame_phase = float(fractional_global % frame_period_samples)
        absolute_phase = correlations[best_index] * np.exp(
            -2j
            * np.pi
            * candidate.frequency_offset_hz
            * (global_device_sample_start + measured)
            / sample_rate_hz
        )
        output.append(
            PssFrameWindow(
                candidate_index=candidate.candidate_index,
                frame_index=frame_index,
                predicted_local_sample=int(predicted),
                measured_local_sample=measured,
                global_device_sample=global_device_sample_start + measured,
                fractional_global_device_sample=float(fractional_global),
                fractional_timing_offset_samples=float(fractional_local - int(predicted)),
                frame_phase_samples=frame_phase,
                frame_phase_cycles=float(frame_phase / frame_period_samples),
                frequency_offset_hz=candidate.frequency_offset_hz,
                normalized_match_power=float(scores[best_index]),
                peak_to_local_median=float(
                    scores[best_index] / max(float(np.median(scores)), np.finfo(float).tiny)
                ),
                correlation_phase_cycles=float(np.angle(absolute_phase) / (2.0 * np.pi)),
                local_search_start_sample=search_start,
                local_search_stop_sample=search_stop,
            )
        )
    return tuple(output)


def _local_match_scores(
    values: npt.NDArray[np.complex64],
    template: npt.NDArray[np.complex64],
    *,
    search_start: int,
    search_stop: int,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.complex128]]:
    selected = values[search_start : search_stop + template.size - 1]
    windows = np.lib.stride_tricks.sliding_window_view(selected, template.size)
    correlations = np.asarray(windows @ np.conj(template), dtype=np.complex128)
    energy = np.sum(np.abs(windows) ** 2, axis=1, dtype=np.float64)
    scores = np.zeros(correlations.size, dtype=float)
    np.divide(np.abs(correlations) ** 2, energy, out=scores, where=energy > 0)
    return scores, correlations


def _parabolic_log_peak(scores: npt.NDArray[np.float64], index: int) -> float:
    if index <= 0 or index >= scores.size - 1:
        return 0.0
    selected = np.log(np.maximum(scores[index - 1 : index + 2], np.finfo(float).tiny))
    denominator = selected[0] - 2.0 * selected[1] + selected[2]
    if not math.isfinite(float(denominator)) or abs(denominator) <= np.finfo(float).eps:
        return 0.0
    return float(np.clip(0.5 * (selected[0] - selected[2]) / denominator, -0.5, 0.5))
