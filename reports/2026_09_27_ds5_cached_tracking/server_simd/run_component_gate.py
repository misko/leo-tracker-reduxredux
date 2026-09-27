#!/usr/bin/env python3
"""Run the frozen exact-SIMD complete-call projection gate."""

from __future__ import annotations

import ctypes as ct
import hashlib
import json
import os
import pickle
import statistics
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
DEPLOY = Path("/home/mouse9911/gits/leo-adaptive-position-deploy")
sys.path[:0] = [str(HERE), str(REPORT / "native"), str(DEPLOY), str(DEPLOY / "src")]

from server_simd import NativeServerSIMD  # noqa: E402

RATES = (2_500_000, 5_000_000)
REPETITIONS = 11


def digest_bytes(values: np.ndarray) -> str:
    return "sha256:" + hashlib.sha256(values).hexdigest()


def digest_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def scientific(value):
    if isinstance(value, ct.Structure):
        return {
            name: scientific(getattr(value, name))
            for name, _ in value._fields_
            if "cpu_ms" not in name and "wall_ms" not in name
        }
    if isinstance(value, ct.Array):
        return [scientific(item) for item in value]
    return value


def signature(value) -> str:
    return "sha256:" + hashlib.sha256(pickle.dumps(scientific(value), protocol=5)).hexdigest()


def main() -> int:
    output = HERE / "component_results.json"
    if output.exists():
        raise FileExistsError(output)
    original_affinity = os.sched_getaffinity(0)
    if 0 not in original_affinity:
        raise ValueError("declared P-core 0 unavailable")
    raw = {
        rate: np.random.default_rng(2026092700 + rate).integers(
            -32768, 32768, (rate * 120 // 1000, 2, 2), dtype=np.int16
        )
        for rate in RATES
    }
    before = {rate: digest_bytes(values) for rate, values in raw.items()}
    results = {}
    library = HERE / "libserver_simd.so"
    try:
        os.sched_setaffinity(0, {0})
        for rate in RATES:
            with NativeServerSIMD(rate, "lower", library) as engine:
                for mode in ("scalar", "simd"):
                    engine.force(mode)
                    for receiver in (0, 1):
                        engine.run(raw[rate], receiver, maximum=1, seeded=False)
                samples = {"scalar": [], "simd": []}
                signatures = {"scalar": [], "simd": []}
                for repetition in range(REPETITIONS):
                    order = ("scalar", "simd") if repetition % 2 == 0 else ("simd", "scalar")
                    for mode in order:
                        engine.force(mode)
                        started_cpu = time.thread_time_ns()
                        started_wall = time.perf_counter_ns()
                        returned = [
                            engine.run(raw[rate], receiver, maximum=1, seeded=False)
                            for receiver in (0, 1)
                        ]
                        wall_ms = (time.perf_counter_ns() - started_wall) / 1e6
                        cpu_ms = (time.thread_time_ns() - started_cpu) / 1e6
                        samples[mode].append(
                            {"repetition": repetition, "cpu_ms": cpu_ms, "wall_ms": wall_ms}
                        )
                        signatures[mode].append([signature(item) for item in returned])
                engine.force("auto")
                if signatures["scalar"] != signatures["simd"]:
                    raise ValueError(f"scientific mismatch at {rate}")
                medians = {
                    mode: {
                        clock: statistics.median(row[clock] for row in samples[mode])
                        for clock in ("cpu_ms", "wall_ms")
                    }
                    for mode in samples
                }
                results[str(rate)] = {
                    "samples": samples,
                    "medians": medians,
                    "cpu_speedup": medians["scalar"]["cpu_ms"] / medians["simd"]["cpu_ms"],
                    "wall_speedup": medians["scalar"]["wall_ms"] / medians["simd"]["wall_ms"],
                    "science_signatures": signatures["simd"][0],
                }
    finally:
        os.sched_setaffinity(0, original_affinity)
    after = {rate: digest_bytes(values) for rate, values in raw.items()}
    if after != before:
        raise ValueError("component input mutated")
    gate_passed = all(results[str(rate)]["cpu_speedup"] >= 1.10 for rate in RATES)
    sources = {
        name: digest_file(HERE / name)
        for name in (
            "design.json", "run_component_gate.py", "server_simd.c", "server_simd.h",
            "ci16_fold.h", "ci16_lag.h", "build.py", "server_simd.py",
            "libserver_simd.so", "libserver_simd.so.build.json",
        )
    }
    payload = {
        "schema": "org.leo.research.server-simd-component-result/v1",
        "fresh_holdout_opened": False,
        "kernel": "SSSE3/SSE4.1 forced versus exact scalar fallback",
        "affinity_cpu": 0,
        "affinity_restored": sorted(original_affinity),
        "warmups_per_mode_receiver_rate": 1,
        "repetitions": REPETITIONS,
        "timed_scope": "two complete sequential receiver dwell calls; mode switch and signatures excluded",
        "input_sha256_before": {str(k): v for k, v in before.items()},
        "input_sha256_after": {str(k): v for k, v in after.items()},
        "results": results,
        "required_cpu_speedup_each_rate": 1.10,
        "component_gate_passed": gate_passed,
        "source_sha256": sources,
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "output": str(output), "component_gate_passed": gate_passed,
        "cpu_speedup": {rate: results[str(rate)]["cpu_speedup"] for rate in RATES},
    }, sort_keys=True))
    return 0 if gate_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
