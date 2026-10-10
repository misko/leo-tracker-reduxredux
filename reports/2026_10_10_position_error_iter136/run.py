"""Saved-endpoint correlation audit with public support metadata; no fitting."""

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

from adapter import adapt_support
from audit_core import audit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def reconstruct(plan, binding):
    clean_audit = module(
        "clean132_for136", ROOT / "reports/2026_10_10_position_error_iter132/audit.py"
    )
    clean = module(
        "clean131_for136", ROOT / "reports/2026_10_09_position_error_iter131/inference_loader.py"
    )
    folder = ROOT / "reports/2026_10_09_position_error_iter116"
    sys.path.insert(0, str(folder))
    entry = module("entry116_for136", folder / "entrypoint.py")
    case_binding = binding["case_binding"]
    backend = entry.make_loader(
        ROOT,
        dict(case_binding, loader_source=entry.LOADER, loader_sha256=plan["sources"][entry.LOADER]),
    )
    return clean_audit.build_model(
        case_binding,
        clean.InferenceLoader(ROOT, backend.load_case),
        clean_audit.numerical_components(),
    )


def public_support(case, binding):
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    identity = dict(
        binding["model_identity"],
        observation_order_signature=binding["expected_input_binding"][
            "observation_order_signature"
        ],
    )
    store = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    try:
        source = store.load(binding["session_id"])
    finally:
        store.close()
    # Verify the freshly reloaded public source before projecting its metadata.
    for field in ("session_id", "input_manifest_sha256", "analysis_manifest_sha256"):
        if getattr(source, field) != identity[field]:
            raise ValueError("reloaded public identity changed: " + field)
    return adapt_support(source, case["prepared"], project_scanner_candidates(source), identity)


def perform(plan, binding):
    support = None
    try:
        parity = json.loads((ROOT / binding["parity_receipt"]).read_text())
        if (
            parity["status"] != "complete"
            or parity["label"] != binding["label"]
            or parity["protocol_sha256"] != plan["clean_protocol_sha256"]
        ):
            raise ValueError("clean parity prerequisite failed or foreign")
        model, projection, case = reconstruct(plan, binding)
        support = public_support(case, binding["case_binding"])
        result = audit(model, projection["archive"], support)
    except Exception as error:
        result = dict(
            status="failed", error=repr(error), optimizer_calls=0, position_evaluation=False
        )
    result["support"] = support
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    if any(
        os.environ.get(key) != "1"
        for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
    ):
        raise ValueError("single-thread environment required")
    path = HERE / "protocol.json"
    plan = json.loads(path.read_text())
    labels = [member["label"] for member in plan["members"]]
    if (
        len(labels) != 12
        or len(set(labels)) != 12
        or plan["optimizer_calls"] != 0
        or plan["maximum_endpoint_evaluations_per_member"] != 2
        or plan["arms"] != ["fitted-c", "zero-c"]
    ):
        raise ValueError("unexpected frozen audit scope")
    for group in ("sources", "inputs"):
        for name, expected in plan[group].items():
            if sha(ROOT / name) != expected:
                raise ValueError("frozen source/input changed: " + name)
    selected = [m for m in plan["members"] if m["label"] == args.label]
    if len(selected) != 1:
        raise ValueError("member outside fixed cohort")
    output = HERE / "results" / (args.label + ".json")
    output.parent.mkdir(exist_ok=True)
    identity = dict(label=args.label, protocol_sha256=sha(path))
    if output.exists():
        raise FileExistsError("terminal receipt already exists")
    with output.with_suffix(".claim.json").open("x") as stream:
        json.dump(identity, stream)
    started = time.monotonic()
    result = perform(plan, selected[0])
    result.update(identity, total_elapsed_s=time.monotonic() - started)
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
