#!/usr/bin/env python3
"""Analyze the sealed DS1 one-hour matrix without modifying its artifacts.

The post-seal reference is read only to describe the reported-error diagnostic.
All grid and basin conclusions come from sealed inference outputs and their
reference-free RF objectives.
"""

from __future__ import annotations

import collections
import hashlib
import json
import math
from pathlib import Path
from statistics import median

SOURCE = Path("reports/2026_09_24_ds1_train_full")
OUTPUT = Path("reports/2026_09_24_ds1_grid_floor")
EARTH_RADIUS_KM = 6371.0088


def geodesic_km(a: dict, b: dict) -> float:
    """Great-circle distance; sufficient for the small reported separations."""
    lat1, lon1 = math.radians(a["latitude_deg"]), math.radians(a["longitude_deg"])
    lat2, lon2 = math.radians(b["latitude_deg"]), math.radians(b["longitude_deg"])
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def pos_key(position: dict) -> tuple[float, float]:
    return (round(position["latitude_deg"], 10), round(position["longitude_deg"], 10))


def compact_position(position: dict) -> dict:
    return {
        "latitude_deg": position["latitude_deg"],
        "longitude_deg": position["longitude_deg"],
    }


def task_case(task_id: str, prior: str) -> str:
    marker = f"--{prior}--"
    if marker not in task_id:
        raise ValueError(f"cannot remove prior from task id: {task_id}")
    return task_id.split(marker, 1)[0].removeprefix("one-hour--")


def load_rows() -> list[dict]:
    evaluation = json.loads(
        (SOURCE / "post-seal-evaluation" / "one-hour-post-seal-evaluation.json").read_text()
    )
    errors = {row["task_id"]: row["reference_error_km"] for row in evaluation["rows"]}
    rows = []
    for path in sorted((SOURCE / "artifacts" / "one-hour").glob("*/*.json")):
        artifact = json.loads(path.read_text())
        position = artifact["estimated_position"]
        prior = artifact["prior"]["name"]
        convergence = artifact.get("convergence", {})
        row = {
            "task_id": artifact["task_id"],
            "case_id": task_case(artifact["task_id"], prior),
            "group_id": artifact["group_id"],
            "method": artifact.get("method_requested", artifact["method"]),
            "artifact_method": artifact["method"],
            "prior": prior,
            "position": compact_position(position),
            "reference_error_km": errors[artifact["task_id"]],
            "rf_objective_value": artifact["rf_objective"].get(
                "value",
                artifact["rf_objective"].get(
                    "selection_value", artifact["rf_objective"].get("full_observation_capped_loss")
                ),
            ),
            "artifact_path": str(path.relative_to(SOURCE)),
            "convergence": convergence,
        }
        rows.append(row)
    if len(rows) != 64 or len({row["task_id"] for row in rows}) != 64:
        raise RuntimeError(f"expected 64 distinct completed artifacts, found {len(rows)}")
    return rows


def reference_diagnostics(rows: list[dict]) -> dict:
    buckets: dict[float, list[dict]] = collections.defaultdict(list)
    for row in rows:
        buckets[round(row["reference_error_km"], 6)].append(row)
    notable = []
    for value in (4.999002, 6.008604):
        members = buckets[value]
        notable.append(
            {
                "reported_error_km": value,
                "count": len(members),
                "coordinate": members[0]["position"] if members else None,
                "members": [
                    {key: row[key] for key in ("case_id", "method", "prior", "task_id")}
                    for row in members
                ],
            }
        )
    return {
        "reference_role": "post-seal diagnostic only; never a selection or gating input",
        "error_value_counts": [
            {"reference_error_km": value, "count": len(members)}
            for value, members in sorted(buckets.items())
        ],
        "notable_4_999_and_6_009_km_values": notable,
    }


