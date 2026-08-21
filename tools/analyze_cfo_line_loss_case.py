#!/usr/bin/env python3
"""Trace persisted Standard inventories for one fragmented CFO-line case study."""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from leo.analysis.research.cfo_lines import CfoPoint, HoughConfig, LineSegment, weighted_hough_lines

SESSION_ID = "cap-20260821T001623-1eb9c80e03dd"
SCOPE = "radio_pluto_19f2 / stream-1 / RX1"
ALIAS_HZ = 1.0 / 4.4e-6


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser.parse_args()


def _read(root: Path, name: str) -> dict[str, Any]:
    return json.loads((root / name).read_text(encoding="utf-8"))


def _points(pilot: dict[str, Any]) -> tuple[CfoPoint, ...]:
    result = []
    for detection_index, detection in enumerate(pilot["detections"]):
        for candidate in detection["candidates"]:
            score = next(item for item in candidate["scores"] if item["method"] == "glrt64")
            result.append(
                CfoPoint(
                    point_id=f"probe-{detection_index:04d}-rank-{int(candidate['rank'])}",
                    time_s=float(detection["time_s"]),
                    frequency_hz=float(score["tracking_cfo_hz"]),
                    exact_score=float(score["exact_score"]),
                    control_score=float(score["control_score"]),
                    margin=float(score["margin"]),
                )
            )
    return tuple(result)


def _histogram(values: list[float], edges: tuple[float, ...]) -> dict[str, int]:
    result = {}
    previous = 0.0
    for edge in edges:
        result[f"[{previous:g},{edge:g})"] = sum(previous <= value < edge for value in values)
        previous = edge
    result[f"[{previous:g},inf)"] = sum(value >= previous for value in values)
    return result


def _selected_model(branch: dict[str, Any]) -> dict[str, Any]:
    return next(
        model for model in branch["models"] if model["model_id"] == branch["selected_model_id"]
    )


def _branch_metrics(dealiased: dict[str, Any]) -> list[dict[str, Any]]:
    observation_time = {
        item["observation_id"]: float(item["time_s"]) for item in dealiased["observations"]
    }
    association_cost = {
        item["branch_id"]: item["selected_link_cost"]
        for item in dealiased["association"]["branches"]
    }
    result = []
    for branch in dealiased["branches"]:
        times = sorted(observation_time[item] for item in branch["observation_ids"])
        gaps = np.diff(times)
        model = _selected_model(branch)
        result.append(
            {
                "branch_id": branch["branch_id"],
                "short_id": branch["branch_id"].removeprefix("sha256:")[:8],
                "support": len(times),
                "start_s": min(times),
                "end_s": max(times),
                "span_s": max(times) - min(times),
                "maximum_internal_gap_s": float(np.max(gaps)) if gaps.size else 0.0,
                "median_internal_gap_s": float(np.median(gaps)) if gaps.size else 0.0,
                "selected_degree": int(model["polynomial_degree"]),
                "selected_bic": float(model["bic"]),
                "residual_rms_hz": float(model["residual_rms_hz"]),
                "selected_link_cost": association_cost.get(branch["branch_id"]),
            }
        )
    return result


def _replay_metrics(replay: dict[str, Any]) -> dict[str, Any]:
    rows = []
    failures: Counter[str] = Counter()
    for row in replay["rows"]:
        evaluated = int(row["evaluated_probe_count"])
        improved_fraction = int(row["improved_probe_count"]) / evaluated if evaluated else 0.0
        gates = {
            "minimum_3_probes": evaluated >= 3,
            "improved_fraction_ge_0.5": improved_fraction >= 0.5,
            "median_margin_delta_gt_0": float(row["median_margin_delta"]) > 0.0,
            "median_control_separation_ge_0.05": (float(row["median_control_separation"]) >= 0.05),
        }
        for name, passed in gates.items():
            if not passed:
                failures[name] += 1
        rows.append(
            {
                "branch_id": row["branch_id"],
                "short_id": row["branch_id"].removeprefix("sha256:")[:8],
                "alias_index": int(row["alias_index"]),
                "evaluated_probe_count": evaluated,
                "improved_probe_count": int(row["improved_probe_count"]),
                "improved_fraction": improved_fraction,
                "median_margin_delta": float(row["median_margin_delta"]),
                "median_control_separation": float(row["median_control_separation"]),
                "status": row["status"],
                "gates": gates,
            }
        )
    return {"rows": rows, "failed_gate_counts": dict(sorted(failures.items()))}


