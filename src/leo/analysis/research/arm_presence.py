"""Experimental, infrastructure-blind presence detectors for desktop ARM screening.

These are research scores, not a new persisted detector contract or calibrated
Starlink verdict. A missing reference detection never constitutes noise truth.
No carrier phase is transported through a retune.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import cast

import numpy as np

from leo.analysis.starlink.acquisition import (
    ReceiverFrequencyCalibration,
    SymbolwiseAcquisitionConfig,
    acquire_symbolwise,
)
from leo.analysis.starlink.pilot_methods import (
    conditioned_glrt64_scores,
    refine_glrt64_epochs,
)
from leo.analysis.starlink.pss_timing import PssTimingSearchConfig, search_pss_frame_timing
from leo.analysis.starlink.templates import FRAME_RATE_HZ, StarlinkEdge

MARGIN_GATE = 0.025


def _values(samples: np.ndarray, sample_rate_hz: int) -> np.ndarray:
    values = np.asarray(samples, dtype=np.complex64)
    if sample_rate_hz <= 0 or values.ndim != 1 or values.size < sample_rate_hz / 375:
        raise ValueError("a positive rate and at least two frames of one receiver are required")
    if not np.all(np.isfinite(values)):
        raise ValueError("IQ must be finite")
    return values


def periodicity_scout(samples: np.ndarray, sample_rate_hz: int) -> dict[str, float]:
    """Sparse fractional-lag correlation, with two non-frame-lag controls.

    Eight time groups are accumulated noncoherently, limiting cancellation from
    changing lag phase. Linear interpolation is an explicitly approximate scout,
    not the fractional scientific GLRT sampler. Tone/DC rejection is diagnostic,
    not a claim that every other interferer is rejected.
    """
    values = _values(samples, sample_rate_hz)
    period = sample_rate_hz / FRAME_RATE_HZ
    stop = values.size - math.ceil(1.07 * period) - 1
    indexes = np.linspace(0, stop - 1, min(8192, stop), dtype=np.int64)
    groups = np.array_split(indexes, 8)
    scores = []
    for ratio in (1.0, 0.93, 1.07):
        lag = ratio * period
        offset = math.floor(lag)
        fraction = lag - offset
        correlations = []
        for group in groups:
            left = values[group]
            right = (1 - fraction) * values[group + offset] + fraction * values[group + offset + 1]
            energy = float(np.vdot(left, left).real * np.vdot(right, right).real)
            correlations.append(float(abs(np.vdot(left, right)) ** 2) / max(energy, 1e-30))
        scores.append(float(np.mean(correlations)))
    energy = np.abs(values) ** 2
    return {
        "lag_margin": scores[0] - max(scores[1:]),
        "lag_exact": scores[0],
        "rms": float(np.sqrt(np.mean(energy))),
        "crest_factor": float(np.max(energy) / max(float(np.mean(energy)), 1e-30)),
    }


def pss_scout(
    samples: np.ndarray,
    sample_rate_hz: int,
    *,
    slice_center_offset_hz: float,
    cfo_bank_hz: tuple[float, ...] = (-400_000.0, -200_000.0, 0.0, 200_000.0, 400_000.0),
) -> dict[str, float]:
    """Blind short-template correlation + exact 750 Hz power folding.

    Every bank member gets a blind search. The timing API's frequency_offsets
    argument alone would refine already selected epochs, not search blindly at
    each CFO. Disable downstream per-frame refinements: this is only a scout.
    """
    values = _values(samples, sample_rate_hz)
    if not cfo_bank_hz or not all(math.isfinite(cfo) for cfo in cfo_bank_hz):
        raise ValueError("a finite nonempty CFO bank is required")
    policy = PssTimingSearchConfig(
        minimum_epoch_robust_z=1e12,
        maximum_epoch_candidates=1,
    )
    best = {"pss_z": 0.0, "pss_ratio": 0.0, "pss_epoch": 0.0, "pss_cfo_hz": 0.0}
    for cfo in cfo_bank_hz:
        result = search_pss_frame_timing(
            values,
            sample_rate_hz,
            global_device_sample_start=0,
            continuity_segment_index=0,
            slice_center_offset_hz=slice_center_offset_hz,
            nominal_frequency_offset_hz=cfo,
            config=policy,
        )
        for candidate in result.candidates:
            if candidate.robust_z > best["pss_z"]:
                best = {
                    "pss_z": float(candidate.robust_z),
                    "pss_ratio": float(candidate.peak_to_median),
                    "pss_epoch": float(candidate.epoch_sample),
                    "pss_cfo_hz": cfo,
                }
    return best


@dataclass(frozen=True)
class PresenceCandidate:
    epoch_sample: int
    fractional_offset_samples: float
    acquired_cfo_hz: float
    tracking_cfo_hz: float
    margin: float
    exact_score: float

    @property
    def passed(self) -> bool:
        return self.margin >= MARGIN_GATE


def _fractional_candidates(
    values, rate, edge, epochs, frequencies
) -> tuple[PresenceCandidate, ...]:
    refinements = refine_glrt64_epochs(
        values,
        rate,
        integer_epoch_samples=epochs,
        acquired_cfo_hz=frequencies,
        edge=edge,
    )
    return tuple(
        PresenceCandidate(
            epoch_sample=epoch,
            fractional_offset_samples=float(cast(float, refined.fractional_epoch_offset_samples)),
            acquired_cfo_hz=frequency,
            tracking_cfo_hz=float(cast(float, refined.fractional_tracking_cfo_hz)),
            margin=float(refined.fractional_margin),
            exact_score=float(cast(float, refined.fractional_exact_score)),
        )
        for epoch, frequency, refined in zip(epochs, frequencies, refinements, strict=True)
        if refined.fractional_margin is not None
    )


def fresh_glrt(
    samples: np.ndarray,
    sample_rate_hz: int,
    *,
    edge: str,
    candidate_count: int = 8,
) -> tuple[PresenceCandidate, ...]:
    """Actual fresh acquisition at the requested budget, then fractional GLRT.

    Truncating an eight-candidate result AFTER acquisition is not equivalent to
    running a two-candidate search; the requested budget is applied at acquisition.
    """
    values = np.ascontiguousarray(_values(samples, sample_rate_hz), dtype=np.complex128)
    if not 1 <= candidate_count <= 8:
        raise ValueError("experimental acquisition budget must be in 1..8")
    acquired = acquire_symbolwise(
        values,
        sample_rate_hz,
        ReceiverFrequencyCalibration("research", 0.0, "0" * 64),
        edge=edge,
        config=SymbolwiseAcquisitionConfig(
            maximum_probe_samples=values.size,
            retained_candidate_count=candidate_count,
            candidate_epoch_separation_samples=5,
            candidate_cfo_separation_hz=10_000.0,
        ),
    )
    return _fractional_candidates(
        values,
        sample_rate_hz,
        edge,
        tuple(c.refined_epoch_sample for c in acquired.candidates),
        tuple(c.absolute_cfo_hz for c in acquired.candidates),
    )


def best_candidate(candidates: tuple[PresenceCandidate, ...]) -> PresenceCandidate | None:
    return max(candidates, key=lambda candidate: candidate.margin, default=None)


@dataclass(frozen=True)
class TimingSeed:
    """Receiver/channel/session-local state; never a transported carrier phase."""

    device_counter: int
    sample_rate_hz: int
    candidate: PresenceCandidate

    def predict_epoch(self, device_counter: int) -> float:
        if device_counter <= self.device_counter:
            raise ValueError("cached confirmation requires strictly later device time")
        elapsed = device_counter - self.device_counter
        # Integer subtraction before float arithmetic preserves epoch precision.
        period = self.sample_rate_hz / FRAME_RATE_HZ
        return (
            self.candidate.epoch_sample
            + self.candidate.fractional_offset_samples
            - elapsed % period
        ) % period


def cached_glrt(
    samples: np.ndarray,
    sample_rate_hz: int,
    *,
    edge: str,
    device_counter: int,
    seed: TimingSeed,
    search_radius_us: float = 2.4,
) -> tuple[PresenceCandidate, ...]:
    """Search a bounded local timing neighborhood and fractionally confirm its best cell."""
    if sample_rate_hz != seed.sample_rate_hz or search_radius_us <= 0:
        raise ValueError("cache rate must match and timing radius must be positive")
    values = np.ascontiguousarray(_values(samples, sample_rate_hz), dtype=np.complex128)
    epoch = seed.predict_epoch(device_counter)
    radius = math.ceil(sample_rate_hz * search_radius_us * 1e-6)
    cells = tuple(
        sorted(
            {
                (round(epoch) + delta) % round(sample_rate_hz / FRAME_RATE_HZ)
                for delta in range(-radius, radius + 1)
            }
        )
    )
    cfo = seed.candidate.tracking_cfo_hz
    scores = conditioned_glrt64_scores(
        values,
        sample_rate_hz,
        epoch_samples=cells,
        acquired_cfo_hz=(cfo,) * len(cells),
        edge=StarlinkEdge(edge),
    )
    index = max(range(len(scores)), key=lambda i: scores[i].margin)
    return _fractional_candidates(values, sample_rate_hz, edge, (cells[index],), (cfo,))


def reference_label(windows: list[tuple[PresenceCandidate, ...]]) -> str:
    """CFO-consistent repeated fractional GLRT support, not independent truth.

    All retained basins participate, avoiding a changing best candidate hiding a
    persistent signal. Distinct nonoverlapping windows are required.
    """
    hits = [[candidate for candidate in window if candidate.passed] for window in windows]
    for index, first in enumerate(hits):
        for second in hits[index + 1 :]:
            if any(
                abs(a.tracking_cfo_hz - b.tracking_cfo_hz) <= 8_000.0 for a in first for b in second
            ):
                return "repeated_reference_positive"
    return "single_window_reference_positive" if any(hits) else "unresolved"


def noise_control(
    sample_count: int,
    sample_rate_hz: int,
    *,
    seed: int,
    kind: str,
) -> np.ndarray:
    """Known synthetic negatives; NOT a substitute for real RF negatives."""
    rng = np.random.default_rng(seed)
    values = rng.normal(size=sample_count) + 1j * rng.normal(size=sample_count)
    if kind == "tone_noise":
        values += 6 * np.exp(2j * np.pi * 173_123.0 * np.arange(sample_count) / sample_rate_hz)
    elif kind != "gaussian":
        raise ValueError("unknown synthetic negative kind")
    return np.asarray(values, dtype=np.complex64)
