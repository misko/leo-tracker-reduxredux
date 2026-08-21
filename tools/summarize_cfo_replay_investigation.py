#!/usr/bin/env python3
"""Summarize persisted CFO funnel products and render fixed-axis replay overlays."""

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

ALIAS_SPACING_HZ = 2_500_000 / 11
TIER_COLORS = {
    "replay_improved": "#138a36",
    "replay_stable": "#087e8b",
    "geometry_only": "#d97706",
    "replay_rejected": "#c81d25",
    "insufficient": "#7a7a7a",
}


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sealed-run-root", type=Path, required=True)
    parser.add_argument("--exact-v2-root", type=Path, required=True)
    parser.add_argument("--wrong-edge-v2-root", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--scope-digest")
    parser.add_argument("--exact-edge", choices=("lower", "upper"), required=True)
    parser.add_argument("--highlight-branch")
    return parser.parse_args()


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _model_values(model: dict[str, Any], alias_index: int = 0) -> tuple[np.ndarray, np.ndarray]:
    times = np.linspace(float(model["start_s"]), float(model["end_s"]), 240)
    values = np.polyval(
        np.asarray(model["coefficients_hz"], dtype=float),
        times - float(model["reference_time_s"]),
    )
    return times, values + alias_index * ALIAS_SPACING_HZ


def _raw_points(pilot: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    times: list[float] = []
    frequencies: list[float] = []
    for detection in pilot["detections"]:
        for candidate in detection["candidates"]:
            score = next(item for item in candidate["scores"] if item["method"] == "glrt64")
            times.append(float(detection["time_s"]))
            frequencies.append(float(score["tracking_cfo_hz"]))
    return np.asarray(times), np.asarray(frequencies)


def _background(axis: Any, times: np.ndarray, frequencies: np.ndarray) -> None:
    axis.scatter(
        times,
        frequencies / 1_000,
        s=2,
        color="#9ca3af",
        alpha=0.15,
        rasterized=True,
    )
    axis.set_xlim(0, 60)
    axis.set_ylim(-420, 420)
    axis.grid(alpha=0.18)


def _render_path(
    output: Path,
    label: str,
    pilot: dict[str, Any],
    raw_bank: dict[str, Any],
    bank: dict[str, Any],
    final: dict[str, Any],
    replay_v2: dict[str, Any],
    final_v2: dict[str, Any],
    *,
    exact_edge: str,
) -> None:
    times, frequencies = _raw_points(pilot)
    figure, axes = plt.subplots(4, 1, figsize=(16, 18), sharex=True, sharey=True)
    for axis in axes:
        _background(axis, times, frequencies)
        axis.set_ylabel("Baseband CFO (kHz)")

    for trajectory in raw_bank["trajectories"]:
        curve_times, values = _model_values(trajectory)
        axes[0].plot(curve_times, values / 1_000, linewidth=1.5)
    axes[0].set_title(
        f"A · raw independent-search candidates + {len(raw_bank['trajectories'])} raw fits",
        loc="left",
    )

    for branch in bank["branches"]:
        model = min(branch["models"], key=lambda item: (item["bic"], item["polynomial_degree"]))
        for alias_index in branch["observed_alias_indices"]:
            curve_times, values = _model_values(model, int(alias_index))
            axes[1].plot(curve_times, values / 1_000, linewidth=1.3)
    axes[1].set_title(
        f"B · de-aliased observed lifts · {len(bank['branches'])} fitted branches",
        loc="left",
    )

    for trajectory in final["trajectories"]:
        model = {
            **trajectory,
            "coefficients_hz": trajectory["absolute_coefficients_hz"],
        }
        curve_times, values = _model_values(model)
        axes[2].plot(curve_times, values / 1_000, color="#138a36", linewidth=2.2)
    axes[2].set_title(
        f"C · persisted V1 final · {len(final['trajectories'])} supported lifts",
        loc="left",
    )

    del bank, replay_v2
    for trajectory in final_v2["trajectories"]:
        model = {
            **trajectory,
            "coefficients_hz": trajectory["absolute_coefficients_hz"],
        }
        curve_times, values = _model_values(model)
        axes[3].plot(
            curve_times,
            values / 1_000,
            color=TIER_COLORS[trajectory["replay_tier"]],
            linewidth=2.3 if trajectory["automatic_correction_eligible"] else 1.8,
            linestyle="-" if trajectory["automatic_correction_eligible"] else "--",
            label=trajectory["replay_tier"],
        )
    handles, labels = axes[3].get_legend_handles_labels()
    if handles:
        unique = dict(zip(labels, handles, strict=True))
        axes[3].legend(unique.values(), unique.keys(), fontsize=8, ncol=3)
    axes[3].set_title(
        f"D · exact {exact_edge}-edge V2 final candidates · solid automatic, dashed display-only",
        loc="left",
    )
    axes[3].set_xlabel("Elapsed time (s)")
    figure.suptitle(label, fontweight="bold")
    figure.tight_layout()
    figure.savefig(
        output,
        dpi=170,
        facecolor="white",
        metadata={"Software": "leo-tracker replay investigation"},
    )
    plt.close(figure)


def _render_highlight_evidence(
    output: Path,
    label: str,
    branch_id: str,
    replay_v2: dict[str, Any],
    final_v2: dict[str, Any],
) -> None:
    rows = [item for item in replay_v2["rows"] if item["branch_id"] == branch_id]
    if not rows:
        raise ValueError(f"highlight branch {branch_id} was not present in replay V2")
    selected = {(item["branch_id"], item["alias_index"]): item for item in final_v2["trajectories"]}
    gate = replay_v2["gate_config"]
    tolerance = float(rows[0]["equivalence_tolerance"])
    figure, axes = plt.subplots(2, 1, figsize=(14, 9), sharex=True)
    for row in rows:
        alias = int(row["alias_index"])
        blocks = row["blocks"]
        block_indices = [int(item["block_index"]) for item in blocks]
        suffix = " · selected display-only" if (branch_id, alias) in selected else ""
        axes[0].plot(
            block_indices,
            [float(item["median_margin_delta"]) for item in blocks],
            marker="o",
            linewidth=1.4,
            label=f"alias {alias:+d}{suffix}",
        )
        axes[1].plot(
            block_indices,
            [float(item["median_corrected_margin"]) for item in blocks],
            marker="o",
            linewidth=1.4,
            label=f"alias {alias:+d}{suffix}",
        )
    axes[0].axhspan(-tolerance, tolerance, color="#138a36", alpha=0.09)
    axes[0].axhline(-tolerance, color="#138a36", linestyle="--", linewidth=1)
    axes[0].axhline(tolerance, color="#138a36", linestyle="--", linewidth=1)
    axes[0].axhline(float(gate["harmful_block_delta"]), color="#c81d25", linestyle=":")
    axes[0].set_ylim(-0.022, 0.002)
    axes[0].set_ylabel("Corrected − baseline margin")
    axes[0].set_title("Blockwise relative evidence (fixed axis)", loc="left")
    axes[1].axhline(
        float(gate["minimum_geometry_display_corrected_margin"]),
        color="#d97706",
        linestyle="--",
        label="display-only absolute floor",
    )
    axes[1].axhline(
        float(gate["minimum_median_corrected_margin"]),
        color="#138a36",
        linestyle="--",
        label="automatic-correction absolute floor",
    )
    axes[1].set_ylim(-0.002, 0.06)
    axes[1].set_ylabel("Corrected exact − control margin")
    axes[1].set_xlabel("One-second replay block index")
    axes[1].set_title("Blockwise absolute evidence (fixed axis)", loc="left")
    for axis in axes:
        axis.grid(alpha=0.18)
        axis.legend(fontsize=8, ncol=3)
    figure.suptitle(f"{label} · branch {branch_id[7:15]}", fontweight="bold")
    figure.tight_layout()
    figure.savefig(
        output,
        dpi=170,
        facecolor="white",
        metadata={"Software": "leo-tracker replay recovery investigation"},
    )
    plt.close(figure)


def _branch_facts(
    bank: dict[str, Any],
    old: dict[str, Any],
    exact: dict[str, Any],
    wrong: dict[str, Any] | None,
    final_v2: dict[str, Any],
) -> list[dict[str, Any]]:
    old_rows = {(item["branch_id"], item["alias_index"]): item for item in old["rows"]}
    wrong_rows = (
        {}
        if wrong is None
        else {(item["branch_id"], item["alias_index"]): item for item in wrong["rows"]}
    )
    branches = {item["branch_id"]: item for item in bank["branches"]}
    selected = {(item["branch_id"], item["alias_index"]): item for item in final_v2["trajectories"]}
    result = []
    for row in exact["rows"]:
        branch = branches[row["branch_id"]]
        model = next(
            item for item in branch["models"] if item["model_id"] == row["canonical_model_id"]
        )
        times = sorted(
            item["time_s"]
            for item in bank["observations"]
            if item["observation_id"] in set(branch["observation_ids"])
        )
        prior = old_rows.get((row["branch_id"], row["alias_index"]))
        wrong_row = wrong_rows.get((row["branch_id"], row["alias_index"]))
        best_bic = min(item["bic"] for item in branch["models"])
        result.append(
            {
                "branch": row["branch_id"][7:15],
                "alias": row["alias_index"],
                "observations": row["observation_count"],
                "duration_s": row["duration_s"],
                "maximum_observation_gap_s": max(np.diff(times), default=0.0),
                "degree": row["polynomial_degree"],
                "selected_bic": model["bic"],
                "best_bic": best_bic,
                "bic_delta": model["bic"] - best_bic,
                "residual_rms_hz": row["residual_rms_hz"],
                "residual_max_hz": row["residual_max_hz"],
                "v1_status": None if prior is None else prior["status"],
                "v1_probes": None if prior is None else prior["evaluated_probe_count"],
                "v1_improved_fraction": (
                    None
                    if prior is None or not prior["evaluated_probe_count"]
                    else prior["improved_probe_count"] / prior["evaluated_probe_count"]
                ),
                "v1_median_delta": None if prior is None else prior["median_margin_delta"],
                "v1_corrected_margin": (
                    None if prior is None else prior["median_control_separation"]
                ),
                "v2_tier": row["tier"],
                "v2_probes": row["evaluated_probe_count"],
                "v2_blocks": row["evaluated_block_count"],
                "v2_coverage": row["block_coverage_ratio"],
                "v2_median_delta": row["median_block_margin_delta"],
                "v2_corrected_margin": row["median_block_corrected_margin"],
                "v2_harmful_blocks": row["harmful_block_count"],
                "v2_max_harmful_run": row["maximum_consecutive_harmful_blocks"],
                "wrong_edge_tier": None if wrong_row is None else wrong_row["tier"],
                "wrong_edge_corrected_margin": (
                    None if wrong_row is None else wrong_row["median_block_corrected_margin"]
                ),
                "v2_final_selected": (row["branch_id"], row["alias_index"]) in selected,
                "v2_final_automatic_correction_eligible": (
                    selected[(row["branch_id"], row["alias_index"])][
                        "automatic_correction_eligible"
                    ]
                    if (row["branch_id"], row["alias_index"]) in selected
                    else False
                ),
                "reason": "; ".join(row["reasons"]),
            }
        )
    return result


def main() -> int:
    args = _args()
    args.output_root.mkdir(parents=True, exist_ok=True)
    scientific = args.sealed_run_root / "scientific" / "path-standard"
    facts: list[dict[str, Any]] = []
    scopes = sorted(item for item in scientific.iterdir() if item.is_dir())
    if args.scope_digest is not None:
        scopes = [item for item in scopes if item.name == args.scope_digest]
        if not scopes:
            raise ValueError(f"scope {args.scope_digest} was not present in the sealed run")
    for scope in scopes:
        report = _read(scope / "standard.path-report.v2.json")["raw_report"]
        short_radio = "5d4d" if report["radio_id"].endswith("5d4d") else "19f2"
        label = f"{short_radio} RX{report['receiver_id']} ({report['stream_id']})"
        slug = f"{short_radio}-rx{report['receiver_id']}"
        pilot = _read(scope / "standard.pilot-scan.v3.json")
        raw_bank = _read(scope / "standard.trajectory-bank.v2.json")
        alias_map = _read(scope / "standard.cfo-alias-map.v2.json")
        bank = _read(scope / "standard.dealiased-trajectory-bank.v2.json")
        old = _read(scope / "standard.cfo-lift-replay.v1.json")
        final = _read(scope / "standard.final-trajectory-bank.v1.json")
        exact = _read(args.exact_v2_root / scope.name / "standard.cfo-lift-replay.v2.json")
        final_v2 = _read(args.exact_v2_root / scope.name / "standard.final-trajectory-bank.v2.json")
        wrong_path = (
            None
            if args.wrong_edge_v2_root is None
            else args.wrong_edge_v2_root / scope.name / "standard.cfo-lift-replay.v2.json"
        )
        wrong = None if wrong_path is None else _read(wrong_path)
        schedule = _read(scope / "standard.probe-schedule.v2.json")
        association = bank["association"]
        edge_statuses = Counter(item["status"] for item in association["edge_decisions"])
        edge_reasons = Counter(item["reason"] for item in association["edge_decisions"])
        branch_rows = _branch_facts(bank, old, exact, wrong, final_v2)
        facts.append(
            {
                "label": label,
                "slug": slug,
                "scope_digest": scope.name,
                "stream_id": report["stream_id"],
                "radio_id": report["radio_id"],
                "receiver_id": report["receiver_id"],
                "scheduled_probes": schedule["source_probe_count"],
                "returned_probes": schedule["returned_probe_count"],
                "raw_candidates": sum(len(item["candidates"]) for item in pilot["detections"]),
                "raw_trajectories": len(raw_bank["trajectories"]),
                "alias_representatives": alias_map["returned_representative_count"],
                "alias_components": alias_map["component_count"],
                "canonical_observations": bank["returned_observation_count"],
                "association_source_edges": association["source_edge_count"],
                "association_edge_statuses": dict(edge_statuses),
                "association_top_rejections": edge_reasons.most_common(8),
                "association_source_branches": association["source_branch_count"],
                "association_returned_branches": association["returned_branch_count"],
                "association_truncated_branches": association["truncated_branch_count"],
                "fitted_branches": len(bank["branches"]),
                "v1_replayed_lifts": len(old["rows"]),
                "v1_supported_lifts": sum(item["status"] == "supported" for item in old["rows"]),
                "v1_final_trajectories": len(final["trajectories"]),
                "v2_tiers": dict(Counter(item["tier"] for item in exact["rows"])),
                "v2_final_candidates": len(final_v2["trajectories"]),
                "v2_final_automatic": len(final_v2["automatic_correction_trajectory_ids"]),
                "wrong_edge_v2_tiers": (
                    {} if wrong is None else dict(Counter(item["tier"] for item in wrong["rows"]))
                ),
                "branches": branch_rows,
            }
        )
        _render_path(
            args.output_root / f"{slug}-funnel.png",
            label,
            pilot,
            raw_bank,
            bank,
            final,
            exact,
            final_v2,
            exact_edge=args.exact_edge,
        )
        if args.highlight_branch is not None:
            _render_highlight_evidence(
                args.output_root / f"{slug}-highlight-replay-evidence.png",
                label,
                args.highlight_branch,
                exact,
                final_v2,
            )
    (args.output_root / "facts.json").write_text(
        json.dumps(facts, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"paths": len(facts), "output_root": str(args.output_root.resolve())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
