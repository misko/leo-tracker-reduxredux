"""One clean phase replication member; no hidden preparation or retry."""

import argparse
import hashlib
import importlib.util
import json
import os
import runpy
import sys
import time
from pathlib import Path

from compare import compare

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    if any(
        os.environ.get(k) != "1"
        for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
    ):
        raise ValueError("single-thread environment required")
    path = HERE / "protocol.json"
    plan = json.loads(path.read_text())
    if (
        plan["maximum_fit_calls"] != 48
        or plan["maximum_seconds_per_fit"] != 90
        or plan["maximum_iterations_per_fit"] != 600
        or len(plan["members"]) != 12
        or plan["variants"] != ["timestamp", "phase"]
        or plan["qualification_threshold"] != 0.001
    ):
        raise ValueError("unexpected frozen scope")
    for group in ("sources", "inputs"):
        for name, expected in plan[group].items():
            if sha(ROOT / name) != expected:
                raise ValueError("frozen source/input changed: " + name)
    selected = [m for m in plan["members"] if m["label"] == args.label]
    if len(selected) != 1:
        raise ValueError("member outside fixed cohort")
    binding = selected[0]
    output = HERE / "results" / (args.label + ".json")
    output.parent.mkdir(exist_ok=True)
    identity = dict(label=args.label, protocol_sha256=sha(path))
    with output.with_suffix(".claim.json").open("x") as stream:
        json.dump(identity, stream)
    started = time.monotonic()
    engine = None
    try:
        # Import only unchanged fitter/qualification, never its historical loader.
        engine = runpy.run_path(str(ROOT / "reports/2026_10_09_position_error_iter106/engine.py"))
        parity = json.loads((ROOT / binding["parity_receipt"]).read_text())
        if parity["status"] != "complete" or parity["label"] != args.label:
            raise ValueError("clean parity prerequisite failed")
        audit = module(
            "clean132_for135", ROOT / "reports/2026_10_10_position_error_iter132/audit.py"
        )
        clean = module(
            "clean131_for135",
            ROOT / "reports/2026_10_09_position_error_iter131/inference_loader.py",
        )
        folder = ROOT / "reports/2026_10_09_position_error_iter116"
        sys.path.insert(0, str(folder))
        entry = module("entry116_for135", folder / "entrypoint.py")
        case_binding = binding["case_binding"]
        backend = entry.make_loader(
            ROOT,
            dict(
                case_binding,
                loader_source=entry.LOADER,
                loader_sha256=plan["sources"][entry.LOADER],
            ),
        )
        model, projection, _ = audit.build_model(
            case_binding,
            clean.InferenceLoader(ROOT, backend.load_case),
            audit.numerical_components(),
        )
        result = compare(model, projection["archive"], engine["run_attempt"])
    except Exception as error:
        result = dict(status="failed", error=repr(error), attempts={})
    result.update(identity, total_elapsed_s=time.monotonic() - started)
    if engine is None:
        with output.open("x") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
    else:
        engine["write"](output, result)


if __name__ == "__main__":
    main()
