"""No-fit selected B7 reconstruction, at most one evaluation per saved arm."""

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def construct(case, selected, components):
    if selected["selection"]["accepted_stage"] != "B7":
        raise ValueError("Unsupported selected stage; preserve member failure")
    fit = selected["fit"]
    state = fit["joint_state"]
    if state["stage"] != "B7" or not fit["converged"]:
        raise ValueError("Unqualified or mismatched selected B7 state")
    numbers = selected["selection"]["satellites"]
    if len(set(numbers)) != len(numbers):
        raise ValueError("Duplicate selected satellites")
    lookup = {int(n): i for i, n in enumerate(case["bank"].numbers)}
    bank = case["bank"].select([lookup[n] for n in numbers])
    baseline = np.asarray(state["receiver_baseline_hz"], float)
    nodes = np.asarray(state["clock_nodes_s"], float)
    centers = np.asarray(state["satellite_centers_s"], float)
    if baseline.shape != case["observations"].times_s.shape:
        raise ValueError("Saved baseline observation shape mismatch")
    if nodes.ndim != 1 or len(nodes) < 3 or not np.all(np.diff(nodes) > 0):
        raise ValueError("Invalid saved clock node authority")
    if not all(np.isfinite(a).all() for a in (baseline, nodes, centers)):
        raise ValueError("Nonfinite saved physical state")
    base = components["Hard60Objective"](
        case["observations"],
        bank,
        case["prior"],
        components["HARD60_SCORE"],
        receiver_baseline_hz=baseline,
    )
    model = components["SlopePrior"](base, nodes, np.zeros((2, len(nodes))), centers, 0.5)
    vector, clock = np.asarray(fit["vector"], float), np.asarray(fit["clock_coefficients"], float)
    if vector.shape != (model.size,) or clock.shape != model.initial_clock.shape:
        raise ValueError("Saved endpoint layout mismatch")
    if not np.isfinite(vector).all() or not np.isfinite(clock).all():
        raise ValueError("Nonfinite endpoint")
    np.testing.assert_array_equal(vector, state["vector"])
    np.testing.assert_array_equal(clock, state["clock_coefficients"])
    return model, vector, clock


def check_member(binding, loader, components, projection):
    if projection["session_id"] != binding["session_id"]:
        raise ValueError("Selected session mismatch")
    if projection["input_binding"] != binding["expected_input_binding"]:
        raise ValueError("Selected physical signatures mismatch")
    if "preparation_source_sha256" in projection:
        raise ValueError("Provenance-only source digest cannot be inference admission")
    case = loader(binding)  # Clean131 validates all five physical signatures.
    arms = {}
    evaluations = 0
    for arm in ("fitted-c", "zero-c"):
        try:
            selected = projection["operational"][arm]
            model, vector, clock = construct(case, selected, components)
            if arm == "zero-c" and (vector[6] != 0 or np.any(clock[-2:] != 0)):
                raise ValueError("Saved zero-c endpoint is not RF locked")
            evaluations += 1
            actual = float(model.evaluate_joint(vector, clock)[0])
            stored = float(selected["fit"]["objective"])
            delta = actual - stored
            if not np.isfinite(actual) or not np.isfinite(stored) or abs(delta) > 1e-6:
                raise ValueError(f"Saved selected objective mismatch {arm}: {delta}")
            arms[arm] = dict(status="complete", stored=stored, reconstructed=actual, delta=delta)
        except Exception as exc:
            arms[arm] = dict(status="failed", error=repr(exc))
    return dict(
        status="complete" if all(a["status"] == "complete" for a in arms.values()) else "failed",
        label=binding["label"],
        arms=arms,
        optimizer_calls=0,
        endpoint_evaluations=evaluations,
    )


def read_projection(binding):
    import hashlib

    path = ROOT / binding["selected_path"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != binding["selected_sha256"]:
        raise ValueError("Selected inference projection hash mismatch")
    return json.loads(path.read_text())


def main():
    import argparse
    import hashlib
    import importlib.util
    import os
    import sys
    import time

    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        if os.environ.get(name) != "1":
            raise ValueError(name + " must equal 1")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=HERE / "parity-protocol.json")
    parser.add_argument("--shard", type=int, choices=(0, 1), required=True)
    args = parser.parse_args()
    plan = json.loads(args.protocol.read_text())
    if (
        plan["optimizer_calls"] != 0
        or plan["endpoint_evaluations_per_member"] != 2
        or len(plan["members"]) != 193
    ):
        raise ValueError("Wrong no-fit scope")
    for relative, expected in {**plan["sources"], **plan["inputs"]}.items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen input/source changed: " + relative)

    def module(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        value = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(value)
        return value

    helper = module(
        "pure132_helpers_for137", HERE.parent / "2026_10_10_position_error_iter132/audit.py"
    )
    clean = module(
        "clean131_for137", HERE.parent / "2026_10_09_position_error_iter131/inference_loader.py"
    )
    entry_dir = HERE.parent / "2026_10_09_position_error_iter116"
    sys.path.insert(0, str(entry_dir))
    entry = module("entry116_for137", entry_dir / "entrypoint.py")
    protocol_sha = hashlib.sha256(args.protocol.read_bytes()).hexdigest()
    directory = HERE / "parity-results"
    directory.mkdir(exist_ok=True)
    for index, binding in enumerate(plan["members"]):
        if index % 2 != args.shard:
            continue
        output = directory / (binding["label"] + ".json")
        if output.exists():
            raise ValueError("Terminal result exists; no silent rerun")
        with output.with_suffix(".claim.json").open("x") as stream:
            json.dump(dict(label=binding["label"], protocol_sha256=protocol_sha), stream)
        began = time.monotonic()
        try:
            backend = entry.make_loader(
                ROOT,
                dict(
                    binding, loader_source=entry.LOADER, loader_sha256=plan["sources"][entry.LOADER]
                ),
            )
            loader = clean.InferenceLoader(ROOT, backend.load_case)
            result = check_member(
                binding, loader, helper.numerical_components(), read_projection(binding)
            )
        except Exception as exc:
            result = dict(
                status="failed", label=binding["label"], error=repr(exc), optimizer_calls=0
            )
        result.update(
            protocol_sha256=protocol_sha,
            elapsed_s=time.monotonic() - began,
            session_id=binding["session_id"],
        )
        with output.open("x") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.write("\n")


if __name__ == "__main__":
    main()
