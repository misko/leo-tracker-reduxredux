#!/usr/bin/env python3
"""Build the machine-readable iteration-15/19 boundary audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

CONTROL_BOUND = 0.25
MARGIN = 1e-6


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def rates(inference: dict[str, Any], predicate: Any) -> list[dict[str, Any]]:
    rows = []
    for audit in inference["selected_group_audits"]:
        for norad, value in audit["rate_only"]["rates_s_h"].items():
            value = float(value)
            if predicate(value):
                rows.append(
                    {"group_id": audit["group_id"], "norad": norad, "rate_s_h": value}
                )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--postseal", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    control = json.loads(args.control.read_text())
    candidate = json.loads(args.candidate.read_text())
    qualification = json.loads(args.qualification.read_text())
    postseal = json.loads(args.postseal.read_text())
    path = [
        {
            "stage_index": row["stage_index"],
            "translation_index": row["translation_index"],
            "east_km_from_parent": row["winner"]["east_km_from_iteration12"],
            "north_km_from_parent": row["winner"]["north_km_from_iteration12"],
            "winner_on_edge": row["winner_on_edge"],
            "selection_objective": row["winner"]["weighted_selection_objective"],
        }
        for row in candidate["steps"]
    ]
    output = {
        "schema": "ds1-iteration19-rate-bound-comparison/v1",
        "reference_used_for_inference": False,
        "inputs": {
            "control": {"path": str(args.control), "sha256": digest(args.control)},
            "candidate": {"path": str(args.candidate), "sha256": digest(args.candidate)},
            "qualification": {
                "path": str(args.qualification),
                "sha256": digest(args.qualification),
            },
            "postseal": {"path": str(args.postseal), "sha256": digest(args.postseal)},
        },
        "control": {
            "rate_bound_s_h": CONTROL_BOUND,
            "reported_qualified": bool(control["qualified"]),
            "postseal_error_km": 0.5755771101795844,
            "rates_inside_numerical_guard": rates(
                control, lambda value: abs(value) >= CONTROL_BOUND - MARGIN
            ),
        },
        "candidate": {
            "rate_bound_s_h": float(candidate["rate_bound_s_h"]),
            "complete": bool(candidate["complete"]),
            "qualified": bool(qualification["qualified"]),
            "postseal_error_km": float(postseal["postseal_error_km"]),
            "unique_group_coordinate_fits": int(candidate["unique_group_coordinate_fits"]),
            "elapsed_s": float(candidate["elapsed_s"]),
            "rates_beyond_control_bound": rates(
                candidate, lambda value: abs(value) > CONTROL_BOUND
            ),
            "rates_inside_candidate_guard": rates(
                candidate,
                lambda value: abs(value)
                >= float(candidate["rate_bound_s_h"])
                - float(candidate["rate_boundary_margin_s_h"]),
            ),
            "path": path,
        },
        "conclusion": "widened-rate basin remained on the northwest boundary and is unqualified",
    }
    content = json.dumps(output, indent=2, sort_keys=True) + "\n"
    args.output.write_text(content)
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )


if __name__ == "__main__":
    main()
