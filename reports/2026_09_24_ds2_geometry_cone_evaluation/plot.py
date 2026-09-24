#!/usr/bin/env python3
"""Render compact coverage and post-seal-error summaries."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def main() -> None:
    inference = json.loads((HERE / "inference.json").read_text())
    evaluation = json.loads((HERE / "postseal-evaluation.json").read_text())
    figure, (coverage, error) = plt.subplots(1, 2, figsize=(14, 5), layout="constrained")
    for result in inference["results"]:
        scenarios = result["staged_full_fov"]["scenarios"]
        coverage.plot(
            [item["full_fov_deg"] for item in scenarios],
            [item["supported_occupied_second_fraction"] for item in scenarios],
            marker="o",
            label=result["label"].replace("scan-fw-", "")[:18],
        )
    coverage.set(
        title="LT3D constrained-cone support at each conditional Doppler fit",
        xlabel="Full field of view (degrees)",
        ylabel="Supported occupied-second fraction",
        ylim=(-0.03, 1.03),
    )
    coverage.legend(fontsize=8)
    selected = [
        row
        for row in evaluation["results"]
        if row["method"] in {"conditional Doppler baseline", "local fitted cone, 50° full FOV"}
    ]
    labels = sorted({row["label"] for row in selected})
    methods = (("conditional Doppler baseline", "o"), ("local fitted cone, 50° full FOV", "s"))
    for method, marker in methods:
        values = {
            row["label"]: row["horizontal_error_km"] for row in selected if row["method"] == method
        }
        error.plot(
            labels,
            [values.get(label, float("nan")) for label in labels],
            marker=marker,
            label=method,
        )
    error.set(
        title="Post-seal external error only\n(saved-candidate conditional diagnostic)",
        ylabel="Horizontal error (km)",
    )
    error.tick_params(axis="x", rotation=30, labelsize=8)
    error.legend(fontsize=8)
    figure.savefig(HERE / "geometry-cone-summary.png", dpi=160)


if __name__ == "__main__":
    main()
