#!/usr/bin/env python3
"""Execute the receipt-bound DS2 LT3D geometry/cone arm.

This adapter admits only the sessions sealed by the successor geometry plan,
delegates numerical inference to the reviewed blind runner, and adds successor
provenance before sealing the new artifact.  It never accepts a reference
coordinate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "2026_09_24_ds2_geometry_cone_evaluation"
RUNNER = SOURCE / "run_blind_reassociated.py"
EXPECTED_FAMILIES = {
    "learned_pointing_cone_quantiles",
    "fixed_hard_cone_orientation",
    "staged_full_fov_cone_sweep",
    "local_fitted_full_fov_cone_position",
}
EXPECTED_MAPPINGS = {(0, 1), (1, 0)}


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def validate_plan(plan: dict[str, Any]) -> tuple[str, ...]:
    if plan.get("schema") != "ds2-successor-geometry-cone-plan/v1":
        raise ValueError("unexpected successor geometry plan schema")
    if plan.get("reference_coordinate_present") is not False:
        raise ValueError("geometry inference plan must not contain a reference coordinate")
    if plan.get("reference_used_for_inference") is not False:
        raise ValueError("geometry inference plan may not use a reference coordinate")
    if set(plan.get("fitted_cone_families", [])) != EXPECTED_FAMILIES:
        raise ValueError("successor plan does not admit the complete cone family")
    mappings = {tuple(map(int, row)) for row in plan.get("receiver_slot_mappings", [])}
    if mappings != EXPECTED_MAPPINGS:
        raise ValueError("successor plan must marginalize both RX-to-slot mappings")
    sessions = tuple(row["session_id"] for row in plan.get("sessions", []))
    if len(sessions) != 3 or len(set(sessions)) != 3:
        raise ValueError("successor geometry plan must contain three unique bound sessions")
    for row in plan["sessions"]:
        if not str(row.get("capture_binding_digest", "")).startswith("sha256:"):
            raise ValueError("session lacks a capture-time geometry binding digest")
        if not str(row.get("fixture_digest", "")).startswith("sha256:"):
            raise ValueError("session lacks a fixture digest")
    return sessions


def validate_labels(path: Path, expected_sessions: tuple[str, ...]) -> None:
    labels = json.loads(path.read_text())
    if labels.get("schema") != "ds2-portable-track-receiver-labels/v1":
        raise ValueError("unexpected receiver-label schema")
    actual = {row["session_id"] for row in labels.get("sessions", [])}
    if actual != set(expected_sessions):
        raise ValueError("receiver-label sessions do not match the successor geometry plan")
    for scan in labels["sessions"]:
        if not scan.get("tracks"):
            raise ValueError(f"no receipt-bound tracks for {scan['session_id']}")
        if any(int(row["receiver_id"]) not in (0, 1) for row in scan["tracks"]):
            raise ValueError("receiver label outside RX0/RX1")


def validate_inference(document: dict[str, Any], expected_sessions: tuple[str, ...]) -> None:
    if document.get("schema") != "ds2-lt3d-geometry-cone-blind-reassociated-inference/v1":
        raise ValueError("unexpected geometry inference schema")
    if document.get("complete") is not True:
        raise ValueError("geometry inference is incomplete")
    if document.get("reference_used_for_inference") is not False:
        raise ValueError("reference coordinate leaked into geometry inference")
    if document.get("held_used_for_selection") is not False:
        raise ValueError("held rows were used for model selection")
    results = document.get("results", [])
    if len(results) != 4:
        raise ValueError("expected three single-session and one joint geometry result")
    singles = {row["label"] for row in results if len(row.get("session_ids", [])) == 1}
    if singles != set(expected_sessions):
        raise ValueError("geometry output sessions do not match admitted sessions")
    joint = [row for row in results if len(row.get("session_ids", [])) == 3]
    if len(joint) != 1 or set(joint[0]["session_ids"]) != set(expected_sessions):
        raise ValueError("missing all-three-session joint geometry result")
    for row in results:
        if len(row["staged_full_fov"]["cone_quantiles"]) != 2:
            raise ValueError("learned cone quantiles do not contain both mappings")
        if len(row["staged_full_fov"]["scenarios"]) != 10:
            raise ValueError("incomplete 10-90 degree staged FOV sweep")
        if set(row["fixed_hard_half_angle"]) != {"10", "15", "20", "30"}:
            raise ValueError("incomplete fixed hard-cone family")
        if set(row["local_fitted_cone"]["winners"]) != {
            "10", "20", "25", "30", "40", "50"
        }:
            raise ValueError("incomplete local fitted-cone family")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--receiver-labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.output.exists() or args.output.with_suffix(".sha256").exists():
        raise FileExistsError(f"refusing to replace sealed output: {args.output}")
    plan = json.loads(args.plan.read_text())
    sessions = validate_plan(plan)
    validate_labels(args.receiver_labels, sessions)
    started = time.monotonic()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.output.parent, prefix=".geometry-rerun-") as raw:
        temporary = Path(raw) / "inference.json"
        command = [
            sys.executable,
            str(RUNNER),
            "--cache-root",
            str(args.cache_root),
            "--receiver-labels",
            str(args.receiver_labels),
            "--output",
            str(temporary),
        ]
        subprocess.run(command, check=True)
        document = json.loads(temporary.read_text())
    validate_inference(document, sessions)
    document["successor_bindings"] = {
        "geometry_plan": digest(args.plan),
        "receiver_labels": digest(args.receiver_labels),
        "execution_adapter": digest(Path(__file__)),
        "admitted_sessions": list(sessions),
        "capture_binding_digests": {
            row["session_id"]: row["capture_binding_digest"] for row in plan["sessions"]
        },
        "fixture_digests": {
            row["session_id"]: row["fixture_digest"] for row in plan["sessions"]
        },
    }
    document["successor_elapsed_s"] = time.monotonic() - started
    content = canonical(document)
    args.output.write_text(content)
    args.output.with_suffix(".sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )


if __name__ == "__main__":
    main()
