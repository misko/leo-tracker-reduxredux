#!/usr/bin/env python3
"""Synthetic same-library blind acquisition versus known-state GLRT timing."""

from __future__ import annotations

import hashlib
import json
import platform
import statistics
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DEPLOY = Path("/home/mouse9911/gits/leo-adaptive-position-deploy")
sys.path[:0] = [str(HERE), str(DEPLOY), str(DEPLOY / "src")]

from known_state import NativeKnownState, build_library, sha256  # noqa: E402
from leo.analysis.starlink.templates import qin_edge_pilot_frame  # noqa: E402
from tools.presence_dwell import NativeDwell, unpack  # noqa: E402


def synthetic_window(rate: int, edge: str, epoch: int, cfo: float, seed: int):
    rng = np.random.default_rng(seed)
    values = rng.normal(0, 8, (rate // 50, 2))
    template = np.asarray(qin_edge_pilot_frame(rate, edge))
    for frame in range(16):
        start = epoch + round(frame * rate / 750)
        stop = min(start + len(template), len(values))
        if stop <= start:
            break
        k = np.arange(stop - start)
        signal = 1400 * template[: stop - start] * np.exp(2j * np.pi * cfo * k / rate)
        values[start:stop] += np.column_stack((signal.real, signal.imag))
    return np.clip(np.rint(values), -32768, 32767).astype(np.int16)


def median_metrics(rows):
    return {
        key: statistics.median(row[key] for row in rows)
        for key in ("total_cpu_ms", "total_wall_ms")
    }


def run(output: Path, repetitions: int = 300):
    if repetitions < 3:
        raise ValueError("at least three timing repetitions required")
    library = build_library()
    rows = []
    for rate in (2_500_000, 5_000_000):
        edge, epoch, cfo, signal_window = "lower", 320, 65_000.0, 3
        selected = synthetic_window(rate, edge, epoch, cfo, rate)
        rng = np.random.default_rng(rate + 1)
        dwell = rng.integers(-12, 13, (rate * 120 // 1000, 2), dtype=np.int16)
        window = rate // 50
        dwell[signal_window * window : (signal_window + 1) * window] = selected
        with NativeKnownState(rate, edge, library) as known, NativeDwell(
            library, rate, edge, 512
        ) as blind:
            for _ in range(20):
                known.measure(selected, epoch, cfo)
                known.measure(selected, epoch + 0.2, cfo, recover_timing=True)
                blind.run(dwell, maximum=1, seeded=False)
            fast, recovery, baseline = [], [], []
            for repetition in range(repetitions):
                if repetition % 2:
                    baseline.append(unpack(blind.run(dwell, maximum=1, seeded=False)))
                    fast.append(known.measure(selected, epoch, cfo))
                else:
                    fast.append(known.measure(selected, epoch, cfo))
                    baseline.append(unpack(blind.run(dwell, maximum=1, seeded=False)))
                recovery.append(
                    known.measure(selected, epoch + 0.2, cfo, recover_timing=True)
                )
            if any(row["needs_reacquire"] or row["margin"] <= 0.025 for row in fast):
                raise ValueError("synthetic known-state fast point did not remain positive")
            if any(
                row["confirmation_count"] != 1
                or row["confirmations"][0]["candidate_count"] < 1
                or row["confirmations"][0]["candidates"][0]["margin"] <= 0.025
                for row in baseline
            ):
                raise ValueError("synthetic blind baseline did not remain positive")
            fast_timing = median_metrics(fast)
            recovery_timing = median_metrics(recovery)
            blind_timing = median_metrics(baseline)
            rows.append(
                {
                    "rate_hz": rate,
                    "repetitions": repetitions,
                    "selected_window": signal_window,
                    "fast_point": fast_timing,
                    "local_timing_recovery": recovery_timing,
                    "blind_dwell": blind_timing,
                    "blind_over_fast_cpu_ratio": blind_timing["total_cpu_ms"]
                    / fast_timing["total_cpu_ms"],
                    "blind_over_fast_wall_ratio": blind_timing["total_wall_ms"]
                    / fast_timing["total_wall_ms"],
                    "fast_example": fast[0],
                }
            )
    receipt = {
        "schema": "org.leo.research.known-state-synthetic-benchmark/v1",
        "scope": "synthetic same-library microbenchmark; not causal replay or ARM timing",
        "host": platform.uname()._asdict(),
        "library_sha256": sha256(library),
        "build_receipt_sha256": sha256(library.with_name(library.name + ".build.json")),
        "profile_sha256": sha256(HERE / "profile.json"),
        "benchmark_source_sha256": sha256(Path(__file__)),
        "rows": rows,
        "limitations": [
            "known signal/window/state are supplied directly by the synthetic generator",
            "aggregate speedup depends on causal hit rate and reacquisition cost",
            "server x86 timing does not establish ARM timing",
        ],
    }
    with output.open("x") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    run(HERE / "benchmark.json")
