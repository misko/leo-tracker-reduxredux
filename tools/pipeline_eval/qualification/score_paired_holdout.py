"""Lock every assigned paired run, then score the complete geographic holdout."""
import argparse
from collections import defaultdict
import hashlib
import json
from math import cos, radians
from pathlib import Path
from statistics import median

from leo.storage.fast_scan import immutable_json
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
    return dict(panel_sha256=panel_sha, truth_commitment=panel["commitment"],
                candidate_specification_digest=spec_digest, cases=cases)


def score(locked, truth):
    labels = truth["answers"]
    if set(labels) != {c["job"]["offer"] for c in locked["cases"]}:
        raise ValueError("Scoring key and locked cases differ")
    groups = defaultdict(list)
    rows, times = [], []
    failures = 0
    quality = True
    for case in locked["cases"]:
        job, result = case["job"], case["result"]
        label = labels[job["offer"]]
        if label["recording"] != job["recording"]:
            raise ValueError("Scoring key references another recording")
        site, condition = tuple(label["truth"]), label["condition"]
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
                    if (offset <= region["width_km"]/2) != (condition == "containing"):
                        raise ValueError("Offered square disagrees with the scoring condition")
                    if (position is not None) != (receipt["decision"] == "complete"):
                        raise ValueError("Position disagrees with its terminal decision")
                groups[site, condition, calibration, arm].append(error)
                rows.append(dict(**job, site=site, condition=condition, calibration=calibration,
                                 arm=arm, decision=receipt.get("decision", "failed"), error_km=error,
                                 frequency_rms_hz=prediction.get("rf_rms_hz"), elapsed_s=run.get("elapsed_s"),
                                 cpu_s=run.get("cpu_s"), pair_failure=result.get("failure")))
            if condition == "containing" and errors[0] is not None and errors[1] is None:
                quality = False
            if condition != "containing" and errors[0] is None and errors[1] is not None:
                quality = False
    summaries = []
    for (site, condition, calibration, arm), errors in groups.items():
        stats = distribution(errors)
        summaries.append(dict(site=site, condition=condition, calibration=calibration, arm=arm,
                              assigned=len(errors), fixes=stats["n"], error_km=stats,
                              false_fixes=stats["n"] if condition != "containing" else 0,
                              within_km_count=thresholds(errors)))
        if arm == "candidate" and condition == "containing":
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
        any(s["site"] == site and s["condition"] != "containing" for s in summaries) for site in sites)
    return dict(assigned=len(locked["cases"]), failed_pairs=failures, rows=rows, by_site=summaries,
                median_elapsed_ratio=paired, summed_elapsed_ratio=summed,
                geographic_confirmation_coverage=coverage,
                relative_quality_preserved=quality and not failures,
                passed=bool(quality and coverage and paired is not None and max(paired, summed) <= .5))


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
