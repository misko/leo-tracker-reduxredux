#!/usr/bin/env python3
"""Derive the sealed, truth-blind I29 refinement findings."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def verified(path: Path) -> dict:
    seal = path.with_suffix(path.suffix + ".sha256")
    if seal.read_text().split()[0] != digest(path).split(":", 1)[1]:
        raise ValueError(f"bad seal: {path}")
    return json.loads(path.read_text())


def main() -> None:
    inference_path = HERE / "inference.json"
    cells_path = HERE / "cells.json"
    direction_path = HERE / "stage-0-direction.json"
    inference = verified(inference_path)
    cells = verified(cells_path)
    direction = verified(direction_path)
    stage = inference["stages"][0]
    vector = np.asarray(direction["descent_direction_east_north"])
    scalar = []
    for offset in stage["sampled_offsets_m"]:
        coordinate = float(offset) * vector
        matches = [
            row
            for row in cells["cells"]
            if np.linalg.norm(np.asarray([row["east_m"], row["north_m"]], float) - coordinate)
            < 1e-8
        ]
        if len(matches) != 1:
            raise ValueError(f"no unique cell for ray offset {offset}")
        scalar.append({"offset_m": offset, "score": matches[0]["actual_material_score"]})
    winner_index = min(range(len(scalar)), key=lambda index: scalar[index]["score"])
    final_left = scalar[winner_index - 1]["offset_m"]
    final_right = scalar[winner_index + 1]["offset_m"]
    history = stage["refinement"]["history"]
    result = {
        "schema": "ds1-iteration29-resolution-safe-findings/v1",
        "complete": True,
        "truth_used": False,
        "held_used": False,
        "bindings": {
            "inference": digest(inference_path),
            "cells": digest(cells_path),
            "direction": digest(direction_path),
        },
        "outcome": "no-go-primary-refinement-post-proposal-audit-missing",
        "primary_ray": {
            "best_offset_m": scalar[winner_index]["offset_m"],
            "best_score": scalar[winner_index]["score"],
            "final_adjacent_bracket_m": [final_left, final_right],
            "final_adjacent_bracket_width_m": final_right - final_left,
            "declared_stop_width_m": 97.65625,
            "final_bracket_satisfies_declared_stop_width": final_right - final_left <= 97.65625,
            "runner_checked_only_pre_proposal_brackets": True,
            "last_checked_pre_proposal_bracket_width_m": (
                history[-1]["right_m"] - history[-1]["left_m"]
            ),
        },
        "resolution_safety": {
            "proposal_count": sum("proposal_m" in row for row in history),
            "all_proposals_met_declared_separation": all(
                row.get("proposal_minimum_separation_m", 0.0)
                >= row.get("proposal_resolution_m", float("inf"))
                for row in history
                if "proposal_m" in row
            ),
            "minimum_separation_to_requirement_ratio": min(
                row["proposal_minimum_separation_m"] / row["proposal_resolution_m"]
                for row in history
                if "proposal_m" in row
            ),
            "near_duplicate_failure_reproduced": False,
        },
        "cell_accounting": {
            "total": inference["cell_count"],
            "reused_iteration28": inference["reused_iteration28_cell_count"],
            "new": inference["new_cell_count"],
        },
        "next_iteration": (
            "after the last allowed proposal, recompute the adjacent-neighbour bracket and accept "
            "only if its width is <=97.65625 m; otherwise fail without adding an unplanned point"
        ),
    }
    output = HERE / "findings.json"
    if output.exists() or output.with_suffix(output.suffix + ".sha256").exists():
        raise FileExistsError(output)
    content = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    output.write_text(content)
    output.with_suffix(output.suffix + ".sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "  " + output.name + "\n"
    )


if __name__ == "__main__":
    main()
