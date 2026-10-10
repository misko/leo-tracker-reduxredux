"""Bounded matched frame model sensitivity, append-only member results."""

import argparse
import hashlib
import json
import os
import runpy
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def member(binding, digest, reconstruct, engine, convert, directory):
    label = binding["member"]["inventory_label"]
    path = directory / f"{label}.json"
    if path.exists():
        result = json.loads(path.read_text())
        assert result["member"] == binding["member"] and result["protocol_sha256"] == digest
        return result
    claim = directory / f"{label}.claim.json"
    with claim.open("x") as stream:
        json.dump({"protocol_sha256": digest, "member": binding["member"]}, stream)
    start = time.monotonic()
    result = {
        "member": binding["member"],
        "protocol_sha256": digest,
        "status": "failed",
        "attempts": {},
        "failures": [],
    }
    try:
        archive = json.loads((ROOT / binding["b7_source"]).read_text())
        assert archive["member"] == binding["member"] and archive["status"] == "complete"
        model, _ = reconstruct(binding, archive)
        alternative = convert(model)
        for arm in ("fitted-c", "zero-c"):
            endpoint = archive["stages"]["B7"][arm]
            seed = np.asarray(endpoint["vector"])
            clock = np.asarray(endpoint["clock_coefficients"])
            value = model.evaluate_joint(seed, clock)[0]
            assert abs(value - endpoint["objective"]) <= 1e-6
            result["attempts"][arm] = {"archive": endpoint, "control": None, "phase": None}
            for name, current in (("control", model), ("phase", alternative)):
                try:
                    fit = engine["run_attempt"](current, seed.copy(), clock.copy(), arm)
                    result["attempts"][arm][name] = {
                        "status": "complete",
                        "fit": fit,
                        "qualified": fit["converged"],
                        "fallback": "none"
                        if fit["converged"]
                        else "original archive reported separately",
                    }
                except Exception as error:
                    result["attempts"][arm][name] = {
                        "status": "failed",
                        "error": repr(error),
                        "fallback": "original archive reported separately",
                    }
                    result["failures"].append(f"{arm}/{name}: {error!r}")
        result["status"] = "complete" if not result["failures"] else "attempt-failed"
    except Exception as error:
        result["failures"].append(repr(error))
    result["elapsed_s"] = time.monotonic() - start
    engine["write"](path, result)
    return result


def main():
    assert all(
        os.environ.get(k) == "1"
        for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", required=True, type=int, choices=(0, 1))
    args = parser.parse_args()
    plan = json.loads((HERE / "protocol.json").read_text())
    assert plan["maximum_seconds_per_fit"] == 90 and plan["maximum_iterations_per_fit"] == 600
    for path, digest in plan["frozen_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    sys.path.insert(0, str(HERE.parent / "2026_10_09_position_error_iter108"))
    reconstruct = runpy.run_path(str(HERE.parent / "2026_10_09_position_error_iter108/audit.py"))[
        "reconstruct"
    ]
    engine = runpy.run_path(str(HERE.parent / "2026_10_09_position_error_iter106/engine.py"))
    convert = runpy.run_path(str(HERE / "objective.py"))["convert"]
    directory = HERE / "results"
    directory.mkdir(exist_ok=True)
    digest = hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
    for binding in plan["members"][args.shard :: 2]:
        member(binding, digest, reconstruct, engine, convert, directory)


if __name__ == "__main__":
    main()
