#!/usr/bin/env python3
"""Plot the sealed I29 search cells and optional post-seal reference."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
REFERENCE = (37.84903264307456, -122.4856541910174)


def verified(path: Path) -> dict:
    seal = path.with_suffix(path.suffix + ".sha256")
    expected = seal.read_text().split()[0]
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError(f"bad seal: {path}")
    return json.loads(path.read_text())


def reference_enu() -> tuple[float, float]:
    # Small-offset WGS84 approximation is more accurate than the plot scale requires.
    lat0, lon0 = map(np.radians, (37.85822833, -122.47896246))
    lat, lon = map(np.radians, REFERENCE)
    north = (lat - lat0) * 6_371_008.8
    east = (lon - lon0) * 6_371_008.8 * np.cos(0.5 * (lat + lat0))
    return float(east), float(north)


def main() -> None:
    cells = verified(HERE / "cells.json")["cells"]
    inference = verified(HERE / "inference.json")
    evaluation = verified(HERE / "evaluation" / "postseal-evaluation.json")
    east = np.asarray([row["east_m"] for row in cells])
    north = np.asarray([row["north_m"] for row in cells])
    score = np.asarray([row["actual_material_score"] for row in cells])
    reused = np.asarray([bool(row.get("reused_bit_for_bit_from_iteration28")) for row in cells])
    score_delta = 1e6 * (score - np.min(score))
    figure, axis = plt.subplots(figsize=(8.3, 7.0), constrained_layout=True)
    scatter = axis.scatter(east, north, c=score_delta, cmap="viridis", s=38, zorder=2)
    axis.scatter(
        east[reused],
        north[reused],
        s=78,
        facecolors="none",
        edgecolors="0.45",
        linewidths=0.8,
        label="reused exact I28 cell",
    )
    estimate = inference.get("estimate")
    if estimate is not None:
        axis.scatter(
            [estimate["east_m"]],
            [estimate["north_m"]],
            marker="*",
            s=220,
            c="tab:red",
            edgecolors="black",
            label="sealed RF estimate",
            zorder=4,
        )
    truth_e, truth_n = reference_enu()
    axis.scatter(
        [truth_e],
        [truth_n],
        marker="X",
        s=150,
        c="white",
        edgecolors="black",
        label="post-seal surveyed reference",
        zorder=4,
    )
    status = "qualified" if evaluation["qualified_before_truth"] else "not qualified"
    error = evaluation.get("estimate")
    suffix = (
        "no terminal estimate" if error is None else f"{error['postseal_error_km']:.3f} km error"
    )
    axis.set(
        xlabel="East of sealed anchor (m)",
        ylabel="North of sealed anchor (m)",
        title=f"DS1 iteration 29 resolution-safe search\n{status}; {suffix}",
    )
    axis.set_aspect("equal", adjustable="datalim")
    axis.grid(alpha=0.2)
    axis.legend(loc="best")
    figure.colorbar(scatter, ax=axis, label="TRAIN score above evaluated minimum (×10⁻⁶)")
    figure.savefig(HERE / "search_surface.png", dpi=180)


if __name__ == "__main__":
    main()
