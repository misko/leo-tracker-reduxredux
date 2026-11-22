"""Lock every assigned paired run, then score the complete geographic holdout."""
import argparse
from collections import defaultdict
import hashlib
import json
from math import cos, isfinite, radians
from pathlib import Path
from statistics import median

from leo.storage.fast_scan import immutable_json
from leo.storage.short_window import ShortWindowReader
from tools.pipeline_eval.qualification.holdout_geography import CONTAINING, EDGE_CASES, EDGE_PROTOCOL, drawn_pilot_edges
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
    pilot_edges = {}
    if protocol == EDGE_PROTOCOL:
        for recording in sorted({job["recording"] for job in panel["jobs"]}):
            if Path(recording).name != recording or recording in ("", ".", ".."):
                raise ValueError("Expected a local recording name")
            reader = ShortWindowReader(panel_path.parent / recording)
            if reader.manifest_sha256 != panel["inputs"]["recordings"][recording]:
                raise ValueError("Recording manifest changed after freezing")
            edges = {target.get("edge") for target in reader.manifest.configuration["targets"]}
            if edges not in ({"upper"}, {"lower"}):
                raise ValueError("Fresh confirmation expects one pilot edge per recording")
            pilot_edges[recording], = edges
    return dict(panel_sha256=panel_sha, truth_commitment=panel["commitment"], geography_protocol=protocol,
                candidate_specification_digest=spec_digest, cases=cases, recording_pilot_edges=pilot_edges)


def offset_km(region, point):
    lat, lon = region["center"]
    return (point[1]-lon)*111.32*cos(radians(lat)), (point[0]-lat)*111


def face_clearance_km(region, point):
    """Distance to the nearest face in the solver frame, negative outside."""
    return region["width_km"]/2 - max(map(abs, offset_km(region, point)))


def matches_edge_design(site, offers):
    """Verify the four-way geometry from locked receipts and revealed truth."""
    if len(offers) != len(EDGE_CASES) or {label for label, _ in offers} != EDGE_CASES:
        return False
    regions = dict(offers)
    widths = {region["width_km"] for region in regions.values()}
    if len(widths) != 1:
        return False
    width = widths.pop()
    if not 18 <= width <= 40:
        return False
    half = width / 2
    tolerance = 1e-8  # km, for converting saved coordinates back into the local frame
    limits = {"containing": (.15*half, .8*half), "far": (2.5*half, 5.5*half),
              "edge-containing": (half-.25, half-.05), "edge-omitted": (half+.05, half+.25)}
    edge_faces = set()
    for label, region in regions.items():
        # The fresh panel gives inference a search square without a separate sky prior.
        if region.get("screen_center", region["center"]) != region["center"]:
            return False
        east, north = offset_km(region, site)
        if east == 0 or north == 0:
            return False  # The offer would disclose one exact receiver coordinate.
        axis, normal, along = ("east", east, north) if abs(east) >= abs(north) else ("north", north, east)
        lo, hi = limits[label]
        if not (lo-tolerance <= abs(normal) <= hi+tolerance and abs(along) <= .75*half+tolerance):
            return False
        if label.startswith("edge-"):
            edge_faces.add((axis, normal > 0))
    return len(edge_faces) == 1


def elapsed_ratios(assigned):
    if not assigned or None in assigned:
        return None, None
    return (median(b/a for a, b in assigned),
            sum(b for _, b in assigned) / sum(a for a, _ in assigned))


