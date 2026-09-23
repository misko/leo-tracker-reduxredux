#!/usr/bin/env python3
"""Verify and render the three-region randomized TLE coverage maps."""

import csv
import gzip
import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm

HERE = Path(__file__).resolve().parent
CITIES = ("sacramento", "reno", "denver")


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def uncompressed_digest(path):
    with gzip.open(path, "rb") as stream:
        return "sha256:" + hashlib.sha256(stream.read()).hexdigest()


def read(path):
    if path.suffix == ".gz":
        with gzip.open(path, "rt") as stream:
            return json.load(stream)
    return json.loads(path.read_text())


def candidates(path):
    with gzip.open(path, "rt") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def distance_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    value = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(value))


def verify_city(city):
    directory = HERE / "inputs" / city
    result_path, map_path = directory / "result.json.gz", directory / "map.npz"
    candidate_path = directory / "candidates.jsonl.gz"
    result = read(result_path)
    assert result["schema"] == "randomized-tle-coverage-map/v1"
    assert result["complete"] is True and result["truth_accessed"] is False
    assert result["session_id"] == "scan-fw-cf510316ae7f05d5"
    assert result["eligible_track_count"] == 21 and len(result["track_inventory"]) == 10
    assert result["threshold_hz_strict_less_than"] == 800
    assert result["observer_dependent_partition"] is True
    assert result["observer_label"] == "randomized-coverage-grid-v1"
    assert result["evaluation_used_for_cell_selection"] is True
    assert result["source_digest"] == digest(HERE / "source" / "map_randomized_tle_coverage.py")
    assert result["candidate_inventory_digest"] == digest(candidate_path)
    assert result["candidate_inventory_file"] == "candidates.jsonl.gz"
    with np.load(map_path) as grid:
        arrays = {
            name: np.asarray(grid[name])
            for name in (
                "east_km",
                "north_km",
                "latitude_deg",
                "longitude_deg",
                "count",
                "tie_score",
            )
        }
    cells = result["cells"]
    assert cells and all(len(value) == len(cells) for value in arrays.values())
    for index, cell in enumerate(cells):
        assert cell["index"] == index
        assert arrays["east_km"][index] == cell["east_km"]
        assert arrays["north_km"][index] == cell["north_km"]
        assert arrays["latitude_deg"][index] == cell["latitude_deg"]
        assert arrays["longitude_deg"][index] == cell["longitude_deg"]
        assert int(arrays["count"][index]) == cell["qualifying_track_count"]
        assert arrays["tie_score"][index] == cell["clipped_best_rms_sum_hz"]
        assert 0 <= cell["qualifying_track_count"] <= 10
        assert len(cell["tracks"]) == cell["qualifying_track_count"]
    order = sorted(
        range(len(cells)),
        key=lambda i: (
            -cells[i]["qualifying_track_count"],
            cells[i]["clipped_best_rms_sum_hz"],
            cells[i]["east_km"],
            cells[i]["north_km"],
        ),
    )
    assert [cell["index"] for cell in result["top_five_cells"]] == order[:5]
    assert result["maximum_count_tie_cells"] == sum(
        cell["qualifying_track_count"] == cells[order[0]]["qualifying_track_count"]
        for cell in cells
    )
    rows = candidates(candidate_path)
    by_cell_track = {}
    for row in rows:
        assert row["heldout_rms_hz"] < result["threshold_hz_strict_less_than"]
        key = (row["cell_index"], row["track_rank"])
        by_cell_track.setdefault(key, []).append(row)
    for values in by_cell_track.values():
        values.sort(
            key=lambda row: (
                row["heldout_rms_hz"],
                row["training_rms_hz"],
                row["norad"],
                row["tau_s"],
            )
        )
    ranked = []
    for rank, index in enumerate(order[:15], 1):
        cell = cells[index]
        tracks = []
        for track in sorted(cell["tracks"], key=lambda row: row["track_rank"]):
            best = by_cell_track[(index, track["track_rank"])][0]
            assert best["tracklet_id"] == track["tracklet_id"]
            assert best["heldout_rms_hz"] == track["best_heldout_rms_hz"]
            tracks.append(
                {
                    "track_rank": track["track_rank"],
                    "tracklet_id": track["tracklet_id"],
                    "minimum_heldout_rms_hz": best["heldout_rms_hz"],
                    "candidate_id_norad": best["norad"],
                    "tau_s": best["tau_s"],
                }
            )
        ranked.append(
            {
                "rank": rank,
                "cell_index": index,
                "east_km": cell["east_km"],
                "north_km": cell["north_km"],
                "latitude_deg": cell["latitude_deg"],
                "longitude_deg": cell["longitude_deg"],
                "qualifying_track_count": cell["qualifying_track_count"],
                "clipped_best_rms_sum_hz": cell["clipped_best_rms_sum_hz"],
                "candidate_ids_norad_by_track": [track["candidate_id_norad"] for track in tracks],
                "tracks": tracks,
            }
        )
    observations = {row["rank"]: row["observation_count"] for row in result["track_inventory"]}
    sensitivity = []
    for threshold in (800, 500, 300, 200, 100):
        covered = []
        track_counts = []
        clipped_sums = []
        for index in range(len(cells)):
            ranks = [
                rank
                for rank in observations
                if (index, rank) in by_cell_track
                and by_cell_track[(index, rank)][0]["heldout_rms_hz"] < threshold
            ]
            covered.append(sum(observations[rank] for rank in ranks))
            track_counts.append(len(ranks))
            clipped_sums.append(
                sum(
                    min(by_cell_track[(index, rank)][0]["heldout_rms_hz"], threshold)
                    if (index, rank) in by_cell_track
                    else threshold
                    for rank in observations
                )
            )
        maximum = max(covered)
        best_indices = [index for index, value in enumerate(covered) if value == maximum]
        representative = min(
            best_indices,
            key=lambda index: (
                clipped_sums[index],
                cells[index]["east_km"],
                cells[index]["north_km"],
            ),
        )
        sensitivity.append(
            {
                "threshold_hz_strict_less_than": threshold,
                "maximum_covered_observations": maximum,
                "total_selected_track_observations": sum(observations.values()),
                "qualifying_tracks_at_representative_cell": track_counts[representative],
                "maximum_observation_cells": len(best_indices),
                "representative_tie_policy": (
                    "minimum threshold-clipped per-track best-RMS sum, then east/north"
                ),
                "representative_clipped_best_rms_sum_hz": clipped_sums[representative],
                "representative_cell_index": representative,
                "representative_latitude_deg": cells[representative]["latitude_deg"],
                "representative_longitude_deg": cells[representative]["longitude_deg"],
            }
        )
    complete = []
    for index in range(len(cells)):
        values = [
            by_cell_track[(index, rank)][0]["heldout_rms_hz"]
            for rank in observations
            if (index, rank) in by_cell_track
        ]
        if len(values) == len(observations):
            complete.append((max(values), cells[index]["clipped_best_rms_sum_hz"], index))
    minimax_value, _, minimax_index = min(complete)
    minimax = {
        "cell_index": minimax_index,
        "latitude_deg": cells[minimax_index]["latitude_deg"],
        "longitude_deg": cells[minimax_index]["longitude_deg"],
        "maximum_track_best_heldout_rms_hz": minimax_value,
    }
    return result, arrays, ranked[:5], ranked, sensitivity, minimax


