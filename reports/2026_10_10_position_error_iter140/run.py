"""One full-cohort phase comparison member; preparation only until frozen."""

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


def verify_prerequisites(plan):
    if (
        len(plan["members"]) != 193
        or len({m["label"] for m in plan["members"]}) != 193
        or plan["arms"] != ["fitted-c", "zero-c"]
        or plan["variants"] != ["timestamp", "phase"]
        or plan["maximum_fit_calls"] != 772
        or plan["maximum_seconds_per_fit"] != 90
        or plan["maximum_iterations_per_fit"] != 600
        or plan["qualification_threshold"] != 0.001
    ):
        raise ValueError("Wrong global comparison scope")
    for group in ("sources", "inputs"):
        for path, expected in plan[group].items():
            if sha(ROOT / path) != expected:
                raise ValueError("Frozen binding changed: " + path)
    for binding in plan["members"]:
        receipt = json.loads((ROOT / binding["parity_receipt"]).read_text())
        if (
            receipt["status"] != "complete"
            or receipt["label"] != binding["label"]
            or receipt["protocol_sha256"] != plan["parity_protocol_sha256"]
            or receipt["endpoint_evaluations"] != 2
        ):
            raise ValueError("Full193 parity prerequisite failed")
        for arm in ("fitted-c", "zero-c"):
            row = receipt["arms"][arm]
            import math

            if (
                row["status"] != "complete"
                or not math.isfinite(row["delta"])
                or abs(row["delta"]) > 1e-6
            ):
                raise ValueError("Arm parity prerequisite failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    if any(
        os.environ.get(k) != "1"
        for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
    ):
        raise ValueError("Single-thread environment required")
    protocol = HERE / "protocol.json"
    plan = json.loads(protocol.read_text())
    verify_prerequisites(plan)
    bindings = [m for m in plan["members"] if m["label"] == args.label]
    if len(bindings) != 1:
        raise ValueError("Member outside frozen cohort")
    binding = bindings[0]
    output = HERE / "results" / (args.label + ".json")
    output.parent.mkdir(exist_ok=True)
    identity = dict(label=args.label, protocol_sha256=sha(protocol))
    with output.with_suffix(".claim.json").open("x") as stream:
        json.dump(identity, stream)
    began = time.monotonic()
    engine = None
    try:
        engine = runpy.run_path(str(ROOT / "reports/2026_10_09_position_error_iter106/engine.py"))
        parity = module(
            "parity137_for140", HERE.parent / "2026_10_10_position_error_iter137/parity.py"
        )
        helpers = module(
            "helpers132_for140", HERE.parent / "2026_10_10_position_error_iter132/audit.py"
        )
        clean = module(
            "clean131_for140", HERE.parent / "2026_10_09_position_error_iter131/inference_loader.py"
        )
        folder = HERE.parent / "2026_10_09_position_error_iter116"
        sys.path.insert(0, str(folder))
        entry = module("entry116_for140", folder / "entrypoint.py")
        case_binding = binding["case_binding"]
        backend = entry.make_loader(
            ROOT,
            dict(
                case_binding,
                loader_source=entry.LOADER,
                loader_sha256=plan["sources"][entry.LOADER],
            ),
        )
        case = clean.InferenceLoader(ROOT, backend.load_case)(case_binding)
        projection = parity.read_projection(case_binding)
        model, _, _ = parity.construct(
            case, projection["operational"]["fitted-c"], helpers.numerical_components()
        )
        result = compare(model, projection, engine["run_attempt"])
    except Exception as exc:
        result = dict(status="failed", error=repr(exc), attempts={})
    result.update(identity, total_elapsed_s=time.monotonic() - began)
    if engine is None:
        with output.open("x") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
    else:
        engine["write"](output, result)


if __name__ == "__main__":
    main()
