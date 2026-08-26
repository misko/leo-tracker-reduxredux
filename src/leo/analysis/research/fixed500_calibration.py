"""Frozen fixed-500-ms calibration and physical sample-clock kernels.

This module is intentionally infrastructure-free.  It expands a committed
factor table, injects a truly time-resampled repository Qin waveform, and
computes grouped calibration quantities.  Storage authorization and digest
verification remain the responsibility of the bounded report tool.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from leo.analysis.research.adaptive_frame_cfo import AdaptiveFrameCfoPoint
from leo.analysis.research.polynomial_injection import (
    FrameCfoEvidence,
    InjectionDiagnostics,
    occupied_frame_mask,
)
from leo.analysis.research.polynomial_injection_protocol import (
    InjectionScenario,
    PolynomialInjectionProtocol,
)
from leo.analysis.starlink.templates import qin_edge_pilot_frame, template_sha256

_SCHEMA = "org.leo.research.fixed500-calibration-protocol/v1"
_QIN_TEMPLATE_DIGEST = "15455635bcdcfe0747f686ae317d235b5dfa54ae49c76b9741e6acc889d8a657"


@dataclass(frozen=True, slots=True)
class FrozenCalibrationScenario:
    """One exact expanded row and its immutable calibration/evaluation role."""

    row_id: str
    split: str
    scenario: InjectionScenario


@dataclass(frozen=True, slots=True)
class ResampledInjectionDiagnostics:
    """Proof that both waveform and lattice used the physical clock scale."""

    base: InjectionDiagnostics
    clock_scale: float
    nominal_last_frame_start_sample: int
    resampled_last_frame_start_sample: int
    accumulated_lattice_shift_samples: int
    resampled_template_sample_count: int
    complete_occupied_frame_count: int


@dataclass(frozen=True, slots=True)
class PolynomialRatePoint:
    """One causal derivative from a fixed-history polynomial CFO fit."""

    frame_start_sample: int
    reference_time_s: float
    rate_hz_s: float | None
    rate_sigma_hz_s: float | None
    frame_count: int
    effective_frame_count: float
    status: str


def load_frozen_scenarios(
    path: Path,
    *,
    protocol: PolynomialInjectionProtocol,
) -> tuple[FrozenCalibrationScenario, ...]:
    """Expand and fail-close the committed 12-by-three factor design."""

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema") != _SCHEMA:
        raise ValueError("unsupported fixed500 calibration protocol")
    if raw.get("protocol_status") != "frozen_before_any_new_iq_read_or_outcome_scoring":
        raise ValueError("fixed500 calibration protocol was not frozen before scoring")
    authority = _mapping(raw.get("input_authority"), "input_authority")
    permitted = tuple(_string_sequence(authority.get("permitted_capture_ids")))
    background_ids = tuple(item.session_id for item in protocol.backgrounds)
    if permitted != background_ids or len(permitted) != 3:
        raise ValueError("fixed500 backgrounds differ from the frozen polynomial role")
    if any(
        authority.get(name) is not True
        for name in (
            "dynamic_discovery_forbidden",
            "capture_substitution_forbidden",
            "newer_pre_fix_holdout_and_capture_only_data_forbidden",
        )
    ):
        raise ValueError("fixed500 input authority is not deny-by-default")
    if authority.get("raw_iq_opened_for_this_experiment_before_freeze") is not False:
        raise ValueError("protocol does not attest a pre-IQ freeze")
    design = _mapping(raw.get("scenario_design"), "scenario_design")
    rows = design.get("design_rows")
    if not isinstance(rows, list) or len(rows) != 12:
        raise ValueError("fixed500 design must contain exactly twelve factor rows")
    output: list[FrozenCalibrationScenario] = []
    for background_index, background_id in enumerate(permitted):
        for row_index, item in enumerate(rows):
            row = _mapping(item, f"design_rows[{row_index}]")
            row_id = str(row.get("row_id"))
            split = str(row.get("split"))
            if row_id != f"{'C' if row_index < 6 else 'E'}{row_index % 6 + 1:02d}":
                raise ValueError("fixed500 design row order or identity differs")
            if split != ("calibration" if row_index < 6 else "evaluation"):
                raise ValueError("fixed500 split differs from row identity")
            scenario_id = f"F5-{background_index + 1}-{row_id}"
            scenario = InjectionScenario(
                scenario_id=scenario_id,
                background_session_id=background_id,
                seed=914_000 + 12 * background_index + row_index,
                rate_hz_s=_finite(row, "rate_hz_s"),
                acceleration_hz_s2=_finite(row, "acceleration_hz_s2"),
                jerk_hz_s3=_finite(row, "jerk_hz_s3"),
                snr_db=_finite(row, "snr_db"),
                frame_occupancy=_finite(row, "frame_occupancy"),
                alias_change_hz=_finite(row, "alias_change_hz"),
                cfo_step_hz=_finite(row, "cfo_step_hz"),
                sample_clock_offset_ppm=_finite(row, "sample_clock_offset_ppm"),
            )
            if not 0.0 < scenario.frame_occupancy <= 1.0:
                raise ValueError("frame occupancy lies outside (0, 1]")
            output.append(FrozenCalibrationScenario(row_id, split, scenario))
    if len(output) != int(design.get("scenario_count", -1)):
        raise ValueError("expanded fixed500 scenario count differs")
    return tuple(output)


def resampled_frame_starts(
    *, frame_count: int, sample_rate_hz: int, sample_clock_offset_ppm: float
) -> np.ndarray:
    """Map a physical 750-Hz frame lattice into receiver sample coordinates."""

    if frame_count < 1 or sample_rate_hz < 1:
        raise ValueError("frame count and sample rate must be positive")
    scale = clock_scale(sample_clock_offset_ppm)
    indexes = np.arange(frame_count, dtype=float)
    starts = np.rint(indexes * sample_rate_hz * scale / 750.0).astype(np.int64)
    if np.any(np.diff(starts) <= 0):
        raise ValueError("resampled frame lattice is not strictly increasing")
    return starts


def clock_scale(sample_clock_offset_ppm: float) -> float:
    """Return the finite positive receiver/physical clock scale."""

    if not math.isfinite(sample_clock_offset_ppm):
        raise ValueError("sample-clock offset must be finite")
    scale = 1.0 + sample_clock_offset_ppm * 1e-6
    if scale <= 0.0:
        raise ValueError("sample-clock scale must be positive")
    return scale


def inject_resampled_exact_qin(
    background: npt.ArrayLike,
    frozen: FrozenCalibrationScenario,
    protocol: PolynomialInjectionProtocol,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, ResampledInjectionDiagnostics]:
    """Inject Qin after resampling both its waveform and its frame lattice."""

    scenario = frozen.scenario
    values = np.asarray(background, dtype=np.complex64)
    binding = protocol.background(scenario.background_session_id)
    if values.ndim != 1 or values.size != binding.sample_count:
        raise ValueError("background must be the exact frozen span")
    if not np.all(np.isfinite(values)):
        raise ValueError("background contains non-finite values")
    template = qin_edge_pilot_frame(binding.sample_rate_hz, "lower")
    if template_sha256(template) != _QIN_TEMPLATE_DIGEST:
        raise ValueError("runtime Qin template differs from the frozen digest")
    scale = clock_scale(scenario.sample_clock_offset_ppm)
    source_coordinate = (
        np.arange(int(math.floor((template.size - 1) * scale)) + 1, dtype=float) / scale
    )
    resampled = np.asarray(
        np.interp(source_coordinate, np.arange(template.size), template.real)
        + 1j * np.interp(source_coordinate, np.arange(template.size), template.imag),
        dtype=np.complex64,
    )
    starts = resampled_frame_starts(
        frame_count=protocol.frame_count,
        sample_rate_hz=binding.sample_rate_hz,
        sample_clock_offset_ppm=scenario.sample_clock_offset_ppm,
    )
    nominal = resampled_frame_starts(
        frame_count=protocol.frame_count,
        sample_rate_hz=binding.sample_rate_hz,
        sample_clock_offset_ppm=0.0,
    )
    occupied = occupied_frame_mask(
        frame_count=protocol.frame_count,
        occupancy=scenario.frame_occupancy,
        seed=scenario.seed,
    )
    background_power = float(np.mean(np.abs(values.astype(np.complex128)) ** 2))
    template_power = float(np.mean(np.abs(resampled.astype(np.complex128)) ** 2))
    if background_power <= np.finfo(float).tiny or template_power <= np.finfo(float).tiny:
        raise ValueError("background and resampled template powers must be positive")
    amplitude = math.sqrt(background_power * 10.0 ** (scenario.snr_db / 10.0) / template_power)
    output = values.copy()
    complete = 0
    for frame_index in np.flatnonzero(occupied):
        start = int(starts[frame_index])
        stop = start + resampled.size
        if start < 0 or stop > output.size:
            continue
        receiver_time = (start + np.arange(resampled.size, dtype=float)) / binding.sample_rate_hz
        phase_cycles = _physical_phase_cycles(scenario, receiver_time, protocol)
        signal = amplitude * resampled * np.exp(2j * np.pi * phase_cycles)
        output[start:stop] += np.asarray(signal, dtype=np.complex64)
        complete += 1
    base = InjectionDiagnostics(
        background_power=background_power,
        template_power=template_power,
        amplitude_scale=amplitude,
        target_snr_db=scenario.snr_db,
        occupied_frame_count=int(np.sum(occupied)),
        opportunity_count=protocol.frame_count,
    )
    return (
        output,
        occupied,
        starts,
        ResampledInjectionDiagnostics(
            base=base,
            clock_scale=scale,
            nominal_last_frame_start_sample=int(nominal[-1]),
            resampled_last_frame_start_sample=int(starts[-1]),
            accumulated_lattice_shift_samples=int(starts[-1] - nominal[-1]),
            resampled_template_sample_count=int(resampled.size),
            complete_occupied_frame_count=complete,
        ),
    )


def causal_quadratic_rates(
    evidence: tuple[FrameCfoEvidence, ...],
    *,
    history_s: float = 0.5,
    minimum_frames: int = 24,
    minimum_effective_frames: float = 16.0,
    measurement_sigma_hz: float = 50.0,
    minimum_coverage: float = 0.95,
    huber_tuning: float = 1.345,
    maximum_iterations: int = 24,
) -> tuple[PolynomialRatePoint, ...]:
    """Fit a lean causal quadratic derivative on the even-supported history."""

    points = tuple(
        AdaptiveFrameCfoPoint(
            frame_start_sample=item.absolute_frame_start_sample,
            reference_time_s=item.reference_time_s,
            continuity_segment=0,
            even_cfo_hz=float(item.even_canonical_cfo_hz),
            even_cfo_sigma_hz=measurement_sigma_hz,
        )
        for item in evidence
        if item.training_supported and item.even_canonical_cfo_hz is not None
    )
    output: list[PolynomialRatePoint] = []
    for endpoint_index, endpoint in enumerate(points):
        window = tuple(
            item
            for item in points[: endpoint_index + 1]
            if item.reference_time_s >= endpoint.reference_time_s - history_s - 1e-12
        )
        span = window[-1].reference_time_s - window[0].reference_time_s
        if len(window) < minimum_frames or span + 1e-12 < history_s * minimum_coverage:
            output.append(_empty_polynomial_point(endpoint, len(window)))
            continue
        fit = _robust_polynomial_fit(
            window,
            order=2,
            huber_tuning=huber_tuning,
            maximum_iterations=maximum_iterations,
        )
        if fit is None or fit[2] + 1e-12 < minimum_effective_frames:
            output.append(_empty_polynomial_point(endpoint, len(window)))
            continue
        coefficients, covariance, effective = fit
        output.append(
            PolynomialRatePoint(
                frame_start_sample=endpoint.frame_start_sample,
                reference_time_s=endpoint.reference_time_s,
                rate_hz_s=float(coefficients[1]),
                rate_sigma_hz_s=float(math.sqrt(max(float(covariance[1, 1]), 0.0))),
                frame_count=len(window),
                effective_frame_count=effective,
                status="complete",
            )
        )
    return tuple(output)


def select_spaced_endpoints(
    frame_starts: npt.ArrayLike,
    reference_times_s: npt.ArrayLike,
    *,
    targets_s: tuple[float, ...] = (0.5, 1.0, 1.5),
) -> tuple[int, ...]:
    """Select the first supported frame at or after each frozen time target."""

    starts = np.asarray(frame_starts, dtype=np.int64)
    times = np.asarray(reference_times_s, dtype=float)
    if starts.ndim != 1 or times.shape != starts.shape or np.any(np.diff(times) <= 0.0):
        raise ValueError("endpoint inputs must be aligned and strictly increasing")
    output: list[int] = []
    for target in targets_s:
        indexes = np.flatnonzero(times >= target - 1e-12)
        if indexes.size:
            output.append(int(starts[int(indexes[0])]))
    return tuple(output)


def grouped_conformal_multiplier(
    scenario_standardized_maxima: npt.ArrayLike,
    *,
    confidence: float = 0.95,
) -> tuple[float, int]:
    """Return the frozen finite-sample grouped split-conformal quantile."""

    values = np.asarray(scenario_standardized_maxima, dtype=float)
    if values.ndim != 1 or values.size < 1 or not np.all(np.isfinite(values)):
        raise ValueError("grouped calibration scores must be a finite non-empty vector")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must lie in (0, 1)")
    order = min(int(math.ceil((values.size + 1) * confidence)), int(values.size))
    return float(np.partition(values, order - 1)[order - 1]), order


def _physical_phase_cycles(
    scenario: InjectionScenario,
    receiver_time_s: np.ndarray,
    protocol: PolynomialInjectionProtocol,
) -> np.ndarray:
    scale = clock_scale(scenario.sample_clock_offset_ppm)
    physical_time = (receiver_time_s - protocol.reference_time_s) / scale
    phase = (
        protocol.carrier_origin_hz * physical_time
        + 0.5 * scenario.rate_hz_s * physical_time**2
        + scenario.acceleration_hz_s2 * physical_time**3 / 6.0
        + scenario.jerk_hz_s3 * physical_time**4 / 24.0
    )
    physical_step_time = (protocol.cfo_step_time_s - protocol.reference_time_s) / scale
    phase += scenario.cfo_step_hz * np.maximum(physical_time - physical_step_time, 0.0)
    phase += scenario.alias_change_hz * np.maximum(
        receiver_time_s - protocol.alias_change_time_s, 0.0
    )
    return phase


def _robust_polynomial_fit(
    points: tuple[AdaptiveFrameCfoPoint, ...],
    *,
    order: int,
    huber_tuning: float,
    maximum_iterations: int,
) -> tuple[np.ndarray, np.ndarray, float] | None:
    reference = points[-1].reference_time_s
    times = np.asarray([item.reference_time_s - reference for item in points], dtype=float)
    values = np.asarray([item.even_cfo_hz for item in points], dtype=float)
    sigmas = np.asarray([item.even_cfo_sigma_hz for item in points], dtype=float)
    design = np.column_stack(tuple(times**power for power in range(order + 1)))
    precision = 1.0 / sigmas**2
    weights = np.ones(len(points), dtype=float)
    coefficients: np.ndarray | None = None
    for _ in range(maximum_iterations):
        normal = design.T @ ((precision * weights)[:, None] * design)
        if not np.all(np.isfinite(normal)) or np.linalg.cond(normal) > 1e14:
            return None
        updated = np.linalg.solve(normal, design.T @ (precision * weights * values))
        if coefficients is not None and np.max(np.abs(design @ (updated - coefficients))) <= 1e-6:
            coefficients = updated
            break
        coefficients = updated
        residual = values - design @ coefficients
        standardized = residual / sigmas
        scale = max(1.0, 1.4826 * float(np.median(np.abs(standardized - np.median(standardized)))))
        magnitude = np.abs(standardized) / scale
        weights = np.ones_like(magnitude)
        tail = magnitude > huber_tuning
        weights[tail] = huber_tuning / magnitude[tail]
    assert coefficients is not None
    residual = values - design @ coefficients
    standardized = residual / sigmas
    effective = float(np.sum(weights) ** 2 / np.sum(weights**2))
    degrees = max(float(np.sum(weights)) - design.shape[1], 1.0)
    reduced = float(np.sum(weights * standardized**2) / degrees)
    normal = design.T @ ((precision * weights)[:, None] * design)
    covariance = np.linalg.inv(normal) * max(1.0, reduced)
    return coefficients, covariance, effective


def _empty_polynomial_point(
    endpoint: AdaptiveFrameCfoPoint, frame_count: int
) -> PolynomialRatePoint:
    return PolynomialRatePoint(
        frame_start_sample=endpoint.frame_start_sample,
        reference_time_s=endpoint.reference_time_s,
        rate_hz_s=None,
        rate_sigma_hz_s=None,
        frame_count=frame_count,
        effective_frame_count=0.0,
        status="warmup",
    )


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _string_sequence(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("permitted capture IDs must be a string list")
    return tuple(value)


def _finite(row: dict[str, Any], name: str) -> float:
    value = row.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    output = float(value)
    if not math.isfinite(output):
        raise ValueError(f"{name} must be finite")
    return output
