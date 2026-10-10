"""Clean physical reconstruction with isolated acquisition-support adapter."""

import argparse
import hashlib
import importlib.util
import json
import os
import runpy
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def perform(plan, binding, engine, progress):
    support_port = module(
        "support138_for145", ROOT / "reports/2026_10_10_position_error_iter138/run.py"
    ).implementation
    model, projection, case = support_port.reconstruct(plan, binding)
    support = support_port.public_support(case, binding["case_binding"])
    progress["support"] = support
    expected = binding["support_binding"]
    for field in ("observation_order_signature", "window_evidence_sha256"):
        if support[field] != expected[field]:
            raise ValueError("Frozen acquisition evidence changed: " + field)
    pairing = module(
        "pair136_for145", ROOT / "reports/2026_10_10_position_error_iter136/pair_score.py"
    )
    measurement = runpy.run_path(
        str(ROOT / "reports/2026_10_10_position_error_iter133/measurement.py")
    )
    phase = runpy.run_path(str(ROOT / "reports/2026_10_10_position_error_iter130/objective.py"))
    objective = module("objective145_for_execution", HERE / "objective.py")
    emission = module("emission145_for_execution", HERE / "pair_likelihood.py")
    comparison = module("compare145_for_execution", HERE / "compare.py")
    return comparison.compare(
        model,
        projection["archive"],
        support,
        physics=plan["physics"],
        pair_rows=pairing.pair_rows,
        shared_starts=measurement["shared_starts"],
        clone_model=measurement["clone_measurement_model"],
        phase_convert=phase["convert"],
        paired_convert=objective.convert,
        phase_predict=phase["predict"],
        timestamp_predict=objective.timestamp_prediction,
        emission=emission.paired_likelihood,
        run_attempt=engine["run_attempt"],
        progress=progress,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    if any(
        os.environ.get(k) != "1"
        for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
    ):
        raise ValueError("Single-thread environment required")
    path = HERE / "protocol.json"
    plan = json.loads(path.read_text())
    if (
        plan["physics"] not in ("timestamp", "phase")
        or plan["rho"] != 0.25
        or plan["maximum_fit_calls"] != 48
        or plan["maximum_seconds_per_fit"] != 90
        or plan["maximum_iterations_per_fit"] != 600
        or plan["qualification_threshold"] != 0.001
        or plan["variants"] != ["control", "rho25"]
        or plan["arms"] != ["fitted-c", "zero-c"]
        or plan["maximum_workers"] != 1
        or plan["threads_per_worker"] != 1
        or len(plan["members"]) != 12
        or len({m["label"] for m in plan["members"]}) != 12
    ):
        raise ValueError("Unexpected frozen scope")
    for group in ("sources", "inputs"):
        for name, expected in plan[group].items():
            if sha(ROOT / name) != expected:
                raise ValueError("Frozen binding changed: " + name)
    bindings = [m for m in plan["members"] if m["label"] == args.label]
    if len(bindings) != 1:
        raise ValueError("Outside fixed cohort")
    output = HERE / "results" / (args.label + ".json")
    output.parent.mkdir(exist_ok=True)
    identity = dict(label=args.label, protocol_sha256=sha(path))
    if output.exists():
        raise FileExistsError("Terminal receipt already exists; no overwrite")
    with output.with_suffix(".claim.json").open("x") as stream:
        json.dump(identity, stream)
    began = time.monotonic()
    engine = None
    progress = {"attempts": {}}
    try:
        engine = runpy.run_path(str(ROOT / "reports/2026_10_09_position_error_iter106/engine.py"))
        result = perform(plan, bindings[0], engine, progress)
    except Exception as exc:
        result = dict(progress, status="failed", error=repr(exc))
    result.update(identity, total_elapsed_s=time.monotonic() - began)
    if engine is None:
        with output.open("x") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
    else:
        engine["write"](output, result)


if __name__ == "__main__":
    main()
