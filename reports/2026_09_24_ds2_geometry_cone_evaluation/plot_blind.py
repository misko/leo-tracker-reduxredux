#!/usr/bin/env python3
"""Render the sealed blind/re-associated cone diagnostic."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def main() -> None:
    inference = json.loads((HERE / "blind-inference.json").read_text())
    evaluation = json.loads((HERE / "blind-postseal-evaluation.json").read_text())
    figure, (coverage, held, error) = plt.subplots(1, 3, figsize=(18, 5), layout="constrained")
    for result in inference["results"]:
        label = result["label"].replace("scan-fw-", "")[:14]
        scenarios = result["staged_full_fov"]["scenarios"]
        width = [item["full_fov_deg"] for item in scenarios]
        coverage.plot(
            width,
            [item["supported_occupied_second_fraction"] for item in scenarios],
            marker="o",
            label=label,
        )
        held.plot(
            width,
            [item["held_rms_hz_supported"] for item in scenarios],
            marker="o",
            label=label,
        )
    coverage.set(
        title="Blind re-associated cone support",
        xlabel="Full field of view (degrees)",
        ylabel="Supported occupied-second fraction",
        ylim=(-0.03, 1.03),
    )
    coverage.legend(fontsize=8)
    held.set(
        title="Held-sample RMS on supported tracks",
        xlabel="Full field of view (degrees)",
        ylabel="RMS (Hz)",
    )
    selected = [
        row
        for row in evaluation["results"]
        if row["method"]
        in {
            "blind re-associated Doppler baseline",
            "blind re-associated local fitted cone, 50° full FOV",
        }
    ]
    labels = sorted({row["label"] for row in selected})
    for method, marker in (
        ("blind re-associated Doppler baseline", "o"),
        ("blind re-associated local fitted cone, 50° full FOV", "s"),
    ):
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
        title="Post-seal external error only\n(full-catalogue blind arm)",
        ylabel="Horizontal error (km)",
    )
    error.tick_params(axis="x", rotation=30, labelsize=8)
    error.legend(fontsize=8)
    figure.savefig(HERE / "blind-geometry-cone-summary.png", dpi=160)


if __name__ == "__main__":
    main()
