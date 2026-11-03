"""Continue the common blind geographic grid to sub-kilometer mesh scales."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, OUTPUT, Scan

from leo.analysis.research.phase_linear_geometry import phase_linear_frequency


def shape_proposals(scan, directory):
    """Curved-only regional proposals with offsets removed; never final labels."""
    grid = []
    for east in np.arange(-250.0, 250.001, 50.0):
        for north in np.arange(-250.0, 250.001, 50.0):
            if east**2 + north**2 > 250**2:
                continue
            point = np.array([east, north])
            f, e, h = phase_linear_frequency(scan.geometry, *scan.latlon(point))
            score = 0.0
            for i in scan.curved:
                t, ix = scan.tracks[i], scan.index[i]
                q = t["rf_hz"] / 11.5e9
                r = t["values"] - q * f[:, ix]
                r -= r.mean(axis=1)[:, None]
                derivative = q * h[:, ix]
                derivative -= derivative.mean(axis=1)[:, None]
                information = np.sum(derivative**2, axis=1)
                phase = np.clip(
                    np.sum(r * derivative, axis=1) / (information + 150**2 / scan.sigma**2), -15, 15
                )
                residual = r - derivative * phase[:, None]
                cost = np.mean(residual**2, axis=1) + 150**2 * (phase / scan.sigma) ** 2 / len(
                    t["times"]
                )
                cost[e[:, ix].min(axis=1) < -2] = np.inf
                score += min(len(t["times"]), 50) * min(float(np.min(cost)), 900**2)
            grid.append(dict(east_north_km=point.tolist(), score=score))
    chosen = []
    for row in sorted(grid, key=lambda r: r["score"]):
        if all(np.linalg.norm(np.array(row["east_north_km"]) - old) >= 50 for old in chosen):
            chosen.append(np.array(row["east_north_km"]))
        if len(chosen) == 4:
            break
    write(
        directory / "shape_discovery.json",
        dict(
            grid=grid,
            selected=chosen,
            calibration_population="raw-curved fragments only",
            same_proposals_for_all_models_and_c_arms=True,
            free_curve_constants_and_individual_phases_are_proposals_only=True,
            labels_and_nuisance_values_never_imported_into_final_fits=True,
            reference_position_used=False,
        ),
    )
    return chosen


def run(case):
    started = time.monotonic()
    directory = OUTPUT / case
    parent = json.loads((directory / "protocol.json").read_text())
    assert parent["inherited_hardware_or_position_seeds_used"] is False
    scan = Scan(case)
    progress = json.loads((directory / "progress.json").read_text())
    scores = {tuple(r["east_north_km"]): r["scores"] for r in progress}
    new = []
    limit = 128
    protocol = dict(
        case=case,
        additional_location_budget=limit,
        parent_protocol_sha256=hashlib.sha256(
            (directory / "protocol.json").read_bytes()
        ).hexdigest(),
        scales_km=[25.0, 12.5, 6.25, 3.125, 1.5625, 0.78125, 0.390625, 0.1953125],
        directions="eight axial/diagonal neighbors of up to two model-disagreement basins",
        same_locations_for_all_methods_and_c_arms=True,
        geographic_proposals_rank_c0_only=True,
        known_reference_used=False,
        inherited_hardware_initializer_used=False,
        curved_only_updates=True,
        coordinate_region=parent["regional_center"],
        radius_km=250,
        nuisance_rounds_per_location=2,
        finalizer_rounds=3,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    )
    write(directory / "refinement_protocol.json", protocol)

    def evaluate(point):
        point = np.asarray(point, float)
        key = tuple(np.round(point, 8))
        if np.linalg.norm(point) > 250 or key in scores or len(new) >= limit:
            return
        mark = time.monotonic()
        result = scan.at_point(point)
        scores[key] = {k: r["score"] for k, r in result.items()}
        new.append(
            dict(east_north_km=list(key), scores=scores[key], seconds=time.monotonic() - mark)
        )
        write(directory / "refinement_progress.json", new)
        print(
            json.dumps(
                dict(case=case, refined=len(new), point=list(key), seconds=new[-1]["seconds"])
            ),
            flush=True,
        )

    # Regional shape discovery supplies fresh geographic proposals without
    # importing any historical position, hardware offset or satellite label.
    for point in shape_proposals(scan, directory):
        evaluate(point)

    directions = [(a, b) for a in (-1, 0, 1) for b in (-1, 0, 1) if a or b]
    for scale in protocol["scales_km"]:
        winners = []
        for method in METHODS:
            point = min(scores, key=lambda p: scores[p][f"c0/{method}"])
            if point not in winners:
                winners.append(point)
        centers = [winners[0]]
        if len(winners) > 1:
            centers.append(max(winners[1:], key=lambda p: np.linalg.norm(np.array(p) - centers[0])))
        for center in centers:
            for direction in directions:
                evaluate(np.array(center) + scale * np.array(direction))
    points = {k: min(scores, key=lambda p: scores[p][k]) for k in scores[next(iter(scores))]}
    complete = {}
    for point in set(points.values()):
        complete[point] = scan.at_point(point, rounds=3, all_tracks=True)
    endpoints = {k: complete[p][k] for k, p in points.items()}
    write(directory / "refined_endpoints.json", endpoints)
    write(
        directory / "refinement_summary.json",
        dict(
            case=case,
            initial_locations=len(progress),
            additional_locations=len(new),
            total_locations=len(scores),
            elapsed_seconds=time.monotonic() - started,
            known_gps_used=False,
            global_optimum_proven=False,
            method_endpoint_points={k: list(p) for k, p in points.items()},
        ),
    )
    print(json.dumps(dict(case=case, refinement_complete=True, locations=len(scores))), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=[f"DSX01-S{i:02d}" for i in range(1, 6)])
    run(parser.parse_args().case)
