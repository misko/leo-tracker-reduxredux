#!/usr/bin/env python3
"""Benchmark exact GLRT execution backends without changing production dispatch."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import platform
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np

import leo.analysis.starlink.acquisition as acquisition
import leo.analysis.starlink.pilot_methods as pilot_methods
from leo.analysis.starlink.acquisition import (
    DEFAULT_ACQUIRE_SYMBOLS,
    DEFAULT_ANCHOR_SYMBOLS,
    ReceiverFrequencyCalibration,
    SymbolwiseAcquisitionConfig,
    acquire_symbolwise,
)
from leo.analysis.starlink.pilot_methods import _SymbolCorrelations
from leo.analysis.starlink.templates import StarlinkEdge, qin_edge_pilot_frame
from leo.contracts.digests import canonical_digest

SAMPLE_RATE_HZ = 2_500_000
SAMPLE_COUNT = 50_000
EPOCH_SAMPLE = 347
SEED = 0xC0A25E


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--core-label", default="unlabelled")
    parser.add_argument("--native-extension", type=Path)
    parser.add_argument("--prototype-native-extension", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def _timing(function: Callable[[], Any], repeats: int) -> tuple[Any, dict[str, Any]]:
    function()
    wall_ms: list[float] = []
    cpu_ms: list[float] = []
    selected = None
    for _ in range(repeats):
        cpu_started = time.process_time_ns()
        wall_started = time.perf_counter_ns()
        selected = function()
        wall_ms.append((time.perf_counter_ns() - wall_started) / 1_000_000)
        cpu_ms.append((time.process_time_ns() - cpu_started) / 1_000_000)
    return selected, {
        "wall_ms": wall_ms,
        "process_cpu_ms": cpu_ms,
        "median_wall_ms": float(np.median(wall_ms)),
        "p95_wall_ms": float(np.percentile(wall_ms, 95)),
        "minimum_wall_ms": min(wall_ms),
        "median_process_cpu_ms": float(np.median(cpu_ms)),
    }


def _comparison(
    baseline: Callable[[], Any],
    prototype: Callable[[], Any],
    repeats: int,
    delta: Callable[[Any, Any], dict[str, Any]],
) -> dict[str, Any]:
    expected, baseline_timing = _timing(baseline, repeats)
    actual, prototype_timing = _timing(prototype, repeats)
    return {
        "baseline": baseline_timing,
        "prototype": prototype_timing,
        "wall_speedup": baseline_timing["median_wall_ms"] / prototype_timing["median_wall_ms"],
        "equivalence": delta(expected, actual),
    }


def _sequence_delta(expected: Any, actual: Any) -> dict[str, Any]:
    expected_values = np.asarray(expected)
    actual_values = np.asarray(actual)
    return {
        "shape": list(actual_values.shape),
        "maximum_absolute_delta": float(
            np.max(np.abs(expected_values - actual_values), initial=0.0)
        ),
        "argmax_match": int(np.argmax(expected_values)) == int(np.argmax(actual_values)),
    }


def _acquisition_delta(expected: Any, actual: Any) -> dict[str, Any]:
    expected_rows = [asdict(candidate) for candidate in expected.candidates]
    actual_rows = [asdict(candidate) for candidate in actual.candidates]
    paired = tuple(zip(expected_rows, actual_rows, strict=False))
    return {
        "status_match": expected.status == actual.status,
        "candidate_count": len(actual_rows),
        "candidate_count_match": len(expected_rows) == len(actual_rows),
        "rank_or_epoch_mismatch_count": sum(
            left["rank"] != right["rank"]
            or left["coarse_epoch_sample"] != right["coarse_epoch_sample"]
            or left["refined_epoch_sample"] != right["refined_epoch_sample"]
            for left, right in paired
        ),
        "maximum_absolute_residual_cfo_delta_hz": max(
            (abs(left["residual_cfo_hz"] - right["residual_cfo_hz"]) for left, right in paired),
            default=0.0,
        ),
        "maximum_absolute_margin_delta": max(
            (
                abs(left["verify_minus_control_margin"] - right["verify_minus_control_margin"])
                for left, right in paired
            ),
            default=0.0,
        ),
    }


def _glrt_delta(expected: Any, actual: Any) -> dict[str, Any]:
    expected_values = np.asarray(expected, dtype=float)
    actual_values = np.asarray(actual, dtype=float)
    return {
        "maximum_absolute_score_delta": float(
            np.max(np.abs(expected_values[:, 0] - actual_values[:, 0]), initial=0.0)
        ),
        "winner_cfo_match": bool(np.array_equal(expected_values[:, 1], actual_values[:, 1])),
    }


def _workspace_delta(expected: Any, actual: Any) -> dict[str, Any]:
    arrays = (
        "exact_values",
        "exact_power",
        "control_values",
        "control_power",
        "times_s",
    )
    maximum = 0.0
    for name in arrays:
        for left, right in zip(getattr(expected, name), getattr(actual, name), strict=True):
            maximum = max(
                maximum,
                float(np.max(np.abs(np.asarray(left) - np.asarray(right)), initial=0.0)),
            )
    return {
        "maximum_absolute_array_delta": maximum,
        "valid_rows_exact_match": all(
            np.array_equal(left, right)
            for left, right in zip(expected.valid_rows, actual.valid_rows, strict=True)
        ),
    }


def _detection_delta(expected: Any, actual: Any) -> dict[str, Any]:
    score_pairs = tuple(
        (left_score, right_score)
        for left_candidate, right_candidate in zip(
            expected.candidates, actual.candidates, strict=False
        )
        for left_score, right_score in zip(
            left_candidate.scores, right_candidate.scores, strict=False
        )
    )
    return {
        "status_match": expected.status == actual.status,
        "candidate_count": len(actual.candidates),
        "candidate_count_match": len(expected.candidates) == len(actual.candidates),
        "epoch_mismatch_count": sum(
            left.local_epoch_sample != right.local_epoch_sample
            for left, right in zip(expected.candidates, actual.candidates, strict=False)
        ),
        "maximum_absolute_acquired_cfo_delta_hz": max(
            (
                abs(left.acquired_cfo_hz - right.acquired_cfo_hz)
                for left, right in zip(expected.candidates, actual.candidates, strict=False)
            ),
            default=0.0,
        ),
        "method_mismatch_count": sum(left.method != right.method for left, right in score_pairs),
        "maximum_absolute_score_delta": max(
            (abs(left.exact_score - right.exact_score) for left, right in score_pairs),
            default=0.0,
        ),
        "maximum_absolute_margin_delta": max(
            (abs(left.margin - right.margin) for left, right in score_pairs),
            default=0.0,
        ),
        "maximum_absolute_tracking_cfo_delta_hz": max(
            (abs(left.tracking_cfo_hz - right.tracking_cfo_hz) for left, right in score_pairs),
            default=0.0,
        ),
    }


def _local_peak_indexes_vectorized(scores: np.ndarray) -> tuple[int, ...]:
    """Vectorized form of the production plateau-aware local-maximum rule."""

    values = np.asarray(scores)
    if values.size == 0:
        return ()
    if values.size == 1:
        return (0,) if values[0] > 0 else ()
    left = np.empty_like(values)
    right = np.empty_like(values)
    left[0] = -math.inf
    left[1:] = values[:-1]
    right[-1] = -math.inf
    right[:-1] = values[1:]
    selected = (values >= left) & (values >= right) & ((values > left) | (values > right))
    return tuple(int(index) for index in np.flatnonzero(selected))


def _received_frames(
    values: np.ndarray,
    sample_indexes: np.ndarray,
    epoch_sample: int,
    period: float,
) -> tuple[np.ndarray, list[np.ndarray]]:
    frames: list[np.ndarray] = []
    frame = 0
    while True:
        start = epoch_sample + round(frame * period)
        absolute = start + sample_indexes
        if absolute[-1] >= values.size:
            break
        frames.append(values[absolute])
        frame += 1
    return sample_indexes, frames


def _normalized_frame_scores_factored(
    values: np.ndarray,
    template: np.ndarray,
    sample_rate_hz: float,
    epoch_sample: int,
    absolute_cfo_hz: tuple[float, ...],
    symbols: tuple[int, ...],
) -> tuple[float, ...]:
    """Direct exact grid using a factored base phase and BLAS matrix product."""

    if not absolute_cfo_hz:
        return ()
    sample_indexes = acquisition._pilot_sample_indexes(sample_rate_hz, symbols)
    references = template[sample_indexes]
    _, frames = _received_frames(
        values,
        sample_indexes,
        epoch_sample,
        sample_rate_hz / acquisition.FRAME_RATE_HZ,
    )
    if not frames:
        return tuple(0.0 for _ in absolute_cfo_hz)
    received = np.stack(frames, axis=0)
    template_energy = float(np.vdot(references, references).real)
    denominators = np.sqrt(template_energy * np.sum(np.abs(received) ** 2, axis=1))
    step = acquisition._constant_grid_step(absolute_cfo_hz)
    if step is None:
        rotation = np.exp(
            (-2j * np.pi * np.asarray(absolute_cfo_hz)[:, None])
            * sample_indexes[None, :]
            / sample_rate_hz
        )
        correlations = rotation @ (received * np.conj(references)[None, :]).T
    else:
        base = np.exp(-2j * np.pi * absolute_cfo_hz[0] * sample_indexes / sample_rate_hz)
        offsets = acquisition._cached_normalized_offset_rotation(
            float(sample_rate_hz), symbols, len(absolute_cfo_hz), step
        )
        correlations = offsets @ (received * np.conj(references)[None, :] * base).T
    scores = np.divide(
        np.abs(correlations),
        denominators[None, :],
        out=np.zeros_like(correlations.real),
        where=denominators[None, :] > 0,
    )
    return tuple(float(value) for value in np.mean(scores, axis=1))


def _normalized_frame_scores_adaptive(
    values: np.ndarray,
    template: np.ndarray,
    sample_rate_hz: float,
    epoch_sample: int,
    absolute_cfo_hz: tuple[float, ...],
    symbols: tuple[int, ...],
) -> tuple[float, ...]:
    # The study deliberately tests only the observed production crossover:
    # Research's 201-bin grid uses GEMM; Standard's 321-bin grid retains FFT.
    if len(absolute_cfo_hz) <= 256:
        return _normalized_frame_scores_factored(
            values,
            template,
            sample_rate_hz,
            epoch_sample,
            absolute_cfo_hz,
            symbols,
        )
    return _PRODUCTION_NORMALIZED_FRAME_SCORES(
        values,
        template,
        sample_rate_hz,
        epoch_sample,
        absolute_cfo_hz,
        symbols,
    )


def _conditioned_frame_scores_factored(
    values: np.ndarray,
    template: np.ndarray,
    sample_rate_hz: float,
    epoch_sample: int,
    absolute_cfo_hz: tuple[float, ...],
) -> tuple[float, ...]:
    """Whole-frame exact grid using a factored base phase and BLAS product."""

    if not absolute_cfo_hz:
        return ()
    indexes = np.arange(template.size, dtype=float)
    _, segments = _received_frames(
        values,
        indexes.astype(np.intp),
        epoch_sample,
        sample_rate_hz / acquisition.FRAME_RATE_HZ,
    )
    if not segments:
        return tuple(0.0 for _ in absolute_cfo_hz)
    received = np.stack(segments, axis=0)
    template_energy = float(np.vdot(template, template).real)
    denominators = np.sqrt(template_energy * np.sum(np.abs(received) ** 2, axis=1))
    step = acquisition._constant_grid_step(absolute_cfo_hz)
    if step is None:
        rotation = np.exp(
            (-2j * np.pi * np.asarray(absolute_cfo_hz)[:, None]) * indexes[None, :] / sample_rate_hz
        )
        correlations = rotation @ (received * np.conj(template)[None, :]).T
    else:
        base = np.exp(-2j * np.pi * absolute_cfo_hz[0] * indexes / sample_rate_hz)
        offsets = acquisition._cached_conditioned_offset_rotation(
            float(sample_rate_hz), template.size, len(absolute_cfo_hz), step
        )
        correlations = offsets @ (received * np.conj(template)[None, :] * base).T
    scores = np.divide(
        np.abs(correlations),
        denominators[None, :],
        out=np.zeros_like(correlations.real),
        where=denominators[None, :] > 0,
    )
    return tuple(float(value) for value in np.mean(scores, axis=1))


def _glrt_pair_autocorrelation(
    exact: _SymbolCorrelations,
    control: _SymbolCorrelations,
    *,
    size: int = 512,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Evaluate a GLRT from summed short autocorrelations and two final FFTs."""

    pilot_methods._validate_glrt_pair(exact, control)
    if not exact.values.size:
        return (0.0, 0.0), (0.0, 0.0)
    if not pilot_methods._uniform_glrt_geometry(exact, size=size):
        raise ValueError("GLRT symbol geometry is not a supported uniform grid")
    symbol_count = exact.values.shape[1]
    short_size = 1 << (2 * symbol_count - 2).bit_length()
    combined = np.concatenate((exact.values, control.values), axis=0)
    short = np.fft.fft(combined, n=short_size, axis=1)
    frame_count = exact.values.shape[0]
    grid = np.fft.fftfreq(size, d=exact.symbol_step_s)

    def evaluate(values: np.ndarray, transformed: np.ndarray) -> tuple[float, float]:
        autocorrelation = np.fft.ifft(np.sum(np.abs(transformed) ** 2, axis=0))
        packed = np.zeros(size, dtype=np.complex128)
        packed[:symbol_count] = autocorrelation[:symbol_count]
        if symbol_count > 1:
            packed[-(symbol_count - 1) :] = autocorrelation[-(symbol_count - 1) :]
        spectrum = np.fft.fft(packed).real
        ceiling = pilot_methods._coherent_ceiling(values)
        normalized = spectrum / ceiling if ceiling > 0 else spectrum
        best = int(np.argmax(normalized))
        return float(normalized[best]), float(grid[best])

    return (
        evaluate(exact.values, short[:frame_count]),
        evaluate(control.values, short[frame_count:]),
    )