def score(locked, truth):
    labels = truth["answers"]
    if set(labels) != {c["job"]["offer"] for c in locked["cases"]}:
        raise ValueError("Scoring key and locked cases differ")
    groups = defaultdict(list)
    recording_sites = {}
    heights = {}
    conditions_by_recording = defaultdict(set)
    edge_offers = defaultdict(list)
    times_by_site = defaultdict(list)
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
        height = label.get("height_m")
        if "height_m" in label and (type(height) not in (int, float) or not isfinite(height)):
            raise ValueError("Expected a finite receiver height in the scoring key")
        if heights.setdefault(site, height) != height:
            raise ValueError("One receiver location is assigned multiple heights")
        height_field = {} if height is None else {"height_m": height}
        conditions_by_recording[job["recording"]].add(condition)
        runs = result.get("runs", {})
        failed = "failure" in result or set(runs) != {"baseline", "candidate"}
        failures += int(failed)
        if locked.get("geography_protocol") == EDGE_PROTOCOL and not failed:
            for arm in ("baseline", "candidate"):
                receipt = runs[arm].get("receipt", {})
                if "region" in receipt:
                    edge_offers[job["recording"], arm].append((condition, receipt["region"]))
        matched = None if failed else (runs["baseline"]["elapsed_s"], runs["candidate"]["elapsed_s"])
        times.append(matched)
        times_by_site[site].append(matched)
        for calibration in ARMS:
            errors = []
            for arm in ("baseline", "candidate"):
                run = runs.get(arm, {})
                receipt = run.get("receipt", {})
                prediction = run.get("arms", {}).get(calibration, {})
                position = prediction.get("latlon")
                error = distance_km(position, site)
                errors.append(error)
                center_error = clearance = prediction_clearance = None
                if receipt:
                    region = receipt["region"]
                    center_error = distance_km(region["center"], site)
                    clearance = face_clearance_km(region, site)
                    if position is not None:
                        prediction_clearance = face_clearance_km(region, position)
                    if (clearance >= 0) != (condition in CONTAINING):
                        raise ValueError("Offered square disagrees with the scoring condition")
                    if condition in ("edge-containing", "edge-omitted") and not .05 - 1e-8 <= abs(clearance) <= .25 + 1e-8:
                        raise ValueError("Edge offer outside specified distance from the face")
                    if (position is not None) != (receipt["decision"] == "complete"):
                        raise ValueError("Position disagrees with its terminal decision")
                groups[site, condition, calibration, arm].append(error)
                rows.append(dict(**job, site=site, condition=condition, calibration=calibration,
                                 arm=arm, decision=receipt.get("decision", "failed"), error_km=error,
                                 offered_center_error_km=center_error,
                                 truth_face_clearance_km=clearance,
                                 prediction_face_clearance_km=prediction_clearance,
                                 improvement_over_center_km=(center_error - error
                                                             if center_error is not None and error is not None else None),
                                 frequency_rms_hz=prediction.get("rf_rms_hz"), elapsed_s=run.get("elapsed_s"),
                                 cpu_s=run.get("cpu_s"), pair_failure=result.get("failure"), **height_field))
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
        if heights[site] is not None:
            summaries[-1]["height_m"] = heights[site]
        if arm == "candidate" and condition in CONTAINING:
            base = distribution(groups[site, condition, calibration, "baseline"])
            if base["n"] and (not stats["n"] or any(stats[k] > base[k] for k in ("p50", "p90"))):
                quality = False
    paired, summed = elapsed_ratios(times)
    sites = {tuple(s["site"]) for s in summaries}
    tested_sites = {tuple(s["site"]) for s in summaries if s["condition"] == "containing"
                    and s["arm"] == "baseline" and s["fixes"] > 0}
    coverage = len(sites) >= 2 and tested_sites == sites and all(
        any(s["site"] == site and s["condition"] not in CONTAINING for s in summaries) for site in sites)
    if locked.get("geography_protocol") == EDGE_PROTOCOL:
        # Vary only the offered region within each four-way comparison.
        coverage &= all(conditions == EDGE_CASES for conditions in conditions_by_recording.values())
        for recording, site in recording_sites.items():
            baseline_offers = edge_offers[recording, "baseline"]
            coverage &= (baseline_offers == edge_offers[recording, "candidate"]
                         and matches_edge_design(site, baseline_offers))
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
    expected_edges = (drawn_pilot_edges(truth.get("seed"), sites)
                      if locked.get("geography_protocol") == EDGE_PROTOCOL else {})
    observed_edges = locked.get("recording_pilot_edges", {})
    verified_edges = bool(expected_edges and observed_edges == {
        recording: expected_edges[site] for recording, site in recording_sites.items()})
    geographic_pass = relative_pass and candidate_regions_correct and verified_edges
    site_runtimes = []
    for site, assigned in sorted(times_by_site.items()):
        regional_median, regional_total = elapsed_ratios(assigned)
        site_runtimes.append(dict(site=site, assigned=len(assigned), completed=len(assigned)-assigned.count(None),
                                  median_elapsed_ratio=regional_median, summed_elapsed_ratio=regional_total))
    return dict(assigned=len(locked["cases"]), failed_pairs=failures, rows=rows, by_site=summaries,
                runtime_by_site=site_runtimes,
                geography_protocol=locked.get("geography_protocol"), missing_region=omission,
                median_elapsed_ratio=paired, summed_elapsed_ratio=summed,
                geographic_confirmation_coverage=coverage, fresh_site_draw_verified=bool(expected_edges),
                recording_pilot_edges=observed_edges, fresh_pilot_edges_verified=verified_edges,
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
