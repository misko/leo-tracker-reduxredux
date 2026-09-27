#!/usr/bin/env python3
"""Strided/selective and partial-support known-state synthetic benchmark."""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DEPLOY = Path("/home/mouse9911/gits/leo-adaptive-position-deploy")
sys.path[:0] = [str(HERE), str(DEPLOY), str(DEPLOY / "src")]

from benchmark import synthetic_window  # noqa: E402
from known_state import NativeKnownState, sha256  # noqa: E402
from known_state_v2 import NativeKnownStateV2, build_library_v2  # noqa: E402
from tools.presence_dwell import NativeDwell  # noqa: E402


def timed(function):
    started = time.perf_counter_ns()
    result = function()
    return result, (time.perf_counter_ns() - started) / 1e6


def summarize(rows):
    return {
        "internal_cpu_ms": statistics.median(row[0]["total_cpu_ms"] for row in rows),
        "internal_wall_ms": statistics.median(row[0]["total_wall_ms"] for row in rows),
        "python_call_wall_ms": statistics.median(row[1] for row in rows),
    }


def run(output: Path, repetitions=300):
    library = build_library_v2()
    output_rows = []
    for rate in (2_500_000, 5_000_000):
        epoch, cfo, edge = 320.35, 65_000.0, "lower"
        selected = synthetic_window(rate, edge, 320, cfo, rate + 20)
        selected_dual = np.empty((len(selected), 2, 2), dtype=np.int16)
        selected_dual[:, 0, :] = selected
        selected_dual[:, 1, :] = -selected
        selected_view = selected_dual[:, 0, :]
        rng = np.random.default_rng(rate + 21)
        dwell_dual = rng.integers(
            -12, 13, (rate * 120 // 1000, 2, 2), dtype=np.int16
        )
        samples = rate // 50
        dwell_dual[3 * samples : 4 * samples, 0, :] = selected
        dwell_view = dwell_dual[:, 0, :]
        with NativeKnownState(rate, edge, library) as v1, NativeKnownStateV2(
            rate, edge, library
        ) as v2, NativeDwell(library, rate, edge, 512) as blind:
            calls = {
                "v1_full_packed": lambda: v1.measure(selected_view, epoch, cfo),
                "v2_full_strided": lambda: v2.measure(selected_view, epoch, cfo),
                "v2_partial4_strided": lambda: v2.measure(
                    selected_view, epoch, cfo, frame_limit=4
                ),
                "v2_partial2_strided": lambda: v2.measure(
                    selected_view, epoch, cfo, frame_limit=2
                ),
                "blind_dwell_natural_rx": lambda: _blind_dict(blind.run(
                    dwell_view, maximum=1, seeded=False
                )),
            }
            for _ in range(20):
                for function in calls.values():
                    function()
            rows = {name: [] for name in calls}
            names = list(calls)
            for repetition in range(repetitions):
                order = names if repetition % 2 == 0 else list(reversed(names))
                for name in order:
                    rows[name].append(timed(calls[name]))
            summary = {name: summarize(values) for name, values in rows.items()}
            baseline = summary["blind_dwell_natural_rx"]["python_call_wall_ms"]
            for name, value in summary.items():
                value["blind_over_python_call_wall_ratio"] = (
                    baseline / value["python_call_wall_ms"]
                )
            output_rows.append(
                {
                    "rate_hz": rate,
                    "predicted_fractional_offset_samples": 0.35,
                    "repetitions": repetitions,
                    "selected_input_c_contiguous": selected_view.flags.c_contiguous,
                    "selected_input_strides_bytes": list(selected_view.strides),
                    "timing": summary,
                    "examples": {name: values[0][0] for name, values in rows.items()},
                }
            )
    receipt = {
        "schema": "org.leo.research.known-state-v2-synthetic-benchmark/v1",
        "scope": "synthetic same-library microbenchmark; partial scores unqualified",
        "library_sha256": sha256(library),
        "build_receipt_sha256": sha256(library.with_name(library.name + ".build.json")),
        "source_sha256": sha256(Path(__file__)),
        "rows": output_rows,
    }
    with output.open("x") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(output_rows, indent=2))


def _blind_dict(result):
    return {"total_cpu_ms": result.total_cpu_ms, "total_wall_ms": result.total_wall_ms}


if __name__ == "__main__":
    run(HERE / "benchmark_v2.json")
