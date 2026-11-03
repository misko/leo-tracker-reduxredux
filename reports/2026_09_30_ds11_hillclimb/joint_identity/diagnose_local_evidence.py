"""Bounded training-only joint-vs-IID local evidence diagnostic."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import statistics
import sys
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = HERE.parent.parent / "2026_09_30_ds11_single10"
SCREEN = tuple(range(0, 32, 4))
POINTS = {
    "incumbent": (0.0, 0.0),
    "east_plus_2km": (2.0, 0.0),
    "east_minus_2km": (-2.0, 0.0),
    "north_plus_2km": (0.0, 2.0),
    "north_minus_2km": (0.0, -2.0),
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_model():
    path = HERE / "model.py"
    spec = importlib.util.spec_from_file_location("ds11_joint_identity_diagnostic", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def summarize_responsibilities(rows):
    tv = [row["total_variation"] for row in rows]
    iid = [row["iid_selected_probability"] for row in rows]
    joint = [row["joint_selected_probability"] for row in rows]
    maximum = [row["joint_max_probability"] for row in rows]
    return {
        "grouped_tracks": len(rows),
        "mean_total_variation": statistics.fmean(tv),
        "median_total_variation": statistics.median(tv),
        "max_total_variation": max(tv),
        "mean_iid_frozen_identity_probability": statistics.fmean(iid),
        "mean_joint_frozen_identity_probability": statistics.fmean(joint),
        "mean_abs_frozen_identity_probability_change": statistics.fmean(
            abs(a - b) for a, b in zip(iid, joint, strict=True)
        ),
        "joint_frozen_identity_is_max": sum(
            abs(a - b) <= 1e-12 for a, b in zip(joint, maximum, strict=True)
        ),
        "joint_max_probability_ge_0_99": sum(value >= 0.99 for value in maximum),
        "joint_max_probability_ge_0_999999": sum(value >= 0.999999 for value in maximum),
    }


def main():
    sys.path.insert(0, str(ROOT / "tools"))
    import ds7_fast_baseline_adapter as baseline

    baseline.baseline.profile = baseline.profile
    plugin = load_model()
    plan_path = BASE / "plan.json"
    plan = json.loads(plan_path.read_text())
    scans = []
    for index in SCREEN:
        entry = plan["inputs"][index]
        documents = baseline.load_documents({"config": plan["config"], "inputs": [entry]})
        incumbent_path = BASE / "runs" / f"{index:02d}_iid.json"
        incumbent = np.asarray(json.loads(incumbent_path.read_text())["selected"]["x"])
        iid = baseline.baseline.Stationary(documents[0], plan["config"])
        joint = plugin.build_model(documents, plan["config"], "joint_identity", index=index)
        points = []
        for label, (east, north) in POINTS.items():
            x = incumbent + np.asarray([east, north, 0.0])
            iid_score, iid_gradient = iid.evaluate(x, True)
            joint_result = joint.evaluate(x, True)
            joint_gradient = np.asarray(joint_result["gradient"])
            iid_gradient = np.asarray(iid_gradient)
            delta = joint_gradient - iid_gradient
            iid_norm = float(np.linalg.norm(iid_gradient[:2]))
            joint_norm = float(np.linalg.norm(joint_gradient[:2]))
            cosine = None
            if iid_norm > 0 and joint_norm > 0:
                cosine = float(
                    iid_gradient[:2] @ joint_gradient[:2] / (iid_norm * joint_norm)
                )
            points.append({
                "label": label,
                "x": x.tolist(),
                "iid_score": float(iid_score),
                "joint_score": float(joint_result["score"]),
                "joint_minus_iid_score": float(joint_result["score"] - iid_score),
                "iid_gradient": iid_gradient.tolist(),
                "joint_gradient": joint_gradient.tolist(),
                "joint_minus_iid_gradient": delta.tolist(),
                "position_gradient_delta_norm": float(np.linalg.norm(delta[:2])),
                "timing_gradient_abs_delta": abs(float(delta[2])),
                "position_gradient_cosine": cosine,
                "responsibility": summarize_responsibilities(
                    joint.responsibility_diagnostics(x)
                ),
            })
        scans.append({
            "index": index,
            "session_id": entry["session_id"],
            "joint_groups": joint.metadata["joint_groups"],
            "joint_group_tracks": joint.metadata["joint_group_tracks"],
            "points": points,
            "incumbent_sha256": digest(incumbent_path),
        })
    output = {
        "schema": "ds11-joint-identity-local-evidence/v1",
        "scope": "screen8 training only; original IID incumbent and fixed +/-2km E/N offsets",
        "screen_indices": list(SCREEN),
        "points": list(POINTS),
        "scans": scans,
        "source_sha256": {
            str(path): digest(path) for path in (
                Path(__file__), HERE / "model.py", HERE / "DESIGN.md", plan_path,
                HERE.parent / "source_balance/catalogue_identities.json",
            )
        },
    }
    destination = HERE / "local_evidence.json"
    with destination.open("x") as stream:
        json.dump(output, stream, indent=2, allow_nan=False)
    compact = []
    for scan in scans:
        for point in scan["points"]:
            compact.append({
                "index": scan["index"],
                "point": point["label"],
                "gradient_delta_norm": point["position_gradient_delta_norm"],
                "gradient_cosine": point["position_gradient_cosine"],
                "mean_tv": point["responsibility"]["mean_total_variation"],
                "joint_saturated": point["responsibility"]["joint_max_probability_ge_0_999999"],
                "grouped_tracks": point["responsibility"]["grouped_tracks"],
            })
    print(json.dumps(compact, indent=2))


if __name__ == "__main__":
    main()
