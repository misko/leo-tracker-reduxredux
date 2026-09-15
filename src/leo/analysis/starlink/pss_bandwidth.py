"""PSS acquisition on the observable channel slice, at the original sample rate.

The reference is the published 240 MHz waveform. An explicitly declared ideal
receiver passband (or measured complex response) filters that reference before
sampling. No claim about an unknown analogue response is inferred from IQ rate.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
import numpy.typing as npt

from leo.analysis.starlink.pss_timing import (
    PSS_NATIVE_SAMPLE_RATE_HZ,
    PssFrameTimingResult,
    PssTimingSearchConfig,
    pss_native_time_samples,
    search_pss_frame_timing,
)


@dataclass(frozen=True)
class PssCaptureBand:
    """Receiver-relative passband and center relative to the PSS channel reference.

    Response knots, if supplied, contain (baseband Hz, real gain, imaginary gain).
    They must cover the passband. Absolute instrument delay is caller supplied
    through that response; otherwise all output timing is template relative.
    """

    sample_rate_hz: float
    center_offset_hz: float
    passband_low_hz: float
    passband_high_hz: float
    response: tuple[tuple[float, float, float], ...] = ()

    def __post_init__(self) -> None:
        values = (
            self.sample_rate_hz,
            self.center_offset_hz,
            self.passband_low_hz,
            self.passband_high_hz,
        )
        if not all(math.isfinite(x) for x in values):
            raise ValueError("PSS band frequencies must be finite")
        if not 0 < self.sample_rate_hz <= PSS_NATIVE_SAMPLE_RATE_HZ:
            raise ValueError("PSS rate must lie in (0, 240 MS/s]")
        if not (
            -self.sample_rate_hz / 2
            <= self.passband_low_hz
            < self.passband_high_hz
            <= self.sample_rate_hz / 2
        ):
            raise ValueError("PSS passband must fit within sampled Nyquist bounds")
        if self.response:
            knots = np.asarray(self.response, dtype=float)
            if (
                knots.ndim != 2
                or knots.shape[1] != 3
                or len(knots) < 2
                or not np.all(np.isfinite(knots))
                or not np.all(np.diff(knots[:, 0]) > 0)
                or knots[0, 0] > self.passband_low_hz
                or knots[-1, 0] < self.passband_high_hz
            ):
                raise ValueError("PSS response knots must be ordered and cover the passband")

    def overlap_hz(self, cfo_hz: float) -> tuple[float, float] | None:
        """Intersection in receiver coordinates for a declared CFO hypothesis."""
        if not math.isfinite(cfo_hz):
            raise ValueError("PSS CFO must be finite")
        low = max(self.passband_low_hz, -120_000_000 + cfo_hz - self.center_offset_hz)
        high = min(self.passband_high_hz, 120_000_000 + cfo_hz - self.center_offset_hz)
        return (low, high) if high > low else None


@dataclass(frozen=True)
class PssBandTemplate:
    samples: npt.NDArray[np.complex64]
    overlap_hz: tuple[float, float]
    sha256: str


@lru_cache(maxsize=128)
def band_template(band: PssCaptureBand, cfo_hz: float, *, fft_size: int = 16384) -> PssBandTemplate:
    """Project the finite published symbol via spectral quadrature.

    Keep the published 4.4 us observation aperture. FFT zero padding controls
    frequency quadrature precision, not added signal bandwidth. The returned
    template excludes the CFO phasor: the existing timing kernel applies it.
    """
    overlap = band.overlap_hz(cfo_hz)
    if overlap is None:
        raise ValueError("PSS channel has no overlap with the receiver passband")
    if type(fft_size) is not int or fft_size < 4096 or fft_size > 262144:
        raise ValueError("PSS spectral quadrature size must be in 4096..262144")
    native = pss_native_time_samples()
    frequencies = np.fft.fftfreq(fft_size, 1 / PSS_NATIVE_SAMPLE_RATE_HZ)
    receiver_frequencies = frequencies + cfo_hz - band.center_offset_hz
    mask = (receiver_frequencies >= overlap[0]) & (receiver_frequencies < overlap[1])
    if np.count_nonzero(mask) < 4:
        raise ValueError("PSS overlap is too narrow for the declared spectral quadrature")
    spectrum = np.fft.fft(native, fft_size)[mask]
    if band.response:
        knots = np.asarray(band.response)
        spectrum *= np.interp(
            receiver_frequencies[mask], knots[:, 0], knots[:, 1]
        ) + 1j * np.interp(receiver_frequencies[mask], knots[:, 0], knots[:, 2])
    count = math.ceil(len(native) * band.sample_rate_hz / PSS_NATIVE_SAMPLE_RATE_HZ)
    times = np.arange(count) / band.sample_rate_hz
    template = np.empty(count, dtype=np.complex64)
    tile = min(128, max(1, 1_048_576 // len(spectrum)))
    for start in range(0, count, tile):
        phase = (
            2j
            * np.pi
            * times[start : start + tile, None]
            * (frequencies[mask] - band.center_offset_hz)
        )
        template[start : start + tile] = np.exp(phase) @ spectrum / fft_size
    norm = float(np.linalg.norm(template))
    if not math.isfinite(norm) or norm < 1e-12:
        raise ValueError("PSS template has no observable energy")
    template /= norm
    template = np.frombuffer(template.astype("<c8").tobytes(), dtype="<c8")
    return PssBandTemplate(template, overlap, hashlib.sha256(template.tobytes()).hexdigest())


@dataclass(frozen=True)
class PssBandSearch:
    band: PssCaptureBand
    device_sample_start: int
    sample_count: int
    continuity_segment_index: int
    hypotheses: tuple[PssFrameTimingResult, ...]
    unsupported_offsets_hz: tuple[float, ...]
    candidate_only: bool = field(default=True, init=False)


def acquire_pss_band(
    samples: npt.ArrayLike,
    band: PssCaptureBand,
    *,
    device_sample_start: int,
    continuity_segment_index: int,
    frequency_offsets_hz: tuple[float, ...],
    config: PssTimingSearchConfig | None = None,
) -> PssBandSearch:
    """Run a genuine blind timing search at every declared carrier hypothesis."""
    values = np.asarray(samples, dtype=np.complex64)
    if values.ndim != 1 or not values.size or not np.all(np.isfinite(values)):
        raise ValueError("PSS input must be finite nonempty one-dimensional IQ")
    if (
        type(device_sample_start) is not int
        or device_sample_start < 0
        or type(continuity_segment_index) is not int
        or continuity_segment_index < 0
    ):
        raise ValueError("PSS source coordinates must be nonnegative integers")
    if (
        not frequency_offsets_hz
        or len(frequency_offsets_hz) > 257
        or len(set(frequency_offsets_hz)) != len(frequency_offsets_hz)
        or any(
            not math.isfinite(f) or abs(f) >= band.sample_rate_hz / 2 for f in frequency_offsets_hz
        )
    ):
        raise ValueError("PSS bank must have 1..257 unique finite CFOs inside Nyquist")
    results = []
    unsupported = []
    for cfo in frequency_offsets_hz:
        if band.overlap_hz(cfo) is None:
            unsupported.append(cfo)
            continue
        template = band_template(band, cfo)
        results.append(
            search_pss_frame_timing(
                values,
                band.sample_rate_hz,
                global_device_sample_start=device_sample_start,
                continuity_segment_index=continuity_segment_index,
                slice_center_offset_hz=band.center_offset_hz,
                nominal_frequency_offset_hz=cfo,
                frequency_offsets_hz=(cfo,),
                template_samples=template.samples,
                config=config,
            )
        )
    return PssBandSearch(
        band,
        device_sample_start,
        len(values),
        continuity_segment_index,
        tuple(results),
        tuple(unsupported),
    )


def acquire_pss_coarse_to_fine(
    samples: npt.ArrayLike,
    band: PssCaptureBand,
    *,
    device_sample_start: int,
    continuity_segment_index: int,
    coarse_offsets_hz: tuple[float, ...],
    fine_radius_hz: float = 100_000.0,
    fine_step_hz: float = 25_000.0,
    maximum_centers: int = 4,
    config: PssTimingSearchConfig | None = None,
) -> PssBandSearch:
    """Refine up to four strongest coarse hypotheses without re-searching them.

    Every fine hypothesis repeats blind timing acquisition with its own overlap
    template. The combined budget remains at most 257 hypotheses. Diagnostics
    retain both coarse and fine searches; extra trials do not establish detection.
    """
    if (
        not math.isfinite(fine_radius_hz)
        or not math.isfinite(fine_step_hz)
        or fine_radius_hz < 0
        or fine_step_hz <= 0
        or type(maximum_centers) is not int
        or not 1 <= maximum_centers <= 4
    ):
        raise ValueError("invalid PSS fine-bank bounds")
    half_steps = math.floor(fine_radius_hz / fine_step_hz)
    if half_steps > 128:
        raise ValueError("PSS fine-bank request exceeds bounded search budget")
    coarse = acquire_pss_band(
        samples,
        band,
        device_sample_start=device_sample_start,
        continuity_segment_index=continuity_segment_index,
        frequency_offsets_hz=coarse_offsets_hz,
        config=config,
    )
    ranked = sorted(
        coarse.hypotheses,
        key=lambda h: max((c.robust_z for c in h.candidates), default=-math.inf),
        reverse=True,
    )
    centers = [
        h.nominal_frequency_offset_hz
        for h in ranked[:maximum_centers]
        if max((c.robust_z for c in h.candidates), default=0) >= 4
    ]
    fine = sorted(
        {
            center + i * fine_step_hz
            for center in centers
            for i in range(-half_steps, half_steps + 1)
            if abs(center + i * fine_step_hz) < band.sample_rate_hz / 2
        }
        - set(coarse_offsets_hz)
    )
    if len(fine) + len(coarse_offsets_hz) > 257:
        raise ValueError("PSS combined bank exceeds bounded search budget")
    if not fine:
        return coarse
    refinement = acquire_pss_band(
        samples,
        band,
        device_sample_start=device_sample_start,
        continuity_segment_index=continuity_segment_index,
        frequency_offsets_hz=tuple(fine),
        config=config,
    )
    return PssBandSearch(
        band,
        device_sample_start,
        coarse.sample_count,
        continuity_segment_index,
        coarse.hypotheses + refinement.hypotheses,
        coarse.unsupported_offsets_hz + refinement.unsupported_offsets_hz,
    )