def _conditioned_correlation_workspace_factored(
    samples: np.ndarray,
    sample_rate_hz: int,
    epoch_sample: int,
    cfo_hz: float,
    *,
    edge: StarlinkEdge,
    selected_symbols: np.ndarray | None = None,
) -> Any:
    """Workspace prototype factoring frame-common CFO phase from sample phases."""

    first_symbol = pilot_methods._FIRST_PILOT_SYMBOL
    last_symbol = pilot_methods._LAST_PILOT_SYMBOL
    exact_template = np.asarray(qin_edge_pilot_frame(sample_rate_hz, edge), np.complex128)
    control_template = np.asarray(
        qin_edge_pilot_frame(
            sample_rate_hz,
            edge,
            symbol_roll=pilot_methods.CONTROL_SYMBOL_ROLL,
        ),
        np.complex128,
    )
    frame_period = sample_rate_hz / pilot_methods.FRAME_RATE_HZ
    symbol_period = sample_rate_hz * pilot_methods.OFDM_SYMBOL_DURATION_S
    symbols = np.arange(first_symbol, last_symbol + 1)
    selected = symbols if selected_symbols is None else np.asarray(selected_symbols, dtype=int)
    if (
        selected.ndim != 1
        or not selected.size
        or np.any(np.diff(selected) <= 0)
        or selected[0] < first_symbol
        or selected[-1] > last_symbol
    ):
        raise ValueError("selected workspace symbols must be unique, ordered, and supported")
    selected_positions = selected - first_symbol
    local_starts = np.rint(symbols * symbol_period).astype(int)
    local_stops = np.minimum(
        np.rint((symbols + 1) * symbol_period).astype(int), len(exact_template)
    )
    counts = local_stops - local_starts
    frame_starts: list[int] = []
    frame = 0
    while True:
        frame_start = epoch_sample + round(frame * frame_period)
        if frame_start >= len(samples) or frame_start + local_starts[0] >= len(samples):
            break
        frame_starts.append(frame_start)
        frame += 1
    shape = (len(frame_starts), len(symbols))
    exact_matrix = np.zeros(shape, np.complex128)
    exact_power_matrix = np.zeros(shape, float)
    control_matrix = np.zeros(shape, np.complex128)
    control_power_matrix = np.zeros(shape, float)
    time_matrix = np.zeros(shape, float)
    valid_matrix = np.zeros(shape, bool)

    for count in np.unique(counts[selected_positions]):
        if count < 2:
            continue
        positions = selected_positions[counts[selected_positions] == count]
        relative = local_starts[positions, None] + np.arange(int(count))[None, :]
        relative_rotation = np.exp(-2j * np.pi * cfo_hz * relative / sample_rate_hz)
        exact_reference = exact_template[relative]
        control_reference = control_template[relative]
        exact_energy = np.sum(np.abs(exact_reference) ** 2, axis=1)
        control_energy = np.sum(np.abs(control_reference) ** 2, axis=1)
        for frame_index, frame_start in enumerate(frame_starts):
            starts = frame_start + local_starts[positions]
            valid = (starts >= 0) & (starts + count <= len(samples))
            if not np.any(valid):
                continue
            active_positions = positions[valid]
            absolute = frame_start + relative[valid]
            frame_rotation = np.exp(-2j * np.pi * cfo_hz * frame_start / sample_rate_hz)
            received = samples[absolute]
            corrected = received * relative_rotation[valid] * frame_rotation
            received_energy = np.sum(np.abs(received) ** 2, axis=1)
            exact_correlation = np.sum(np.conj(exact_reference[valid]) * corrected, axis=1)
            control_correlation = np.sum(np.conj(control_reference[valid]) * corrected, axis=1)
            exact_matrix[frame_index, active_positions] = exact_correlation
            control_matrix[frame_index, active_positions] = control_correlation
            exact_power_matrix[frame_index, active_positions] = np.abs(
                exact_correlation
            ) ** 2 / np.maximum(exact_energy[valid] * received_energy, 1e-20)
            control_power_matrix[frame_index, active_positions] = np.abs(
                control_correlation
            ) ** 2 / np.maximum(control_energy[valid] * received_energy, 1e-20)
            time_matrix[frame_index, active_positions] = (
                starts[valid] + (count - 1) / 2
            ) / sample_rate_hz
            valid_matrix[frame_index, active_positions] = True

    return pilot_methods._ConditionedCorrelationWorkspace(
        tuple(exact_matrix[:, index].copy() for index in range(len(symbols))),
        tuple(exact_power_matrix[:, index].copy() for index in range(len(symbols))),
        tuple(control_matrix[:, index].copy() for index in range(len(symbols))),
        tuple(control_power_matrix[:, index].copy() for index in range(len(symbols))),
        tuple(time_matrix[:, index].copy() for index in range(len(symbols))),
        tuple(valid_matrix[:, index].copy() for index in range(len(symbols))),
    )


