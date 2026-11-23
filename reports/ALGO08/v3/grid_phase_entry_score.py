"""Verify the combined exact row and phase options on the weak saved publication."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path

from leo.contracts.digests import canonical_digest
from leo.contracts.fast_standard_analysis import PLOTS
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore


def read(path):
    return json.loads(path.read_bytes())


def check(candidate, control):
    archive = Path(__file__).with_name("measurements") / "cold-track-row-transfer.json.gz"
    historical = json.loads(gzip.decompress(archive.read_bytes()))["physical"]
    name = "joint-research-receipt.json"
    if sha256((control/name).read_bytes()).hexdigest() != historical["files_sha256"][name]:
        raise ValueError("Weak control differs from sealed single-option publication")
    baseline = historical["documents"][name]
    trial = read(candidate/name)
    identifier = trial["receipt"]["run_id"]
    products = [FastStandardAnalysisStore(root) for root in (control, candidate)]
    grids = [store.position_grid(identifier) for store in products]
    recipe = read(candidate/"full-short-recipe.json")
    phase = trial["solve"]["predictive_phase_states"]
    checks = {
        "input_and_region": all(trial["receipt"][key] == baseline["receipt"][key] for key in ("decision", "region", "run_id"))
                            and trial["saved_digest"] == baseline["saved_digest"],
        "terminal": trial["receipt"]["terminal_sha256"] == baseline["receipt"]["terminal_sha256"]
                    == canonical_digest(read(candidate/"fast-scan-automatic-work"/identifier/"terminal.json")),
        "owners_and_roles": trial["selected_rows"] == baseline["selected_rows"],
        "complete_grid": all(grid["complete"] for grid in grids)
                         and {k:v for k,v in grids[0].items() if k!="elapsed_seconds"} ==
                             {k:v for k,v in grids[1].items() if k!="elapsed_seconds"},
        "path": products[0].position_path(identifier) == products[1].position_path(identifier),
        "all_figure_bytes_and_pixels": (set(trial["evidence"]["images"]) == set(PLOTS)
                                         and trial["evidence"]["images"] == baseline["evidence"]["images"]),
        "activated": recipe.get("reuse_grid_phase_states") is True and recipe.get("reuse_cold_track_rows") is True
                     and phase["prepared_calls"] == 356 and phase["prepared_views"] == 2
                     and trial["solve"]["cold_track_rows"]["reused_requests"] > 0,
    }
    if not all(checks.values()):
        raise ValueError(f"Combined full-grid publication differs: {checks}")
    return dict(checks=checks, candidate_receipt_sha256=sha256((candidate/name).read_bytes()).hexdigest(),
                control_receipt_sha256=historical["files_sha256"][name], native_sha256=trial["saved_digest"],
                phase=phase, cold_rows=trial["solve"]["cold_track_rows"], grid_points=grids[1]["evaluated_points"],
                historical_results=historical["documents"]["cold-track-transfer-verified.json"]["scores_from_identical_endpoints"],
                solve_cpu_s=[v["solve"]["cpu_s"] for v in (baseline, trial)],
                publication_cpu_s=[v["publication_cpu_s"] for v in (baseline, trial)])


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("candidate", "control", "output"):
        cli.add_argument(name, type=Path)
    args = cli.parse_args()
    val = check(args.candidate, args.control)
    with args.output.open("x") as stream:
        json.dump(val, stream, indent=2, allow_nan=False)
        stream.write("\n")
