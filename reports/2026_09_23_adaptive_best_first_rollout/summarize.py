"""Reproduce descriptive rollout summaries from public immutable publications.

Run with the qualified release Python, --bulk-root, --inventory, and --output.
Reference errors are post-selection diagnostics, never selection inputs.
"""

import argparse
import csv
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure

from leo.storage.adaptive_tle_position import AdaptiveTlePositionStore, AdaptiveTlePositionStoreV2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", choices=("v1", "v2"), default="v2")
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text())
    store_type = AdaptiveTlePositionStoreV2 if args.version == "v2" else AdaptiveTlePositionStore
    store = store_type(args.bulk_root)
    rows, counts, reasons = [], Counter(), Counter()
    for sid, epoch in zip(
        inventory["session_ids_newest_first"],
        inventory["window_publication_utc_ns_newest_first"],
        strict=True,
    ):
        status = store.status(sid)
        if status.manifest is None:
            raise ValueError(f"Frozen session still pending: {sid}")
        doc = status.manifest.document
        counts[doc.state] += 1
        reasons.update(doc.reasons)
        for prior in doc.priors:
            if prior.selected is None:
                reasons[f"{prior.name}:no-selected-candidate"] += 1
                continue
            if prior.selected.horizontal_error_m is None:
                raise ValueError(f"Reference evaluation missing: {sid}/{prior.name}")
            rows.append(
                dict(
                    session_id=sid,
                    publication_utc=datetime.fromtimestamp(epoch / 1e9, UTC).isoformat(),
                    prior=prior.name,
                    prior_radius_km=prior.region.radius_km,
                    tracks=prior.accounting.eligible_track_count,
                    observations=prior.accounting.eligible_observation_count,
                    evaluated_positions=prior.accounting.evaluated_point_count,
                    selected_latitude_deg=prior.selected.latitude_deg,
                    selected_longitude_deg=prior.selected.longitude_deg,
                    selected_spacing_km=prior.selected.spacing_km,
                    selected_rmse_hz=prior.selected.capped_weighted_rmse_hz,
                    selected_uncapped_rmse_hz=prior.selected.uncapped_weighted_rmse_hz,
                    selected_matched_track_count=prior.selected.matched_track_count,
                    selected_unmatched_track_count=prior.selected.unmatched_track_count,
                    finest_rmse_hz=(prior.finest.capped_weighted_rmse_hz if prior.finest else None),
                    finest_evaluated_positions=prior.accounting.finest_evaluated_point_count,
                    deferred_cells=prior.accounting.deferred_cell_count,
                    selected_reference_error_km=prior.selected.horizontal_error_m / 1000,
                    finest_reference_error_km=(
                        prior.finest.horizontal_error_m / 1000
                        if prior.finest and prior.finest.horizontal_error_m is not None
                        else None
                    ),
                    runtime_ms=prior.accounting.runtime_ms,
                    search_complete=prior.search_complete,
                )
            )
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "positions.csv").open("w") as output:
        writer = csv.DictWriter(
            output, fieldnames=list(rows[0]) if rows else ["session_id", "prior"]
        )
        writer.writeheader()
        writer.writerows(rows)
    summary = dict(
        analysis_version=args.version,
        frozen_session_count=len(inventory["session_ids_newest_first"]),
        scientific_states=dict(counts),
        reasons=dict(reasons),
        reference_used_for_inference=False,
        evaluation_score_used_for_selection=True,
        note=(
            "Descriptive errors against supplied reference; not calibrated accuracy or uncertainty."
        ),
        priors={},
    )
    paired = {}
    for row in rows:
        paired.setdefault(row["session_id"], {})[row["prior"]] = row
    pairs = [pair for pair in paired.values() if set(pair) == {"sacramento", "reno"}]
    summary["paired_comparison"] = dict(
        count=len(pairs),
        sacramento_lower_score_count=sum(
            pair["sacramento"]["selected_rmse_hz"] < pair["reno"]["selected_rmse_hz"]
            for pair in pairs
        ),
        sacramento_lower_error_count=sum(
            pair["sacramento"]["selected_reference_error_km"]
            < pair["reno"]["selected_reference_error_km"]
            for pair in pairs
        ),
        lower_score_has_higher_error_count=sum(
            (pair["sacramento"]["selected_rmse_hz"] - pair["reno"]["selected_rmse_hz"])
            * (
                pair["sacramento"]["selected_reference_error_km"]
                - pair["reno"]["selected_reference_error_km"]
            )
            < 0
            for pair in pairs
        ),
        caveat=(
            "Different centres, grid phases and search radii; not an isolated radius experiment."
        ),
    )
    figure = Figure(figsize=(13, 9), layout="constrained")
    axes = figure.subplots(2, 2)
    for column, name in enumerate(("sacramento", "reno")):
        subset = [row for row in rows if row["prior"] == name]
        if not subset:
            summary["priors"][name] = dict(diagnostic_count=0)
            for axis in axes[:, column]:
                axis.text(
                    0.5,
                    0.5,
                    "No selected positions",
                    ha="center",
                    va="center",
                    transform=axis.transAxes,
                )
                axis.set(title=name.title())
            continue
        error = np.asarray([row["selected_reference_error_km"] for row in subset])
        score = [row["selected_rmse_hz"] for row in subset]
        dates = [datetime.fromisoformat(row["publication_utc"]) for row in subset]
        summary["priors"][name] = dict(
            radius_km=subset[0]["prior_radius_km"],
            diagnostic_count=len(subset),
            selected_error_km_quantiles=dict(
                zip(
                    ("minimum", "p25", "median", "p75", "maximum"),
                    np.quantile(error, (0, 0.25, 0.5, 0.75, 1)).tolist(),
                    strict=True,
                )
            ),
            below_1km_count=int(np.sum(error < 1)),
            below_10km_count=int(np.sum(error < 10)),
            below_50km_count=int(np.sum(error < 50)),
            selected_score_hz_median=float(np.median(score)),
        )
        axes[0, column].scatter(dates, error, s=13)
        axes[0, column].set(
            title=name.title(),
            ylabel="Selected position error to reference (km)",
            xlabel="Capture publication time (UTC)",
            yscale="log",
        )
        axes[0, column].tick_params(axis="x", labelrotation=25)
        axes[1, column].scatter(score, error, s=13)
        axes[1, column].set(
            xlabel="Capped duration-weighted selection RMSE (Hz)",
            ylabel="Selected position error to reference (km)",
            yscale="log",
        )
        for axis in axes[:, column]:
            axis.grid(alpha=0.2)
    figure.suptitle(
        "Frozen 24-hour adaptive position backfill · post-selection reference comparison\n"
        f"All eligible tracks; {args.version} declared priors · bounded search, not a position fix"
    )
    figure.savefig(args.output / "position-summary.png", dpi=150)
    (args.output / "position-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
