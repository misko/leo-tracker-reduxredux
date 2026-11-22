"""Reopen one verified DS30 pair for a per-recording report during staged testing."""

import argparse
import json
from pathlib import Path

from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

from . import ds30_stage as stage
from . import selected_changes
from .compare_publications import compare


def compare_grid_samples(before, after):
    """Compare scores only where the published coordinate sequence matches."""
    grids = (before, after)
    keys = set(before) | set(after)
    result = dict(points=[len(grid["points"]) for grid in grids],
                  metadata_changed=sorted(k for k in keys - {"binding", "elapsed_seconds", "points"}
                                          if before.get(k) != after.get(k)))
    positions = [[(point["east_km"], point["north_km"], point["latlon"]) for point in grid["points"]]
                 for grid in grids]
    result["same_positions_in_order"] = positions[0] == positions[1]
    if result["same_positions_in_order"]:
        points = list(zip(before["points"], after["points"], strict=True))
        result["failure_maps_changed"] = sum(p.get("failures") != q.get("failures") for p, q in points)
        result["arms"] = {}
        for arm in stage.ARMS:
            values = [(p["scores"][arm], q["scores"][arm]) for p, q in points]
            deltas = [abs(a - b) for a, b in values if a is not None and b is not None]
            result["arms"][arm] = dict(scored_by_both=len(deltas),
                                       validity_changed=sum((a is None) != (b is None) for a, b in values),
                                       scores_changed=sum(delta != 0 for delta in deltas),
                                       max_abs_delta=max(deltas, default=None))
    return result


def audit_pair(inventory, path):
    case = path.parent.name
    rows = [row for row in inventory["cases"] if row["case"] == case]
    if len(rows) != 1 or rows[0]["state"] != "verified":
        raise ValueError("Pair must belong to a verified recording in the stage inventory")
    row = rows[0]
    spec = inventory["candidate_specification_digest"]
    receipt = stage.read(path)
    if stage.file_sha(path) != row["pair_sha256"] or receipt["candidate_specification_digest"] != spec:
        raise ValueError("Pair receipt or candidate differs from the stage inventory")
    measured = compare(path, stage_clocks=True)
    if row["raw_authority"] != measured["raw_authority"] or (
        "region" in row and row["region"] != measured["region"]
    ):
        raise ValueError("Recording or region differs from the reopened publication")
    truth = stage.pinned(stage.OUT / "reference-audit.json", stage.REFERENCE_SHA256)["cases"]
    refs = {r["dataset_label"]: (r["reference"]["latitude_deg"], r["reference"]["longitude_deg"])
            for r in truth if r["authority_eligible"]}
    # Compute position and timing from the reopened publications.
    verified = dict(row, region=measured["region"], arms={name: measured[name]["arms"] for name in stage.BUILDS},
                    elapsed_s={name: measured[name]["elapsed_s"] for name in stage.BUILDS})
    selected = selected_changes.compare(path, summary=True)
    grid_comparison = None
    if all(measured[name]["decision"] == "complete" for name in stage.BUILDS):
        grids = []
        for name in stage.BUILDS:
            run = receipt["runs"][name]["receipt"]["run_id"]
            grid = FastStandardAnalysisStore(path.parent / name).position_grid(run)
            scientific = {k: v for k, v in grid.items() if k not in ("binding", "elapsed_seconds")}
            if stage.canonical_digest(scientific) != measured[name]["scientific_digests"]["grid"]:
                raise ValueError("Grid changed during the paired comparison")
            grids.append(grid)
        grid_comparison = compare_grid_samples(*grids)
    if stage.file_sha(path) != row["pair_sha256"]:
        raise ValueError("Pair receipt changed during audit")
    return dict(measured, case=case, candidate_specification_digest=spec, pair_sha256=row["pair_sha256"],
                selected_fields=selected, grid_comparison=grid_comparison,
                verified_subset_quality=stage.local_quality([verified], refs))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("pair", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit_pair(stage.read(args.inventory), args.pair), indent=2, allow_nan=False))