_PRODUCTION_NORMALIZED_FRAME_SCORES = acquisition._normalized_frame_scores
_PRODUCTION_FOLDED_ANCHOR_SCORE_GRID = acquisition._folded_anchor_score_grid
_PROTOTYPE_NATIVE_EXTENSION = acquisition._native_acquisition


def _folded_anchor_score_grid_padded(
    values: np.ndarray,
    template: np.ndarray,
    sample_rate_hz: float,
    absolute_cfo_hz: tuple[float, ...],
    symbols: tuple[int, ...],
    epoch_count: int,
) -> tuple[np.ndarray, ...]:
    """Pad the 11-bin Standard execution bank to 12 SIMD-friendly lanes."""

    if len(absolute_cfo_hz) == 11 and acquisition._native_acquisition is not None:
        step = acquisition._constant_grid_step(absolute_cfo_hz)
        if step is not None:
            padded = (*absolute_cfo_hz, absolute_cfo_hz[-1] + step)
            return acquisition._folded_anchor_score_grid_native(
                values,
                template,
                sample_rate_hz,
                padded,
                symbols,
                epoch_count,
            )[: len(absolute_cfo_hz)]
    return _PRODUCTION_FOLDED_ANCHOR_SCORE_GRID(
        values,
        template,
        sample_rate_hz,
        absolute_cfo_hz,
        symbols,
        epoch_count,
    )


