#!/usr/bin/env python3
"""Propose a refinement solely from a finished regional training-score map."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def propose(run: Path, output: Path, modes=3, divisions=8):
    result = json.loads((run / "result.json").read_text())
    if not result["complete"] or output.exists():
        raise ValueError("finished source and fresh output required")
    grid = np.load(run / "grid.npz")
    scores = np.load(run / "accumulated.npz")["train"]
    region = result["region"]
    # Infer actual local sample spacing for second refinement too.
    dx = np.diff(np.unique(np.round(grid["east_km"], 8)))
    dy = np.diff(np.unique(np.round(grid["north_km"], 8)))
    radius = max(float(np.min(dx[dx > 1e-7])), float(np.min(dy[dy > 1e-7])))
    selected = []
    for i in np.argsort(-scores, kind="stable"):
        centre = np.array([grid["east_km"][i], grid["north_km"][i]])
        if all(np.linalg.norm(centre - old) > 2 * radius for old in selected):
            selected.append(centre)
        if len(selected) >= modes:
            break
    offsets = np.linspace(-radius, radius, 2 * divisions + 1)
    xx, yy = np.meshgrid(offsets, offsets)
    points = np.concatenate(
        [centre + np.column_stack([xx.ravel(), yy.ravel()]) for centre in selected]
    )
    points = np.unique(np.round(points, 8), axis=0)
    inside = (np.abs(points[:, 0]) <= region["width_km"] / 2) & (
        np.abs(points[:, 1]) <= region["height_km"] / 2
    )
    points = points[inside]
    proposal = {
        "east_km": points[:, 0].tolist(),
        "north_km": points[:, 1].tolist(),
        "altitude_m": result["altitude_m"],
        "training_map_digest": "sha256:"
        + hashlib.sha256((run / "accumulated.npz").read_bytes()).hexdigest(),
        "parent_run": run.name,
        "selected_centres_km": [v.tolist() for v in selected],
        "half_width_km": radius,
        "spacing_km": radius / divisions,
        "mode_limit": modes,
        "not_an_exhaustive_global_refinement": True,
        "heldout_values_or_truth_used": False,
    }
    output.write_text(json.dumps(proposal, indent=2, allow_nan=False) + "\n")
    print(f"{len(points)} refinement points; spacing {radius / divisions:g} km; {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--modes", type=int, default=3)
    parser.add_argument("--divisions", type=int, default=8)
    args = parser.parse_args()
    propose(args.run, args.output, args.modes, args.divisions)


if __name__ == "__main__":
    main()
