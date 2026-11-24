"""Measure the cost of recovering signed carrier lifts after coherent repeat folding."""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import time


HERE = Path(__file__).resolve().parent
SIGNED_BANDWIDTH_HZ = 1_600_000
TOLERANCE_HZ = 4_550
TARGET_DENSE_S = 3.490
GRID_STAGES = ("lag_timing", "carrier_grid")
FRONT_STAGES = (*GRID_STAGES, "input_mix", "fir", "frame_modes")
BUILD_FLAGS = ("-O3", "-march=native", "-std=c11", "-Wall", "-Wextra", "-Werror")
LAYOUTS = (
    ("native", 40_000, 250, 1),
    ("quarter-rate", 10_000, 250, 1),
    ("quarter-rate-thinned", 10_000, 250, 2),
    ("smooth-proxy", 4_096, 750, 1),
    ("smooth-proxy-thinned", 4_096, 750, 2),
    ("smooth-proxy-16-native-stride", 4_096, 750, 4),
)


def lift_cover(spacing_hz, tolerance_hz=TOLERANCE_HZ):
    """Optimistic minimum bank size when the signed lifts share one exact residue."""
    lifts = SIGNED_BANDWIDTH_HZ // spacing_hz
    per_row = 2 * (tolerance_hz // spacing_hz) + 1
    return lifts, per_row, (lifts + per_row - 1) // per_row


def arithmetic(period, stride, rows):
    length = period // stride
    return {
        "inverse_length": length,
        "complex_products": rows * period,
        "real_alias_additions": 2 * rows * (period - length),
        "idealized_flop_model": rows * (6 * period + 2 * (period - length)
                                         + 5 * length * math.log2(length)),
    }


def dense_budget(price, stages):
    dense = price["projections"]["DS30-0008"]
    calls = dense["short_calls"]
    removed_s = sum(dense["attributed_s"][stage] for stage in stages)
    return {"calls": calls, "removed_s": removed_s, "gross_us_per_call": 1e6 * removed_s / calls,
            "available_us_per_call": 1e6 * (removed_s - TARGET_DENSE_S) / calls}


def measure(executable, period, stride, rows, tile, lift_step):
    args = [executable, *(str(field) for field in (period, stride, rows, tile, lift_step))]
    clocks = {"inverse_only": [], "multiply_inverse": []}
    for line in subprocess.check_output(args, text=True).splitlines():
        trial, multiply, cpu, wall = line.split()
        arm = "multiply_inverse" if int(multiply) else "inverse_only"
        if int(trial) != len(clocks[arm]):
            raise RuntimeError(f"Noncontiguous {arm} clock index {trial}")
        clocks[arm].append({"thread_cpu_us": 1e6 * float(cpu), "elapsed_us": 1e6 * float(wall)})
    if any(len(samples) != 9 for samples in clocks.values()):
        raise RuntimeError("Incomplete paired timing")
    return {
        "tile": tile,
        "samples": clocks,
        "median_thread_cpu_us": {arm: statistics.median(row["thread_cpu_us"] for row in samples)
                                 for arm, samples in clocks.items()},
    }


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(out):
    if os.sched_getaffinity(0) != {2}:
        raise RuntimeError("Run on the shared low-priority CPU2 slot")
    out.mkdir()
    executable = out / "repeat_fold_bank"
    source = HERE / "repeat_fold_bank.c"
    start = time.monotonic()
    subprocess.run(["cc", *BUILD_FLAGS, source, "-lfftw3f", "-lm", "-o", executable], check=True)
    build_s = time.monotonic() - start
    native_max_error = float(subprocess.check_output([executable, "--check"], text=True))
    price_path = HERE / "measurements" / "short-primary-fusion-price.json"
    price = json.loads(price_path.read_bytes())
    budgets = {"timing_and_carrier": dense_budget(price, GRID_STAGES),
               "whole_frontend_grant": dense_budget(price, FRONT_STAGES)}
    timings = []
    for name, period, spacing, stride in LAYOUTS:
        lifts, per_row, rows = lift_cover(spacing)
        arms = [measure(executable, period, stride, rows, tile, per_row) for tile in (1, 8)]
        best = {arm: min(tile["median_thread_cpu_us"][arm] for tile in arms)
                for arm in ("inverse_only", "multiply_inverse")}
        cases = {scope: budget["removed_s"] - best["multiply_inverse"] * budget["calls"] * 1e-6
                 for scope, budget in budgets.items()}
        timings.append({"layout": name, "period": period, "lift_spacing_hz": spacing,
                        "stride": stride, "signed_lifts": lifts, "lifts_per_row": per_row, "rows": rows,
                        "arithmetic": arithmetic(period, stride, rows), "plans": arms,
                        "best_median_cpu_us": best, "optimistic_dense_saving_s": cases})
    result = {
        "source_sha256": sha256(source), "runner_sha256": sha256(Path(__file__)),
        "binary_sha256": sha256(executable), "archive_sha256": sha256(price_path),
        "fftw3f": subprocess.check_output(["pkg-config", "--modversion", "fftw3f"], text=True).strip(),
        "compiler": subprocess.check_output(["cc", "--version"], text=True).splitlines()[0],
        "build_flags": BUILD_FLAGS, "build_elapsed_s": build_s,
        "cpu_affinity": sorted(os.sched_getaffinity(0)), "native_max_absolute_error": native_max_error,
        "waveform_source": "deterministic synthetic spectra", "signed_bandwidth_hz": SIGNED_BANDWIDTH_HZ,
        "tolerance_hz": TOLERANCE_HZ, "dense_target_s": TARGET_DENSE_S, "dense_budgets": budgets,
        "layouts": timings,
    }
    (out / "repeat-fold-bank.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    run(parser.parse_args().out.resolve())
