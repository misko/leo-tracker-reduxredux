#!/usr/bin/env python3
"""Render the sealed circular-offset conditional diagnostic."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_executed_module():
    path = HERE / "executed-ablation-source.py"
    spec = importlib.util.spec_from_file_location("executed_circular_ablation", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def synthetic_convergence(module) -> dict:
    """Exercise the circular quadrature on fixed arbitrary multimodal examples."""
    rows = []
    values = {}
    sharp_values = {}
    offsets = np.array([-91_000.0, 28_000.0, 34_000.0, 103_000.0])
    shape = np.array([-2.0, 0.0, -0.8, -3.0])
    for size in (512, 1024, 2048):
        grid = np.linspace(
            -module.PILOT_ALIAS_HZ / 2,
            module.PILOT_ALIAS_HZ / 2,
            size,
            endpoint=False,
        )
        likelihood = np.vstack(
            [
                module.track_log_likelihood(
                    shape,
                    -4.5,
                    offsets + shift,
                    grid,
                    30_000.0,
                    0.05,
                )
                for shift in (0.0, 2_000.0, -1_500.0, 800.0)
            ]
        )
        value = module.predictive_delta(
            likelihood,
            np.array([True, True, True, False]),
            np.array([False, False, False, True]),
        )
        values[size] = value
        # Stress the narrowest arm with as many repeated training tracks as the
        # largest real receiver/edge group. Put the true mode halfway between
        # adjacent 1024-grid nodes, and offset the heldout track by 900 Hz.
        half_1024_bin = module.PILOT_ALIAS_HZ / 2048
        train_factor = module.circular_factor(
            np.array([half_1024_bin]), grid, 3_000.0, 0.05
        )[0]
        heldout_factor = module.circular_factor(
            np.array([half_1024_bin + 900.0]), grid, 3_000.0, 0.05
        )[0]
        sharp_likelihood = np.vstack(
            [np.log(train_factor)] * 77 + [np.log(heldout_factor)]
        )
        sharp_value = module.predictive_delta(
            sharp_likelihood,
            np.array([True] * 77 + [False]),
            np.array([False] * 77 + [True]),
        )
        sharp_values[size] = sharp_value
        rows.append(
            {
                "grid_size": size,
                "arbitrary_multimodal_delta_log_score": value,
                "sharp_77_training_tracks_delta_log_score": sharp_value,
            }
        )
    return {
        "schema": "circular-offset-synthetic-grid-convergence/v1",
        "scope": (
            "synthetic arbitrary multimodal and 77-track narrow-posterior stress; "
            "real-data grid convergence not rerun"
        ),
        "rows": rows,
        "arbitrary_absolute_delta_1024_vs_2048": abs(values[1024] - values[2048]),
        "sharp_absolute_delta_1024_vs_2048": abs(
            sharp_values[1024] - sharp_values[2048]
        ),
        "sharp_case": {
            "training_track_count": 77,
            "sigma_hz": 3_000.0,
            "outlier_probability": 0.05,
            "mode_hz": module.PILOT_ALIAS_HZ / 2048,
            "heldout_offset_difference_hz": 900.0,
        },
        "executed_source_digest": sha256(HERE / "executed-ablation-source.py"),
    }


def main() -> None:
    result = json.loads((HERE / "result.json").read_text())
    convergence = synthetic_convergence(load_executed_module())
    (HERE / "grid-convergence.json").write_text(
        json.dumps(convergence, indent=2, allow_nan=False) + "\n"
    )

    breakdown = []
    for arm in result["arms"]:
        groups = defaultdict(list)
        for row in arm["tracks"]:
            groups[(row["receiver_id"], row["pilot_edge"])].append(
                row["delta_log_score"]
            )
        for (receiver, edge), scores in sorted(groups.items()):
            values = np.asarray(scores)
            breakdown.append(
                {
                    "sigma_hz": arm["sigma_hz"],
                    "outlier_probability": arm["outlier_probability"],
                    "receiver_id": receiver,
                    "pilot_edge": edge,
                    "track_count": len(values),
                    "total_delta_log_score": float(np.sum(values)),
                    "positive_count_gt_1e-6": int(np.sum(values > 1e-6)),
                    "negative_count_lt_minus_1e-6": int(np.sum(values < -1e-6)),
                    "near_zero_count_abs_le_1e-6": int(np.sum(np.abs(values) <= 1e-6)),
                }
            )
    (HERE / "group-breakdown.json").write_text(
        json.dumps({"schema": "circular-offset-group-breakdown/v1", "groups": breakdown}, indent=2)
        + "\n"
    )

    labels = [
        f"{a['sigma_hz']/1000:g}k / {a['outlier_probability']:.2f}"
        for a in result["arms"]
    ]
    totals = [a["total_delta_log_score"] for a in result["arms"]]
    fig, ax = plt.subplots(figsize=(9, 4.8), constrained_layout=True)
    bars = ax.bar(labels, totals, color="#4878a8")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_ylabel("summed heldout Δ composite log score")
    ax.set_xlabel("circular σ / outlier probability")
    ax.set_title("Whole-track circular-intercept prediction at frozen blocked position")
    for bar, value in zip(bars, totals, strict=True):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 5, f"{value:.1f}", ha="center")
    ax.text(
        0.01,
        0.02,
        "Conditional diagnostic; totals are not confidence or independent validation.",
        transform=ax.transAxes,
        fontsize=9,
    )
    fig.savefig(HERE / "circular-offset-prediction.png", dpi=180)


if __name__ == "__main__":
    main()