def _prototype_acquisition(
    values: np.ndarray,
    calibration: ReceiverFrequencyCalibration,
    config: SymbolwiseAcquisitionConfig,
) -> Any:
    with (
        patch.object(acquisition, "_native_acquisition", _PROTOTYPE_NATIVE_EXTENSION),
        patch.object(
            acquisition,
            "_folded_anchor_score_grid",
            _folded_anchor_score_grid_padded,
        ),
        patch.object(acquisition, "_local_peak_indexes", _local_peak_indexes_vectorized),
        patch.object(
            acquisition,
            "_conditioned_frame_scores",
            _conditioned_frame_scores_factored,
        ),
        patch.object(
            acquisition,
            "_normalized_frame_scores",
            _normalized_frame_scores_adaptive,
        ),
    ):
        return acquire_symbolwise(
            values,
            SAMPLE_RATE_HZ,
            calibration,
            edge=StarlinkEdge.LOWER,
            config=config,
        )


def _detect(
    values: np.ndarray,
    calibration: ReceiverFrequencyCalibration,
    config: SymbolwiseAcquisitionConfig,
    glrt_size: int,
) -> Any:
    return pilot_methods.detect_pilot_method_candidates(
        values,
        SAMPLE_RATE_HZ,
        sample_start=0,
        calibration=calibration,
        acquisition_config=config,
        edge=StarlinkEdge.LOWER,
        maximum_scored_candidates=config.retained_candidate_count,
        glrt_size=glrt_size,
    )


