#!/usr/bin/env python3
"""Render the descriptive GLRT-alternative inventory without inference."""

from __future__ import annotations

import gzip
import hashlib
import json
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

PILOT_ALIAS_HZ = 1.0 / 4.4e-6


def wrap_alias_hz(value: float) -> float:
    return (value + PILOT_ALIAS_HZ / 2) % PILOT_ALIAS_HZ - PILOT_ALIAS_HZ / 2


def unique_alternative_offsets(group: dict) -> list[float]:
    unique: list[tuple[float, float]] = []
    for candidate in group["candidates"]:
        if not candidate["passed_fractional_margin_gate"]:
            continue
        frequency = candidate["fractional_tracking_cfo_hz"]
        epoch = candidate["integer_epoch_sample"] + candidate["fractional_epoch_offset_samples"]
        if any(
            abs(frequency - old_frequency) < 0.01 and abs(epoch - old_epoch) < 0.01
            for old_frequency, old_epoch in unique
        ):
            continue
        unique.append((frequency, epoch))
    selected = group["selected_raw_candidate_cfo_hz"]
    return [
        abs(wrap_alias_hz(frequency - selected))
        for frequency, _epoch in unique
        if abs(wrap_alias_hz(frequency - selected)) >= 0.01
    ]


def main() -> None:
    directory = Path(__file__).parent
    gzip_path = directory / "position-selected-glrt-alternatives-v3.json.gz"
    receipt = json.loads((directory / "execution-receipt.json").read_text())
    actual_digest = "sha256:" + hashlib.sha256(gzip_path.read_bytes()).hexdigest()
    if actual_digest != receipt["output"]["gzip_digest"]:
        raise ValueError("gzip artifact differs from execution receipt")
    with gzip.open(gzip_path, "rt") as stream:
        document = json.load(stream)
    if (
        document.get("truth_accessed") is not False
        or document.get("inference_performed") is not False
    ):
        raise ValueError("descriptive truth-free export required")

    labels, selected, multiple, duplicates = [], [], [], []
    native_medians, canonical_medians, all_native, all_canonical = [], [], [], []
    for session in document["sessions"]:
        native, canonical = [], []
        for group in session["groups"]:
            offsets = unique_alternative_offsets(group)
            native.extend(offsets)
            canonical.extend(value * group["canonical_rf_scale"] for value in offsets)
        if len(native) != session["alternative_diagnostics"][
            "nonzero_unique_circular_alternative_count"
        ]:
            raise ValueError("alternative accounting differs from v3 export")
        labels.append(session["session_id"].removeprefix("scan-fw-")[:4])
        selected.append(session["selected_source_group_count"])
        multiple.append(
            session["alternative_diagnostics"][
                "source_groups_with_multiple_unique_passing_candidates"
            ]
        )
        duplicates.append(session["alternative_diagnostics"]["duplicate_passing_candidate_count"])
        native_medians.append(statistics.median(native))
        canonical_medians.append(statistics.median(canonical))
        all_native.extend(native)
        all_canonical.extend(canonical)
    if statistics.median(all_native) != document["alternative_diagnostics"][
        "median_nonzero_unique_circular_offset_hz"
    ]:
        raise ValueError("native median differs from v3 export")

    figure, (left, right) = plt.subplots(
        1, 2, figsize=(10.4, 4.6), gridspec_kw={"width_ratios": [1.35, 1]}
    )
    x = np.arange(len(labels))
    width = 0.25
    left.bar(x - width, selected, width, label="selected source groups", color="#9aa5b1")
    left.bar(x, multiple, width, label="groups with retained alternatives", color="#2a9d8f")
    left.bar(x + width, duplicates, width, label="duplicate passing rows", color="#e9a03b")
    left.set_xticks(x, labels)
    left.set_xlabel("Session ID prefix")
    left.set_ylabel("Count")
    left.set_title("Per-session retained structure")
    left.grid(axis="y", alpha=0.2)
    left.legend(frameon=False, fontsize=8, loc="upper right")

    right.scatter(x, canonical_medians, s=52, color="#2a9d8f", zorder=3, label="session median")
    for position, value in zip(x, canonical_medians, strict=True):
        right.annotate(
            f"{value:.1f}",
            (position, value),
            xytext=(0, 7),
            textcoords="offset points",
            ha="center",
            fontsize=8,
        )
    canonical_median = statistics.median(all_canonical)
    right.axhline(
        canonical_median,
        color="#245a87",
        linewidth=1.8,
        label=f"all-session median {canonical_median:.1f} Hz",
    )
    right.axhline(
        250,
        color="#c44e52",
        linewidth=1.5,
        linestyle="--",
        label="current shape scale 250 Hz",
    )
    right.set_xticks(x, labels)
    right.set_xlabel("Session ID prefix")
    right.set_ylabel("Canonical 11.2 GHz CFO offset (Hz)")
    right.set_title("Nonzero unique alternative offsets")
    right.set_ylim(0, max(360, float(np.max(canonical_medians)) + 35))
    right.grid(axis="y", alpha=0.2)
    right.legend(frameon=False, fontsize=8, loc="lower right")

    figure.suptitle(
        "Saved GLRT alternatives in 5,432 source groups used in position fits",
        fontweight="bold",
    )
    figure.text(
        0.5,
        0.015,
        "Descriptive inventory only · no probability, phase, or position inference",
        ha="center",
        fontsize=9,
        color="#4c566a",
    )
    figure.tight_layout(rect=(0, 0.055, 1, 0.93))
    figure.savefig(directory / "glrt-frequency-alternatives.png", dpi=170)
    plt.close(figure)
    print(
        json.dumps(
            {
                "native_median_hz": statistics.median(all_native),
                "canonical_11_2ghz_median_hz": canonical_median,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