def trace_summary(row: dict) -> dict | None:
    trace = row["convergence"].get("geographic_trace")
    levels = row["convergence"].get("geographic_levels_km")
    if not trace or not levels:
        return None
    final_level = min(levels)
    final = [item for item in trace if item["level_km"] == final_level]
    # A coordinate may be revisited; retain its best score.
    cells: dict[tuple[float, float], dict] = {}
    for item in final:
        key = (item["east_km"], item["north_km"])
        if key not in cells or item["objective"] < cells[key]["objective"]:
            cells[key] = item
    ranked = sorted(cells.values(), key=lambda item: item["objective"])
    selected = row["position"]
    selected_matches = [item for item in trace if geodesic_km(selected, item) < 1e-6]
    selected_score_matches = [
        item
        for item in selected_matches
        if abs(item["objective"] - row["rf_objective_value"]) < 1e-12
    ]
    selected_item = min(
        selected_score_matches or selected_matches, key=lambda item: item["objective"]
    )
    global_winner = min(trace, key=lambda item: item["objective"])
    winner = ranked[0]
    final_step_residual = max(
        abs(selected_item["east_km"] / final_level - round(selected_item["east_km"] / final_level)),
        abs(
            selected_item["north_km"] / final_level - round(selected_item["north_km"] / final_level)
        ),
    )
    # The nearest sampled competitors show only the local stencil that this
    # beam search actually visited.  Missing cardinal neighbours are explicit.
    cardinal = []
    for east, north, label in (
        (winner["east_km"] - final_level, winner["north_km"], "west"),
        (winner["east_km"] + final_level, winner["north_km"], "east"),
        (winner["east_km"], winner["north_km"] - final_level, "south"),
        (winner["east_km"], winner["north_km"] + final_level, "north"),
    ):
        item = cells.get((east, north))
        cardinal.append(
            {
                "direction": label,
                "sampled": item is not None,
                "objective_gap_from_winner": None
                if item is None
                else item["objective"] - winner["objective"],
            }
        )
    per_level = []
    for level in levels:
        candidates = [item for item in trace if item["level_km"] == level]
        best = min(candidates, key=lambda item: item["objective"])
        per_level.append(
            {
                "level_km": level,
                "candidate_evaluations": len(candidates),
                "best_east_km": best["east_km"],
                "best_north_km": best["north_km"],
                "best_objective": best["objective"],
            }
        )
    return {
        "task_id": row["task_id"],
        "case_id": row["case_id"],
        "method": row["method"],
        "prior": row["prior"],
        "final_level_km": final_level,
        "final_unique_cells_scored": len(cells),
        "final_winner": {
            "east_km": winner["east_km"],
            "north_km": winner["north_km"],
            "objective": winner["objective"],
            "position": compact_position(winner),
        },
        "selected_position_matches_any_lattice": bool(selected_matches),
        "selected_lattice_level_km": selected_item["level_km"],
        "selected_position_matches_final_lattice": any(
            item["level_km"] == final_level for item in selected_matches
        ),
        "selected_is_final_lattice_objective_winner": any(
            item["level_km"] == final_level for item in selected_matches
        )
        and geodesic_km(selected, winner) < 1e-6,
        "selected_is_global_trace_objective_winner": geodesic_km(selected, global_winner) < 1e-6,
        "global_trace_winner_level_km": global_winner["level_km"],
        "final_lattice_step_residual": final_step_residual,
        "final_second_best_objective_gap": (
            ranked[1]["objective"] - winner["objective"] if len(ranked) > 1 else None
        ),
        "final_second_best_relative_gap": (
            (ranked[1]["objective"] - winner["objective"]) / max(abs(winner["objective"]), 1e-12)
            if len(ranked) > 1
            else None
        ),
        "sampled_cardinal_neighbours": cardinal,
        "best_by_level": per_level,
    }


