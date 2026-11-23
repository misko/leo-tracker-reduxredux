"""Verify matched raw publications and score only after both process clocks close."""

import argparse
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path

from aperture_score import PHYSICAL, distance_km
from aperture_trial import ARMS, read, write
from dense_full_short_raw import checked
from full_short_physical_score import classified
from joint_publication import artifacts
from leo.contracts.digests import canonical_digest
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from tools.pipeline_eval.qualification.paired_publication import evidence
from weak_combined_raw import HERE


def decision(stock, candidate, errors, *, complete):
    if any(not isfinite(v) or v <= 0 for v in (stock, candidate)):
        raise ValueError("Process durations must be finite and positive")
    fraction = candidate / stock
    delta = {arm: errors["candidate"][arm] - errors["stock"][arm] for arm in ARMS}
    return dict(elapsed_fraction=fraction, speedup=1 / fraction, passes_one_recording_timing=fraction <= .5,
                added_position_error_km=delta, passes_position=complete and all(x <= .25 for x in delta.values()))


def report_write_seconds(out, receipt, cache):
    """Wall-clock diagnostic from pre-launch cache snapshot through the standard scan report write."""
    report, = (out / "fast-scan-reports").glob("*.json")
    if report.stem != receipt["run_id"]:
        raise ValueError("Standard scan report belongs to another run")
    return (report.stat().st_mtime_ns - cache["ended_unix_ns"]) / 1e9


