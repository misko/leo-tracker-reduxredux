#!/usr/bin/env python3
"""Benchmark the legacy per-CFO and batched folded-anchor acquisition kernels."""

from __future__ import annotations

import argparse
import json
import platform
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np

import leo.analysis.starlink.acquisition as acquisition
from leo.analysis.starlink.acquisition import (
    DEFAULT_ANCHOR_SYMBOLS,
    ReceiverFrequencyCalibration,
    SymbolwiseAcquisitionConfig,
    _cached_dense_rotation_bank,
    _folded_anchor_score_grid_native,
    _folded_anchor_scores_derotated_native,
    _power_prefix,
    acquire_symbolwise,
)
from leo.analysis.starlink.templates import qin_edge_pilot_frame
from leo.contracts.digests import canonical_digest

SAMPLE_RATE_HZ = 2_500_000
SAMPLE_COUNT = 50_000


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--seed", type=int, default=0xC0A25E)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def _grid(step_hz: float) -> tuple[float, ...]:
    return tuple(float(value) for value in np.arange(-400_000.0, 400_000.0 + step_hz, step_hz))


def _legacy_grid(
    values: np.ndarray,
    template: np.ndarray,
    sample_rate_hz: float,
    absolute_cfo_hz: tuple[float, ...],
    symbols: tuple[int, ...],
    epoch_count: int,
) -> tuple[np.ndarray, ...]:
    rotation = _cached_dense_rotation_bank(
        float(sample_rate_hz), values.size, tuple(float(value) for value in absolute_cfo_hz)
    )
    power_prefix = _power_prefix(values)
    return tuple(
        _folded_anchor_scores_derotated_native(
            values * rotation[index],
            template,
            sample_rate_hz,
            symbols,
            epoch_count,
            power_prefix=power_prefix,
        )
        for index in range(len(absolute_cfo_hz))
    )


def _timing(function: Callable[[], Any], repeats: int) -> tuple[Any, dict[str, Any]]:
    function()
    wall_ms = []
    cpu_ms = []
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


def _grid_delta(expected: tuple[np.ndarray, ...], actual: tuple[np.ndarray, ...]) -> dict[str, Any]:
    expected_values = np.asarray(expected)
    actual_values = np.asarray(actual)
    return {
        "shape": list(actual_values.shape),
        "maximum_absolute_score_delta": float(np.max(np.abs(actual_values - expected_values))),
        "argmax_mismatch_count": sum(
            int(np.argmax(left)) != int(np.argmax(right))
            for left, right in zip(expected_values, actual_values, strict=True)
        ),
    }


def _acquisition_delta(expected: Any, actual: Any) -> dict[str, Any]:
    expected_rows = [asdict(candidate) for candidate in expected.candidates]
    actual_rows = [asdict(candidate) for candidate in actual.candidates]
    return {
        "candidate_count": len(actual_rows),
        "rank_or_epoch_mismatch_count": sum(
            left["rank"] != right["rank"]
            or left["refined_epoch_sample"] != right["refined_epoch_sample"]
            for left, right in zip(expected_rows, actual_rows, strict=True)
        ),
        "maximum_absolute_residual_cfo_delta_hz": max(
            (
                abs(left["residual_cfo_hz"] - right["residual_cfo_hz"])
                for left, right in zip(expected_rows, actual_rows, strict=True)
            ),
            default=0.0,
        ),
        "maximum_absolute_margin_delta": max(
            (
                abs(left["verify_minus_control_margin"] - right["verify_minus_control_margin"])
                for left, right in zip(expected_rows, actual_rows, strict=True)
            ),
            default=0.0,
        ),
    }


def main() -> None:
    args = _arguments()
    if not 3 <= args.repeats <= 100:
        raise ValueError("repeats must lie in 3..100")
    generator = np.random.default_rng(args.seed)
    values = np.asarray(
        generator.normal(size=SAMPLE_COUNT) + 1j * generator.normal(size=SAMPLE_COUNT),
        np.complex128,
    )
    template = np.asarray(qin_edge_pilot_frame(SAMPLE_RATE_HZ, "lower"), np.complex128)
    epoch_count = round(SAMPLE_RATE_HZ / 750.0)
    kernel_results = {}
    for key, step_hz in (("standard", 80_000.0), ("research", 10_000.0)):
        cfo_grid = _grid(step_hz)
        legacy, legacy_timing = _timing(
            lambda cfo_grid=cfo_grid: _legacy_grid(
                values,
                template,
                SAMPLE_RATE_HZ,
                cfo_grid,
                DEFAULT_ANCHOR_SYMBOLS,
                epoch_count,
            ),
            args.repeats,
        )
        batched, batched_timing = _timing(
            lambda cfo_grid=cfo_grid: _folded_anchor_score_grid_native(
                values,
                template,
                SAMPLE_RATE_HZ,
                cfo_grid,
                DEFAULT_ANCHOR_SYMBOLS,
                epoch_count,
            ),
            args.repeats,
        )
        kernel_results[key] = {
            "coarse_cfo_step_hz": step_hz,
            "coarse_cfo_bin_count": len(cfo_grid),
            "legacy": legacy_timing,
            "batched": batched_timing,
            "wall_speedup": legacy_timing["median_wall_ms"] / batched_timing["median_wall_ms"],
            "equivalence": _grid_delta(legacy, batched),
        }

    calibration = ReceiverFrequencyCalibration(
        "coarse-kernel-benchmark",
        0.0,
        canonical_digest({"benchmark": "coarse-folded-anchor-batch-v1"}).removeprefix("sha256:"),
    )
    acquisition_results = {}
    acquisition_configs = {
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
    for key, config in acquisition_configs.items():
        with patch.object(acquisition, "_folded_anchor_score_grid", _legacy_grid):
            legacy_acquisition, legacy_acquisition_timing = _timing(
                lambda config=config: acquire_symbolwise(
                    values,
                    SAMPLE_RATE_HZ,
                    calibration,
                    edge="lower",
                    config=config,
                ),
                args.repeats,
            )
        batched_acquisition, batched_acquisition_timing = _timing(
            lambda config=config: acquire_symbolwise(
                values,
                SAMPLE_RATE_HZ,
                calibration,
                edge="lower",
                config=config,
            ),
            args.repeats,
        )
        acquisition_results[key] = {
            "legacy": legacy_acquisition_timing,
            "batched": batched_acquisition_timing,
            "wall_speedup": legacy_acquisition_timing["median_wall_ms"]
            / batched_acquisition_timing["median_wall_ms"],
            "equivalence": _acquisition_delta(legacy_acquisition, batched_acquisition),
        }
    document = {
        "schema": "org.leo.benchmark.coarse-folded-anchor-batch/v1",
        "python": platform.python_version(),
        "numpy": np.__version__,
        "machine": platform.machine(),
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "sample_count": SAMPLE_COUNT,
        "anchor_symbol_count": len(DEFAULT_ANCHOR_SYMBOLS),
        "repeats": args.repeats,
        "seed": args.seed,
        "kernels": kernel_results,
        "acquisitions": acquisition_results,
    }
    encoded = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()