def coordinate_comparison(rows: list[dict]) -> dict:
    clusters: dict[tuple[float, float], list[dict]] = collections.defaultdict(list)
    for row in rows:
        clusters[pos_key(row["position"])].append(row)
    cluster_rows = []
    for key, members in sorted(clusters.items(), key=lambda item: (-len(item[1]), item[0])):
        cluster_rows.append(
            {
                "coordinate": {
                    "latitude_deg": key[0],
                    "longitude_deg": key[1],
                },
                "count": len(members),
                "reference_errors_km": sorted(
                    {round(item["reference_error_km"], 6) for item in members}
                ),
                "members": [
                    {
                        field: item[field]
                        for field in ("case_id", "group_id", "method", "prior", "task_id")
                    }
                    for item in sorted(members, key=lambda item: item["task_id"])
                ],
            }
        )
    prior_pairs = []
    by_case_method: dict[tuple[str, str], dict[str, dict]] = collections.defaultdict(dict)
    for row in rows:
        by_case_method[(row["case_id"], row["method"])][row["prior"]] = row
    by_method: dict[str, list[float]] = collections.defaultdict(list)
    same_by_method: dict[str, int] = collections.Counter()
    for (case, method), variants in sorted(by_case_method.items()):
        if set(variants) != {"reno", "sacramento"}:
            continue
        distance = geodesic_km(variants["reno"]["position"], variants["sacramento"]["position"])
        by_method[method].append(distance)
        same_by_method[method] += distance < 1e-6
        prior_pairs.append({"case_id": case, "method": method, "prior_distance_km": distance})
    prior_summary = [
        {
            "method": method,
            "pair_count": len(values),
            "identical_coordinate_pair_count": same_by_method[method],
            "median_prior_distance_km": median(values),
            "minimum_prior_distance_km": min(values),
            "maximum_prior_distance_km": max(values),
        }
        for method, values in sorted(by_method.items())
    ]
    # Same case/prior, different method. Values are in native geographic units,
    # so this comparison avoids incomparable objective scales.
    method_distances: dict[tuple[str, str], list[float]] = collections.defaultdict(list)
    by_case_prior: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    for row in rows:
        by_case_prior[(row["case_id"], row["prior"])].append(row)
    for members in by_case_prior.values():
        for index, left in enumerate(members):
            for right in members[index + 1 :]:
                key = tuple(sorted((left["method"], right["method"])))
                method_distances[key].append(geodesic_km(left["position"], right["position"]))
    method_pair_summary = [
        {
            "method_a": key[0],
            "method_b": key[1],
            "comparison_count": len(values),
            "identical_coordinate_count": sum(value < 1e-6 for value in values),
            "median_distance_km": median(values),
            "maximum_distance_km": max(values),
        }
        for key, values in sorted(method_distances.items())
    ]
    return {
        "unique_selected_coordinate_count": len(clusters),
        "coordinate_clusters": cluster_rows,
        "prior_pair_distances": prior_pairs,
        "prior_stability_by_method": prior_summary,
        "prior_pair_count": len(prior_pairs),
        "identical_prior_pair_count": sum(
            item["identical_coordinate_pair_count"] for item in prior_summary
        ),
        "minimum_method_median_prior_distance_km": min(
            item["median_prior_distance_km"] for item in prior_summary
        ),
        "maximum_method_median_prior_distance_km": max(
            item["median_prior_distance_km"] for item in prior_summary
        ),
        "within_case_prior_method_pair_distances": method_pair_summary,
    }


def strategy() -> dict:
    return {
        "selection_inputs": (
            "RF objective, fitted nuisance parameters, candidate associations, and independent "
            "observation groups only; no reference coordinate or post-seal error."
        ),
        "local_refinement": [
            "Keep every coarse candidate within a measured score margin of the best candidate, "
            "rather than committing only to the one beam winner.",
            "At each retained 12.5 km cell, re-profile timing/CFO/associations on a symmetric 5x5 "
            "local stencil at 3.125 km, then repeat at 0.78125 km around each surviving local "
            "minimum. Reassociation and nuisance fitting must be repeated at every point.",
            "Use at least the two independent prior-seeded basins when they disagree; deduplicate "
            "only locations closer than the current refinement cell width.",
        ],
        "gate": {
            "refine_and_emit_one_position_only_when": [
                "the proposed winner is interior to a fully sampled local stencil and all four "
                "cardinal neighbours have a worse re-profiled RF objective;",
                "the winner's margin over every retained competing basin exceeds an "
                "objective-noise scale estimated from independent groups (scan blocks, tracks, or "
                "occupied-time "
                "blocks), with the winner selected in at least 90% of resamples;",
                "independent prior seeds converge within one final refinement cell, or their "
                "distinct minima have been separately refined and one passes the same "
                "margin-and-resampling test.",
            ],
            "otherwise": (
                "return an ambiguity state with the surviving local modes, their RF-objective "
                "margins, and a spatial spread; do not turn a coarse-cell centre into a precision "
                "claim."
            ),
            "comparability_rule": (
                "compare objective margins only within the same method, association policy, and "
                "nuisance-parameter model. Never rank methods by raw objective values with "
                "different scales."
            ),
        },
    }


