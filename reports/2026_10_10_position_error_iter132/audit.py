"""Clean admission and saved ordinary endpoint parity; no optimizer or truth port."""

import hashlib
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def numerical_components():
    from leo.analysis.hard60_dynamic_rf import DynamicRFObjective
    from leo.analysis.hard60_score import Hard60Objective
    from leo.analysis.hard60_slope_prior import SlopePrior
    from leo.application.hard60_b7 import reduce_bank
    from leo.application.hard60_runner import HARD60_SCORE

    def reduction(base, seed, threshold):
        if threshold != 5:
            raise ValueError("Only original five-second bank reduction")
        return reduce_bank(base, seed)

    return dict(
        Hard60Objective=Hard60Objective,
        DynamicRFObjective=DynamicRFObjective,
        SlopePrior=SlopePrior,
        reduce_bank=reduction,
        HARD60_SCORE=HARD60_SCORE,
    )


def build_model(binding, loader, components):
    path = ROOT / binding["projection_path"]
    if digest(path) != binding["projection_sha256"]:
        raise ValueError("Clean regional projection changed")
    projection = json.loads(path.read_text())
    case = loader(binding)
    for field in ("session_id", "input_manifest_sha256", "analysis_manifest_sha256"):
        expected = binding["session_id"] if field == "session_id" else case["identity"][field]
        if projection["regional"][field] != expected:
            raise ValueError("Regional inference identity mismatch: " + field)
    constructor = module("clean132_reconstruction", HERE / "reconstruct.py")
    model = constructor.reconstruct(case, projection["regional"], projection["archive"], components)
    return model, projection, case


def check_member(binding, loader, components):
    model, projection, case = build_model(binding, loader, components)
    arms = {}
    for arm in ("fitted-c", "zero-c"):
        saved = projection["archive"]["stages"]["B7"][arm]
        vector, clock = np.asarray(saved["vector"]), np.asarray(saved["clock_coefficients"])
        actual = float(model.evaluate_joint(vector, clock)[0])
        delta = actual - saved["objective"]
        if not np.isfinite(actual) or abs(delta) > 1e-6:
            raise ValueError(f"Saved ordinary objective mismatch {arm}: {delta}")
        arms[arm] = dict(
            stored=saved["objective"],
            reconstructed=actual,
            delta=delta,
            vector_sha256=hashlib.sha256(vector.tobytes()).hexdigest(),
            clock_sha256=hashlib.sha256(clock.tobytes()).hexdigest(),
        )
    return dict(
        status="complete",
        label=binding["label"],
        session_id=binding["session_id"],
        input_binding=binding["expected_input_binding"],
        arms=arms,
        optimizer_calls=0,
    )


def main():
    import argparse

    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        if os.environ.get(name) != "1":
            raise ValueError(name + " must equal1")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=HERE / "protocol.json")
    args = parser.parse_args()
    plan = json.loads(args.protocol.read_text())
    for relative, expected in plan["sources"].items():
        if digest(ROOT / relative) != expected:
            raise ValueError("Frozen source changed: " + relative)
    if plan["optimizer_calls"] != 0 or len(plan["members"]) != 12:
        raise ValueError("Wrong bounded diagnostic scope")
    clean = module(
        "loader131_clean132", ROOT / "reports/2026_10_09_position_error_iter131/inference_loader.py"
    )
    entry_folder = ROOT / "reports/2026_10_09_position_error_iter116"
    sys.path.insert(0, str(entry_folder))
    entry = module("entry116_clean132", entry_folder / "entrypoint.py")
    for binding in plan["members"]:
        output = HERE / "results" / (binding["label"] + ".json")
        output.parent.mkdir(exist_ok=True)
        with output.with_suffix(".claim.json").open("x") as stream:
            json.dump(dict(label=binding["label"], protocol_sha256=digest(args.protocol)), stream)
        began = time.monotonic()
        result = perform_member(plan, binding, clean, entry)
        result["protocol_sha256"] = digest(args.protocol)
        result["elapsed_s"] = time.monotonic() - began
        with output.open("x") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.write("\n")


def perform_member(plan, binding, clean, entry):
    try:
        backend = entry.make_loader(
            ROOT,
            dict(
                binding,
                loader_source=entry.LOADER,
                loader_sha256=plan["sources"][entry.LOADER],
            ),
        )
        result = check_member(
            binding, clean.InferenceLoader(ROOT, backend.load_case), numerical_components()
        )
    except Exception as exc:
        result = dict(status="failed", label=binding["label"], error=repr(exc), optimizer_calls=0)
    return result


if __name__ == "__main__":
    main()
