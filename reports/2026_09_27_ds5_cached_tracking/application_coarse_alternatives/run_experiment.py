#!/usr/bin/env python3
"""Bounded paired benchmark of rounded-template coarse-grid alternatives."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import statistics
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(HERE), str(ROOT / "src")]

from alternatives import grid_delta, numpy_correlate_grid, numpy_fft_grid  # noqa: E402
from leo.analysis.starlink import acquisition  # noqa: E402
from leo.analysis.starlink.templates import FRAME_RATE_HZ, qin_edge_pilot_frame  # noqa: E402

RATES = (2_500_000, 5_000_000)
VARIANTS = ("production_avx2", "numpy_correlate", "numpy_fft")
THREAD_ENV = (
    "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS",
)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def verify_source_lock() -> dict:
    lock = json.loads((HERE / "source_lock.json").read_text())
    paths = {
        "design": HERE / "design.json",
        "alternatives": HERE / "alternatives.py",
        "runner": Path(__file__),
        "acquisition": Path(acquisition.__file__),
        "native_source": ROOT / "src/leo/analysis/starlink/_native_acquisition.c",
        "native_grid": ROOT / "src/leo/analysis/starlink/_native_acquisition_grid.inc",
        "native_binary": Path(acquisition._native_acquisition.__file__),
    }
    actual = {name: digest(path) for name, path in paths.items()}
    if actual != lock.get("files"):
        raise ValueError("coarse-alternatives source lock changed")
    return lock


def fixture(rate: int, kind: str) -> np.ndarray:
    count = rate // 50
    if kind == "zero":
        return np.zeros(count, dtype=np.complex128)
    if kind == "random":
        rng = np.random.default_rng(20260927 + rate)
        return np.asarray(rng.normal(size=count) + 1j * rng.normal(size=count), np.complex128)
    values = np.zeros(count, dtype=np.complex128)
    template = np.asarray(qin_edge_pilot_frame(rate, "lower"), np.complex128)
    epoch, cfo, frame = 137, 160_000.0, 0
    while True:
        start = epoch + round(frame * rate / FRAME_RATE_HZ)
        if start + len(template) > count:
            break
        indexes = np.arange(start, start + len(template))
        values[start:start + len(template)] += template * np.exp(2j * np.pi * cfo * indexes / rate)
        frame += 1
    return values


def arguments(rate: int, values: np.ndarray):
    template = np.asarray(qin_edge_pilot_frame(rate, "lower"), np.complex128)
    frequencies = tuple(float(value) for value in np.arange(-400_000, 400_001, 80_000))
    return (
        values, template, float(rate), frequencies,
        acquisition.DEFAULT_ANCHOR_SYMBOLS, round(rate / FRAME_RATE_HZ),
    )


def timed(function):
    cpu_started = time.process_time_ns()
    wall_started = time.perf_counter_ns()
    result = function()
    return result, {
        "process_cpu_ms": (time.process_time_ns() - cpu_started) / 1e6,
        "wall_ms": (time.perf_counter_ns() - wall_started) / 1e6,
    }


def median(samples: list[dict]) -> dict:
    return {name: statistics.median(row[name] for row in samples)
            for name in ("process_cpu_ms", "wall_ms")}


def run() -> dict:
    signal.alarm(120)
    lock = verify_source_lock()
    functions = {
        "production_avx2": acquisition._folded_anchor_score_grid,
        "numpy_correlate": numpy_correlate_grid,
        "numpy_fft": numpy_fft_grid,
    }
    science = {}
    timings = {}
    for rate in RATES:
        science[str(rate)] = {}
        for kind in ("random", "zero", "pilot"):
            values = fixture(rate, kind)
            before = hashlib.sha256(values).hexdigest()
            args = arguments(rate, values)
            expected = functions["production_avx2"](*args)
            science[str(rate)][kind] = {}
            for variant in VARIANTS[1:]:
                actual = functions[variant](*args)
                science[str(rate)][kind][variant] = grid_delta(expected, actual)
            if hashlib.sha256(values).hexdigest() != before:
                raise ValueError("fixture mutated")
        values = fixture(rate, "random")
        args = arguments(rate, values)
        for variant in VARIANTS:
            functions[variant](*args)
        samples = {variant: [] for variant in VARIANTS}
        signatures = {variant: [] for variant in VARIANTS}
        for repetition in range(3):
            order = VARIANTS[repetition:] + VARIANTS[:repetition]
            for variant in order:
                returned, elapsed = timed(lambda variant=variant: functions[variant](*args))
                samples[variant].append(elapsed)
                signatures[variant].append("sha256:" + hashlib.sha256(
                    np.stack(returned).tobytes()
                ).hexdigest())
        if any(len(set(values)) != 1 for values in signatures.values()):
            raise ValueError("coarse alternative is nondeterministic")
        medians = {variant: median(samples[variant]) for variant in VARIANTS}
        timings[str(rate)] = {
            "samples": samples, "medians": medians,
            "speedup_vs_production": {
                variant: {
                    "process_cpu": (
                        medians["production_avx2"]["process_cpu_ms"]
                        / medians[variant]["process_cpu_ms"]
                    ),
                    "wall": medians["production_avx2"]["wall_ms"] / medians[variant]["wall_ms"],
                }
                for variant in VARIANTS[1:]
            },
        }
    science_pass = {
        variant: all(
            row[variant]["shape_match"]
            and row[variant]["finite"]
            and row[variant]["peak_indexes_exact"]
            and row[variant]["maximum_absolute_error"] <= 1e-10
            for rate in science.values() for row in rate.values()
        )
        for variant in VARIANTS[1:]
    }
    promoted = [
        variant for variant in VARIANTS[1:]
        if science_pass[variant]
        and all(timings[str(rate)]["speedup_vs_production"][variant]["process_cpu"] >= 10.0
                for rate in RATES)
    ]
    return {
        "schema": "org.leo.research.application-coarse-alternatives-result/v1",
        "fresh_holdout_opened": False,
        "source_lock": lock,
        "native_backend": acquisition._folded_anchor_score_grid_backend(),
        "science": science,
        "science_pass": science_pass,
        "timing": timings,
        "promotion_gate_speedup": 10.0,
        "promoted_variants": promoted,
        "saved_iq_application_calls_run": bool(promoted),
        "status": "promotion_required" if promoted else "rejected_at_component_gate",
        "limitations": [
            "NumPy correlation and FFT reductions are numerical variants, not bit-exact execution.",
            "No saved-IQ full application call is run unless a candidate passes the frozen 10x stage gate.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "results.json")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.parent != HERE or output.exists():
        raise ValueError("output must be a new file beneath application_coarse_alternatives")
    environment = {name: os.environ.get(name) for name in THREAD_ENV}
    if any(value != "1" for value in environment.values()):
        raise ValueError("numerical thread environment must be fixed to one")
    original_affinity = os.sched_getaffinity(0)
    if 0 not in original_affinity:
        raise ValueError("P-core 0 unavailable")
    started = time.perf_counter_ns()
    try:
        os.sched_setaffinity(0, {0})
        payload = run()
    finally:
        signal.alarm(0)
        os.sched_setaffinity(0, original_affinity)
    payload.update(
        thread_environment=environment,
        affinity_cpu=0,
        affinity_restored=sorted(original_affinity),
        elapsed_wall_ms=(time.perf_counter_ns() - started) / 1e6,
    )
    with output.open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({
        "status": payload["status"],
        "science_pass": payload["science_pass"],
        "speedup": {rate: row["speedup_vs_production"] for rate, row in payload["timing"].items()},
    }, sort_keys=True))


if __name__ == "__main__":
    main()