def score(root, saved, old, cold_root=None):
    reference = read(checked(old, "ab65bd4f9a03491c945bbaa2fcbaf0413beda18f1bd25452f17d081a74a98a28"))
    entry = read(HERE / "measurements/grid-phase-entry.json")
    ref = read(checked(saved / "joint-research-receipt.json", entry["candidate_receipt_sha256"]))
    bind = read(root / "binding.json")
    clocks = {name: read(root / f"{name}-clock.json") for name in ("stock", "candidate")}
    if any(clock["status"] for clock in clocks.values()):
        raise ValueError("Expected both arms to exit successfully")
    trial = read(root / "candidate/joint-research-receipt.json")
    stock = json.loads((root / "stock-stdout").read_text().strip().splitlines()[-1])
    store = FastStandardAnalysisStore(saved)
    saved_grid = store.position_grid(ref["receipt"]["run_id"])
    survey, = [row["reference"] for row in read(PHYSICAL)["cases"] if row["dataset_label"] == "DS30-0016"
               and row["authority_eligible"]]
    truth = [survey[k] for k in ("latitude_deg", "longitude_deg")]
    rows, checks, errors = {}, {}, {}
    sources = []
    for arm, receipt in (("stock", stock), ("candidate", trial["receipt"])):
        out = root / arm
        observed = evidence(out, receipt, 0, read_only=True)
        figures = json.loads(json.dumps(artifacts(out, receipt)))["images"]
        native_path, = (out / "fast-scan-automatic-work").glob("*/detections.json")
        native = read(native_path)
        probes = native["source"]["probes"]
        sources.append([{k:v for k,v in p.items() if k != "candidates"} for p in probes])
        cache = read(root / f"{arm}-before.json")
        grid = FastStandardAnalysisStore(out).position_grid(receipt["run_id"])
        expected = reference["runs"]["stock"] if arm == "stock" else None
        checks[arm] = dict(raw_authority=observed["raw_authority"] == bind["request"]["raw_authority"],
             region=receipt["region"] == bind["request"]["offered_region"],
             inventory=native["source"]["input_manifest_sha256"] == bind["inventory"],
             complete=receipt["decision"] == "complete" and grid["complete"] and grid["evaluated_points"] == 179,
             counts=receipt["window_count"] == 808 and receipt["counts"] == dict(processed=713, invalid_capture=95, skipped_fast_score=0),
             images=figures == (expected["publication"] if expected else ref)["evidence"]["images"] and len(figures) == 8)
        if expected:
            checks[arm]["original_science"] = all(observed[key] == expected["verified"][key]
                                                  for key in ("scientific_digests", "owners", "arms"))
            checks[arm]["detector"] = canonical_digest(native) == expected["detection"]["native_sha256"]
        else:
            checks[arm]["detector"] = canonical_digest(native) == ref["saved_digest"] and trial["saved_digest"] is None
            checks[arm]["terminal"] = receipt["terminal_sha256"] == ref["receipt"]["terminal_sha256"]
            checks[arm]["owners_and_roles"] = trial["selected_rows"] == ref["selected_rows"]
            checks[arm]["grid"] = {k:v for k,v in grid.items() if k != "elapsed_seconds"} == {
                                  k:v for k,v in saved_grid.items() if k != "elapsed_seconds"}
            checks[arm]["path"] = trial["evidence"]["path"] == ref["evidence"]["path"]
            recipe = read(out / "full-short-recipe.json")
            audit = recipe["receiver_audit"]
            checks[arm]["calls"] = all(audit["native"][k] == v for k,v in classified(probes).items())
            checks[arm]["active"] = (recipe["graph"] == "installed" and recipe["reuse_grid_phase_states"]
                and recipe["reuse_cold_track_rows"] and trial["solve"]["predictive_phase_states"] == entry["phase"]
                and trial["solve"]["cold_track_rows"] == entry["cold_rows"] and trial["solve"]["geographic_projector"]["calls"] > 0)
        errors[arm] = {a:distance_km(observed["arms"][a]["latlon"], truth) for a in ARMS}
        rows[arm] = dict(process=clocks[arm], cache=cache, report_write_s=report_write_seconds(out, receipt, cache),
            errors_km=errors[arm], arms=observed["arms"],
            owners=observed["owners"], scientific_digests=observed["scientific_digests"], images=figures,
            native_sha256=canonical_digest(native), terminal_sha256=receipt["terminal_sha256"],
            counts=receipt["counts"], grid_points=grid["evaluated_points"])
    checks["same_opportunities"] = sources[0] == sources[1] and len(sources[0]) == 1426
    if not all(all(value.values()) if isinstance(value,dict) else value for value in checks.values()):
        raise ValueError(f"Raw pair differs from its science references: {checks}")
    cold = None
    if cold_root is not None:
        cold_trial = read(cold_root / "candidate/joint-research-receipt.json")
        cold_clock = read(cold_root / "candidate-clock.json")
        cold_cache = read(cold_root / "candidate-before.json")
        cold_recipe = read(cold_root / "candidate/full-short-recipe.json")
        if (cold_clock["status"] != 0 or cold_trial["receipt"]["terminal_sha256"] != trial["receipt"]["terminal_sha256"]
                or cold_trial["evidence"]["images"] != trial["evidence"]["images"]
                or cold_recipe["recipe"] != recipe["recipe"] or cold_trial["selected_rows"] != trial["selected_rows"]):
            raise ValueError("Cold observation did not reproduce the completed candidate")
        cold = dict(process=cold_clock, cache=cold_cache, receipt_sha256=cold_trial["receipt"]["terminal_sha256"],
                    acquisition=cold_recipe["receiver_audit"]["acquire"])
    return dict(checks=checks, runs=rows, initial_cold_candidate=cold, binding=bind,
        survey_sha256=sha256(PHYSICAL.read_bytes()).hexdigest(),
        candidate_acquisition=audit["acquire"], candidate_native=audit["native"], candidate_solve=trial["solve"],
        candidate_publication_cpu_s=trial["publication_cpu_s"], candidate_publication_elapsed_s=trial["publication_elapsed_s"],
        decision=decision(clocks["stock"]["elapsed_s"], clocks["candidate"]["elapsed_s"], errors, complete=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "saved", "old", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--cold-root", type=Path)
    args = parser.parse_args()
    write(args.output, score(args.root, args.saved, args.old, args.cold_root))
