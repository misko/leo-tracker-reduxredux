#!/usr/bin/env python3
"""Run the reviewed blind staged/local cone models on five DS3 bindings."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE_PATH = HERE.parents[1] / "2026_09_24_ds2_geometry_cone_evaluation/run_blind_reassociated.py"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_source() -> Any:
    spec = importlib.util.spec_from_file_location("ds3_dynamic_geometry", SOURCE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load reviewed DS2 geometry runner")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--receiver-labels", type=Path, required=True)
    parser.add_argument(
        "--orientation-mode", choices=("learned15", "fixed-up"), default="learned15"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix(args.output.suffix + ".sha256").exists():
        raise FileExistsError(f"refusing to replace sealed output: {args.output}")
    plan = json.loads(args.plan.read_text())
    sessions = tuple(map(str, plan.get("eligible_session_ids", [])))
    labels = json.loads(args.receiver_labels.read_text())
    if len(sessions) != 5 or {x["session_id"] for x in labels["sessions"]} != set(sessions):
        raise ValueError("geometry plan and receiver labels must bind the same five sessions")
    if labels.get("reference_coordinate_present") is not False:
        raise ValueError("receiver-label artifact must explicitly exclude a reference coordinate")

    source = load_source()
    source.SESSIONS = sessions
    original_orientations = source.BASE.orientations

    def bounded_orientations() -> np.ndarray:
        grid = original_orientations()
        maximum_tilt = 15 if args.orientation_mode == "learned15" else 0
        return grid[grid[:, 0] <= maximum_tilt]

    source.BASE.orientations = bounded_orientations
    with tempfile.TemporaryDirectory(dir=args.output.parent) as raw:
        temporary = Path(raw) / "inference.json"
        compatible_labels = Path(raw) / "receiver-labels.json"
        compatible = dict(labels)
        compatible["schema"] = "ds2-portable-track-receiver-labels/v1"
        compatible_labels.write_text(json.dumps(compatible, sort_keys=True) + "\n")
        old_argv = sys.argv
        try:
            sys.argv = [
                str(SOURCE_PATH),
                "--cache-root",
                str(args.cache_root),
                "--receiver-labels",
                str(compatible_labels),
                "--output",
                str(temporary),
            ]
            source.main()
        finally:
            sys.argv = old_argv
        document = json.loads(temporary.read_text())
    joint = [row for row in document["results"] if len(row["session_ids"]) > 1]
    singles = [row for row in document["results"] if len(row["session_ids"]) == 1]
    if len(singles) != 5 or len(joint) != 1 or set(joint[0]["session_ids"]) != set(sessions):
        raise ValueError("reviewed runner did not emit five singles and one joint result")
    joint[0]["label"] = "joint-five-geometry-captures"
    document["schema"] = "ds3-lt3d-staged-local-cone-inference/v1"
    document["dataset_name"] = "DS3"
    document["session_policy"] = "all five explicitly capture-bound LT3D-001A sessions"
    document["orientation_mode"] = args.orientation_mode
    document["orientation_constraint"] = (
        "fixture tilt <=15 degrees from zenith; yaw fitted"
        if args.orientation_mode == "learned15"
        else "fixture tilt fixed at zero; yaw fitted"
    )
    document["top10_model_ids"] = (
        ["lt3d_geometry_only", "lt3d_learned_zenith_cone"]
        if args.orientation_mode == "learned15"
        else ["lt3d_fixed_up_cone"]
    )
    document["ds3_bindings"] = {
        "geometry_plan": digest(args.plan),
        "receiver_labels": digest(args.receiver_labels),
        "adapter": digest(Path(__file__)),
        "reviewed_runner": digest(SOURCE_PATH),
    }
    content = json.dumps(document, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content)
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )


if __name__ == "__main__":
    main()
