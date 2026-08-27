"""Exact-Qin injection for a frozen receiver-clock CFO trajectory.

This module is a response-independent numerical kernel.  It neither reads IQ
nor selects a catalogue object.  A caller must supply an exact background span
and a trajectory frozen before that background is opened.  The piecewise-linear
trajectory integrates phase analytically, so an SGP4-derived curve and a radio
polynomial curve can pass through the same injection and measurement path.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from leo.analysis.qam.pilot import (
    PilotFrameCfoConfig,
    evaluate_edge_pilot_frame_cfo_likelihood,
)
from leo.analysis.research.polynomial_injection import (
    FrameCfoEvidence,
    InjectionDiagnostics,
    occupied_frame_mask,
    qin_frame_starts,
)
from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.templates import (
    OFDM_SYMBOL_DURATION_S,
    qin_edge_pilot_frame,
    template_sha256,
)

_QIN_TEMPLATE_DIGEST = "15455635bcdcfe0747f686ae317d235b5dfa54ae49c76b9741e6acc889d8a657"


@dataclass(frozen=True, slots=True)
class PiecewiseLinearCfoTrajectory:
    """Finite receiver-clock CFO knots with an exact piecewise-linear phase."""

    trajectory_id: str
    knot_times_s: tuple[float, ...]
    knot_cfo_hz: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.trajectory_id.strip():
            raise ValueError("trajectory identity cannot be empty")
        if len(self.knot_times_s) < 2 or len(self.knot_times_s) != len(self.knot_cfo_hz):
            raise ValueError("trajectory needs at least two paired knots")
        if not all(math.isfinite(item) for item in (*self.knot_times_s, *self.knot_cfo_hz)):
            raise ValueError("trajectory knots must be finite")
        if any(
            later <= earlier
            for earlier, later in zip(self.knot_times_s, self.knot_times_s[1:], strict=False)
        ):
            raise ValueError("trajectory times must be strictly increasing")

    def cfo_hz(self, receiver_time_s: npt.ArrayLike) -> np.ndarray:
        """Interpolate CFO at receiver-clock times inside the frozen support."""

        query = self._validated_query(receiver_time_s)
        return np.asarray(np.interp(query, self.knot_times_s, self.knot_cfo_hz), dtype=float)

    def phase_cycles(self, receiver_time_s: npt.ArrayLike) -> np.ndarray:
        """Integrate CFO exactly from the first knot to each query time."""

        query = self._validated_query(receiver_time_s)
        times = np.asarray(self.knot_times_s, dtype=float)
        cfo = np.asarray(self.knot_cfo_hz, dtype=float)
        widths = np.diff(times)
        slopes = np.diff(cfo) / widths
        cumulative = np.concatenate(
            (
                np.zeros(1, dtype=float),
                np.cumsum(0.5 * (cfo[:-1] + cfo[1:]) * widths),
            )
        )
        segment = np.searchsorted(times, query, side="right") - 1
        segment = np.clip(segment, 0, len(times) - 2)
        delta = query - times[segment]
        return np.asarray(
            cumulative[segment] + cfo[segment] * delta + 0.5 * slopes[segment] * delta**2,
            dtype=float,
        )

    def _validated_query(self, receiver_time_s: npt.ArrayLike) -> np.ndarray:
        query = np.asarray(receiver_time_s, dtype=float)
        if not np.all(np.isfinite(query)):
            raise ValueError("trajectory query times must be finite")
        if np.any(query < self.knot_times_s[0]) or np.any(query > self.knot_times_s[-1]):
            raise ValueError("trajectory query lies outside the frozen knot support")
        return query


@dataclass(frozen=True, slots=True)
class TrajectoryQinInjectionConfig:
    """Frozen geometry and measurement settings for one injected span."""

    scenario_id: str
    sample_rate_hz: int
    sample_count: int
    frame_count: int
    snr_db: float
    frame_occupancy: float
    seed: int
    frame_cfo_search_half_width_hz: float
    profile_step_hz: float
    minimum_exact_coherence: float
    minimum_coherence_margin: float

    def __post_init__(self) -> None:
        if not self.scenario_id.strip():
            raise ValueError("scenario identity cannot be empty")
        if self.sample_rate_hz != 2_500_000:
            raise ValueError("v1 is bound to the 2.5 Msps Qin template")
        if self.sample_count < 1 or self.frame_count < 1:
            raise ValueError("sample and frame counts must be positive")
        if self.seed < 0:
            raise ValueError("seed must be non-negative")
        if not math.isfinite(self.snr_db):
            raise ValueError("SNR must be finite")
        if not math.isfinite(self.frame_occupancy) or not 0.0 < self.frame_occupancy <= 1.0:
            raise ValueError("frame occupancy must lie in (0, 1]")
        if (
            not math.isfinite(self.frame_cfo_search_half_width_hz)
            or self.frame_cfo_search_half_width_hz <= 0.0
            or not math.isfinite(self.profile_step_hz)
            or self.profile_step_hz <= 0.0
        ):
            raise ValueError("CFO search geometry must be finite and positive")
        if not 0.0 <= self.minimum_exact_coherence <= 1.0:
            raise ValueError("minimum exact coherence must lie in [0, 1]")
        if not -1.0 <= self.minimum_coherence_margin <= 1.0:
            raise ValueError("minimum coherence margin must lie in [-1, 1]")


def inject_exact_qin_trajectory(
    background: npt.ArrayLike,
    trajectory: PiecewiseLinearCfoTrajectory,
    config: TrajectoryQinInjectionConfig,
) -> tuple[np.ndarray, np.ndarray, InjectionDiagnostics]:
    """Inject exact lower-edge Qin along one pre-frozen CFO trajectory."""

    values = np.asarray(background, dtype=np.complex64)
    if values.ndim != 1 or values.size != config.sample_count:
        raise ValueError("background must be the exact configured span")
    if not np.all(np.isfinite(values)):
        raise ValueError("background contains non-finite samples")
    template = qin_edge_pilot_frame(config.sample_rate_hz, "lower")
    if template.size != 3_333 or template_sha256(template) != _QIN_TEMPLATE_DIGEST:
        raise ValueError("runtime Qin template differs from the frozen v1 template")
    starts = qin_frame_starts(frame_count=config.frame_count, sample_rate_hz=config.sample_rate_hz)
    if starts[-1] + template.size > values.size:
        raise ValueError("Qin lattice exceeds the configured background span")
    if np.any(starts[:-1] + template.size > starts[1:]):
        raise ValueError("Qin template placements overlap")
    occupied = occupied_frame_mask(
        frame_count=config.frame_count,
        occupancy=config.frame_occupancy,
        seed=config.seed,
    )
    background_power = float(np.mean(np.abs(values.astype(np.complex128)) ** 2))
    template_power = float(np.mean(np.abs(template.astype(np.complex128)) ** 2))
    if background_power <= np.finfo(float).tiny or template_power <= np.finfo(float).tiny:
        raise ValueError("background and template powers must be positive")
    amplitude = math.sqrt(background_power * 10.0 ** (config.snr_db / 10.0) / template_power)
    output = values.copy()
    sample_offsets = np.arange(template.size, dtype=float)
    for frame_index in np.flatnonzero(occupied):
        start = int(starts[frame_index])
        receiver_time_s = (start + sample_offsets) / config.sample_rate_hz
        signal = (
            amplitude * template * np.exp(2j * np.pi * trajectory.phase_cycles(receiver_time_s))
        )
        output[start : start + template.size] += np.asarray(signal, dtype=np.complex64)
    return (
        output,
        occupied,
        InjectionDiagnostics(
            background_power=background_power,
            template_power=template_power,
            amplitude_scale=amplitude,
            target_snr_db=config.snr_db,
            occupied_frame_count=int(np.sum(occupied)),
            opportunity_count=config.frame_count,
        ),
    )


def evaluate_exact_qin_trajectory_frames(
    samples: npt.ArrayLike,
    occupied: npt.ArrayLike,
    trajectory: PiecewiseLinearCfoTrajectory,
    config: TrajectoryQinInjectionConfig,
    *,
    absolute_span_start_sample: int,
) -> tuple[FrameCfoEvidence, ...]:
    """Measure every opportunity with the public parity-split Qin CFO kernel."""

    values = np.asarray(samples, dtype=np.complex64)
    occupancy = np.asarray(occupied, dtype=bool)
    if values.ndim != 1 or values.size != config.sample_count:
        raise ValueError("samples must be the exact configured span")
    if occupancy.shape != (config.frame_count,):
        raise ValueError("occupancy mask has the wrong geometry")
    if absolute_span_start_sample < 0:
        raise ValueError("absolute span start must be non-negative")
    starts = qin_frame_starts(frame_count=config.frame_count, sample_rate_hz=config.sample_rate_hz)
    frame_content = round(302 * config.sample_rate_hz * OFDM_SYMBOL_DURATION_S)
    reference_offset_s = float(
        np.mean((np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S)
    )
    grid = np.arange(
        -config.frame_cfo_search_half_width_hz,
        config.frame_cfo_search_half_width_hz + 0.5 * config.profile_step_hz,
        config.profile_step_hz,
    )
    estimator_config = PilotFrameCfoConfig(
        residual_half_width_hz=config.frame_cfo_search_half_width_hz,
        minimum_exact_coherence=config.minimum_exact_coherence,
        minimum_coherence_margin=config.minimum_coherence_margin,
    )
    output: list[FrameCfoEvidence] = []
    for frame_index, raw_start in enumerate(starts):
        local_start = int(raw_start)
        reference_time_s = local_start / config.sample_rate_hz + reference_offset_s
        truth_cfo = float(trajectory.cfo_hz(reference_time_s))
        coarse_seed = float(np.rint(truth_cfo / 750.0) * 750.0)
        absolute_start = absolute_span_start_sample + local_start
        if local_start < 1 or local_start + frame_content + 1 > values.size:
            output.append(
                _incomplete_frame(
                    config,
                    frame_index=frame_index,
                    local_start=local_start,
                    absolute_start=absolute_start,
                    reference_time_s=reference_time_s,
                    occupied=bool(occupancy[frame_index]),
                    coarse_seed=coarse_seed,
                    truth_cfo=truth_cfo,
                )
            )
            continue
        guarded = values[local_start - 1 : local_start + frame_content + 1]
        profile = evaluate_edge_pilot_frame_cfo_likelihood(
            guarded,
            config.sample_rate_hz,
            frame_start_sample=absolute_start,
            acquisition_absolute_cfo_hz=coarse_seed,
            edge="lower",
            residual_grid_hz=grid,
            config=estimator_config,
        )
        split = profile.split_validation
        if profile.status is not NumericalStatus.COMPLETE:
            output.append(
                _incomplete_frame(
                    config,
                    frame_index=frame_index,
                    local_start=local_start,
                    absolute_start=absolute_start,
                    reference_time_s=reference_time_s,
                    occupied=bool(occupancy[frame_index]),
                    coarse_seed=coarse_seed,
                    truth_cfo=truth_cfo,
                )
            )
            continue
        profile_maxima = tuple(
            float(np.max(curve))
            for curve in (
                profile.even_exact_log_likelihood,
                profile.even_control_log_likelihood,
                profile.odd_exact_log_likelihood,
                profile.odd_control_log_likelihood,
            )
        )
        output.append(
            FrameCfoEvidence(
                scenario_id=config.scenario_id,
                frame_index=frame_index,
                local_frame_start_sample=local_start,
                absolute_frame_start_sample=absolute_start,
                reference_time_s=reference_time_s,
                occupied=bool(occupancy[frame_index]),
                status=profile.status.value,
                training_supported=split.training_supported,
                training_rejection_reasons=split.training_rejection_reasons,
                coarse_seed_hz=coarse_seed,
                alias_label_hz=0.0,
                even_canonical_cfo_hz=split.even_absolute_cfo_hz,
                odd_canonical_cfo_hz=split.odd_absolute_cfo_hz,
                even_frequency_uncertainty_hz=split.even_frequency_uncertainty_hz,
                odd_frequency_uncertainty_hz=split.odd_frequency_uncertainty_hz,
                even_exact_coherence=split.even_exact_coherence,
                even_control_coherence=split.even_control_coherence,
                even_coherence_margin=split.even_coherence_margin,
                even_exact_profile_max=profile_maxima[0],
                even_control_profile_max=profile_maxima[1],
                odd_exact_profile_max=profile_maxima[2],
                odd_control_profile_max=profile_maxima[3],
                even_profile_margin=profile_maxima[0] - profile_maxima[1],
                odd_profile_margin=profile_maxima[2] - profile_maxima[3],
                even_search_boundary=split.even_search_boundary,
                odd_search_boundary=split.odd_search_boundary,
                receiver_truth_cfo_hz=truth_cfo,
                physical_truth_cfo_hz=truth_cfo,
            )
        )
    return tuple(output)


def _incomplete_frame(
    config: TrajectoryQinInjectionConfig,
    *,
    frame_index: int,
    local_start: int,
    absolute_start: int,
    reference_time_s: float,
    occupied: bool,
    coarse_seed: float,
    truth_cfo: float,
) -> FrameCfoEvidence:
    return FrameCfoEvidence(
        scenario_id=config.scenario_id,
        frame_index=frame_index,
        local_frame_start_sample=local_start,
        absolute_frame_start_sample=absolute_start,
        reference_time_s=reference_time_s,
        occupied=occupied,
        status="incomplete_guard",
        training_supported=False,
        training_rejection_reasons=("guarded_frame_outside_frozen_span",),
        coarse_seed_hz=coarse_seed,
        alias_label_hz=0.0,
        even_canonical_cfo_hz=None,
        odd_canonical_cfo_hz=None,
        even_frequency_uncertainty_hz=None,
        odd_frequency_uncertainty_hz=None,
        even_exact_coherence=None,
        even_control_coherence=None,
        even_coherence_margin=None,
        even_exact_profile_max=None,
        even_control_profile_max=None,
        odd_exact_profile_max=None,
        odd_control_profile_max=None,
        even_profile_margin=None,
        odd_profile_margin=None,
        even_search_boundary=False,
        odd_search_boundary=False,
        receiver_truth_cfo_hz=truth_cfo,
        physical_truth_cfo_hz=truth_cfo,
    )
