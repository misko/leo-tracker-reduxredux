"""Summarize and plot the September 24 random-group dual-RX phase replay."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent
PRIOR = ROOT.parent / "2026_09_23_random_phase_links"
INVENTORY = ROOT / "inventory-summary.json"
PRIOR_CUTOFF_NS = int(datetime(2026, 9, 24, 15, 39, 44, tzinfo=UTC).timestamp() * 1_000_000_000)


def _load(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt") as source:
        return json.load(source)


def dwell_rows(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten every selected dwell while retaining all abstentions."""
    rows = []
    for session in document["sessions"]:
        for visit in session["visits"]:
            row = {
                "session_id": session["session_id"],
                "radio_id": session["radio_id"],
                "sample_rate_hz": session.get("sample_rate_hz"),
                "inventory_segment": (
                    "added_after_prior_cutoff"
                    if int(session.get("created_utc_ns", 0)) > PRIOR_CUTOFF_NS
                    else "original_published_cohort"
                ),
                "visit_index": visit["visit_index"],
                "phase_blind_priority": visit["phase_blind_priority"],
                "state": visit["state"],
                "reason": visit.get("reason"),
                "channel": visit.get("channel"),
                "edge": visit.get("edge"),
                "supported": False,
                "band_phase_resultant": None,
                "tracked_coherence": None,
                "wrong_pair_coherence": None,
                "held_group_count": None,
            }
            if visit["state"] == "replayed":
                phase = visit["random_phase"]
                row.update(
                    supported=bool(phase["supported"]),
                    band_phase_resultant=float(phase["band_phase_resultant"]),
                    tracked_coherence=float(phase["tracked_coherence"]),
                    wrong_pair_coherence=float(phase["wrong_pair_coherence"]),
                    held_group_count=len(phase["split"]["held_groups"]),
                )
            rows.append(row)
    return rows


def _finite(rows: list[dict[str, Any]], key: str) -> np.ndarray:
    return np.asarray([row[key] for row in rows if row[key] is not None], dtype=float)


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    replayed = [row for row in rows if row["state"] == "replayed"]
    supported = [row for row in replayed if row["supported"]]
    return {
        "selected_count": len(rows),
        "replayed_count": len(replayed),
        "abstained_count": len(rows) - len(replayed),
        "supported_count": len(supported),
        "supported_fraction_of_selected": len(supported) / len(rows) if rows else None,
        "supported_fraction_of_replayed": len(supported) / len(replayed) if replayed else None,
        "median_band_phase_resultant": float(np.median(_finite(replayed, "band_phase_resultant")))
        if replayed
        else None,
        "median_tracked_coherence": float(np.median(_finite(replayed, "tracked_coherence")))
        if replayed
        else None,
        "median_wrong_pair_coherence": float(np.median(_finite(replayed, "wrong_pair_coherence")))
        if replayed
        else None,
    }


