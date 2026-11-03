#!/usr/bin/env python3
"""Fixed-endpoint cost, gradient and CFO-profile diagnostic; never fits position."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = HERE.parent.parent / "2026_09_30_ds11_single10"
SCREEN = tuple(range(0, 32, 4))
PROJECTED_GRADIENT_EVALUATIONS = 109
PROJECTED_SCORE_EVALUATIONS = 24
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as fast  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_model_module():
    path = HERE / "model.py"
    spec = importlib.util.spec_from_file_location("soft_fragment_cfo_diagnostic_model", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def timed_evaluate(model, x, gradient):
    started = time.monotonic()
    outcome = model.evaluate(x, gradient=gradient)
    elapsed = time.monotonic() - started
    return outcome, elapsed, dict(model.last_profile_audit)


def run(indices):
    fast.baseline.profile = fast.profile
    plugin = load_model_module()
    plan_path = BASE / "plan.json"
    plan = json.loads(plan_path.read_text())
    rows = []
    for index in indices:
        entry = plan["inputs"][index]
        for artifact in entry["artifacts"]:
            if "sha256:" + digest(Path(artifact["path"])) != artifact["sha256"]:
                raise ValueError(f"plan artifact digest mismatch at index {index}")
        documents = fast.load_documents({"config": plan["config"], "inputs": [entry]})
        result_path = BASE / "runs" / f"{index:02d}_iid.json"
        endpoint = np.asarray(json.loads(result_path.read_text())["selected"]["x"], dtype=float)
        identity = plugin.build_model(documents, plan["config"], "identity_only", index=index)
        treatment = plugin.build_model(documents, plan["config"], "gamma1000", index=index)
        identity_result, identity_seconds, identity_audit = timed_evaluate(
            identity, endpoint, True
        )
        treatment_score_only, score_seconds, _ = timed_evaluate(
            treatment, endpoint, False
        )
        treatment_result, gradient_seconds, treatment_audit = timed_evaluate(
            treatment, endpoint, True
        )
        if treatment_score_only["score"] != treatment_result["score"]:
            raise ValueError("score differs between gradient modes")
        numerical = np.empty(3)
        finite_difference_seconds = 0.0
        for axis, step in enumerate((1e-4, 1e-4, 1e-5)):
            delta = np.eye(3)[axis] * step
            plus, elapsed_plus, _ = timed_evaluate(treatment, endpoint + delta, False)
            minus, elapsed_minus, _ = timed_evaluate(treatment, endpoint - delta, False)
            finite_difference_seconds += elapsed_plus + elapsed_minus
            numerical[axis] = (plus["score"] - minus["score"]) / (2.0 * step)
        discrepancy = np.abs(numerical - treatment_result["gradient"])
        projected = (
            PROJECTED_GRADIENT_EVALUATIONS * gradient_seconds
            + PROJECTED_SCORE_EVALUATIONS * score_seconds
        )
        rows.append({
            "index": index, "session_id": entry["session_id"],
            "endpoint": endpoint.tolist(), "pairs": treatment.metadata["paired_groups"],
            "identity_only": {
                "score": float(identity_result["score"]),
                "gradient": identity_result["gradient"].tolist(),
                "gradient_seconds": identity_seconds,
                "profile_audit": identity_audit,
            },
            "gamma1000": {
                "score": float(treatment_result["score"]),
                "gradient": treatment_result["gradient"].tolist(),
                "score_seconds": score_seconds, "gradient_seconds": gradient_seconds,
                "finite_difference_seconds": finite_difference_seconds,
                "finite_difference_gradient": numerical.tolist(),
                "finite_difference_discrepancy": discrepancy.tolist(),
                "max_finite_difference_discrepancy": float(discrepancy.max()),
                "profile_audit": treatment_audit,
            },
            "cfo_effect": {
                "score_difference": float(treatment_result["score"] - identity_result["score"]),
                "gradient_difference": (
                    treatment_result["gradient"] - identity_result["gradient"]
                ).tolist(),
                "max_absolute_gradient_difference": float(np.max(np.abs(
                    treatment_result["gradient"] - identity_result["gradient"]
                ))),
            },
            "runtime_projection": {
                "basis": (
                    "109 gradient evaluations: maximum observed four-start screen total; "
                    "plus 24 score-only finite-difference evaluations"
                ),
                "gradient_evaluations": PROJECTED_GRADIENT_EVALUATIONS,
                "score_evaluations": PROJECTED_SCORE_EVALUATIONS,
                "projected_seconds": projected,
                "passes_90_second_gate": projected <= 90.0,
            },
        })
    return {
        "schema": "ds11-soft-fragment-cfo-fixed-endpoint-diagnostic/v1",
        "scope": "fixed original IID endpoints only; no position optimization",
        "indices": list(indices), "rows": rows,
        "summary": {
            "all_runtime_projections_pass": all(
                row["runtime_projection"]["passes_90_second_gate"] for row in rows
            ),
            "max_projected_seconds": max(
                row["runtime_projection"]["projected_seconds"] for row in rows
            ),
            "max_finite_difference_discrepancy": max(
                row["gamma1000"]["max_finite_difference_discrepancy"] for row in rows
            ),
            "max_profile_gradient": max(
                row["gamma1000"]["profile_audit"]["max_gradient"] for row in rows
            ),
            "worst_profile_max_hessian_eigenvalue": max(
                row["gamma1000"]["profile_audit"]["worst_max_hessian_eigenvalue"]
                for row in rows if row["gamma1000"]["profile_audit"]["candidate_profiles"]
            ),
            "max_absolute_cfo_gradient_effect": max(
                row["cfo_effect"]["max_absolute_gradient_difference"] for row in rows
            ),
        },
        "source_sha256": {
            str(path): digest(path) for path in (
                HERE / "model.py", HERE / "diagnostic.py",
                HERE.parent / "same_source_cfo_audit" / "SOFT_CFO_DESIGN.md",
                HERE.parent / "same_source_cfo_audit" / "results.json",
                plan_path, ROOT / "tools" / "ds7_baseline_adapter.py",
                ROOT / "tools" / "ds7_fast_baseline_adapter.py",
            )
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--indices", default=",".join(map(str, SCREEN)))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    indices = tuple(int(value) for value in args.indices.split(","))
    result = run(indices)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    main()