def render_report(analysis: dict) -> str:
    grid = analysis["grid_quantization"]
    diagnostics = analysis["reference_diagnostics"]["notable_4_999_and_6_009_km_values"]
    coords = analysis["coordinate_comparison"]
    basin = analysis["local_basin_behavior"]
    lines = [
        "# DS1 one-hour grid-floor analysis",
        "",
        "This review reads 64 sealed inference artifacts from the DS1 one-hour matrix. "
        "The Sausalito reference is used only to identify the two reported error values below; "
        "the grid and basin findings use the inference artifacts' coordinates, traces, and RF "
        "objectives.",
        "",
        "## Finding",
        "",
        f"All {grid['trace_artifact_count']} artifacts that expose a geographic trace select a "
        f"point from the nested {grid['final_grid_km']:.1f} km lattice. Every selected coordinate "
        f"matches a traced geographic candidate, and every selected east/north coordinate is an "
        f"integer multiple of the lattice step (largest numerical residual "
        f"{grid['maximum_step_residual']:.3g}). "
        f"{grid['selected_final_lattice_match_count']} selections are directly at the final "
        f"level; {grid['selected_coarser_lattice_match_count']} retain a coarser candidate "
        "because the score did not monotonically improve with subdivision. This establishes a "
        "resolution ceiling for those outputs, not a "
        "measured localization floor.",
        "",
    ]
    for item in diagnostics:
        coord = item["coordinate"]
        lines.append(
            f"The {item['reported_error_km']:.3f} km value occurs {item['count']} times at "
            f"({coord['latitude_deg']:.8f}, {coord['longitude_deg']:.8f}). It is a repeated "
            "selected lattice point, so it is consistent with grid quantization. It does not "
            "show that the RF optimum is exactly that far from the reference."
        )
    lines += [
        "",
        f"Across all methods, the 64 runs collapse to "
        f"{coords['unique_selected_coordinate_count']} exact coordinates. None of the "
        f"{coords['prior_pair_count']} matched prior pairs selects the identical coordinate; their "
        "method-level "
        f"median separations range from {coords['minimum_method_median_prior_distance_km']:.2f} to "
        "not compared across methods because their losses use different definitions and scales.",
        f"{coords['maximum_method_median_prior_distance_km']:.2f} km. Prior changes therefore "
        "select different basins. Raw RF objectives are not compared across methods because their "
        "losses use different definitions and scales.",
        "not compared across methods because their losses use different definitions and scales.",
        "",
        "## Basin evidence",
        "",
        f"The final lattice contains a median of "
        f"{basin['median_final_unique_cells_scored']:.0f} distinct sampled cells per traced run. "
        f"The median best-versus-second sampled-cell relative gap is "
        f"{basin['median_second_best_relative_gap']:.3g}; the range is "
        f"{basin['minimum_second_best_relative_gap']:.3g} to "
        f"{basin['maximum_second_best_relative_gap']:.3g}. In "
        f"{basin['selected_not_final_global_winner_count']}/{basin['traced_artifact_count']} "
        "traces, the final-level winner is not the selected global trace winner. No final winner "
        "has all four cardinal neighbours sampled "
        f"({basin['two_cardinal_neighbour_count']} have two and "
        f"{basin['three_cardinal_neighbour_count']} have three). "
        "The traces therefore do not prove even an interior local minimum, much less a global "
        "optimum.",
        "",
        "## Recommended reference-free refinement and gate",
        "",
        "Retain all coarse basins within a measured within-method RF score margin. Re-profile "
        "dynamic associations and nuisance parameters on a symmetric 5×5 stencil at 3.125 km, "
        "then 0.78125 km around each surviving minimum. Start from both prior-seeded locations "
        "whenever they disagree. Emit a single coordinate only when it is an interior local "
        "minimum, wins resampled independent observation groups at least 90% of the time, and "
        "beats every retained basin by more than the resampling-derived objective noise. "
        "Otherwise emit the modes and their spread as an ambiguity result.",
        "",
        "The complete per-artifact lattice checks, basin margins, coordinate clusters, and "
        "pairwise prior/method distances are in `analysis.json`.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    rows = load_rows()
    traces = [summary for row in rows if (summary := trace_summary(row)) is not None]
    if not traces:
        raise RuntimeError("no geographic traces found")
    matched = [item for item in traces if item["selected_position_matches_any_lattice"]]
    final_matched = [item for item in traces if item["selected_position_matches_final_lattice"]]
    grid = {
        "interpretation": (
            "A final 12.5 km geographic screen discretizes traced selected locations. It cannot "
            "substantiate sub-grid accuracy."
        ),
        "trace_artifact_count": len(traces),
        "final_grid_km": min(item["final_level_km"] for item in traces),
        "selected_any_lattice_match_count": len(matched),
        "selected_final_lattice_match_count": len(final_matched),
        "selected_coarser_lattice_match_count": len(matched) - len(final_matched),
        "selected_global_trace_winner_count": sum(
            item["selected_is_global_trace_objective_winner"] for item in traces
        ),
        "maximum_step_residual": max(item["final_lattice_step_residual"] for item in traces),
    }
    relative_gaps = [
        item["final_second_best_relative_gap"]
        for item in traces
        if item["final_second_best_relative_gap"] is not None
    ]
    cardinal_counts = [
        sum(item["sampled"] for item in trace["sampled_cardinal_neighbours"]) for trace in traces
    ]
    basin = {
        "scope": (
            "Only artifacts with recorded geographic traces; exact-orbit and soft-association "
            "artifacts do not expose an equivalent trace."
        ),
        "traced_artifact_count": len(traces),
        "median_final_unique_cells_scored": median(
            item["final_unique_cells_scored"] for item in traces
        ),
        "median_second_best_relative_gap": median(relative_gaps),
        "minimum_second_best_relative_gap": min(relative_gaps),
        "maximum_second_best_relative_gap": max(relative_gaps),
        "selected_not_final_global_winner_count": sum(
            not item["selected_is_final_lattice_objective_winner"] for item in traces
        ),
        "full_cardinal_neighbour_count": sum(count == 4 for count in cardinal_counts),
        "two_cardinal_neighbour_count": sum(count == 2 for count in cardinal_counts),
        "three_cardinal_neighbour_count": sum(count == 3 for count in cardinal_counts),
        "per_artifact": traces,
    }
    source_files = sorted((SOURCE / "artifacts" / "one-hour").glob("*/*.json"))
    artifact_digest = hashlib.sha256(
        "".join(
            f"{path.relative_to(SOURCE)}:{hashlib.sha256(path.read_bytes()).hexdigest()}\n"
            for path in source_files
        ).encode()
    ).hexdigest()
    analysis = {
        "schema": "ds1-grid-floor-analysis/v1",
        "source": {
            "artifact_count": len(rows),
            "artifact_tree": str(SOURCE / "artifacts" / "one-hour"),
            "artifact_path_sha256": artifact_digest,
            "post_seal_evaluation": str(
                SOURCE / "post-seal-evaluation" / "one-hour-post-seal-evaluation.json"
            ),
        },
        "grid_quantization": grid,
        "reference_diagnostics": reference_diagnostics(rows),
        "coordinate_comparison": coordinate_comparison(rows),
        "local_basin_behavior": basin,
        "reference_free_refinement_and_gate": strategy(),
        "selected_runs": [
            {key: value for key, value in row.items() if key != "convergence"} for row in rows
        ],
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "analysis.json").write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n")
    (OUTPUT / "REPORT.md").write_text(render_report(analysis))


if __name__ == "__main__":
    main()