def _line_metrics(segment: LineSegment) -> dict[str, Any]:
    return {
        "segment_id": segment.segment_id,
        "short_id": segment.segment_id.removeprefix("sha256:")[:8],
        "support": segment.support,
        "start_s": segment.start_s,
        "end_s": segment.end_s,
        "span_s": segment.end_s - segment.start_s,
        "slope_hz_per_s": segment.slope_hz_per_s,
        "intercept_mod_alias_hz": segment.intercept_mod_alias_hz,
        "residual_rms_hz": segment.residual_rms_hz,
        "maximum_gap_s": segment.maximum_gap_s,
    }


def _plot(
    path: Path,
    points: tuple[CfoPoint, ...],
    raw: dict[str, Any],
    dealiased: dict[str, Any],
    final: dict[str, Any],
    hough: tuple[LineSegment, ...],
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    times = np.asarray([point.time_s for point in points])
    frequency = np.asarray([point.frequency_hz for point in points])
    margins = np.asarray([point.margin for point in points])
    obs = {item["observation_id"]: item for item in dealiased["observations"]}
    figure, axes = plt.subplots(4, 1, figsize=(17, 15), sharex=True, sharey=True)
    visible = margins >= 0.024214120259181748
    for axis in axes:
        axis.scatter(
            times,
            frequency / 1_000.0,
            s=2,
            color="#aeb7c2",
            alpha=0.10,
            linewidths=0,
            rasterized=True,
        )
        axis.scatter(
            times[visible],
            frequency[visible] / 1_000.0,
            s=7,
            c=margins[visible],
            cmap="viridis",
            vmin=0.024,
            vmax=0.65,
            alpha=0.58,
            linewidths=0,
            rasterized=True,
        )
        axis.set_xlim(0.0, 60.0)
        axis.set_ylim(-525.0, 525.0)
        axis.set_ylabel("Raw CFO (kHz)")
        axis.grid(alpha=0.15)
    representatives = {family["representative_trajectory_id"] for family in raw["families"]}
    for trajectory in raw["trajectories"]:
        if trajectory["trajectory_id"] not in representatives:
            continue
        dense = np.linspace(float(trajectory["start_s"]), float(trajectory["end_s"]), 300)
        base = np.polyval(
            trajectory["coefficients_hz"], dense - float(trajectory["reference_time_s"])
        )
        axes[0].plot(dense, base / 1_000.0, linewidth=2.4, label=trajectory["trajectory_id"][7:15])
    axes[0].set_title("1. Raw tracker representatives: three smooth spans", loc="left")
    axes[0].legend(fontsize=8, ncol=3)
    colors = plt.get_cmap("tab20")
    for index, branch in enumerate(dealiased["branches"]):
        branch_points = [obs[item] for item in branch["observation_ids"]]
        axes[1].plot(
            [item["time_s"] for item in branch_points],
            [item["component_cfo_hz"] / 1_000.0 for item in branch_points],
            marker="o",
            markersize=2.5,
            linewidth=1.0,
            color=colors(index % 20),
            alpha=0.85,
        )
    axes[1].set_title("2. Returned association: 58 short fragments (5–15 observations)", loc="left")
    line_colors = ("#d73027", "#1a9850", "#4575b4", "#984ea3", "#e6ab02")
    for index, segment in enumerate(hough):
        dense = np.linspace(segment.start_s, segment.end_s, 240)
        base = segment.slope_hz_per_s * dense + segment.intercept_hz
        for alias in range(-3, 4):
            curve = base + alias * ALIAS_HZ
            shown = (curve >= -525_000.0) & (curve <= 525_000.0)
            axes[2].plot(
                dense[shown],
                curve[shown] / 1_000.0,
                color=line_colors[index % len(line_colors)],
                linewidth=2.2,
            )
        axes[2].plot(
            [],
            [],
            color=line_colors[index % len(line_colors)],
            label=(
                f"H{index + 1} n={segment.support}, span={segment.end_s - segment.start_s:.1f}s, "
                f"slope={segment.slope_hz_per_s / 1_000:.2f} kHz/s"
            ),
        )
    axes[2].set_title("3. Offline weighted Hough reconstruction (alias-aware)", loc="left")
    axes[2].legend(fontsize=8, ncol=2)
    branch_by_id = {branch["branch_id"]: branch for branch in dealiased["branches"]}
    for trajectory in final["trajectories"]:
        branch = branch_by_id[trajectory["branch_id"]]
        dense = np.linspace(float(trajectory["start_s"]), float(trajectory["end_s"]), 80)
        base = np.polyval(
            trajectory["absolute_coefficients_hz"],
            dense - float(trajectory["reference_time_s"]),
        )
        axes[3].plot(dense, base / 1_000.0, color="#d73027", linewidth=2.0)
        axes[3].text(
            float(branch["start_s"]),
            float(base[0] / 1_000.0),
            trajectory["trajectory_id"][7:15],
            fontsize=6,
        )
    axes[3].set_title("4. Final replay-supported output: 19 short trajectories", loc="left")
    axes[3].set_xlabel("Recording time (s)")
    figure.suptitle(
        f"{SESSION_ID} · {SCOPE}\n"
        "Why the apparent line fragmented · fixed axes · candidate-only evidence"
    )
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _markdown(report: dict[str, Any]) -> str:
    inventory = report["inventory"]
    lines = [
        f"# CFO line-loss case study: `{SESSION_ID}`",
        "",
        f"Scope: `{SCOPE}`.",
        "",
        "## Finding",
        "",
        "The dense hits are consistent with one slowly evolving apparent CFO curve, but the "
        "persisted Standard output cannot carry it end to end. The raw tracker forms three long "
        "representatives. Alias comparison rejects the first/second join at 5.908 kHz RMS and "
        "does not compare the second/third across a 0.525 s no-overlap gap. The association then "
        "returns only 64 of 1,281 source branches and the polynomial stage can fit only the 58 "
        "branches with at least five observations. Replay supports 19 of 84 lifts.",
        "",
        "## Persisted inventory",
        "",
        "| Stage | Persisted result | Loss / gate |",
        "|---|---:|---|",
        (
            f"| Probe schedule | {inventory['schedule']['returned']} / "
            f"{inventory['schedule']['source']} | "
            f"{inventory['schedule']['truncated']} truncated |"
        ),
        (
            f"| Pilot scan | {inventory['pilot']['detections']} probes, "
            f"{inventory['pilot']['candidates']} candidates | "
            f"{inventory['pilot']['strong_hits']} hits at margin ≥ 0.05 |"
        ),
        (
            f"| Raw tracker | {inventory['raw_tracker']['trajectories']} fits, "
            f"{inventory['raw_tracker']['representatives']} representatives | "
            f"high gate {inventory['raw_tracker']['high_gate']:.6f} |"
        ),
        (
            f"| Alias map | {inventory['alias_map']['components']} components | "
            "first/second rejected at 5.908 kHz RMS; second/third no overlap |"
        ),
        (
            f"| Association | {inventory['association']['returned_branches']} / "
            f"{inventory['association']['source_branches']} branches returned | "
            f"{inventory['association']['truncated_branches']} truncated |"
        ),
        (
            f"| Polynomial bank | {inventory['polynomial']['eligible_branches']} "
            "eligible branches | six 4-point branches ineligible |"
        ),
        (
            f"| Lift replay | {inventory['replay']['supported']} supported / "
            f"{inventory['replay']['rows']} lifts | "
            f"{inventory['replay']['rejected']} rejected |"
        ),
        (
            f"| Final | {inventory['final']['trajectories']} trajectories | "
            "all remain short fragments |"
        ),
        "",
        "## Offline reconstructed lines",
        "",
        "| ID | Support | Span (s) | Slope (kHz/s) | RMS (Hz) | Max gap (s) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for item in report["hough_lines"]:
        lines.append(
            f"| {item['short_id']} | {item['support']} | {item['span_s']:.3f} | "
            f"{item['slope_hz_per_s'] / 1_000:.3f} | {item['residual_rms_hz']:.1f} | "
            f"{item['maximum_gap_s']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Audit limitation",
            "",
            "The persisted contract records exact aggregate source/truncation counts, but not the "
            "1,217 omitted source branches or 42,560 omitted edge decisions. Therefore their "
            "individual ranks and rejection reasons cannot be reconstructed after publication. "
            "No Standard or live state was changed for this analysis.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = _arguments()
    args.output_root.mkdir(parents=True, exist_ok=True)
    schedule = _read(args.source_root, "standard.probe-schedule.v2.json")
    pilot = _read(args.source_root, "standard.pilot-scan.v3.json")
    raw = _read(args.source_root, "standard.trajectory-bank.v2.json")
    alias = _read(args.source_root, "standard.cfo-alias-map.v2.json")
    dealiased = _read(args.source_root, "standard.dealiased-trajectory-bank.v2.json")
    replay = _read(args.source_root, "standard.cfo-lift-replay.v1.json")
    final = _read(args.source_root, "standard.final-trajectory-bank.v1.json")
    points = _points(pilot)
    started = time.perf_counter()
    hough = weighted_hough_lines(points, HoughConfig())
    hough_runtime = time.perf_counter() - started
    branches = _branch_metrics(dealiased)
    association = dealiased["association"]
    association_reasons = Counter(item["status"] for item in association["edge_decisions"])
    replay_metrics = _replay_metrics(replay)
    selected_degrees = Counter(item["selected_degree"] for item in branches)
    strong_hits = sum(point.margin >= 0.05 for point in points)
    report: dict[str, Any] = {
        "schema": "org.leo.research.cfo-line-loss-case/v1",
        "session_id": SESSION_ID,
        "scope": SCOPE,
        "finding": (
            "one apparent evolving curve fragmented by component, association, and replay gates"
        ),
        "inventory": {
            "schedule": {
                "source": schedule["source_probe_count"],
                "returned": schedule["returned_probe_count"],
                "truncated": schedule["truncated_probe_count"],
            },
            "pilot": {
                "detections": len(pilot["detections"]),
                "candidates": len(points),
                "strong_hits": strong_hits,
                "strong_hit_probes": len(
                    {point.time_s for point in points if point.margin >= 0.05}
                ),
                "truncated_candidates": sum(
                    int(item["truncated_candidate_count"]) for item in pilot["detections"]
                ),
            },
            "raw_tracker": {
                "observation_count": raw["observation_count"],
                "trajectories": len(raw["trajectories"]),
                "representatives": len(raw["families"]),
                "high_gate": raw["trajectories"][0]["high_gate"],
                "representative_rows": [
                    {
                        "trajectory_id": family["representative_trajectory_id"],
                        "start_s": family["start_s"],
                        "end_s": family["end_s"],
                        "member_count": len(family["member_trajectory_ids"]),
                    }
                    for family in raw["families"]
                ],
            },
            "alias_map": {
                "components": alias["component_count"],
                "pair_decisions": alias["pair_decisions"],
                "truncated_representatives": alias["truncated_representative_count"],
            },
            "association": {
                "observations": association["source_observation_count"],
                "source_edges": association["source_edge_count"],
                "returned_edges": association["returned_edge_count"],
                "truncated_edges": association["truncated_edge_count"],
                "source_branches": association["source_branch_count"],
                "returned_branches": association["returned_branch_count"],
                "truncated_branches": association["truncated_branch_count"],
                "edge_status_counts": dict(sorted(association_reasons.items())),
            },
            "polynomial": {
                "eligible_branches": len(branches),
                "ineligible_four_point_branches": sum(
                    len(item["observation_ids"]) == 4 for item in association["branches"]
                ),
                "selected_degree_counts": dict(sorted(selected_degrees.items())),
            },
            "replay": {
                "rows": len(replay["rows"]),
                "supported": sum(row["status"] == "supported" for row in replay["rows"]),
                "rejected": sum(row["status"] == "rejected" for row in replay["rows"]),
                "failed_gate_counts": replay_metrics["failed_gate_counts"],
            },
            "final": {"trajectories": len(final["trajectories"])},
        },
        "branch_histograms": {
            "support": dict(sorted(Counter(item["support"] for item in branches).items())),
            "span_s": _histogram([item["span_s"] for item in branches], (0.25, 0.5, 1.0, 2.0, 4.0)),
            "maximum_internal_gap_s": _histogram(
                [item["maximum_internal_gap_s"] for item in branches],
                (0.05, 0.1, 0.25, 0.5, 1.0),
            ),
        },
        "branches": branches,
        "replay": replay_metrics,
        "hough_runtime_s": hough_runtime,
        "hough_lines": [_line_metrics(segment) for segment in hough],
    }
    (args.output_root / "case-metrics.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output_root / "case-report.md").write_text(_markdown(report), encoding="utf-8")
    _plot(args.output_root / "line-loss-case.png", points, raw, dealiased, final, hough)
    print(args.output_root / "case-report.md")


if __name__ == "__main__":
    main()