def _prototype_detector(
    values: np.ndarray,
    calibration: ReceiverFrequencyCalibration,
    config: SymbolwiseAcquisitionConfig,
    glrt_size: int,
) -> Any:
    with (
        patch.object(acquisition, "_native_acquisition", _PROTOTYPE_NATIVE_EXTENSION),
        patch.object(
            acquisition,
            "_folded_anchor_score_grid",
            _folded_anchor_score_grid_padded,
        ),
        patch.object(acquisition, "_local_peak_indexes", _local_peak_indexes_vectorized),
        patch.object(
            acquisition,
            "_conditioned_frame_scores",
            _conditioned_frame_scores_factored,
        ),
        patch.object(
            acquisition,
            "_normalized_frame_scores",
            _normalized_frame_scores_adaptive,
        ),
        patch.object(pilot_methods, "_glrt_pair", _glrt_pair_autocorrelation),
        patch.object(
            pilot_methods,
            "_conditioned_correlation_workspace",
            _conditioned_correlation_workspace_factored,
        ),
    ):
        return _detect(values, calibration, config, glrt_size)


def _lane_configs() -> dict[str, SymbolwiseAcquisitionConfig]:
    return {
        "standard": SymbolwiseAcquisitionConfig(
            retained_candidate_count=10,
            candidate_epoch_separation_samples=5,
            candidate_cfo_separation_hz=10_000.0,
            maximum_probe_samples=SAMPLE_COUNT,
        ),
        "research": SymbolwiseAcquisitionConfig(
            coarse_cfo_step_hz=10_000.0,
            fine_cfo_radius_hz=10_000.0,
            fine_cfo_step_hz=100.0,
            conditioned_cfo_radius_hz=1_000.0,
            conditioned_cfo_step_hz=25.0,
            retained_candidate_count=32,
            candidate_epoch_separation_samples=5,
            candidate_cfo_separation_hz=10_000.0,
            maximum_probe_samples=SAMPLE_COUNT,
        ),
    }


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                return line.split(":", maxsplit=1)[1].strip()
    except OSError:
        pass
    return platform.processor()


