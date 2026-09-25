#!/usr/bin/env python3
"""Render the sealed TRAIN-only iteration-27 stencil surface."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def verified(path: Path) -> dict:
    expected = path.with_suffix(path.suffix + ".sha256").read_text().split()[0]
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError("stencil seal mismatch")
    return json.loads(path.read_text())


def main() -> None:
    result = verified(HERE / "stencil.json")
    if result.get("truth_used") is not False or result.get("held_used") is not False:
        raise ValueError("plot input is not TRAIN-only")
    cells = result["cells"]
    east = sorted({row["east_m"] for row in cells})
    north = sorted({row["north_m"] for row in cells})
    score = {(row["east_m"], row["north_m"]): row["actual_material_score"] for row in cells}
    center = score[(0.0, 0.0)]
    values = np.asarray([[1e6 * (score[(x, y)] - center) for x in east] for y in north])
    figure, axis = plt.subplots(figsize=(6.4, 5.3), constrained_layout=True)
    image = axis.imshow(
        values,
        origin="lower",
        cmap="coolwarm",
        extent=(east[0] - 24.4, east[-1] + 24.4, north[0] - 24.4, north[-1] + 24.4),
    )
    for row in cells:
        label = f"{1e6 * (row['actual_material_score'] - center):+.2f}"
        axis.text(row["east_m"], row["north_m"], label, ha="center", va="center", fontsize=9)
    axis.scatter([-48.828125], [-48.828125], marker="*", s=180, c="black", label="winner")
    axis.scatter(
        [0], [0], marker="o", s=80, facecolors="none", edgecolors="black", label="sealed center"
    )
    axis.set(
        xlabel="east offset (m)",
        ylabel="north offset (m)",
        title="DS1 iteration 27 TRAIN score minus center (×10⁻⁶)",
    )
    axis.legend(loc="upper right")
    figure.colorbar(image, ax=axis, label="score difference ×10⁻⁶ (lower is better)")
    figure.savefig(HERE / "stencil_surface.png", dpi=180)


if __name__ == "__main__":
    main()
