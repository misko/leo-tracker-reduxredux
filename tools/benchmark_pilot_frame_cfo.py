#!/usr/bin/env python3
"""Bounded single-thread runtime benchmark for one-frame Qin CFO analysis."""

from __future__ import annotations

import argparse
import json
import os
import platform
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from leo.analysis.qam import estimate_edge_pilot_frame_cfo
from leo.analysis.qam.pilot import (
    _KnownPilotDemodulator,
    _maximize_frequency_likelihood,
    _refine_frequency_from_phase,
)
from leo.analysis.starlink import OFDM_SYMBOL_DURATION_S, StarlinkEdge, qin_edge_pilot_frame
from leo.analysis.starlink.templates import qin_edge_pilot_symbols

DEFAULT_OUTPUT = Path(
    "reports/figures/2026_08_24_frame_cfo_estimator_study/frame-cfo-runtime-benchmark.json"
)
THREAD_VARIABLES = (
    "OPENBLAS_NUM_THREADS",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def _timings(operation: Callable[[], Any], iterations: int) -> dict[str, float]:
    for _ in range(5):
        operation()
    values = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        operation()
        values.append((time.perf_counter_ns() - started) / 1e6)
    measured = np.asarray(values, dtype=float)
    return {
        "iteration_count": iterations,
        "median_ms": float(np.median(measured)),
        "p95_ms": float(np.percentile(measured, 95)),
        "minimum_ms": float(np.min(measured)),
        "maximum_ms": float(np.max(measured)),
    }


def _cpu_model() -> str:
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    return platform.processor() or "unknown"


def main() -> int:
    args = _arguments()
    if args.iterations < 20:
        raise ValueError("runtime benchmark requires at least 20 iterations")
    thread_settings = {name: os.environ.get(name) for name in THREAD_VARIABLES}
    if any(value != "1" for value in thread_settings.values()):
        raise RuntimeError(
            "pin every BLAS thread variable to 1 before importing NumPy: "
            + ", ".join(THREAD_VARIABLES)
        )

    rate_hz = 2_500_000.0
    frame_start = 1_234_567
    acquisition_cfo_hz = 200_000.0
    residual_cfo_hz = 317.4
    template = np.asarray(qin_edge_pilot_frame(rate_hz, StarlinkEdge.LOWER), np.complex128)
    frame_content = round(302 * rate_hz * OFDM_SYMBOL_DURATION_S)
    samples = np.zeros(frame_content + 2, dtype=np.complex128)
    indexes = np.arange(frame_content)
    samples[1 + indexes] = template[:frame_content] * np.exp(
        2j * np.pi * (acquisition_cfo_hz + residual_cfo_hz) * (frame_start + indexes) / rate_hz
    )
    demodulator = _KnownPilotDemodulator(
        samples,
        rate_hz,
        StarlinkEdge.LOWER,
        acquisition_cfo_hz,
    )
    pilot = demodulator.frame(1)
    exact = pilot * np.conj(qin_edge_pilot_symbols(StarlinkEdge.LOWER))
    times_s = (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
    times_s -= np.mean(times_s)

    def point_estimate() -> float:
        estimate = _maximize_frequency_likelihood(
            exact,
            times_s,
            maximum_residual_cfo_hz=2_000.0,
        )
        return _refine_frequency_from_phase(exact, times_s, estimate)

    def qualified_estimate() -> None:
        estimate_edge_pilot_frame_cfo(
            samples,
            rate_hz,
            frame_start_sample=frame_start,
            acquisition_absolute_cfo_hz=acquisition_cfo_hz,
            edge=StarlinkEdge.LOWER,
        )

    point = _timings(point_estimate, args.iterations)
    full = _timings(qualified_estimate, args.iterations)
    median_ms = full["median_ms"]
    result = {
        "schema": "frame-cfo-runtime-benchmark-v1",
        "method": (
            "in-process perf_counter_ns after five warmups; synthetic high-SNR 2.5 MS/s "
            "frame; BLAS threads pinned to one"
        ),
        "hardware": {
            "cpu_model": _cpu_model(),
            "logical_cpu_count": os.cpu_count(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "thread_environment": thread_settings,
            "cpu_affinity": sorted(os.sched_getaffinity(0)),
        },
        "ordinary_exact_profile_point_estimate": point,
        "qualified_public_api": full,
        "qualified_to_point_median_ratio": float(median_ms / point["median_ms"]),
        "median_projection": {
            "56_frames_75ms_segment_s": float(56 * median_ms / 1_000.0),
            "35000_frame_research_dwell_s": float(35_000 * median_ms / 1_000.0),
            "projection_is_linear_single_process_estimate": True,
        },
        "p95_projection": {
            "56_frames_75ms_segment_s": float(56 * full["p95_ms"] / 1_000.0),
            "35000_frame_research_dwell_s": float(35_000 * full["p95_ms"] / 1_000.0),
            "projection_is_linear_single_process_estimate": True,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