def _working_sets() -> dict[str, int]:
    complex_bytes = np.dtype(np.complex128).itemsize
    return {
        "probe_complex128_bytes": SAMPLE_COUNT * complex_bytes,
        "standard_fine_rotation_bank_bytes": 321 * 1_650 * complex_bytes,
        "research_fine_rotation_bank_bytes": 201 * 1_650 * complex_bytes,
        "standard_conditioned_rotation_bank_bytes": 41 * 3_333 * complex_bytes,
        "research_conditioned_rotation_bank_bytes": 81 * 3_333 * complex_bytes,
        "standard_fine_fft_scratch_bytes_15_frames": 15 * 5_000 * complex_bytes,
        "research_fine_fft_scratch_bytes_15_frames": 15 * 25_000 * complex_bytes,
    }


def _load_native_extension(path: Path) -> Any:
    resolved = path.resolve()
    spec = importlib.util.spec_from_file_location(
        "leo.analysis.starlink._native_acquisition", resolved
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load native extension from {resolved}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    acquisition._native_acquisition = module
    return module


def main() -> None:
    global _PROTOTYPE_NATIVE_EXTENSION

    args = _arguments()
    if not 3 <= args.repeats <= 100:
        raise ValueError("repeats must lie in 3..100")
    native_extension = (
        _load_native_extension(args.native_extension)
        if args.native_extension is not None
        else acquisition._native_acquisition
    )
    production_native_extension = acquisition._native_acquisition
    if args.prototype_native_extension is not None:
        _PROTOTYPE_NATIVE_EXTENSION = _load_native_extension(args.prototype_native_extension)
        acquisition._native_acquisition = production_native_extension
    else:
        _PROTOTYPE_NATIVE_EXTENSION = native_extension
    generator = np.random.default_rng(SEED)
    values = np.asarray(
        generator.normal(size=SAMPLE_COUNT) + 1j * generator.normal(size=SAMPLE_COUNT),
        np.complex128,
    )
    template = np.asarray(qin_edge_pilot_frame(SAMPLE_RATE_HZ, StarlinkEdge.LOWER), np.complex128)
    calibration = ReceiverFrequencyCalibration(
        "hardware-execution-benchmark",
        0.0,
        canonical_digest({"benchmark": "glrt-hardware-execution-v1"}).removeprefix("sha256:"),
    )
    lane_configs = _lane_configs()

    peak_scores = generator.normal(size=round(SAMPLE_RATE_HZ / 750.0))
    peak_iterations = 1_000
    peaks = _comparison(
        lambda: tuple(acquisition._local_peak_indexes(peak_scores) for _ in range(peak_iterations)),
        lambda: tuple(_local_peak_indexes_vectorized(peak_scores) for _ in range(peak_iterations)),
        args.repeats,
        lambda expected, actual: {"exact_match": expected == actual},
    )
    peaks["iterations_per_timing"] = peak_iterations

    workspace = pilot_methods._conditioned_correlation_workspace(
        values,
        SAMPLE_RATE_HZ,
        EPOCH_SAMPLE,
        12_345.5,
        edge=StarlinkEdge.LOWER,
    )
    glrt_values = workspace.select(np.arange(2, 66))
    glrt_control = workspace.select(np.arange(2, 66), control=True)
    workspace_symbols = np.unique(
        np.concatenate(
            (
                np.rint(np.linspace(2, 301, 8)).astype(int),
                np.arange(2, 66),
            )
        )
    )
    workspace_comparison = _comparison(
        lambda: pilot_methods._conditioned_correlation_workspace(
            values,
            SAMPLE_RATE_HZ,
            EPOCH_SAMPLE,
            12_345.5,
            edge=StarlinkEdge.LOWER,
            selected_symbols=workspace_symbols,
        ),
        lambda: _conditioned_correlation_workspace_factored(
            values,
            SAMPLE_RATE_HZ,
            EPOCH_SAMPLE,
            12_345.5,
            edge=StarlinkEdge.LOWER,
            selected_symbols=workspace_symbols,
        ),
        args.repeats,
        _workspace_delta,
    )

    lanes: dict[str, Any] = {}
    for lane, config in lane_configs.items():
        coarse_grid = tuple(
            float(value)
            for value in np.arange(
                config.residual_cfo_min_hz,
                config.residual_cfo_max_hz + config.coarse_cfo_step_hz,
                config.coarse_cfo_step_hz,
            )
        )
        epoch_count = round(SAMPLE_RATE_HZ / acquisition.FRAME_RATE_HZ)
        coarse_scores, coarse_timing = _timing(
            lambda coarse_grid=coarse_grid, epoch_count=epoch_count: (
                acquisition._folded_anchor_score_grid(
                    values,
                    template,
                    SAMPLE_RATE_HZ,
                    coarse_grid,
                    DEFAULT_ANCHOR_SYMBOLS,
                    epoch_count,
                )
            ),
            args.repeats,
        )
        fine_count = round(2 * config.fine_cfo_radius_hz / config.fine_cfo_step_hz) + 1
        fine_grid = tuple(
            -config.fine_cfo_radius_hz + index * config.fine_cfo_step_hz
            for index in range(fine_count)
        )
        conditioned_count = (
            round(2 * config.conditioned_cfo_radius_hz / config.conditioned_cfo_step_hz) + 1
        )
        conditioned_grid = tuple(
            -config.conditioned_cfo_radius_hz + index * config.conditioned_cfo_step_hz
            for index in range(conditioned_count)
        )
        glrt_size = 512 if lane == "standard" else 4_096
        fine = _comparison(
            lambda fine_grid=fine_grid: acquisition._normalized_frame_scores(
                values,
                template,
                SAMPLE_RATE_HZ,
                EPOCH_SAMPLE,
                fine_grid,
                DEFAULT_ACQUIRE_SYMBOLS,
            ),
            lambda fine_grid=fine_grid: _normalized_frame_scores_factored(
                values,
                template,
                SAMPLE_RATE_HZ,
                EPOCH_SAMPLE,
                fine_grid,
                DEFAULT_ACQUIRE_SYMBOLS,
            ),
            args.repeats,
            _sequence_delta,
        )
        conditioned = _comparison(
            lambda conditioned_grid=conditioned_grid: acquisition._conditioned_frame_scores(
                values,
                template,
                SAMPLE_RATE_HZ,
                EPOCH_SAMPLE,
                conditioned_grid,
            ),
            lambda conditioned_grid=conditioned_grid: _conditioned_frame_scores_factored(
                values,
                template,
                SAMPLE_RATE_HZ,
                EPOCH_SAMPLE,
                conditioned_grid,
            ),
            args.repeats,
            _sequence_delta,
        )
        glrt = _comparison(
            lambda glrt_size=glrt_size: pilot_methods._glrt_pair_fft(
                glrt_values, glrt_control, size=glrt_size
            ),
            lambda glrt_size=glrt_size: _glrt_pair_autocorrelation(
                glrt_values, glrt_control, size=glrt_size
            ),
            args.repeats,
            _glrt_delta,
        )
        complete_acquisition = _comparison(
            lambda config=config: acquire_symbolwise(
                values,
                SAMPLE_RATE_HZ,
                calibration,
                edge=StarlinkEdge.LOWER,
                config=config,
            ),
            lambda config=config: _prototype_acquisition(values, calibration, config),
            args.repeats,
            _acquisition_delta,
        )
        complete_detector = _comparison(
            lambda config=config, glrt_size=glrt_size: _detect(
                values, calibration, config, glrt_size
            ),
            lambda config=config, glrt_size=glrt_size: _prototype_detector(
                values, calibration, config, glrt_size
            ),
            args.repeats,
            _detection_delta,
        )
        lanes[lane] = {
            "configuration": asdict(config),
            "coarse_grid": {
                "bin_count": len(coarse_grid),
                "timing": coarse_timing,
                "maximum_score": float(np.max(np.asarray(coarse_scores))),
                "argmax_epochs": [int(np.argmax(row)) for row in coarse_scores],
            },
            "fine_grid": {
                "bin_count": fine_count,
                "production_backend": "exact FFT",
                "prototype_backend": "factored direct GEMM",
                **fine,
            },
            "conditioned_grid": {
                "bin_count": conditioned_count,
                **conditioned,
            },
            "glrt": {"transform_size": glrt_size, **glrt},
            "combined_acquisition": complete_acquisition,
            "combined_detector": complete_detector,
        }

    document = {
        "schema": "org.leo.benchmark.glrt-hardware-execution/v1",
        "python": platform.python_version(),
        "numpy": np.__version__,
        "machine": platform.machine(),
        "cpu_model": _cpu_model(),
        "cpu_affinity": sorted(os.sched_getaffinity(0)),
        "core_label": args.core_label,
        "native_extension": None if native_extension is None else native_extension.__file__,
        "native_grid_backend": acquisition._folded_anchor_score_grid_backend(),
        "prototype_native_extension": (
            None if _PROTOTYPE_NATIVE_EXTENSION is None else _PROTOTYPE_NATIVE_EXTENSION.__file__
        ),
        "openblas_num_threads": os.environ.get("OPENBLAS_NUM_THREADS"),
        "omp_num_threads": os.environ.get("OMP_NUM_THREADS"),
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "sample_count": SAMPLE_COUNT,
        "repeats": args.repeats,
        "seed": SEED,
        "working_sets": _working_sets(),
        "local_peak_extraction": peaks,
        "conditioned_correlation_workspace": workspace_comparison,
        "lanes": lanes,
    }
    encoded = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()
