"""Lock every assigned paired run, then score the complete geographic holdout."""
import argparse
from collections import defaultdict
import hashlib
import json
from math import cos, radians
from pathlib import Path
from statistics import median

from leo.storage.fast_scan import immutable_json
from tools.pipeline_eval.qualification.holdout_geography import CONTAINING, EDGE_CASES, EDGE_PROTOCOL
from tools.pipeline_eval.scoring import ARMS, distance_km, distribution, thresholds


def pinned(path, expected):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"Changed after freezing: {path.name}")
    return json.loads(data)


def lock(panel_path, panel_sha, spec_digest, runs):
    panel = pinned(panel_path, panel_sha)
    offers = [job["offer"] for job in panel["jobs"]]
    if not offers or len(set(offers)) != len(offers):
        raise ValueError("Expected one distinct offered region per assigned case")
    cases = []
    for job in panel["jobs"]:
        path = runs / job["offer"] / "pair.json"
        if path.exists():
            result = json.loads(path.read_bytes())
            assignment = dict(job=job, panel_sha256=panel_sha, truth_commitment=panel["commitment"])
            if result.get("blind_assignment") != assignment or result.get("candidate_specification_digest") != spec_digest:
                raise ValueError("Run differs from frozen assignment or candidate")
        else:
            result = {"failure": "Missing paired run"}
        cases.append(dict(job=job, result=result))
    protocol = panel.get("geography_protocol")
    if protocol not in (None, EDGE_PROTOCOL):
        raise ValueError("Unknown geographic confirmation protocol")
    return dict(panel_sha256=panel_sha, truth_commitment=panel["commitment"], geography_protocol=protocol,
                candidate_specification_digest=spec_digest, cases=cases)