def main():
    parity = read(HERE / "inputs" / "receipts" / "coverage-standard-parity-v3.json")
    assert parity["schema"] == "randomized-tle-coverage-standard-parity/v3"
    assert parity["complete"] is True and parity["truth_accessed"] is False
    assert "sha256:" + parity["tool_source_digest"] == digest(
        HERE / "source" / "map_randomized_tle_coverage.py"
    )
    shard = read(HERE / "inputs" / "receipts" / "coverage-shard-qualification-v1.json")
    assert shard["schema"] == "randomized-tle-coverage-shard-qualification/v1"
    assert shard["complete"] is True and shard["truth_accessed"] is False
    assert all(
        shard[key] is True
        for key in (
            "candidate_row_multiset_exact",
            "cells_exact",
            "maximum_count_tie_cells_exact",
            "top_five_exact",
        )
    )
    assert shard["map_arrays_exact"] and all(shard["map_arrays_exact"].values())
    assert shard["kernel_source_digest"] == digest(
        HERE / "source" / "map_randomized_tle_coverage.py"
    )
    assert shard["wrapper_source_digest"] == digest(
        HERE / "source" / "run_sharded_randomized_tle_coverage.py"
    )
    verified = {city: verify_city(city) for city in CITIES}
    reference_path = HERE / "inputs" / "evaluation-reference.json"
    reference = read(reference_path)
    for city in CITIES:
        for cell in verified[city][2]:
            cell["postselection_evaluation_distance_km"] = distance_km(
                cell["latitude_deg"],
                cell["longitude_deg"],
                reference["latitude_deg"],
                reference["longitude_deg"],
            )
        for row in verified[city][4]:
            row["postselection_evaluation_distance_km"] = distance_km(
                row["representative_latitude_deg"],
                row["representative_longitude_deg"],
                reference["latitude_deg"],
                reference["longitude_deg"],
            )
        minimax = verified[city][5]
        minimax["postselection_evaluation_distance_km"] = distance_km(
            minimax["latitude_deg"],
            minimax["longitude_deg"],
            reference["latitude_deg"],
            reference["longitude_deg"],
        )
    summary = {
        "schema": "cf510-randomized-track-coverage-report/v1",
        "session_id": "scan-fw-cf510316ae7f05d5",
        "truth_accessed_for_scoring_or_selection": False,
        "evaluation_reference_digest": digest(reference_path),
        "evaluation_reference_used_after_selection_only": True,
        "standard_parity_receipt_digest": digest(
            HERE / "inputs" / "receipts" / "coverage-standard-parity-v3.json"
        ),
        "shard_qualification_receipt_digest": digest(
            HERE / "inputs" / "receipts" / "coverage-shard-qualification-v1.json"
        ),
        "interpretation": (
            "exploratory randomized-evaluation coverage; not calibrated identity "
            "or position confidence"
        ),
        "regions": {
            city: {
                "input_bindings": {
                    "compressed_result_digest": digest(HERE / "inputs" / city / "result.json.gz"),
                    "uncompressed_result_digest": uncompressed_digest(
                        HERE / "inputs" / city / "result.json.gz"
                    ),
                    "map_digest": digest(HERE / "inputs" / city / "map.npz"),
                    "candidate_inventory_digest": digest(
                        HERE / "inputs" / city / "candidates.jsonl.gz"
                    ),
                },
                "top_five_cells": verified[city][2],
                "threshold_sensitivity": verified[city][4],
                "minimax_all_ten_tracks": verified[city][5],
            }
            for city in CITIES
        },
    }
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    with (HERE / "top-five-cells.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "city",
                "rank",
                "qualifying_track_count",
                "latitude_deg",
                "longitude_deg",
                "clipped_best_rms_sum_hz",
                "postselection_evaluation_distance_km",
                "candidate_ids_norad_by_track",
                "minimum_heldout_rms_hz_by_track",
            ),
        )
        writer.writeheader()
        for city in CITIES:
            for cell in verified[city][2]:
                writer.writerow(
                    {
                        "city": city,
                        "rank": cell["rank"],
                        "qualifying_track_count": cell["qualifying_track_count"],
                        "latitude_deg": cell["latitude_deg"],
                        "longitude_deg": cell["longitude_deg"],
                        "clipped_best_rms_sum_hz": cell["clipped_best_rms_sum_hz"],
                        "postselection_evaluation_distance_km": cell[
                            "postselection_evaluation_distance_km"
                        ],
                        "candidate_ids_norad_by_track": json.dumps(
                            cell["candidate_ids_norad_by_track"]
                        ),
                        "minimum_heldout_rms_hz_by_track": json.dumps(
                            [track["minimum_heldout_rms_hz"] for track in cell["tracks"]]
                        ),
                    }
                )

    fig, axes = plt.subplots(1, 3, figsize=(15, 5), constrained_layout=True)
    cmap = plt.get_cmap("viridis", 11)
    norm = BoundaryNorm(np.arange(-0.5, 11.5), cmap.N)
    plotted = None
    for ax, city in zip(axes, CITIES, strict=True):
        result, grid, top, _, _, _ = verified[city]
        plotted = ax.scatter(
            grid["longitude_deg"],
            grid["latitude_deg"],
            c=grid["count"],
            cmap=cmap,
            norm=norm,
            marker="s",
            s=27,
            linewidths=0,
        )
        for row in top:
            ax.scatter(
                row["longitude_deg"],
                row["latitude_deg"],
                facecolors="none",
                edgecolors="black",
                linewidths=1.4,
                s=100,
            )
            ax.annotate(
                str(row["rank"]),
                (row["longitude_deg"], row["latitude_deg"]),
                color="black",
                ha="center",
                va="center",
                fontsize=7,
                weight="bold",
                bbox={
                    "boxstyle": "round,pad=.15",
                    "facecolor": "white",
                    "alpha": 0.85,
                    "edgecolor": "black",
                    "linewidth": 0.5,
                },
            )
        ax.scatter(
            result["center_longitude_deg"],
            result["center_latitude_deg"],
            marker="*",
            s=150,
            color="white",
            edgecolor="black",
            linewidth=0.8,
            label="Declared prior centre",
        )
        ax.set_title(
            f"{city.title()} · top {top[0]['qualifying_track_count']}/10"
            f" · {result['maximum_count_tie_cells']} cells tied"
        )
        ax.set_xlabel("Longitude (deg)")
        ax.set_ylabel("Latitude (deg)")
        ax.set_aspect("equal", adjustable="box")
        ax.legend(loc="lower left", fontsize=7, framealpha=0.9)
    colorbar = fig.colorbar(plotted, ax=axes, ticks=range(11), shrink=0.84)
    colorbar.set_label("Tracks with at least one candidate below 800 Hz held-out RMS")
    fig.savefig(HERE / "coverage-maps.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(
        3, 2, figsize=(14, 10), constrained_layout=True, gridspec_kw={"width_ratios": (1, 2.4)}
    )
    heatmap = None
    for row_index, city in enumerate(CITIES):
        _, _, top, ranked, _, _ = verified[city]
        axes[row_index, 0].bar(
            [str(row["rank"]) for row in top], [row["qualifying_track_count"] for row in top]
        )
        axes[row_index, 0].set_ylim(0, 10.5)
        axes[row_index, 0].set_ylabel(f"{city.title()}\nqualifying tracks")
        axes[row_index, 0].set_xlabel("Top-cell rank")
        matrix = np.full((10, len(ranked)), np.nan)
        for column, cell in enumerate(ranked):
            for track in cell["tracks"]:
                matrix[track["track_rank"] - 1, column] = track["minimum_heldout_rms_hz"]
        heatmap = axes[row_index, 1].imshow(
            matrix, aspect="auto", vmin=0, vmax=800, cmap="magma_r", interpolation="nearest"
        )
        axes[row_index, 1].set_yticks(range(10), labels=range(1, 11))
        axes[row_index, 1].set_xticks(range(len(ranked)), labels=range(1, len(ranked) + 1))
        axes[row_index, 1].set_ylabel("Track rank")
        axes[row_index, 1].set_xlabel("Cell rank by count, clipped-RMS tie break")
    detail_colorbar = fig.colorbar(heatmap, ax=axes[:, 1], shrink=0.85)
    detail_colorbar.set_label(
        "Best qualifying held-out RMS (Hz); blank = no candidate below 800 Hz"
    )
    fig.savefig(HERE / "top-cell-track-support.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(14, 4), constrained_layout=True)
    for ax, city in zip(axes, CITIES, strict=True):
        sensitivity = verified[city][4]
        thresholds = [row["threshold_hz_strict_less_than"] for row in sensitivity]
        observations_covered = [row["maximum_covered_observations"] for row in sensitivity]
        tied_cells = [row["maximum_observation_cells"] for row in sensitivity]
        ax.plot(thresholds, observations_covered, marker="o", label="covered observations")
        ax.set(
            title=city.title(),
            xlabel="Strict held-out RMS threshold (Hz)",
            ylabel="Maximum observations in qualifying tracks",
        )
        ax.invert_xaxis()
        twin = ax.twinx()
        twin.plot(thresholds, tied_cells, marker="s", color="#e45756", label="cells tied")
        twin.set_ylabel("Cells attaining maximum")
        lines = ax.lines + twin.lines
        ax.legend(lines, [line.get_label() for line in lines], fontsize=7, loc="best")
    fig.savefig(HERE / "threshold-sensitivity.png", dpi=180)
    plt.close(fig)

    files = {}
    for path in sorted(HERE.rglob("*")):
        if (
            path.is_file()
            and path.name != "artifact-manifest.json"
            and "__pycache__" not in path.parts
        ):
            files[str(path.relative_to(HERE))] = {
                "sha256": digest(path),
                "bytes": path.stat().st_size,
            }
    (HERE / "artifact-manifest.json").write_text(
        json.dumps({"schema": "report-artifact-manifest/v1", "files": files}, indent=2) + "\n"
    )
    print(json.dumps({"verified_regions": list(verified), "manifest_files": len(files)}, indent=2))


if __name__ == "__main__":
    main()
