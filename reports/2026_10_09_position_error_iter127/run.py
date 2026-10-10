"""Independent-noise replication; immutable125 refinements and122 generator."""

import hashlib
import importlib.util
import itertools
import json
import os
import time
import traceback
from pathlib import Path

import numpy as np

from leo.analysis.starlink.pilot_methods import _conditioned_correlation_workspace
from leo.contracts.states import StarlinkEdge
from tools.native_presence import NativePresence, build_library

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cases(plan):
    assert plan["phases_bins"] == [-0.4, -0.2, 0, 0.2, 0.4]
    assert plan["amplitudes"] == [0.25, 1] and plan["cutoffs_s"] == [0.00015, 0.001, 0.020]
    assert plan["seeds"] == list(range(127000, 127016))
    assert plan["margin_gate"] == 0.025 and plan["native_call_cap"] == 480
    return list(
        itertools.product(plan["phases_bins"], plan["amplitudes"], plan["cutoffs_s"], plan["seeds"])
    )


def measure(case, generator, refinement, estimator):
    phase, amplitude, cutoff, seed = case
    values, occupancy = generator.signal(cutoff, phase, amplitude=amplitude, seed=seed)
    started = time.perf_counter()
    exact, control, cfo = estimator.glrt(values, 0, 0, 0)
    native_seconds = time.perf_counter() - started
    if not np.isfinite([exact, control, cfo]).all():
        raise ValueError("nonfinite native output")
    injected = phase * refinement.DELTA_HZ
    baseline = {
        "phase_bins": phase,
        "amplitude": amplitude,
        "cutoff_s": cutoff,
        "seed": seed,
        "occupancy": occupancy,
        "injected_hz": injected,
        "estimated_hz": float(cfo),
        "error_hz": float(cfo - injected),
        "exact": float(exact),
        "control": float(control),
        "margin": float(exact - control),
        "passed": bool(exact - control >= 0.025),
    }
    started = time.perf_counter()
    workspace = _conditioned_correlation_workspace(
        values, 2_500_000, 0, 0, selected_symbols=np.arange(2, 66), edge=StarlinkEdge.LOWER
    )
    z = workspace.select(np.arange(2, 66)).values
    python_correlation_seconds = time.perf_counter() - started
    native_bin = int(round(cfo / refinement.DELTA_HZ)) % 512
    started = time.perf_counter()
    refined = refinement.refine(z, native_bin=native_bin)
    python_refinement_seconds = time.perf_counter() - started
    if abs(refined["coarse_score"] - exact) > 1e-10 or abs(refined["coarse_hz"] - cfo) > 1e-8:
        raise ValueError("native/Python parity failure")
    return {
        "baseline": baseline,
        "refined": refined,
        "native_seconds": native_seconds,
        "python_correlation_seconds": python_correlation_seconds,
        "python_refinement_seconds": python_refinement_seconds,
    }


def main():
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        assert os.environ.get(name) == "1", name
    raw = (HERE / "protocol.json").read_bytes()
    plan = json.loads(raw)
    for path, digest in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path
    inventory = cases(plan)
    assert len(inventory) == len(set(inventory)) == 480
    digest = hashlib.sha256(raw).hexdigest()
    with (HERE / "started.json").open("x") as stream:
        json.dump({"protocol_sha256": digest, "expected_cases": inventory}, stream)
    rows = []
    case = None
    started = time.perf_counter()
    try:
        generator = load(
            "immutable122generator", HERE.parent / "2026_10_09_position_error_iter122/offgrid.py"
        )
        refinement = load(
            "immutable125refinement", HERE.parent / "2026_10_09_position_error_iter125/refine.py"
        )
        library = build_library(HERE / "native.so")
        build_seconds = time.perf_counter() - started
        with (
            (HERE / "rows.jsonl").open("x") as stream,
            NativePresence(library, 2_500_000, "lower") as estimator,
        ):
            for case in inventory:
                row = measure(case, generator, refinement, estimator)
                stream.write(json.dumps(row) + "\n")
                stream.flush()
                rows.append(row)
        result = {
            "status": "complete",
            "protocol_sha256": digest,
            "native_calls": 480,
            "library_sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
            "build_seconds": build_seconds,
            "elapsed_s": time.perf_counter() - started,
            "rows": rows,
        }
    except Exception:
        result = {
            "status": "failed",
            "protocol_sha256": digest,
            "completed_rows": len(rows),
            "failed_case": case,
            "native_calls": "unknown for failed case; see traceback",
            "elapsed_s": time.perf_counter() - started,
            "traceback": traceback.format_exc(),
            "rows": rows,
        }
        with (HERE / "result.json").open("x") as stream:
            json.dump(result, stream, indent=2)
        raise
    with (HERE / "result.json").open("x") as stream:
        json.dump(result, stream, indent=2)


if __name__ == "__main__":
    main()
