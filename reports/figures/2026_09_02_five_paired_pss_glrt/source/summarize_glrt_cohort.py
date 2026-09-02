#!/usr/bin/env python3
"""Summarize selection strength and GLRT CFO alias behavior for the fixed cohort."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

GLRT_ALIAS_SPACING_HZ = 2_500_000.0 / 11.0
COLORS = ("#2563eb", "#ea580c", "#16a34a", "#9333ea", "#0891b2")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _canonical_cfo(observation: dict[str, Any]) -> float:
    return float(observation["raw_cfo_hz"]) - int(observation["alias_index"]) * (
        GLRT_ALIAS_SPACING_HZ
    )


def _track_summary(track: dict[str, Any]) -> dict[str, Any]:
    observations = track["observations"]
    times = np.asarray([float(item["global_time_s"]) for item in observations])
    raw = np.asarray([float(item["raw_cfo_hz"]) for item in observations])
    aliases = np.asarray([int(item["alias_index"]) for item in observations], dtype=int)
    canonical = raw - aliases * GLRT_ALIAS_SPACING_HZ
    reference_time = float(track["global_reference_time_s"])
    published = float(track["cfo_at_reference_hz"]) + float(track["slope_hz_s"]) * (
        times - reference_time
    )
    residual = canonical - published
    alias_counts = Counter(int(value) for value in aliases)
    return {
        "track_label": track["track_label"],
        "track_digest": track["track_digest"],
        "observation_count": len(observations),
        "start_time_s": float(times.min()),
        "stop_time_s": float(times.max()),
        "span_s": float(times.max() - times.min()),
        "published_slope_hz_s": float(track["slope_hz_s"]),
        "alias_spacing_hz": GLRT_ALIAS_SPACING_HZ,
        "alias_index_counts": {str(key): alias_counts[key] for key in sorted(alias_counts)},
        "alias_switch_count": int(np.count_nonzero(np.diff(aliases))),
        "raw_cfo_min_hz": float(raw.min()),
        "raw_cfo_max_hz": float(raw.max()),
        "canonical_cfo_min_hz": float(canonical.min()),
        "canonical_cfo_max_hz": float(canonical.max()),
        "published_line_residual_rms_hz": float(np.sqrt(np.mean(residual**2))),
        "published_line_residual_maximum_hz": float(np.max(np.abs(residual))),
    }


def _path_summary(path: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    document = json.loads(Path(path["path"]).read_text(encoding="utf-8"))
    tracks = [
        track
        for segment in document["segments"]
        for track in segment["hough"]["tracks"]
    ]
    summaries = [_track_summary(track) for track in tracks]
    summary = {
        "receiver_id": int(path["receiver_id"]),
        "physical_receiver_id": path["physical_receiver_id"],
        "product_digest": path["digest"],
        "source_first_sample_timing": document["source"]["timing"],
        "source_center_frequency_hz": int(document["source"]["tuned_center_frequency_hz"]),
        "passing_fraction": float(path["passing_fraction"]),
        "passing_window_count": int(path["passing_window_count"]),
        "valid_window_count": int(path["valid_window_count"]),
        "median_passing_margin": path["median_passing_margin"],
        "hough_track_count": len(tracks),
        "hough_observation_count": sum(len(track["observations"]) for track in tracks),
        "tracks": summaries,
    }
    return summary, document


def _plot_selection(selected: list[dict[str, Any]], output: Path) -> None:
    labels = [str(item["session_id"])[-12:] for item in selected]
    x = np.arange(len(selected))
    width = 0.34
    figure, axes = plt.subplots(2, 1, figsize=(13, 9), constrained_layout=True)
    for receiver, offset, color in ((0, -width / 2, "#2563eb"), (1, width / 2, "#ea580c")):
        values = [
            100.0
            * float(
                next(
                    row for row in item["glrt_2p5m"] if row["receiver_id"] == receiver
                )["passing_fraction"]
            )
            for item in selected
        ]
        axes[0].bar(x + offset, values, width, color=color, label=f"2.5 MS/s RX{receiver}")
    axes[0].set_ylabel("Passing GLRT windows (%)")
    axes[0].set_ylim(0, 105)
    axes[0].set_xticks(x, labels)
    axes[0].legend(loc="best")
    axes[0].grid(axis="y", alpha=0.2)
    density = [100.0 * float(item["stream_25m"]["observed_density"]) for item in selected]
    gaps = [int(item["stream_25m"]["continuity_gap_count"]) for item in selected]
    axes[1].bar(x, density, color="#16a34a", alpha=0.85, label="native-25 observed density")
    axes[1].set_ylabel("Observed native-25 density (%)")
    axes[1].set_ylim(0, 105)
    axes[1].set_xticks(x, labels)
    axes[1].grid(axis="y", alpha=0.2)
    twin = axes[1].twinx()
    twin.plot(x, gaps, marker="o", color="#7c2d12", label="counter-proven gaps")
    twin.set_ylabel("Gap events")
    handles, legend_labels = axes[1].get_legend_handles_labels()
    twin_handles, twin_labels = twin.get_legend_handles_labels()
    axes[1].legend(handles + twin_handles, legend_labels + twin_labels, loc="best")
    figure.suptitle("Fixed five-capture cohort: GLRT selection strength and native-25 continuity")
    figure.savefig(output, dpi=180)
    plt.close(figure)


def _plot_aliases(
    selected: list[dict[str, Any]],
    documents: dict[tuple[str, int], dict[str, Any]],
    output: Path,
) -> None:
    figure, axes = plt.subplots(
        len(selected),
        2,
        figsize=(15, 3.1 * len(selected)),
        constrained_layout=True,
    )
    for row_index, (capture, color) in enumerate(zip(selected, COLORS, strict=True)):
        receiver = int(capture["rank_fields"]["best_receiver_id"])
        document = documents[(str(capture["session_id"]), receiver)]
        tracks = [
            track
            for segment in document["segments"]
            for track in segment["hough"]["tracks"]
        ]
        left, right = axes[row_index]
        for track in tracks:
            observations = track["observations"]
            times = np.asarray([float(item["global_time_s"]) for item in observations])
            raw = np.asarray([float(item["raw_cfo_hz"]) for item in observations])
            aliases = np.asarray([int(item["alias_index"]) for item in observations])
            canonical = raw - aliases * GLRT_ALIAS_SPACING_HZ
            left.scatter(times, raw / 1e3, c=aliases, cmap="viridis", s=4, alpha=0.55)
            right.scatter(times, canonical / 1e3, color=color, s=4, alpha=0.55)
        label = str(capture["session_id"])[-12:]
        left.set_ylabel(f"{label}\nraw CFO (kHz)")
        right.set_ylabel("canonical CFO (kHz)")
        left.grid(alpha=0.18)
        right.grid(alpha=0.18)
        if row_index == 0:
            left.set_title("Raw GLRT CFO; color is integer alias index")
            right.set_title("After subtracting alias_index × 2.5 MHz / 11")
        if row_index == len(selected) - 1:
            left.set_xlabel("Time from 2.5 MS/s stream start (s)")
            right.set_xlabel("Time from 2.5 MS/s stream start (s)")
    figure.suptitle(
        "GLRT aliases are discrete representation branches; canonicalization restores smooth tracks"
    )
    figure.savefig(output, dpi=180)
    plt.close(figure)


def main() -> None:
    arguments = _arguments()
    cohort = json.loads(arguments.cohort.read_text(encoding="utf-8"))
    selected = cohort["selected"]
    summaries: list[dict[str, Any]] = []
    documents: dict[tuple[str, int], dict[str, Any]] = {}
    for capture in selected:
        paths = []
        for raw_path in capture["glrt_2p5m"]:
            path_summary, document = _path_summary(raw_path)
            paths.append(path_summary)
            documents[(str(capture["session_id"]), int(raw_path["receiver_id"]))] = document
        summaries.append(
            {
                "session_id": capture["session_id"],
                "selected_best_receiver_id": capture["rank_fields"]["best_receiver_id"],
                "paths": paths,
            }
        )
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    selection_png = arguments.output_dir / "cohort-selection.png"
    alias_png = arguments.output_dir / "glrt-cfo-alias-canonicalization.png"
    _plot_selection(selected, selection_png)
    _plot_aliases(selected, documents, alias_png)
    evidence = {
        "schema_version": 1,
        "analysis_kind": "five-capture-glrt-strength-and-alias-audit",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "cohort_path": str(arguments.cohort),
        "cohort_sha256": _sha256(arguments.cohort),
        "glrt_alias_spacing_hz": GLRT_ALIAS_SPACING_HZ,
        "canonicalization": "canonical_cfo_hz = raw_cfo_hz - alias_index * (2500000/11)",
        "captures": summaries,
        "artifacts": {
            "cohort_selection_png": {
                "path": selection_png.name,
                "sha256": _sha256(selection_png),
            },
            "glrt_alias_png": {"path": alias_png.name, "sha256": _sha256(alias_png)},
        },
        "limitations": [
            "GLRT CFO sign is a receiver-IQ convention until independently calibrated.",
            (
                "Canonicalization removes a known estimator representation alias; "
                "it does not identify a satellite."
            ),
            (
                "Hough fragments may represent more than one transmitter or "
                "reacquisition of one transmitter."
            ),
        ],
    }
    output = arguments.output_dir / "glrt-cohort-summary.json"
    output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    if not all(
        math.isfinite(float(item["rank_fields"]["best_passing_fraction"]))
        for item in selected
    ):
        raise ValueError("cohort selection contains non-finite GLRT strength")
    print(
        json.dumps(
            {
                "output": str(output),
                "sha256": _sha256(output),
                "captures": len(summaries),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
