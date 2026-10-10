"""Matched replay of the frozen122 synthetic inputs; no production changes."""

import hashlib
import importlib.util
import json
import os
import time
import traceback
from pathlib import Path

import numpy as np
from refine import DELTA_HZ, refine

from leo.analysis.starlink.pilot_methods import _conditioned_correlation_workspace
from leo.contracts.states import StarlinkEdge
from tools.native_presence import NativePresence, build_library

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        assert os.environ.get(name) == "1", name
    raw = (HERE / "protocol.json").read_bytes()
    plan = json.loads(raw)
    for path, digest in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path
    source = ROOT / plan["baseline_result"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == plan["baseline_sha256"]
    previous = json.loads(source.read_text())["rows"]
    assert len(previous) == 480
    spec = importlib.util.spec_from_file_location(
        "frozen122_signal", HERE.parent / "2026_10_09_position_error_iter122/offgrid.py"
    )
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    digest = hashlib.sha256(raw).hexdigest()
    with (HERE / "started.json").open("x") as stream:
        json.dump({"protocol_sha256": digest}, stream)
    started = time.perf_counter()
    library = build_library(HERE / "native.so")
    rows = []
    with NativePresence(library, 2_500_000, "lower") as estimator:
        for old in previous:
            values, _ = generator.signal(
                old["cutoff_s"], old["phase_bins"], amplitude=old["amplitude"], seed=old["seed"]
            )
            began = time.perf_counter()
            exact, control, cfo = estimator.glrt(values, 0, 0, 0)
            native_seconds = time.perf_counter() - began
            np.testing.assert_allclose(
                [exact, control, cfo],
                [old["exact"], old["control"], old["estimated_hz"]],
                atol=1e-10,
                rtol=0,
            )
            began = time.perf_counter()
            workspace = _conditioned_correlation_workspace(
                values, 2_500_000, 0, 0, selected_symbols=np.arange(2, 66), edge=StarlinkEdge.LOWER
            )
            correlations = workspace.select(np.arange(2, 66))
            preparation_seconds = time.perf_counter() - began
            began = time.perf_counter()
            native_bin = int(round(cfo / DELTA_HZ)) % 512
            refined = refine(correlations.values, native_bin=native_bin)
            refinement_seconds = time.perf_counter() - began
            assert abs(refined["coarse_score"] - exact) < 1e-10
            assert abs(refined["coarse_hz"] - cfo) < 1e-8
            rows.append(
                {
                    "baseline": old,
                    "refined": refined,
                    "native_seconds": native_seconds,
                    "python_correlation_seconds": preparation_seconds,
                    "python_refinement_seconds": refinement_seconds,
                }
            )
    with (HERE / "result.json").open("x") as stream:
        json.dump(
            {
                "status": "complete",
                "protocol_sha256": digest,
                "native_calls": len(rows),
                "elapsed_s": time.perf_counter() - started,
                "rows": rows,
                "library_sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
            },
            stream,
            indent=2,
        )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        if (HERE / "started.json").exists() and not (HERE / "result.json").exists():
            with (HERE / "failed.json").open("x") as stream:
                json.dump({"status": "failed", "traceback": traceback.format_exc()}, stream)
        raise
