"""Execute only the predeclared 160 conditioned synthetic calls."""

import hashlib
import json
import math
import os
import time
from pathlib import Path

import numpy as np
from partial_signal import signal

from tools.native_presence import NativePresence, build_library

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def wilson(successes, count):
    z = 1.959963984540054
    p = successes / count
    denominator = 1 + z * z / count
    center = (p + z * z / (2 * count)) / denominator
    radius = z * math.sqrt(p * (1 - p) / count + z * z / (4 * count * count)) / denominator
    return [center - radius, center + radius]


def main():
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        if os.environ.get(name) != "1":
            raise ValueError(f"{name} must be 1")
    raw = (HERE / "synthetic-protocol.json").read_bytes()
    plan = json.loads(raw)
    for path, digest in plan["source_sha256"].items():
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != digest:
            raise ValueError(f"source changed: {path}")
    if len(plan["cutoffs_s"]) * len(plan["amplitudes"]) * len(plan["seeds"]) != 160:
        raise ValueError("unexpected call budget")
    output = HERE / "synthetic-result.json"
    claim = HERE / "synthetic-started.json"
    with claim.open("x") as stream:
        json.dump({"protocol_sha256": hashlib.sha256(raw).hexdigest()}, stream)
    started = time.perf_counter()
    library = build_library(HERE / "synthetic-presence.so")
    build_seconds = time.perf_counter() - started
    rows = []
    with NativePresence(library, 2_500_000, "lower") as estimator:
        for amplitude in plan["amplitudes"]:
            for cutoff in plan["cutoffs_s"]:
                for seed in plan["seeds"]:
                    values, occupancy = signal(cutoff, amplitude=amplitude, noise_rms=1, seed=seed)
                    began = time.perf_counter()
                    exact, control, residual = estimator.glrt(values, 0, 0, 0)
                    elapsed = time.perf_counter() - began
                    if not np.all(np.isfinite([exact, control, residual])):
                        raise ValueError("nonfinite native result")
                    rows.append(
                        {
                            "amplitude": amplitude,
                            "cutoff_s": cutoff,
                            "seed": seed,
                            "occupancy": occupancy,
                            "exact": float(exact),
                            "control": float(control),
                            "margin": float(exact - control),
                            "passed": bool(exact - control >= plan["margin_gate"]),
                            "residual_cfo_hz": float(residual),
                            "elapsed_s": elapsed,
                        }
                    )
    groups = []
    for amplitude in plan["amplitudes"]:
        for cutoff in plan["cutoffs_s"]:
            group = [r for r in rows if r["amplitude"] == amplitude and r["cutoff_s"] == cutoff]
            passed = sum(r["passed"] for r in group)
            frequencies, counts = np.unique(
                [r["residual_cfo_hz"] for r in group], return_counts=True
            )
            groups.append(
                {
                    "amplitude": amplitude,
                    "cutoff_s": cutoff,
                    "occupancy": group[0]["occupancy"],
                    "count": len(group),
                    "passed": passed,
                    "pass_fraction": passed / len(group),
                    "wilson95": wilson(passed, len(group)),
                    "residual_cfo_histogram": list(
                        zip(frequencies.tolist(), counts.tolist(), strict=True)
                    ),
                }
            )
    with output.open("x") as stream:
        json.dump(
            {
                "status": "complete",
                "protocol_sha256": hashlib.sha256(raw).hexdigest(),
                "library_sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
                "build_seconds": build_seconds,
                "total_seconds": time.perf_counter() - started,
                "native_calls": len(rows),
                "groups": groups,
                "rows": rows,
            },
            stream,
            indent=2,
        )


if __name__ == "__main__":
    main()