def score(locked, truth):
    labels = truth["answers"]
    if set(labels) != {c["job"]["offer"] for c in locked["cases"]}:
        raise ValueError("Scoring key and locked cases differ")
    groups = defaultdict(list)
    recording_sites = {}
    conditions_by_recording = defaultdict(set)
    rows, times = [], []
    failures = 0
    quality = True
    for case in locked["cases"]:
        job, result = case["job"], case["result"]
        label = labels[job["offer"]]
        if label["recording"] != job["recording"]:
            raise ValueError("Scoring key references another recording")
        site, condition = tuple(label["truth"]), label["condition"]
        # Replaying a waveform under another offer cannot create a second site.
        if recording_sites.setdefault(job["recording"], site) != site:
            raise ValueError("One recording is assigned multiple receiver locations")
        conditions_by_recording[job["recording"]].add(condition)
        runs = result.get("runs", {})
        failed = "failure" in result or set(runs) != {"baseline", "candidate"}
        failures += int(failed)
        if not failed:
            times.append([runs[arm]["elapsed_s"] for arm in ("baseline", "candidate")])
        for calibration in ARMS:
            errors = []
            for arm in ("baseline", "candidate"):
                run = runs.get(arm, {})
                receipt = run.get("receipt", {})
                prediction = run.get("arms", {}).get(calibration, {})
                position = prediction.get("latlon")
                error = distance_km(position, site)
                errors.append(error)
                if receipt:
                    region = receipt["region"]
                    lat, lon = region["center"]
                    offset = max(abs((site[0]-lat)*111), abs((site[1]-lon)*111.32*cos(radians(lat))))
                    clearance = region["width_km"]/2 - offset
                    if (clearance >= 0) != (condition in CONTAINING):
                        raise ValueError("Offered square disagrees with the scoring condition")
                    if condition in ("edge-containing", "edge-omitted") and not .05 - 1e-8 <= abs(clearance) <= .25 + 1e-8:
                        raise ValueError("Edge offer outside specified distance from the face")
                    if (position is not None) != (receipt["decision"] == "complete"):
                        raise ValueError("Position disagrees with its terminal decision")
                groups[site, condition, calibration, arm].append(error)
                rows.append(dict(**job, site=site, condition=condition, calibration=calibration,
                                 arm=arm, decision=receipt.get("decision", "failed"), error_km=error,
                                 frequency_rms_hz=prediction.get("rf_rms_hz"), elapsed_s=run.get("elapsed_s"),
                                 cpu_s=run.get("cpu_s"), pair_failure=result.get("failure")))
            if condition in CONTAINING and errors[0] is not None and errors[1] is None:
                quality = False
            if condition not in CONTAINING and errors[0] is None and errors[1] is not None:
                quality = False
    summaries = []
    for (site, condition, calibration, arm), errors in groups.items():
        stats = distribution(errors)
        summaries.append(dict(site=site, condition=condition, calibration=calibration, arm=arm,
                              assigned=len(errors), fixes=stats["n"], error_km=stats,
                              false_fixes=stats["n"] if condition not in CONTAINING else 0,
                              within_km_count=thresholds(errors)))
        if arm == "candidate" and condition in CONTAINING:
            base = distribution(groups[site, condition, calibration, "baseline"])
            if base["n"] and (not stats["n"] or any(stats[k] > base[k] for k in ("p50", "p90"))):
                quality = False
    ratios = [b/a for a, b in times]
    paired = median(ratios) if ratios and not failures else None
    summed = sum(b for a, b in times)/sum(a for a, b in times) if paired is not None else None
    sites = {tuple(s["site"]) for s in summaries}
    tested_sites = {tuple(s["site"]) for s in summaries if s["condition"] == "containing"
                    and s["arm"] == "baseline" and s["fixes"] > 0}
    coverage = len(sites) >= 2 and tested_sites == sites and all(
        any(s["site"] == site and s["condition"] not in CONTAINING for s in summaries) for site in sites)
    if locked.get("geography_protocol") == EDGE_PROTOCOL:
        # Vary only the offered region within each four-way comparison.
        coverage &= all(conditions == EDGE_CASES for conditions in conditions_by_recording.values())
        for site in sites:
            controls = [s for s in summaries if s["site"] == site and s["arm"] == "baseline"]
            coverage &= {s["condition"] for s in controls} == EDGE_CASES
            coverage &= all(s["fixes"] > 0 for s in controls if s["condition"] in CONTAINING)
    omission = {}
    for arm in ("baseline", "candidate"):
        # Publication is a single decision shared by both calibration fits.
        omitted = [r for r in rows if r["arm"] == arm and r["calibration"] == "c0"
                   and r["condition"] not in CONTAINING]
        omission[arm] = dict(assigned=len(omitted),
                             false_fixes=sum(r["decision"] == "complete" for r in omitted),
                             withheld=sum(r["decision"] == "withheld" for r in omitted),
                             failed=sum(r["decision"] == "failed" for r in omitted))
    candidate_regions_correct = bool(coverage and not failures and all(
        r["decision"] == ("complete" if r["condition"] in CONTAINING else "withheld")
        for r in rows if r["arm"] == "candidate" and r["calibration"] == "c0"))
    relative_pass = bool(quality and coverage and paired is not None and max(paired, summed) <= .5)
    geographic_pass = relative_pass and candidate_regions_correct and locked.get("geography_protocol") == EDGE_PROTOCOL
    return dict(assigned=len(locked["cases"]), failed_pairs=failures, rows=rows, by_site=summaries,
                geography_protocol=locked.get("geography_protocol"), missing_region=omission,
                median_elapsed_ratio=paired, summed_elapsed_ratio=summed,
                geographic_confirmation_coverage=coverage,
                candidate_correct_on_all_region_decisions=candidate_regions_correct,
                relative_quality_preserved=quality and not failures,
                passed=relative_pass, passed_geographic_holdout=geographic_pass)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    freeze = commands.add_parser("lock")
    freeze.add_argument("panel", type=Path)
    freeze.add_argument("panel_sha256")
    freeze.add_argument("candidate_spec_digest")
    freeze.add_argument("runs", type=Path)
    release = commands.add_parser("score")
    release.add_argument("predictions", type=Path)
    release.add_argument("predictions_sha256")
    release.add_argument("scoring_key", type=Path)
    for command in (freeze, release):
        command.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.action == "lock":
        document = lock(args.panel, args.panel_sha256, args.candidate_spec_digest, args.runs)
    else:
        predictions = pinned(args.predictions, args.predictions_sha256)
        document = score(predictions, pinned(args.scoring_key, predictions["truth_commitment"]))
    immutable_json(args.output, document)
    print(hashlib.sha256(args.output.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
