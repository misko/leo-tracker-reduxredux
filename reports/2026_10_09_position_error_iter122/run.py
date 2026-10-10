"""Frozen 480-call synthetic conditioned experiment, no automatic retry."""

import hashlib
import itertools
import json
import os
import time
from pathlib import Path

import numpy as np
from offgrid import DELTA_HZ, signal

from tools.native_presence import NativePresence, build_library

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def evaluate(plan, estimator):
    rows = []
    for phase, amplitude, cutoff, seed in itertools.product(
        plan["phases_bins"], plan["amplitudes"], plan["cutoffs_s"], plan["seeds"]
    ):
        values, occupancy = signal(cutoff, phase, amplitude=amplitude, seed=seed)
        started = time.perf_counter()
        exact, control, frequency = estimator.glrt(values, 0, 0, 0)
        elapsed = time.perf_counter() - started
        if not np.all(np.isfinite([exact, control, frequency])):
            raise ValueError("nonfinite native output")
        injected = phase * DELTA_HZ
        row = {
            "phase_bins": phase,
            "amplitude": amplitude,
            "cutoff_s": cutoff,
            "seed": seed,
            "occupancy": occupancy,
            "injected_hz": injected,
            "estimated_hz": float(frequency),
            "error_hz": float(frequency - injected),
            "estimated_bin": float(frequency / DELTA_HZ),
            "exact": float(exact),
            "control": float(control),
            "margin": float(exact - control),
            "passed": bool(exact - control >= plan["margin_gate"]),
            "elapsed_s": elapsed,
        }
        rows.append(row)
    return rows


def main():
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        if os.environ.get(name) != "1":
            raise ValueError(f"{name} must be 1")
    raw = (HERE / "protocol.json").read_bytes()
    plan = json.loads(raw)
    for path, digest in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path
    assert plan["phases_bins"] == [-0.4, -0.2, 0, 0.2, 0.4]
    assert plan["amplitudes"] == [0.25, 1] and plan["cutoffs_s"] == [0.00015, 0.001, 0.020]
    assert plan["seeds"] == list(range(122000, 122016)) and plan["margin_gate"] == 0.025
    digest = hashlib.sha256(raw).hexdigest()
    with (HERE / "started.json").open("x") as stream:
        json.dump({"protocol_sha256": digest}, stream)
    started = time.perf_counter()
    library = build_library(HERE / "native.so")
    build_seconds = time.perf_counter() - started
    with NativePresence(library, 2_500_000, "lower") as estimator:
        rows = evaluate(plan, estimator)
    assert len(rows) == 480
    with (HERE / "result.json").open("x") as stream:
        json.dump(
            {
                "status": "complete",
                "protocol_sha256": digest,
                "native_calls": len(rows),
                "library_sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
                "build_seconds": build_seconds,
                "elapsed_s": time.perf_counter() - started,
                "rows": rows,
            },
            stream,
            indent=2,
        )


if __name__ == "__main__":
    main()