def build_summary(document: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_radio: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_radio_sample_rate: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_inventory_segment: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_channel_edge: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_radio[row["radio_id"]].append(row)
        rate_msps = float(row["sample_rate_hz"]) / 1_000_000
        by_radio_sample_rate[f"{row['radio_id']}@{rate_msps:g}Msps"].append(row)
        by_inventory_segment[row["inventory_segment"]].append(row)
        if row["channel"] is not None:
            by_channel_edge[f"ch{row['channel']}-{row['edge']}"].append(row)
    session_states = defaultdict(int)
    inventory_sources = defaultdict(int)
    for session in document["sessions"]:
        session_states[session["state"]] += 1
        inventory_sources[session.get("analysis_inventory_source", "unavailable")] += 1
    prior_summary = json.loads((PRIOR / "summary.json").read_text())
    prior_2p5 = next(row for row in prior_summary["rates"] if row["sample_rate_msps"] == 2.5)
    inventory = json.loads(INVENTORY.read_text())
    if inventory["inventory_cutoff_utc"] != document["cohort"]["inventory_cutoff_utc"]:
        raise ValueError("inventory summary cutoff differs from the frozen replay cohort")
    if set(inventory["sessions"]) != {
        session["session_id"] for session in document["cohort"]["sessions"]
    }:
        raise ValueError("inventory summary sessions differ from the frozen replay cohort")
    return {
        "schema_version": 3,
        "inventory_cutoff_utc": document["cohort"]["inventory_cutoff_utc"],
        "session_count": len(document["sessions"]),
        "session_states": dict(sorted(session_states.items())),
        "frozen_cohort_complete_visit_count": int(inventory["complete_visit_count"]),
        "analyzed_complete_visit_count": sum(
            int(session.get("complete_visit_count", 0)) for session in document["sessions"]
        ),
        "analysis_inventory_sources": dict(sorted(inventory_sources.items())),
        "chronological_holdout_used": False,
        "validation_kind": "random whole 20ms groups; held B conditioned on same-block A",
        "overall": _aggregate(rows),
        "by_radio": {key: _aggregate(value) for key, value in sorted(by_radio.items())},
        "by_radio_sample_rate": {
            key: _aggregate(value) for key, value in sorted(by_radio_sample_rate.items())
        },
        "by_inventory_segment": {
            key: _aggregate(value) for key, value in sorted(by_inventory_segment.items())
        },
        "by_channel_edge": {
            key: _aggregate(value) for key, value in sorted(by_channel_edge.items())
        },
        "prior_random_2p5_msps_reference": prior_2p5,
        "comparison_limit": (
            "historical and current selections differ in capture time, source mixture, radio, "
            "and channel distribution; this is descriptive, not a causal improvement estimate"
        ),
        "geometric_phase_claimed": False,
        "satellite_identity_claimed": False,
    }


def build_report_local_screen_summary(document: dict[str, Any]) -> dict[str, Any]:
    """Retain compact proof that each report-local inventory was exhausted."""
    sessions = []
    for session in document["sessions"]:
        if "report_local_glrt" not in session.get("analysis_inventory_source", ""):
            continue
        checkpoint = _load(ROOT / "rows" / f"{session['session_id']}-phase-blind-screen.json.gz")
        if (
            checkpoint["protocol_sha256"] != document["protocol"]["sha256"]
            or checkpoint["input_manifest_sha256"] != session["input_manifest_sha256"]
        ):
            raise ValueError("screening checkpoint differs from final replay protocol")
        screening_rows = checkpoint["rows"]
        if len(screening_rows) != session["complete_visit_count"]:
            raise ValueError("screening checkpoint does not cover every complete visit")
        canonical_rows = json.dumps(screening_rows, sort_keys=True, separators=(",", ":")).encode()
        sessions.append(
            {
                "session_id": session["session_id"],
                "analysis_inventory_source": session["analysis_inventory_source"],
                "input_manifest_sha256": session["input_manifest_sha256"],
                "screened_visit_count": len(screening_rows),
                "phase_blind_candidate_visit_count": sum(
                    row["phase_blind_priority"] is not None for row in screening_rows
                ),
                "screening_error_count": sum("reason" in row for row in screening_rows),
                "screening_rows_sha256": hashlib.sha256(canonical_rows).hexdigest(),
                "configuration": checkpoint["configuration"],
            }
        )
    return {
        "schema_version": 1,
        "protocol_sha256": document["protocol"]["sha256"],
        "sessions": sessions,
    }


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fields = tuple(rows[0]) if rows else ()
    with path.open("w", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def plot_coverage(document: dict[str, Any], output: Path) -> None:
    sessions = sorted(document["sessions"], key=lambda row: int(row["created_utc_ns"]))
    labels = [row["session_id"][-4:] for row in sessions]
    selected = np.asarray([row["selected_visit_count"] for row in sessions])
    supported = np.asarray([row["supported_visit_count"] for row in sessions])
    replayed = np.asarray([row["replayed_visit_count"] for row in sessions])
    unavailable = np.asarray([row["state"] == "analysis_unavailable" for row in sessions])
    positions = np.arange(len(sessions))
    figure, axis = plt.subplots(figsize=(11, 7.2), layout="constrained")
    axis.barh(positions, supported, color="#20854e", label="Supported")
    axis.barh(
        positions,
        replayed - supported,
        left=supported,
        color="#8db7d6",
        label="Replayed, below gate",
    )
    axis.barh(
        positions,
        selected - replayed,
        left=replayed,
        color="#d95f59",
        label="Abstained",
    )
    if np.any(unavailable):
        axis.scatter(
            np.full(np.sum(unavailable), 0.15),
            positions[unavailable],
            marker="x",
            s=55,
            color="#7b2d43",
            label="Analysis unavailable",
            zorder=4,
        )
    axis.set(
        xlabel="Phase-blind selected visits (maximum 8 per capture)",
        ylabel="Capture suffix in UTC order",
        yticks=positions,
        yticklabels=labels,
        title="Random-group replay coverage across the frozen September 24 cohort",
    )
    axis.invert_yaxis()
    axis.grid(axis="x", alpha=0.2)
    axis.legend(ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.1))
    figure.savefig(output, dpi=190)
    plt.close(figure)


def plot_resultants(rows: list[dict[str, Any]], output: Path) -> None:
    replayed = [row for row in rows if row["state"] == "replayed"]
    figure, axis = plt.subplots(figsize=(11, 5.8), layout="constrained")
    cohort_styles = {
        ("radio_pluto_19f2", 2_500_000): ("#4c78a8", "o", "19f2 / 2.5 MS/s"),
        ("radio_pluto_19f2", 15_000_000): ("#7a5195", "s", "19f2 / 15 MS/s"),
        ("radio_pluto_5d4d", 2_500_000): ("#f28e2b", "o", "5d4d / 2.5 MS/s"),
    }
    categories = sorted({f"ch{row['channel']}-{row['edge'][0]}" for row in replayed})
    positions = {category: index for index, category in enumerate(categories)}
    for index, row in enumerate(replayed):
        category = f"ch{row['channel']}-{row['edge'][0]}"
        jitter = ((index * 37) % 23 - 11) / 75
        color, marker, _ = cohort_styles[(row["radio_id"], row["sample_rate_hz"])]
        axis.scatter(
            positions[category] + jitter,
            row["band_phase_resultant"],
            color=color,
            marker=marker if row["supported"] else "x",
            alpha=0.8,
            s=32,
        )
    axis.axhline(0.8, color="#333333", linestyle="--", linewidth=1, label="R gate = 0.8")
    present_styles = {(row["radio_id"], row["sample_rate_hz"]) for row in replayed}
    for key in sorted(present_styles):
        color, marker, label = cohort_styles[key]
        axis.scatter([], [], color=color, marker=marker, label=label)
    axis.scatter([], [], color="0.25", marker="x", label="Below composite gate")
    axis.set(
        xticks=np.arange(len(categories)),
        xticklabels=categories,
        ylim=(-0.02, 1.02),
        xlabel="Channel and edge (l/u)",
        ylabel="Held B-band residual phase resultant R",
        title="Random-held phase concentration by RF target",
    )
    axis.grid(axis="y", alpha=0.2)
    axis.legend(ncol=2)
    figure.savefig(output, dpi=190)
    plt.close(figure)


def plot_controls(rows: list[dict[str, Any]], output: Path) -> None:
    replayed = [row for row in rows if row["state"] == "replayed"]
    wrong = _finite(replayed, "wrong_pair_coherence")
    tracked = _finite(replayed, "tracked_coherence")
    resultant = _finite(replayed, "band_phase_resultant")
    figure, axis = plt.subplots(figsize=(7.6, 6.6), layout="constrained")
    points = axis.scatter(wrong, tracked, c=resultant, cmap="viridis", vmin=0, vmax=1, s=42)
    upper = max(0.16, float(max(np.max(wrong), np.max(tracked))) * 1.05)
    grid = np.linspace(0, upper, 200)
    axis.plot(grid, 3 * grid, color="#b54a49", linestyle="--", label="tracked = 3 × wrong")
    axis.axhline(0.05, color="#555555", linestyle=":", label="tracked = 0.05")
    axis.set(
        xlim=(0, upper),
        ylim=(0, upper),
        xlabel="Wrong-pair coherence",
        ylabel="Tracked held-B coherence",
        title="Exact simultaneous pairing against the cross-group control",
    )
    axis.grid(alpha=0.2)
    axis.legend()
    figure.colorbar(points, ax=axis, label="Residual phase R")
    figure.savefig(output, dpi=190)
    plt.close(figure)


def plot_historical_comparison(rows: list[dict[str, Any]], output: Path) -> None:
    current = _finite([row for row in rows if row["state"] == "replayed"], "band_phase_resultant")
    with (PRIOR / "per-dwell.csv").open(newline="") as source:
        prior_rows = [
            row for row in csv.DictReader(source) if float(row["sample_rate_msps"]) == 2.5
        ]
    prior = np.asarray(
        [float(row["band_phase_resultant"]) for row in prior_rows if row["band_phase_resultant"]],
        dtype=float,
    )
    figure, axis = plt.subplots(figsize=(8.5, 5.5), layout="constrained")
    for position, values, color in (
        (0, prior, "#7a5195"),
        (1, current, "#2a9d8f"),
    ):
        jitter = np.linspace(-0.16, 0.16, len(values)) if len(values) else np.asarray([])
        axis.scatter(position + jitter, values, color=color, alpha=0.75, s=34)
        if len(values):
            axis.hlines(
                np.median(values), position - 0.25, position + 0.25, color="black", linewidth=2
            )
    axis.axhline(0.8, color="#333333", linestyle="--", linewidth=1)
    axis.set(
        xticks=(0, 1),
        xticklabels=(
            f"Sep 23\n{len(prior)} replayed / 8 selected",
            f"Sep 24\n{len(current)} replayed",
        ),
        ylim=(-0.02, 1.02),
        ylabel="Random-held residual phase resultant R",
        title="Descriptive random-validation comparison",
    )
    axis.grid(axis="y", alpha=0.2)
    axis.text(
        0.5,
        0.02,
        "Different captures and source mixtures; not a causal rate or hardware comparison",
        transform=axis.transAxes,
        ha="center",
        fontsize=9,
    )
    figure.savefig(output, dpi=190)
    plt.close(figure)


def main() -> None:
    document = _load(ROOT / "comparison.json.gz")
    rows = dwell_rows(document)
    summary = build_summary(document, rows)
    local_screen_summary = build_report_local_screen_summary(document)
    (ROOT / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    (ROOT / "report-local-screen-summary.json").write_text(
        json.dumps(local_screen_summary, indent=2, sort_keys=True) + "\n"
    )
    write_csv(rows, ROOT / "per-dwell.csv")
    plot_coverage(document, ROOT / "coverage-by-session.png")
    plot_resultants(rows, ROOT / "r-by-radio-channel.png")
    plot_controls(rows, ROOT / "tracked-vs-control.png")
    plot_historical_comparison(rows, ROOT / "historical-r-comparison.png")


if __name__ == "__main__":
    main()
