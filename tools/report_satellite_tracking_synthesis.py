#!/usr/bin/env python3
"""Render summary figures for the satellite-tracking evidence synthesis.

The tool reads only committed, machine-readable evidence.  It does not reopen IQ,
rerank a catalogue, fit a nuisance parameter, or change an experimental verdict.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "reports" / "figures" / "2026_08_27_satellite_tracking_synthesis"
FINAL_SCORE = ROOT / "reports" / "figures" / "2026_08_26_final_doppler_holdout_attempt2-score.json"
FINAL_INVENTORY = (
    ROOT
    / "reports"
    / "figures"
    / "2026_08_26_final_doppler_holdout_attempt2"
    / "association-bin-inventory.json"
)
RETROSPECTIVE = (
    ROOT
    / "reports"
    / "figures"
    / "2026_08_26_retrospective_satellite_nuisance"
    / "retrospective-satellite-nuisance-evidence.json"
)
LONG_ARC = (
    ROOT
    / "reports"
    / "figures"
    / "2026_08_27_satellite_pnt_long_arc_development_attempt2"
    / "audit-evidence.json"
)
LEGACY = (
    ROOT
    / "reports"
    / "figures"
    / "2026_08_23_thirteen_dwell_starlink_association_fresh"
    / "multi-dwell-track-summary.csv"
)


GATE_ORDER = (
    "recovered_track",
    "minimum_heldout_odd_bins",
    "minimum_heldout_odd_bin_fraction",
    "absolute_rank_one_heldout_odd_rms",
    "primary_baseline_rank_one_agreement",
    "training_runner_margin_ratio",
    "heldout_rank_one_remains_best",
    "heldout_runner_margin_ratio",
    "permutation_empirical_p",
    "at_least_2_rolling_origins_complete_and_stable",
    "utc_site_predecessor_controls_complete_and_stable",
)
GATE_LABELS = (
    "track",
    "future n",
    "future fraction",
    "RMS",
    "model agreement",
    "train margin",
    "future persistence",
    "future margin",
    "permutation",
    "rolling stability",
    "UTC/site/TLE",
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _suffix(session_id: str) -> str:
    return session_id.split("T", 1)[1][:6]


def _final_summary(score: dict[str, Any], inventory: dict[str, Any]) -> list[dict[str, Any]]:
    counts = {
        item["session_id"]: {
            "total_bins": len(item["bins"]),
            "training_bins": sum(row["split"] == "training" for row in item["bins"]),
            "evaluation_bins": sum(row["split"] == "evaluation" for row in item["bins"]),
            "failure_reasons": item["failure_reasons"],
        }
        for item in inventory["inventories"]
    }
    rows: list[dict[str, Any]] = []
    for item in score["association"]:
        session_id = item["session_id"]
        primary_scores = (item.get("primary") or {}).get("scores", [])
        baseline_scores = (item.get("baseline") or {}).get("scores", [])
        future_best = (
            min(primary_scores, key=lambda row: row["heldout_odd_rms_hz"])
            if primary_scores
            else None
        )
        rolling = []
        for origin in (item.get("controls") or {}).get("rolling_origins", []):
            rolling.append(
                origin.get("rank_one_candidate_id") if origin.get("status") == "complete" else None
            )
        row = {
            "session_id": session_id,
            "suffix": _suffix(session_id),
            "evaluable": item["evaluable"],
            **counts[session_id],
            "visible_candidates": len(primary_scores) if primary_scores else None,
            "primary_norad": primary_scores[0]["candidate_id"] if primary_scores else None,
            "primary_training_rms_hz": primary_scores[0]["training_rms_hz"]
            if primary_scores
            else None,
            "primary_future_rms_hz": primary_scores[0]["heldout_odd_rms_hz"]
            if primary_scores
            else None,
            "baseline_norad": baseline_scores[0]["candidate_id"] if baseline_scores else None,
            "future_best_norad": future_best["candidate_id"] if future_best else None,
            "rolling_norads": rolling,
            "conditions": (item.get("gate") or {}).get("conditions", {}),
            "historical_failed_conditions": (item.get("gate") or {}).get("failed_conditions", []),
        }
        rows.append(row)
    return rows


def _legacy_summary() -> dict[str, Any]:
    rows = list(csv.DictReader(LEGACY.read_text(encoding="utf-8").splitlines()))
    return {
        "track_count": len(rows),
        "dwell_count": len({row["session_id"] for row in rows}),
        "orbit_beats_line_count": sum(float(row["holdout_advantage_hz"]) > 0.0 for row in rows),
        "wrong_time_pass_count": sum(float(row["scalar_empirical_p"]) <= 0.05 for row in rows),
        "secure_count": sum(row["secure_association"] == "True" for row in rows),
    }


def _plot_gate_matrix(rows: list[dict[str, Any]], output: Path) -> None:
    evaluable = [row for row in rows if row["evaluable"]]
    matrix = np.array(
        [[1 if row["conditions"][gate] else 0 for gate in GATE_ORDER] for row in evaluable],
        dtype=int,
    )
    figure, axis = plt.subplots(figsize=(12.5, 5.6), constrained_layout=True)
    axis.imshow(matrix, cmap=ListedColormap(["#c84440", "#2d8a58"]), vmin=0, vmax=1, aspect="auto")
    axis.set_xticks(range(len(GATE_LABELS)), GATE_LABELS, rotation=38, ha="right")
    axis.set_yticks(range(len(evaluable)), [row["suffix"] for row in evaluable])
    axis.set_xlabel("Historical v3 condition (retired far-time gate omitted)")
    axis.set_ylabel("Dwell UTC key")
    axis.set_title("Final holdout: track support succeeds, identity stability fails")
    for row_index in range(matrix.shape[0]):
        for column_index in range(matrix.shape[1]):
            axis.text(
                column_index,
                row_index,
                "PASS" if matrix[row_index, column_index] else "FAIL",
                ha="center",
                va="center",
                color="white",
                fontsize=6.5,
                fontweight="bold",
            )
    axis.legend(
        handles=[Patch(color="#2d8a58", label="pass"), Patch(color="#c84440", label="fail")],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.26),
        ncol=2,
        frameon=False,
    )
    figure.savefig(output, dpi=180, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _plot_identity_stability(rows: list[dict[str, Any]], output: Path) -> None:
    evaluable = [row for row in rows if row["evaluable"]]
    columns = ("primary", "fixed500", "future best", "rolling 40%", "rolling 60%", "rolling 80%")
    matrix = []
    labels = []
    for row in evaluable:
        primary = row["primary_norad"]
        identities = [
            primary,
            row["baseline_norad"],
            row["future_best_norad"],
            *row["rolling_norads"],
        ]
        states = [2]
        states.extend(
            0 if identity is None else (2 if identity == primary else 1)
            for identity in identities[1:]
        )
        matrix.append(states)
        labels.append(identities)
    values = np.asarray(matrix, dtype=int)
    figure, axis = plt.subplots(figsize=(10.5, 5.8), constrained_layout=True)
    axis.imshow(
        values,
        cmap=ListedColormap(["#9aa0a6", "#d46a4c", "#2d8a58"]),
        vmin=0,
        vmax=2,
        aspect="auto",
    )
    axis.set_xticks(range(len(columns)), columns, rotation=25, ha="right")
    axis.set_yticks(range(len(evaluable)), [row["suffix"] for row in evaluable])
    axis.set_title("Catalogue-label stability relative to each training-primary candidate")
    axis.set_xlabel("Selection or diagnostic view")
    axis.set_ylabel("Dwell UTC key")
    for row_index, identities in enumerate(labels):
        for column_index, identity in enumerate(identities):
            axis.text(
                column_index,
                row_index,
                "NR" if identity is None else str(identity),
                ha="center",
                va="center",
                color="white",
                fontsize=8,
                fontweight="bold",
            )
    axis.legend(
        handles=[
            Patch(color="#2d8a58", label="same as primary"),
            Patch(color="#d46a4c", label="different identity"),
            Patch(color="#9aa0a6", label="not rankable"),
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.22),
        ncol=3,
        frameon=False,
    )
    figure.savefig(output, dpi=180, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def _plot_long_arc_specificity(audit: dict[str, Any], output: Path) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(12.5, 4.8), constrained_layout=True)
    colors = ["#4477aa", "#cc6677"]
    for axis, arc, color in zip(axes, audit["arcs"], colors, strict=True):
        partitions = arc["partitions"]
        labels = [item["label"].replace("rolling-", "") for item in partitions]
        ratios = [item["minus_500_future_rms_ratio"] for item in partitions]
        bars = axis.bar(labels, ratios, color=color, alpha=0.88)
        axis.axhline(1.0, color="black", linewidth=1.1, linestyle="--")
        axis.set_yscale("log")
        axis.set_ylabel("RMS(−500 s) / RMS(true time)")
        axis.set_title(arc["arc_id"].split("-")[2])
        axis.tick_params(axis="x", rotation=25)
        for bar, ratio in zip(bars, ratios, strict=True):
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                ratio * (1.06 if ratio >= 1 else 0.94),
                f"{ratio:.2f}×",
                ha="center",
                va="bottom" if ratio >= 1 else "top",
                fontsize=8,
            )
    figure.suptitle("Opened long arcs: descriptive wrong-epoch specificity by future partition")
    figure.savefig(output, dpi=180, metadata={"Software": "leo-tracker"})
    plt.close(figure)


def render(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    score = _load_json(FINAL_SCORE)
    inventory = _load_json(FINAL_INVENTORY)
    retrospective = _load_json(RETROSPECTIVE)
    long_arc = _load_json(LONG_ARC)
    final_rows = _final_summary(score, inventory)
    primary_retrospective = [row for row in retrospective["bundle_results"] if row["primary"]]

    _plot_gate_matrix(final_rows, output_dir / "final-holdout-gate-matrix.png")
    _plot_identity_stability(final_rows, output_dir / "final-holdout-identity-stability.png")
    _plot_long_arc_specificity(long_arc, output_dir / "long-arc-wrong-epoch-specificity.png")

    evidence = {
        "schema": "leo.satellite-tracking-synthesis.v1",
        "source_digests": {
            str(path.relative_to(ROOT)): _sha256(path)
            for path in (FINAL_SCORE, FINAL_INVENTORY, RETROSPECTIVE, LONG_ARC, LEGACY)
        },
        "final_holdout": final_rows,
        "final_holdout_aggregate": {
            "capture_count": len(final_rows),
            "evaluable_count": sum(row["evaluable"] for row in final_rows),
            "recovered_count": sum(
                row["conditions"].get("recovered_track", False) for row in final_rows
            ),
            "catalog_compatible_count": sum(
                (item.get("gate") or {}).get("catalog_compatible", False)
                for item in score["association"]
            ),
            "secure_norad_count": int(score["absolute_secure_norad"]),
            "gate_pass_counts": {
                gate: sum(row["conditions"].get(gate, False) for row in final_rows)
                for gate in GATE_ORDER
            },
        },
        "retrospective": {
            "primary_bundle_count": len(primary_retrospective),
            "recovered_count": retrospective["aggregate"]["primary_recovered_track_count"],
            "candidate_evidence_count": retrospective["aggregate"][
                "candidate_evidence_track_count"
            ],
            "secure_norad_count": retrospective["aggregate"]["secure_norad_count"],
            "primary_candidates": [
                {
                    "capture_id": row["capture_id"],
                    "bundle_id": row["bundle_id"],
                    "norad_id": row["hierarchical_top10"][0]["norad_id"],
                    "name": row["hierarchical_top10"][0]["name"],
                    "future_rms_hz": row["hierarchical_top10"][0]["heldout_rms_hz"],
                    "candidate_evidence_pass": row["candidate_evidence_pass"],
                }
                for row in primary_retrospective
            ],
        },
        "long_arcs": [
            {
                "arc_id": arc["arc_id"],
                "candidate_counts": arc["field_candidate_counts"],
                "main": arc["partitions"][0],
                "rolling_training_winners": [
                    partition["training_winner"] for partition in arc["partitions"][1:]
                ],
                "interpretation": arc["audit_interpretation"],
            }
            for arc in long_arc["arcs"]
        ],
        "legacy": _legacy_summary(),
        "claim_boundary": {
            "secure_norad_claimed": False,
            "positioning_validation_claimed": False,
            "wrong_epoch_is_observe_only": True,
        },
    }
    evidence_path = output_dir / "satellite-tracking-synthesis-evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    evidence = render(args.output_dir)
    print(json.dumps(evidence["final_holdout_aggregate"], sort_keys=True))


if __name__ == "__main__":
    main()
