#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sealed-run-root", type=Path, required=True)
    parser.add_argument("--scope-digest", required=True)
    parser.add_argument("--exact-v2", type=Path, required=True)
    parser.add_argument("--wrong-edge-v2", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser.parse_args()


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def model_values(model: dict[str, Any], alias: int = 0, spacing: float = 0.0):
    time = np.linspace(float(model["start_s"]), float(model["end_s"]), 300)
    cfo = np.polyval(
        np.asarray(model["coefficients_hz"], dtype=float),
        time - float(model["reference_time_s"]),
    )
    return time, cfo + alias * spacing


def raw_points(pilot: dict[str, Any]):
    time = []
    cfo = []
    for detection in pilot["detections"]:
        for candidate in detection["candidates"]:
            score = next(row for row in candidate["scores"] if row["method"] == "glrt64")
            time.append(float(detection["time_s"]))
            cfo.append(float(score["tracking_cfo_hz"]))
    return np.asarray(time), np.asarray(cfo)


def branch_model(branch: dict[str, Any]) -> dict[str, Any]:
    return next(row for row in branch["models"] if row["model_id"] == branch["selected_model_id"])


def centered(values: np.ndarray, spacing: float) -> np.ndarray:
    return (values + spacing / 2.0) % spacing - spacing / 2.0


def directed_v3_automatic(row: dict[str, Any], gate: dict[str, Any]) -> bool:
    blocks = int(row["evaluated_block_count"])
    harmful_fraction = float(row["harmful_block_count"]) / blocks if blocks else 1.0
    corrected = row["median_block_corrected_margin"]
    return bool(
        row["geometry_display_eligible"]
        and row["evaluated_probe_count"] >= gate["minimum_probe_count"]
        and row["block_coverage_ratio"] >= gate["minimum_block_coverage_ratio"]
        and corrected is not None
        and corrected >= gate["minimum_median_corrected_margin"]
        and harmful_fraction <= gate["maximum_harmful_block_fraction"]
        and row["maximum_consecutive_harmful_blocks"] <= gate["maximum_consecutive_harmful_blocks"]
    )


def line_matches(
    track: dict[str, Any], branches: list[dict[str, Any]], spacing: float
) -> list[dict[str, Any]]:
    result = []
    for branch in branches:
        model = branch_model(branch)
        start = max(float(track["start_s"]), float(model["start_s"]))
        end = min(float(track["end_s"]), float(model["end_s"]))
        if end - start < 0.25:
            continue
        time = np.linspace(start, end, 256)
        hough = float(track["slope_hz_per_s"]) * time + float(track["intercept_mod_alias_hz"])
        standard = np.polyval(
            np.asarray(model["coefficients_hz"], dtype=float),
            time - float(model["reference_time_s"]),
        )
        residual = centered(hough - standard, spacing)
        standard_slope = np.polyval(
            np.polyder(np.asarray(model["coefficients_hz"], dtype=float)),
            time - float(model["reference_time_s"]),
        )
        result.append(
            {
                "branch_id": branch["branch_id"],
                "overlap_s": end - start,
                "modulo_residual_rms_hz": float(np.sqrt(np.mean(residual**2))),
                "modulo_residual_max_hz": float(np.max(np.abs(residual))),
                "median_slope_difference_hz_per_s": float(
                    np.median(np.abs(float(track["slope_hz_per_s"]) - standard_slope))
                ),
            }
        )
    return sorted(result, key=lambda row: (row["modulo_residual_rms_hz"], row["branch_id"]))


def plot_background(axis: Any, time: np.ndarray, cfo: np.ndarray) -> None:
    axis.scatter(time, cfo / 1_000.0, s=2, alpha=0.12, color="#87909a", rasterized=True)
    axis.set_xlim(0, 60)
    axis.set_ylim(-520, 520)
    axis.set_ylabel("Baseband CFO (kHz)")
    axis.grid(alpha=0.18)


def plot_hough(axis: Any, tracks: list[dict[str, Any]], spacing: float) -> None:
    colors = plt.get_cmap("tab10")
    for index, track in enumerate(tracks):
        time = np.asarray([track["start_s"], track["end_s"]], dtype=float)
        base = float(track["slope_hz_per_s"]) * time + float(track["intercept_mod_alias_hz"])
        first = int(np.floor((-520_000 - float(np.max(base))) / spacing)) - 1
        last = int(np.ceil((520_000 - float(np.min(base))) / spacing)) + 1
        labelled = False
        for alias in range(first, last + 1):
            values = base + alias * spacing
            if np.max(values) < -520_000 or np.min(values) > 520_000:
                continue
            axis.plot(
                time,
                values / 1_000.0,
                color=colors(index % 10),
                linewidth=2.0,
                alpha=0.9,
                label=(f"H{index + 1} {track['track_id'][7:15]}" if not labelled else None),
            )
            labelled = True


def plot_branch_lift(axis: Any, branch: dict[str, Any], alias: int, spacing: float, **style: Any):
    time, values = model_values(branch_model(branch), alias, spacing)
    axis.plot(time, values / 1_000.0, **style)


def main() -> int:
    args = arguments()
    args.output_root.mkdir(parents=True, exist_ok=True)
    standard = args.sealed_run_root / "scientific" / "path-standard" / args.scope_digest
    alternate = args.sealed_run_root / "scientific" / "path-alternate-tracks" / args.scope_digest
    pilot = read(standard / "standard.pilot-scan.v3.json")
    raw = read(standard / "standard.trajectory-bank.v2.json")
    alias_map = read(standard / "standard.cfo-alias-map.v2.json")
    bank = read(standard / "standard.dealiased-trajectory-bank.v2.json")
    v1 = read(standard / "standard.cfo-lift-replay.v1.json")
    final = read(standard / "standard.final-trajectory-bank.v1.json")
    hough = read(alternate / "standard.alternate-cfo-track-bank.v1.json")
    exact = read(args.exact_v2)
    wrong = read(args.wrong_edge_v2)
    spacing = float(hough["configuration"]["alias_spacing_hz"])
    branches = {row["branch_id"]: row for row in bank["branches"]}
    v1_by_key = {(row["branch_id"], row["alias_index"]): row for row in v1["rows"]}
    exact_by_key = {(row["branch_id"], row["alias_index"]): row for row in exact["rows"]}
    wrong_by_key = {(row["branch_id"], row["alias_index"]): row for row in wrong["rows"]}
    time, cfo = raw_points(pilot)

    figure, axes = plt.subplots(5, 1, figsize=(17, 24), sharex=True, sharey=True)
    for axis in axes:
        plot_background(axis, time, cfo)
    plot_hough(axes[0], hough["tracks"], spacing)
    axes[0].set_title(
        f"A · alternate Hough inventory: {len(hough['tracks'])} research-only lines",
        loc="left",
    )
    axes[0].legend(fontsize=7, ncol=4, loc="upper right")
    for trajectory in raw["trajectories"]:
        model_time, values = model_values(trajectory)
        axes[1].plot(model_time, values / 1_000.0, color="#7c3aed", linewidth=1.2)
    for branch in bank["branches"]:
        for alias in branch["observed_alias_indices"]:
            plot_branch_lift(axes[1], branch, int(alias), spacing, color="#0369a1", linewidth=1.8)
    axes[1].set_title(
        f"B · Standard funnel: {len(raw['trajectories'])} raw fits → "
        f"{len(alias_map['components'])} alias components → "
        f"{len(bank['branches'])} fitted branches",
        loc="left",
    )
    for row in v1["rows"]:
        supported = row["status"] == "supported"
        plot_branch_lift(
            axes[2],
            branches[row["branch_id"]],
            int(row["alias_index"]),
            spacing,
            color="#15803d" if supported else "#dc2626",
            linewidth=2.6 if supported else 1.0,
            linestyle="-" if supported else "--",
            alpha=0.95 if supported else 0.55,
        )
    axes[2].set_title(
        f"C · persisted V1 replay: {sum(r['status'] == 'supported' for r in v1['rows'])} "
        f"supported / {len(v1['rows'])} observed lifts (green supported, red rejected)",
        loc="left",
    )
    tier_color = {
        "replay_improved": "#15803d",
        "replay_stable": "#0e7490",
        "geometry_only": "#d97706",
        "replay_rejected": "#dc2626",
        "insufficient": "#6b7280",
    }
    for row in exact["rows"]:
        automatic = row["automatic_correction_eligible"]
        plot_branch_lift(
            axes[3],
            branches[row["branch_id"]],
            int(row["alias_index"]),
            spacing,
            color=tier_color[row["tier"]],
            linewidth=2.6 if automatic else 1.2,
            linestyle="-" if automatic else "--",
            alpha=0.95 if automatic else 0.75,
        )
    tiers = Counter(row["tier"] for row in exact["rows"])
    axes[3].set_title(
        "D · exact lower-edge V2 replay: "
        + ", ".join(f"{key}={value}" for key, value in sorted(tiers.items()))
        + " (solid automatic; dashed display-only/rejected)",
        loc="left",
    )
    for row in exact["rows"]:
        automatic = directed_v3_automatic(row, exact["gate_config"])
        plot_branch_lift(
            axes[4],
            branches[row["branch_id"]],
            int(row["alias_index"]),
            spacing,
            color="#15803d" if automatic else "#d97706",
            linewidth=2.8 if automatic else 1.1,
            linestyle="-" if automatic else "--",
            alpha=0.95 if automatic else 0.65,
        )
    v3_count = sum(directed_v3_automatic(row, exact["gate_config"]) for row in exact["rows"])
    axes[4].set_title(
        f"E · directed V3 projection: {v3_count} automatic lifts; equivalence and minimum-block "
        "gates removed (solid automatic, dashed display-only)",
        loc="left",
    )
    axes[4].set_xlabel("Elapsed recording time (s)")
    figure.suptitle(
        "e2ac389247f3 · radio_pluto_19f2 RX1 · fixed-axis track-retention funnel",
        fontweight="bold",
        fontsize=16,
        y=0.995,
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.982))
    figure.savefig(
        args.output_root / "19f2-rx1-track-retention-funnel.png",
        dpi=170,
        facecolor="white",
        metadata={"Software": "leo-tracker e2ac389 investigation"},
    )
    plt.close(figure)

    best_rows = []
    for branch_id, branch in branches.items():
        choices = [row for key, row in exact_by_key.items() if key[0] == branch_id]
        best = max(
            choices,
            key=lambda row: (
                row["median_block_corrected_margin"]
                if row["median_block_corrected_margin"] is not None
                else -1e30,
                -abs(row["alias_index"]),
            ),
        )
        prior = v1_by_key[(branch_id, best["alias_index"])]
        best_rows.append((branch, best, prior))
    evidence_figure, evidence_axis = plt.subplots(figsize=(13, 8), constrained_layout=True)
    annotation_offsets = {
        "024bfda8": (8, 10),
        "3cfa2482": (8, 8),
        "799b133a": (10, 70),
        "7ed5697c": (-100, 42),
        "97114c6a": (8, 8),
        "9962ad59": (10, 38),
        "9cdd04d8": (8, 8),
        "caa1255b": (8, -2),
    }
    for branch, row, prior in best_rows:
        x = float(row["median_block_margin_delta"] or 0.0)
        y = float(row["median_block_corrected_margin"] or 0.0)
        evidence_axis.scatter(
            x,
            y,
            s=100,
            color=tier_color[row["tier"]],
            edgecolor="black" if directed_v3_automatic(row, exact["gate_config"]) else "#6b7280",
            linewidth=2.0 if directed_v3_automatic(row, exact["gate_config"]) else 0.5,
        )
        evidence_axis.annotate(
            f"{branch['branch_id'][7:15]}\nV1 {prior['status']} · "
            f"V3 {'auto' if directed_v3_automatic(row, exact['gate_config']) else 'display'}",
            (x, y),
            xytext=annotation_offsets[branch["branch_id"][7:15]],
            textcoords="offset points",
            fontsize=8,
            arrowprops={"arrowstyle": "-", "color": "#6b7280", "linewidth": 0.5},
        )
    tolerance = float(exact["gate_config"]["equivalence_control_p95_absolute_delta"]) * float(
        exact["gate_config"]["equivalence_safety_multiplier"]
    )
    absolute_gate = float(exact["gate_config"]["minimum_median_corrected_margin"])
    evidence_axis.axvspan(-tolerance, tolerance, color="#0e7490", alpha=0.08)
    evidence_axis.axvline(-tolerance, color="#0e7490", linestyle=":")
    evidence_axis.axvline(tolerance, color="#0e7490", linestyle=":")
    evidence_axis.axhline(absolute_gate, color="black", linestyle="--")
    evidence_axis.set_xlim(-0.004, 0.0015)
    evidence_axis.set_ylim(-0.02, 0.40)
    evidence_axis.set_xlabel("Median 1-second block Δ vs independent baseline")
    evidence_axis.set_ylabel("Median corrected exact − control margin")
    evidence_axis.set_title(
        "Best observed alias per Standard branch · thick outline = directed V3 automatic",
        loc="left",
        fontweight="bold",
    )
    evidence_axis.grid(alpha=0.2)
    evidence_figure.savefig(
        args.output_root / "19f2-rx1-replay-gate-evidence.png",
        dpi=180,
        facecolor="white",
        metadata={"Software": "leo-tracker e2ac389 investigation"},
    )
    plt.close(evidence_figure)

    association = bank["association"]
    support = [len(row["observation_ids"]) for row in association["branches"]]
    mappings = []
    for index, track in enumerate(hough["tracks"], 1):
        matches = line_matches(track, list(branches.values()), spacing)
        accepted = [
            row
            for row in matches
            if row["modulo_residual_rms_hz"] <= hough["configuration"]["residual_gate_hz"]
        ]
        for match in accepted:
            branch_id = match["branch_id"]
            exact_choices = [row for key, row in exact_by_key.items() if key[0] == branch_id]
            chosen = max(
                exact_choices,
                key=lambda row: (
                    row["median_block_corrected_margin"]
                    if row["median_block_corrected_margin"] is not None
                    else -1e30,
                    -abs(row["alias_index"]),
                ),
            )
            prior = v1_by_key[(branch_id, chosen["alias_index"])]
            wrong_row = wrong_by_key[(branch_id, chosen["alias_index"])]
            match.update(
                {
                    "selected_alias_index": chosen["alias_index"],
                    "v1_status": prior["status"],
                    "v1_improved_probe_fraction": prior["improved_probe_count"]
                    / prior["evaluated_probe_count"],
                    "v1_median_delta": prior["median_margin_delta"],
                    "v1_corrected_margin": prior["median_control_separation"],
                    "v2_tier": chosen["tier"],
                    "v2_automatic": chosen["automatic_correction_eligible"],
                    "v2_median_block_delta": chosen["median_block_margin_delta"],
                    "v2_corrected_margin": chosen["median_block_corrected_margin"],
                    "directed_v3_automatic": directed_v3_automatic(chosen, exact["gate_config"]),
                    "wrong_edge_tier": wrong_row["tier"],
                    "wrong_edge_corrected_margin": wrong_row["median_block_corrected_margin"],
                }
            )
        mappings.append(
            {
                "hough_label": f"H{index}",
                "track_id": track["track_id"],
                "track": track,
                "matching_standard_branches": accepted,
                "best_overlapping_branch_even_if_outside_gate": matches[0] if matches else None,
            }
        )
    facts = {
        "session_id": "cap-20260821T024252-e2ac389247f3",
        "run_id": "capture-651db511cf2149548feee818f0ebf945",
        "pipeline_release_id": "1aa1e795e8af9730a35e80ee4045732e35c9e3bf",
        "path": {"radio_id": "radio_pluto_19f2", "stream_id": "stream-1", "receiver_id": 1},
        "authoritative_edge": "lower",
        "pilot": {
            "probe_count": len(pilot["detections"]),
            "candidate_count": len(time),
            "candidate_cfo_min_hz": float(np.min(cfo)),
            "candidate_cfo_max_hz": float(np.max(cfo)),
        },
        "funnel": {
            "raw_trajectory_count": len(raw["trajectories"]),
            "raw_family_count": len(raw["families"]),
            "alias_representative_count": alias_map["returned_representative_count"],
            "alias_component_count": alias_map["component_count"],
            "canonical_observation_count": bank["returned_observation_count"],
            "association_source_branch_count": association["source_branch_count"],
            "association_returned_branch_count": association["returned_branch_count"],
            "association_truncated_branch_count": association["truncated_branch_count"],
            "association_returned_support_histogram": dict(Counter(support)),
            "association_returned_non_singleton_count": sum(value > 1 for value in support),
            "association_source_path_edge_count": (
                association["source_observation_count"] - association["source_branch_count"]
            ),
            "association_published_path_edge_count": sum(max(0, value - 1) for value in support),
            "association_omitted_paths_are_all_singletons": (
                sum(max(0, value - 1) for value in support)
                == association["source_observation_count"] - association["source_branch_count"]
            ),
            "fitted_branch_count": len(bank["branches"]),
            "v1_lift_count": len(v1["rows"]),
            "v1_supported_lift_count": sum(row["status"] == "supported" for row in v1["rows"]),
            "v1_final_count": len(final["trajectories"]),
            "v2_tiers": dict(Counter(row["tier"] for row in exact["rows"])),
            "v2_automatic_count": sum(
                row["automatic_correction_eligible"] for row in exact["rows"]
            ),
            "directed_v3_automatic_count": sum(
                directed_v3_automatic(row, exact["gate_config"]) for row in exact["rows"]
            ),
            "directed_v3_automatic_lifts": [
                f"{row['branch_id']}:{row['alias_index']}"
                for row in exact["rows"]
                if directed_v3_automatic(row, exact["gate_config"])
            ],
            "wrong_edge_v2_tiers": dict(Counter(row["tier"] for row in wrong["rows"])),
            "wrong_edge_v2_automatic_count": sum(
                row["automatic_correction_eligible"] for row in wrong["rows"]
            ),
            "wrong_edge_directed_v3_automatic_count": sum(
                directed_v3_automatic(row, wrong["gate_config"]) for row in wrong["rows"]
            ),
        },
        "association_edge_statuses": dict(
            Counter(row["status"] for row in association["edge_decisions"])
        ),
        "hough": {
            "automatic_use_allowed": hough["automatic_use_allowed"],
            "track_count": len(hough["tracks"]),
            "mappings": mappings,
        },
        "standard_branches": [
            {
                "branch_id": branch["branch_id"],
                "observation_count": len(branch["observation_ids"]),
                "start_s": branch["start_s"],
                "end_s": branch["end_s"],
                "selected_model": branch_model(branch),
                "v1_rows": [row for key, row in v1_by_key.items() if key[0] == branch["branch_id"]],
                "v2_rows": [
                    row for key, row in exact_by_key.items() if key[0] == branch["branch_id"]
                ],
                "wrong_edge_v2_rows": [
                    row for key, row in wrong_by_key.items() if key[0] == branch["branch_id"]
                ],
            }
            for branch in bank["branches"]
        ],
    }
    (args.output_root / "facts.json").write_text(
        json.dumps(facts, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output_root": str(args.output_root), "tracks": len(mappings)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
