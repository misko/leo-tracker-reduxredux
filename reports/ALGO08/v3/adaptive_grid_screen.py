"""Use only sampled scores to schedule refinement of a conditional position grid."""

import argparse
import gzip
import json
from pathlib import Path

import numpy as np
from scipy.spatial import Delaunay

from leo.analysis.position_grid import ARMS, sample_position_grid
from leo.contracts.digests import canonical_digest
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore


HERE = Path(__file__).resolve().parent
DATA = HERE / "measurements"


def coordinates(point):
    return point["east_km"], point["north_km"]


def choose_nodes(points, initial, scores):
    """scores contains only the first-pass rows, in initial order."""
    mesh = Delaunay(initial)
    values = np.asarray(scores, dtype=float)
    if values.shape != (len(initial), 2):
        raise ValueError("Expected one measured score for each calibration arm")
    finite = np.isfinite(values)
    lowest = np.min(np.where(finite, values, np.inf), axis=0)
    interesting = np.any(~finite | (values <= lowest + 4.5), axis=1)
    selected = set(initial)
    transforms = mesh.transform[np.any(interesting[mesh.simplices], axis=1)]
    for point in points:
        if point in selected:
            continue
        if mesh.find_simplex(point, tol=1e-12) < 0:
            selected.add(point)
            continue
        if len(transforms):
            weights = np.einsum("ijk,ik->ij", transforms[:, :2], np.asarray(point)-transforms[:, 2])
            if np.any((weights.min(axis=1) >= -1e-12) & (weights.sum(axis=1) <= 1+1e-12)):
                selected.add(point)
    return selected


def checked_grid(root, reference):
    store = FastStandardAnalysisStore(root)
    receipt = reference["receipt"]
    run_id = receipt["run_id"]
    grid = store.position_grid(run_id)
    terminal = json.loads((root/"fast-scan-automatic-work"/run_id/"terminal.json").read_bytes())
    evidence = reference["evidence"]
    if (canonical_digest(terminal) != receipt["terminal_sha256"] or grid["binding"]["terminal_sha256"] != receipt["terminal_sha256"]
            or canonical_digest(store.position_path(run_id)) != evidence["path"] or canonical_digest(grid) != evidence["grid"]
            or not grid["complete"] or (grid["coarse_size"], grid["local_size"]) != (9, 7)):
        raise ValueError("Original complete conditional grid or terminal binding changed")
    return grid


def screen(grid):
    indexed = {coordinates(row): row["scores"] for row in grid["points"]}
    def lookup(arm, point):
        val = indexed[point][arm]
        return np.nan if val is None else val

    initial_grid = sample_position_grid(lookup, grid["endpoints"], coarse_size=5, local_size=4,
                                        box_width_km=grid["box_width_km"], local_half_width_km=grid["local_half_width_km"])
    if not initial_grid["complete"]:
        raise ValueError("First-pass grid did not complete")
    initial = [coordinates(row) for row in initial_grid["points"]]
    pts = list(indexed)
    initial_scores = [[lookup(arm, point) for arm in ARMS] for point in initial]
    selected = choose_nodes(pts, initial, initial_scores)
    kept = [pt for pt in pts if pt in selected]
    omitted = [pt for pt in pts if pt not in selected]
    mesh = Delaunay(kept)
    results = {}
    for arm in ARMS:
        values = np.array([lookup(arm, pt) for pt in kept])
        minimum = min((v[arm] for v in indexed.values() if v[arm] is not None), default=np.inf)
        lost_failures = sum(indexed[p][arm] is None for p in omitted)
        held = [p for p in omitted if indexed[p][arm] is not None]
        missed_minima = sum(indexed[p][arm] == minimum for p in held)
        lost_low = sum(indexed[p][arm] <= minimum + 4.5 for p in held)
        errors = []
        for pt in held:
            simplex = mesh.find_simplex(pt, tol=1e-12)
            if simplex < 0:
                continue
            tr = mesh.transform[simplex]
            weights = tr[:2] @ (np.asarray(pt) - tr[2])
            prediction = np.r_[weights, 1-weights.sum()] @ values[mesh.simplices[simplex]]
            if np.isfinite(prediction):
                errors.append(abs(float(prediction) - indexed[pt][arm]))
        results[arm] = dict(missed_minima=missed_minima, missed_low_nodes=lost_low, missed_failed_nodes=lost_failures,
                            predictions=len(errors), omitted_median_abs_loss_difference=float(np.median(errors)) if errors else None,
                            max_abs_loss_difference=max(errors, default=None))
    quality = all(all(row[key] == 0 for key in ("missed_minima", "missed_low_nodes", "missed_failed_nodes"))
                  for row in results.values())
    return dict(original=len(pts), initial=len(initial), selected=len(kept), omitted=len(omitted),
                passed=bool(quality and 4*len(omitted)>=len(pts)), fidelity=quality, arms=results,
                selected_xy=kept, grid_sha256=canonical_digest(grid))


def sources():
    dense = json.loads(gzip.decompress((DATA/"dense-full-short-raw.json.gz").read_bytes()))["candidate"]["result"]
    weak = json.loads(gzip.decompress((DATA/"full-short-DS30-0016-raw.json.gz").read_bytes()))["runs"]["candidate"]["publication"]
    south = json.loads((DATA/"full-short-south.json").read_bytes())["cases"]
    cases = {"DS30-0008": ("/var/tmp/leo-full-short-dense-DS30-0008/publication", dense),
             "DS30-0016": ("/var/tmp/leo-full-short-DS30-0016-pair/candidate", weak)}
    for name in ("containing", "near"):
        cases["south-"+name] = ("/var/tmp/leo-full-short-south-transfer-final/"+name, south[name])
    return cases


def run():
    return {case: screen(checked_grid(Path(root), original)) for case, (root, original) in sources().items()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = run()
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
