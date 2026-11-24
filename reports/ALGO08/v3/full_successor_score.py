"""Score immutable DS30 predictions after benchmark workers finish."""

import argparse
from bisect import bisect_right
from collections import Counter
import csv
from datetime import datetime, timezone
import gzip
from hashlib import sha256
import io
import json
import math
from pathlib import Path
from statistics import median

from tools.pipeline_eval.scoring import ARMS, coordinate, distance_km, distribution


ROOT = Path(__file__).resolve().parents[3]
MANIFEST = "a4ce879975be0593f1adeb7c106f31660c6c423f17e2c7858985244530dc0eb8"
REFERENCE = "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"
RELEASE_100 = "8535781f2ed67016fe42c6ff820f503e9876c1b0f356f3cf2d9c1b6e8d216aa2"
OFFER = "2698d6858da0a2d989d8c2185c9e3bbbba20d539988204c1f93a591eb9471236"
BUILDS = ("installed", "successor")
PINS = {"installed": "sha256:6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f",
        "successor": "sha256:30cc3b044040f2519677d67abfde731f83693612744d2236d1ba71bb5a31e4ab"}
VERIFIED = {"complete", "withheld", "solver_failed"}
RELOCATION_FIELDS = ("historic_raw_authority_sha256", "canonical_reopened_inventory_sha256",
                     "relocation_proof_sha256", "prior_preflight_sha256")


def checked(data, pin):
    if sha256(data).hexdigest() != pin:
        raise ValueError("Historical benchmark input digest changed")
    return data


def roster(root=ROOT):
    data = root / "reports/2026_11_20_ds30_fast/dataset/manifest.json.gz"
    members = json.loads(checked(gzip.decompress(data.read_bytes()), MANIFEST))["members"]
    reference = root / "reports/2026_11_21_ds30_full/reference-audit.json"
    references = json.loads(checked(reference.read_bytes(), REFERENCE))["cases"]
    release = root / "reports/ALGO08/v3/ds30-100/recordings.csv"
    release_rows = csv.DictReader(io.StringIO(checked(release.read_bytes(), RELEASE_100).decode()))
    historical = {r["case"] for r in release_rows}
    lookup = {m["dataset_label"]: m for m in members}
    surveyed = {r["dataset_label"]: r for r in references}
    if len(lookup) != len(members) or len(lookup) != 455 or len(references) != 455 or set(lookup) != set(surveyed):
        raise ValueError("Original recording and reference rosters disagree")
    if len(historical) != 100 or not historical <= lookup.keys():
        raise ValueError("Invalid historical release membership")
    assigned = {}
    for case, original in lookup.items():
        survey = surveyed[case]
        point = survey["reference"] if survey["authority_eligible"] else None
        assigned[case] = dict(case_id=original["case_id"], raw_authority=original["raw_authority_digest"],
                              physical_content=original["raw_recording"]["identity_sha256"],
                              capture_day=datetime.fromtimestamp(original["captured_utc_ns"] // 10**9,
                                                                 timezone.utc).date().isoformat(),
                              recording_state=original["recording_state"], release_100=case in historical,
                              reference=[point["latitude_deg"], point["longitude_deg"]] if point else None)
    return assigned


def outcomes_summary(rows, assigned):
    """Rows represent independently checked terminal results, one per build and recording."""
    if len(rows) != len(assigned) or {r["case"] for r in rows} != set(assigned):
        raise ValueError("Population summary requires every assigned recording exactly once")
    summary = {}
    for arm in ARMS:
        fixes = [r for r in rows if r[arm + "_error_km"] is not None]
        errors = [r[arm + "_error_km"] for r in fixes]
        summary[arm] = dict(fixes=sum(r[arm + "_fix"] for r in rows), scored=len(fixes),
                            error_km=distribution(errors),
                            within_1km=sum(e <= 1 for e in errors), within_2km=sum(e <= 2 for e in errors),
                            rf_rms_hz=distribution([r[arm + "_rf_rms_hz"] for r in fixes]))
    return summary


def paired_timing(pairs, metric):
    if metric not in ("elapsed_s", "cpu_s"):
        raise ValueError("Expected through-exit time")
    matched = [(a[metric], b[metric]) for a, b in pairs if a[metric] is not None and b[metric] is not None]
    if any(not math.isfinite(t) or t <= 0 for pair in matched for t in pair):
        raise ValueError("Timed exits require finite positive clocks")
    if not matched:
        return dict(pairs=0, summed_speedup=None, median_paired_speedup=None)
    return dict(pairs=len(matched), summed_speedup=sum(a for a, _ in matched) / sum(b for _, b in matched),
                median_paired_speedup=1 / median(b / a for a, b in matched))


def capture_day_sensitivity(pairs, assigned):
    """Keep both builds together when measuring the influence of a UTC capture day."""
    by_day = {}
    for pair in pairs:
        day = assigned[pair[0]["case"]]["capture_day"]
        by_day.setdefault(day, []).append(pair)

    def totals(group):
        counts = {}
        for arm in ARMS:
            key = arm + "_error_km"
            counts[arm] = {
                role: sum(pair[i][key] is not None and pair[i][key] <= 1. for pair in group)
                for i, role in enumerate(BUILDS)}
        return dict(pairs=len(group), wall=paired_timing(group, "elapsed_s"), within_1km=counts)

    return {day: dict(on_day=totals(by_day[day]), omitting_day=totals([
                p for other_day, group in by_day.items() if other_day != day for p in group]))
            for day in sorted(by_day)}


def paired_rf_and_error(pairs, arm):
    """Count changes in the conditional RF fit and position on the same recording."""
    rf_key = arm + "_rf_rms_hz"
    error_key = arm + "_error_km"
    counts = Counter()
    for installed, candidate in pairs:
        if None in (installed[rf_key], candidate[rf_key], installed[error_key], candidate[error_key]):
            continue
        rf = candidate[rf_key] - installed[rf_key]
        error = candidate[error_key] - installed[error_key]
        if rf == 0 or error == 0:
            counts["tied"] += 1
        else:
            direction = "rf_lower" if rf < 0 else "rf_higher"
            counts[direction + ("_closer" if error < 0 else "_farther")] += 1
    return dict(comparable=sum(counts.values()), **{key: counts[key] for key in (
        "rf_lower_closer", "rf_lower_farther", "rf_higher_closer", "rf_higher_farther", "tied")})


def empirical_accuracy_gap(pairs, arm):
    """Compare all-attempt coverage and bound how far existing fixes would need to move."""
    key = arm + "_error_km"
    installed, candidate = (sorted(p[i][key] for p in pairs if p[i][key] is not None) for i in (0, 1))
    deficit, at = 0, None
    for threshold in sorted(set(installed)):
        gap = bisect_right(installed, threshold) - bisect_right(candidate, threshold)
        if gap > deficit:
            deficit, at = gap, threshold
    # A displacement of at most d can decrease each radial error by at most d.
    # The same inequality holds for each order statistic, allowing ranks to change.
    radius, rank = None, None
    if len(candidate) >= len(installed):
        radius = 0.
        for i, base in enumerate(installed):
            if candidate[i] - base > radius:
                radius, rank = candidate[i] - base, i + 1
    return dict(assigned=len(pairs), installed_scored=len(installed), candidate_scored=len(candidate),
                largest_coverage_deficit=deficit, first_threshold_km=at,
                maximum_displacement_lower_bound_km=radius, binding_rank=rank)


def squared_error_influence(pairs, arm):
    """Price the largest single contribution to the excess squared error on shared fixes."""
    key = arm + "_error_km"
    shared = [(a["case"], a[key], b[key]) for a, b in pairs if a[key] is not None and b[key] is not None]
    ordered = sorted(shared, key=lambda row: (-(row[2]**2 - row[1]**2), row[0]))
    excess = [candidate**2 - base**2 for _, base, candidate in ordered]
    net = math.fsum(excess)
    result = dict(shared=len(ordered), worse=sum(d > 0 for d in excess), net_sum_squared_excess_km2=net,
                  largest=None, remaining_shared=0, remaining_rms_km=None)
    if not excess or excess[0] <= 0:
        return result
    result["largest"] = dict(case=ordered[0][0], squared_excess_km2=excess[0],
                             fraction_of_net_excess=excess[0]/net if net > 0 else None)
    rest = ordered[1:]
    result["remaining_shared"] = len(rest)
    if rest:
        result["remaining_rms_km"] = {role: math.sqrt(math.fsum(row[i]**2 for row in rest)/len(rest))
                                      for i, role in enumerate(BUILDS, start=1)}
    return result


def time_accounting(pairs):
    totals = {}
    for i, role in enumerate(BUILDS):
        rows = [pair[i] for pair in pairs]
        wall = sum(r["elapsed_s"] for r in rows)
        cpu = sum(r["cpu_s"] for r in rows)
        totals[role] = dict(wall_s=wall, cpu_s=cpu, wall_minus_cpu_s=wall - cpu)
    a, b = (totals[role] for role in BUILDS)
    saved = a["wall_s"] - b["wall_s"]
    cpu_saved = a["cpu_s"] - b["cpu_s"]
    hypothetical = [(base, {"elapsed_s": min(test["elapsed_s"], test["cpu_s"])}) for base, test in pairs]
    return dict(totals=totals, wall_saved_s=saved, cpu_saved_s=cpu_saved,
                residual_saved_s=saved - cpu_saved,
                cpu_fraction_of_wall_savings=cpu_saved / saved if saved > 0 else None,
                removing_positive_candidate_wall_minus_cpu=paired_timing(hypothetical, "elapsed_s"))


def calibration_segment_error_km(reference, zero, fitted):
    """Closest possible horizontal error on the minor arc joining the two published solutions."""
    if reference is None or zero is None or fitted is None:
        return None
    radius = 6371.0088  # The sphere used by scoring.distance_km.
    length = distance_km(zero, fitted) / radius
    if math.pi - length < 1e-12:
        return None  # The endpoints do not specify a unique shortest arc.
    start_error = distance_km(zero, reference)
    endpoint_minimum = min(start_error, distance_km(fitted, reference))
    if length < 1e-12 or endpoint_minimum == 0:
        return endpoint_minimum
    lat, lon = map(math.radians, zero)

    def bearing_to(point):
        other_lat, other_lon = map(math.radians, point)
        east = math.cos(other_lat) * math.sin(other_lon - lon)
        north = (math.cos(lat) * math.sin(other_lat)
                 - math.sin(lat) * math.cos(other_lat) * math.cos(other_lon - lon))
        return math.atan2(east, north)

    angle = bearing_to(reference) - bearing_to(fitted)
    separation = start_error / radius
    along = math.atan2(math.sin(separation) * math.cos(angle), math.cos(separation))
    if not 0 < along < length:
        return endpoint_minimum
    cross = abs(math.sin(separation) * math.sin(angle))
    return min(endpoint_minimum, radius * math.asin(min(1., cross)))


def score_arms(arms, reference):
    output = {}
    for name in ARMS:
        arm = arms[name]
        point, rms = coordinate(arm["latlon"]), arm["rf_rms_hz"]
        if rms is not None and (not math.isfinite(rms) or rms < 0):
            raise ValueError("Invalid calibrated RF residual")
        output.update({name + "_fix": point is not None, name + "_error_km": distance_km(reference, point),
                       name + "_rf_rms_hz": rms})
    output["calibration_segment_min_error_km"] = calibration_segment_error_km(
        reference, arms["c0"]["latlon"], arms["fitted_c"]["latlon"])
    return output


def paired_rows(rows, assigned):
    """Require two distinct, source-matched raw workers for each assigned recording."""
    by_key = {}
    for r in rows:
        case, algorithm = r["case"], r["algorithm"]
        if case not in assigned or algorithm not in BUILDS or (case, algorithm) in by_key:
            raise ValueError("Duplicate or unexpected benchmark arm")
        if r["case_id"] != assigned[case]["case_id"] or r["first"] not in BUILDS:
            raise ValueError("Case identity or assigned run order changed")
        if (r["build_sha256"] != PINS[algorithm] or
                r["manifest_raw_authority_sha256"] != assigned[case]["raw_authority"] or
                r["historical_first100"] != assigned[case]["release_100"]):
            raise ValueError("Published benchmark build or enrollment changed")
        if r["outcome"] not in ("complete", "withheld", "solver_failed", "worker_failed", "invalid_publication"):
            raise ValueError(f"Recording has an unresolved or unmeasured arm: {case}, {algorithm}")
        requested = r["requested_raw_authority_sha256"]
        observed = r["raw_authority_sha256"]
        if (observed is not None and observed != requested) or (r["outcome"] in VERIFIED and not observed):
            raise ValueError("Observed input authority disagrees with the enrolled original")
        digests = ("build_sha256", "requested_raw_authority_sha256", "authority_sha256", "attempt_result_sha256")
        if any(r.get(k) is not None for k in RELOCATION_FIELDS):
            if r.get("raw_identity_sha256") != assigned[case].get("physical_content") or r.get("verified_pair") is not True:
                raise ValueError("Relocation proof requires the verified enrolled physical recording")
            digests += (*RELOCATION_FIELDS, "raw_identity_sha256")
        for field in digests:
            digest = (r.get(field) or "").removeprefix("sha256:")
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError(f"Missing or invalid {field}")
        for field in ("elapsed_s", "cpu_s"):
            if not isinstance(r[field], (float, int)) or not math.isfinite(r[field]) or r[field] <= 0:
                raise ValueError(f"Unmeasured {field} for {case}")
        start, end = r["child_started_unix_ns"], r["child_finished_unix_ns"]
        if type(start) is not int or type(end) is not int or not 0 < start < end:
            raise ValueError("Both child timestamps are required")
        scores = score_arms(r["arms"], assigned[case]["reference"])
        if any(scores[name + "_fix"] != (r["outcome"] == "complete") for name in ARMS):
            raise ValueError("Terminal decision and calibration outputs disagree")
        by_key[case, algorithm] = dict(case=case, algorithm=algorithm, case_id=r["case_id"],
                                       first=r["first"], release_100=int(assigned[case]["release_100"]),
                                       recording_state=assigned[case]["recording_state"], outcome=r["outcome"],
                                       requested_raw_authority_sha256=requested, raw_authority_sha256=observed,
                                       accession_raw_authority_sha256=assigned[case]["raw_authority"],
                                       physical_content_sha256=assigned[case].get("physical_content"),
                                       authority_sha256=r["authority_sha256"], build_sha256=r["build_sha256"],
                                       attempt_result_sha256=r["attempt_result_sha256"], timing_scope=r["timing_scope"],
                                       terminal_sha256=r.get("terminal_sha256"), reason=r.get("reason"),
                                       same_lease=r["same_lease"],
                                       generation=r["generation"], child_started_unix_ns=start,
                                       child_finished_unix_ns=end,
                                       elapsed_s=r["elapsed_s"], cpu_s=r["cpu_s"],
                                       input_blocks=r.get("input_blocks"), output_blocks=r.get("output_blocks"),
                                       child_elapsed_s=r["child_elapsed_s"], child_cpu_s=r["child_cpu_s"],
                                       validator_elapsed_s=r["validator_elapsed_s"], validator_cpu_s=r["validator_cpu_s"],
                                       **{field: r.get(field) for field in RELOCATION_FIELDS}, **scores)
    if len(by_key) != 2 * len(assigned):
        raise ValueError(f"Only {len(by_key)} measured arms for {len(assigned)} assigned recordings")
    pairs = []
    for case in assigned:
        a, b = (by_key[case, role] for role in BUILDS)
        if any(a[key] != b[key] for key in ("first", "authority_sha256", "requested_raw_authority_sha256",
                                           "generation", "same_lease", *RELOCATION_FIELDS)) or type(a["same_lease"]) is not bool:
            raise ValueError(f"Unmatched original input or run order on {case}")
        first, second = (a, b) if a["first"] == "installed" else (b, a)
        if first["child_finished_unix_ns"] > second["child_started_unix_ns"]:
            raise ValueError(f"Actual child clocks disagree with assigned launch order on {case}")
        gap = (second["child_started_unix_ns"] - first["child_finished_unix_ns"]) / 1e9
        a["between_children_s"] = b["between_children_s"] = gap
        pairs.append((a, b))
    return pairs


def shared_position_moments(rows, assigned):
    """Compare scatter only on pairs for which both published a scored position."""
    from reports.ALGO08.v3.ds30_position_moments import decompose, east_north_km

    indexed = {(r["case"], r["algorithm"]): r["arms"] for r in rows}
    result = {}
    for arm in ARMS:
        offsets = {role: [] for role in BUILDS}
        for case, source in assigned.items():
            reference = source["reference"]
            points = [indexed[case, role][arm]["latlon"] for role in BUILDS]
            if reference is None or any(point is None for point in points):
                continue
            for role, point in zip(BUILDS, points, strict=True):
                offsets[role].append(east_north_km(reference, point))
        result[arm] = {role: decompose(values) if values else None for role, values in offsets.items()}
    return result


def compare_centers(pairs, assigned, offer):
    references = {tuple(assigned[a["case"]]["reference"]) for a, _ in pairs}
    if len(references) != 1:
        raise ValueError("Expected one independently surveyed DS30 site")
    reference = references.pop()
    prior_error = distance_km(offer["center"], reference)
    data = {}
    for arm in ARMS:
        data[arm] = {}
        for i, role in enumerate(BUILDS):
            errors = [pair[i][arm + "_error_km"] for pair in pairs if pair[i][arm + "_error_km"] is not None]
            data[arm][role] = dict(assigned=len(pairs), scored=len(errors), closer_than_center=sum(e < prior_error for e in errors))
    return dict(width_km=offer["width_km"], center_error_km=prior_error,
                screen_center_distance_km=distance_km(offer["screen_center"], reference), fixes=data)


def write_report(pairs, output, enrollment, receipt_digest, *, renderer_revision=None, position_moments=None,
                 prior=None, capture_days=None):
    from reports.ALGO08.v3.full_successor_figures import paired_speed_errors, render_distribution_figures

    output.mkdir(parents=True, exist_ok=True)
    all_rows = [r for pair in pairs for r in pair]
    with (output / "recordings.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(all_rows[0]))
        writer.writeheader()
        writer.writerows(all_rows)
    sections = {
        "All DS30 recordings": pairs,
        "Original 100-recording release panel": [pair for pair in pairs if pair[0]["release_100"]],
        "Remaining recordings": [pair for pair in pairs if not pair[0]["release_100"]],
        "Complete captures": [pair for pair in pairs if pair[0]["recording_state"] == "complete"],
        "Interrupted captures": [pair for pair in pairs if pair[0]["recording_state"] == "incomplete"],
        "ALGO08v3 ran first": [pair for pair in pairs if pair[0]["first"] == "installed"],
        "Candidate ran first": [pair for pair in pairs if pair[0]["first"] == "successor"],
        "Both arms in one benchmark slot": [pair for pair in pairs if pair[0]["same_lease"]],
        "Benchmark slot reacquired between arms": [pair for pair in pairs if not pair[0]["same_lease"]],
        "Both builds reached publication verification": [
            pair for pair in pairs if all(r["timing_scope"] == "raw_launcher_through_exit_plus_common_publication_verification"
                                         for r in pair)],
        "Both builds returned a fix": [pair for pair in pairs if all(r["outcome"] == "complete" for r in pair)],
    }
    summaries = {}
    for name, group in sections.items():
        population = {a["case"] for a, _ in group}
        stats = dict(assigned=len(group), wall=paired_timing(group, "elapsed_s"), cpu=paired_timing(group, "cpu_s"),
                     time_accounting=time_accounting(group))
        for i, role in enumerate(BUILDS):
            rows = [p[i] for p in group]
            stats[role] = dict(outcomes=Counter(r["outcome"] for r in rows), wall_s=distribution([r["elapsed_s"] for r in rows]),
                               cpu_s=distribution([r["cpu_s"] for r in rows]), **outcomes_summary(rows, population))
        summaries[name] = stats
    metadata = dict(source_manifest_sha256=MANIFEST, reference_audit_sha256=REFERENCE, attempt_export_sha256=receipt_digest,
                    builds={r["algorithm"]: r["build_sha256"] for r in pairs[0]}, cohorts=summaries)
    metadata["paired_rf_and_error"] = {arm: paired_rf_and_error(pairs, arm) for arm in ARMS}
    metadata["empirical_accuracy_gap"] = {arm: empirical_accuracy_gap(pairs, arm) for arm in ARMS}
    if capture_days is not None:
        metadata["capture_day_sensitivity"] = capture_days
    if renderer_revision is not None:
        if len(renderer_revision) != 40 or any(c not in "0123456789abcdef" for c in renderer_revision):
            raise ValueError("Expected a full Git revision for the report renderer")
        metadata["report_renderer_revision"] = renderer_revision
    if position_moments is not None:
        metadata["position_error_moments_on_shared_fixes"] = position_moments
    if prior is not None:
        metadata["search_center_comparison"] = prior
    full = summaries["All DS30 recordings"]
    gates = {metric: full["wall"][metric] >= 2.0 for metric in ("summed_speedup", "median_paired_speedup")}
    metadata["twofold_wall_time_target"] = {"required_speedup": 2.0, **gates, "both_met": all(gates.values())}
    changes = {}
    for arm in ARMS:
        key = arm + "_error_km"
        delta = [(b[key] - a[key], a["case"]) for a, b in pairs if a[key] is not None and b[key] is not None]
        coverage = {}
        for radius in (1, 2):
            states = Counter((a[key] is not None and a[key] <= radius, b[key] is not None and b[key] <= radius)
                             for a, b in pairs)
            coverage[f"within_{radius}km"] = dict(both=states[True, True], gained=states[False, True],
                                                   lost=states[True, False], neither=states[False, False])
        changes[arm] = dict(shared=len(delta), candidate_minus_installed_km=distribution([d for d, _ in delta]),
                            gained=sum(not a[arm + "_fix"] and b[arm + "_fix"] for a, b in pairs),
                            lost=sum(a[arm + "_fix"] and not b[arm + "_fix"] for a, b in pairs),
                            paired_distance_coverage=coverage,
                            largest_increases=sorted((item for item in delta if item[0] > 0), reverse=True)[:5])
    metadata["paired_error_changes"] = changes
    influences = {arm: squared_error_influence(pairs, arm) for arm in ARMS}
    metadata["squared_error_influence_on_shared_fixes"] = influences
    fast = sum(a["elapsed_s"] >= 2 * b["elapsed_s"] for a, b in pairs)
    joint_performance = {}
    for label, arms in (("c0", ("c0",)), ("fitted_c", ("fitted_c",)), ("both", ARMS)):
        points = paired_speed_errors(pairs, arms)
        fast_errors = [delta for speed, delta in points if speed >= 2]
        joint_performance[label] = dict(shared_scored=len(points), twice_as_fast_with_shared_error=len(fast_errors),
                                        same_or_smaller_error=sum(delta <= 0 for delta in fast_errors),
                                        larger_error=sum(delta > 0 for delta in fast_errors),
                                        twice_as_fast_without_shared_error=fast - len(fast_errors))
    metadata["position_error_on_twice_as_fast_recordings"] = dict(twice_as_fast=fast, calibrations=joint_performance)
    blendable = [(a, b) for a, b in pairs if a["fitted_c_error_km"] is not None
                 and b["calibration_segment_min_error_km"] is not None]
    regressions = [(a, b) for a, b in blendable if b["fitted_c_error_km"] - a["fitted_c_error_km"] > .001]
    residual = [b["calibration_segment_min_error_km"] - a["fitted_c_error_km"] for a, b in regressions]
    metadata["calibration_blend_bound"] = dict(shared_scored=len(blendable), tolerance_km=.001,
                                               fitted_regressions=len(regressions),
                                               regressions_remaining=sum(d > .001 for d in residual))
    joint = Counter((a["outcome"], b["outcome"]) for a, b in pairs)
    metadata["paired_outcomes"] = [
        {"installed": a, "successor": b, "recordings": n} for (a, b), n in sorted(joint.items())]
    metadata["relocated_recordings"] = [
        {field: row[field] for field in ("case", "accession_raw_authority_sha256", "physical_content_sha256",
                                         "raw_authority_sha256", *RELOCATION_FIELDS)}
        for row, _ in pairs if row["relocation_proof_sha256"] is not None]
    (output / "summary.json").write_text(json.dumps(metadata, indent=2, allow_nan=False) + "\n")
    render_distribution_figures(output / "recordings.csv", output, enrollment=enrollment)
    k = full["assigned"]
    def number(x, digits=2):
        return "—" if x is None else f"{x:.{digits}f}"

    lines = ["# DS30 field report · ALGO08v3 and the single-core candidate", "",
             f"Both pipelines were timed on the same **{k} original recordings**. "
             f"The summed wall-time speedup was **{number(full['wall']['summed_speedup'])}×**. "
             f"Speedup at the median paired ratio was **{number(full['wall']['median_paired_speedup'])}×**. "
             f"ALGO08v3 returned **{full['installed']['fitted_c']['fixes']}/{k}** fitted positions "
             f"and the candidate returned **{full['successor']['fitted_c']['fixes']}/{k}**.", "",
             f"The candidate met **{sum(gates.values())} of 2** wall-time targets. "
             f"The summed speedup {'reached' if gates['summed_speedup'] else 'fell below'} 2×. "
             f"The median paired speedup {'reached' if gates['median_paired_speedup'] else 'fell below'} 2×. "
             f"Across all {k} attempts, ALGO08v3 returned a fitted position within 1 km on "
             f"**{full['installed']['fitted_c']['within_1km']}** and the candidate did so on "
             f"**{full['successor']['fitted_c']['within_1km']}**.", "",
             "Gauss ran one pipeline at a time on a single CPU core. The candidate uses 8 ms primary "
             "signal searches between 20 ms two-scan anchors. Both builds read the original waveforms "
             "and use the same search region and causal orbit data for each recording. "
             "The 100-recording panels below use fresh paired measurements on the original release subset. "
             "[Frozen builds and benchmark protocol](https://github.com/misko/leo-tracker-reduxredux/blob/"
             "6e18e827eca1ae6caa78e65d2b0746c3b4f424b2/reports/ALGO08/v3/full-successor-field-protocol.md)", "",
             "## Runtime", "", "![Runtime distributions and run order](runtime.png)", "",
             "![Wall and CPU time histograms](runtime-histogram.png)", "",
             "The runtime histograms count all measured exits, including withheld and failed attempts. "
             "Each metric uses the same bin edges for both builds and cohorts.", "",
             "| Cohort | Pairs | Summed wall speedup | Median paired wall speedup | Summed CPU speedup |",
             "|---|---:|---:|---:|---:|"]
    for name, obj in summaries.items():
        lines.append(f"| {name} | {obj['assigned']} | {number(obj['wall']['summed_speedup'])}× | "
                     f"{number(obj['wall']['median_paired_speedup'])}× | {number(obj['cpu']['summed_speedup'])}× |")
    lines += ["", "Successful times cover process launch through exit and independent publication verification for both builds. "
              "A failure contributes wall and CPU through exit. The per-recording data give the child-only and verifier clocks separately. The summed ratio divides total "
              "ALGO08v3 seconds by total candidate seconds. The paired measure is the reciprocal of the median candidate-to-ALGO08v3 time ratio. "
              "The second worker can benefit from pages cached by the first.", "",
              "| Run order | Wall seconds saved | CPU seconds saved | Change in remaining seconds |",
              "|---|---:|---:|---:|"]
    for name in ("All DS30 recordings", "ALGO08v3 ran first", "Candidate ran first"):
        t = summaries[name]["time_accounting"]
        lines.append(f"| {name} | {number(t['wall_saved_s'], 1)} | {number(t['cpu_saved_s'], 1)} | "
                     f"{number(t['residual_saved_s'], 1)} |")
    sensitivity = full["time_accounting"]["removing_positive_candidate_wall_minus_cpu"]
    lines += ["", "Savings subtract candidate seconds from ALGO08v3 seconds. Wall time minus CPU time can include "
              "storage waits, scheduling delays and clock-accounting differences. As a sensitivity check, removing "
              "every positive wall-minus-CPU second from the candidate on each recording, while holding its CPU cost "
              f"and the measured ALGO08v3 wall times fixed, would give **{number(sensitivity['summed_speedup'])}×** "
              f"summed and **{number(sensitivity['median_paired_speedup'])}×** median paired. These are hypothetical speedups.",
              "", "## Position error", "",
              "![Position errors with all assigned recordings in the denominator](position-error.png)", "",
              "![Horizontal error histograms for fixed-zero and fitted calibration](position-error-histogram.png)", "",
              "The position histograms count scored fixes in shared bins. The legends report the assigned totals "
              "and the numbers withheld, failed or fixed without a scored reference.", "",
              "| Calibration | Build | Fixes | Within 1 km | Within 2 km | Median / P90 error among scored fixes (km) | Median RF RMS (Hz) |",
              "|---|---|---:|---:|---:|---:|---:|"]
    for arm in ARMS:
        for role in BUILDS:
            o = full[role][arm]
            lines.append(f"| {dict(c0='Fixed zero', fitted_c='Fitted')[arm]} | "
                         f"{dict(installed='ALGO08v3', successor='Candidate')[role]} | "
                         f"{o['fixes']}/{k} | {o['within_1km']}/{k} | {o['within_2km']}/{k} | "
                         f"{number(o['error_km']['p50'],3)} / {number(o['error_km']['p90'],3)} | "
                         f"{number(o['rf_rms_hz']['p50'])} |")
    lines += ["", "The cumulative curves also show where the candidate loses the most recordings. "
              "The displacement column gives a lower bound on the largest change to an existing candidate "
              "position required to match or exceed ALGO08v3 coverage at every distance, keeping the same "
              "scored recordings. It compares ranked errors and allows the order of recordings to change.", "",
              "| Calibration | Largest coverage shortfall (recordings) | First distance at that shortfall | "
              "Required displacement of at least one position |", "|---|---:|---:|---:|"]
    for arm, label in (("c0", "Fixed zero"), ("fitted_c", "Fitted")):
        gap = metadata["empirical_accuracy_gap"][arm]
        at, radius = gap["first_threshold_km"], gap["maximum_displacement_lower_bound_km"]
        start = "—" if at is None else f"{at:.3f} km"
        bound = "More scored fixes required" if radius is None else f"{radius:.3f} km"
        lines.append(f"| {label} | {gap['largest_coverage_deficit']} | {start} | {bound} |")
    if capture_days:
        lines += ["", "### Variation by recording date", "",
                  "Each row groups recordings by their original UTC capture date. Coverage counts every "
                  "attempt on that date. The last column recomputes both timing measures on the other dates.",
                  "", "| UTC date | Pairs | Summed wall speedup | Within 1 km, fixed zero (v3 / candidate) | "
                  "Within 1 km, fitted (v3 / candidate) | Omitting date, summed / median paired speedup |",
                  "|---|---:|---:|---:|---:|---:|"]
        for day, split in capture_days.items():
            group = split["on_day"]
            zero, fitted = (group["within_1km"][arm] for arm in ARMS)
            remaining = split["omitting_day"]["wall"]
            lines.append(f"| {day} | {group['pairs']} | {number(group['wall']['summed_speedup'])}× | "
                         f"{zero['installed']} / {zero['successor']} | {fitted['installed']} / {fitted['successor']} | "
                         f"{number(remaining['summed_speedup'])}× / {number(remaining['median_paired_speedup'])}× |")
        lines += ["", "All dates share the Gauss receiver site. Omitting a date measures how much that day's "
                  "recordings affect the comparison. The JSON also gives 1 km coverage on each remaining set.",
                  "", "### Paired changes in position error"]
    lines += ["", "| Calibration | Shared scored fixes | Fixes gained / lost | Within 1 km gained / lost | "
              "Within 2 km gained / lost | Median / P90 change in error on shared fixes (m) |",
              "|---|---:|---:|---:|---:|---:|"]
    for arm in ARMS:
        c = changes[arm]
        delta = c["candidate_minus_installed_km"]
        one, two = (c["paired_distance_coverage"][f"within_{radius}km"] for radius in (1, 2))
        metres = [number(1000 * delta[p], 1) if delta[p] is not None else "—" for p in ("p50", "p90")]
        lines.append(f"| {dict(c0='Fixed zero', fitted_c='Fitted')[arm]} | {c['shared']} | {c['gained']} / {c['lost']} | "
                     f"{one['gained']} / {one['lost']} | {two['gained']} / {two['lost']} | {metres[0]} / {metres[1]} |")
    lines += ["", "A gain at a distance threshold means only the candidate returned a scored position within "
              "that distance on the recording. A loss means only ALGO08v3 did. Error changes subtract the "
              "ALGO08v3 error from the candidate error."]
    if position_moments is not None:
        lines += ["", "### Position scatter at the Gauss roof", "",
                  "On shared fixes, each horizontal error gives a distance and bearing from the survey point. "
                  "The radial RMS includes both the average displacement and the recording-to-recording scatter. "
                  "Subtracting each build’s own average displacement gives the centered RMS. Their squared "
                  "contributions add to the squared radial RMS.", "",
                  "| Calibration | Build | Shared fixes | Radial RMS (km) | Mean displacement magnitude (km) | Centered RMS (km) |",
                  "|---|---|---:|---:|---:|---:|"]
        for arm in ARMS:
            for role in BUILDS:
                item = position_moments[arm][role]
                labels = ("Fixed zero" if arm == "c0" else "Fitted", "ALGO08v3" if role == "installed" else "Candidate")
                n = item["n"] if item else 0
                values = [number(item[k], 3) if item else "—" for k in ("radial_rms_km", "mean_offset_km", "centered_rms_km")]
                lines.append(f"| {labels[0]} | {labels[1]} | {n} | " + " | ".join(values) + " |")
        lines += ["", "This diagnostic uses the survey only after scoring. It measures repeatability at one "
                  "physical location and supplies no location correction to either build."]
    if prior is not None:
        a, b = (prior["fixes"]["fitted_c"][role] for role in BUILDS)
        lines += ["", f"The supplied search square was {prior['width_km']:g} km wide. Returning its center on "
                  f"every recording would give **{prior['center_error_km']:.3f} km** horizontal error. "
                  f"ALGO08v3 beat that distance on {a['closer_than_center']}/{k} recordings and the candidate on "
                  f"{b['closer_than_center']}/{k}, using fitted calibration. The separate satellite screening "
                  f"center was {prior['screen_center_distance_km']:.3f} km from the surveyed receiver."]
    lines += ["", "### When speed and accuracy coincide", "",
              "![Wall speedup and change in horizontal position error on each recording](paired-speed-and-error.png)", "",
              f"On **{fast}/{k}** recordings the candidate took half the ALGO08v3 wall time or less. "
              "Each dot compares two scored fixes on one recording. Lower dots indicate smaller candidate error. "
              "The table accounts for every recording that reached this speed, including cases without two scored fixes.", "",
              "| Calibration | Equal or smaller error | Larger error | Lacking a paired error |",
              "|---|---:|---:|---:|"]
    for label, key in (("Fixed zero", "c0"), ("Fitted", "fitted_c"), ("Both calibrations", "both")):
        data = joint_performance[key]
        lines.append(f"| {label} | {data['same_or_smaller_error']} | {data['larger_error']} | "
                     f"{data['twice_as_fast_without_shared_error']} |")
    lines += ["", "The last row requires equal or smaller error in both calibrations. The two timing targets at "
              "the start of the report apply to the whole panel."]
    lines += ["", "| Capture state | Paired recordings | ALGO08v3 fitted fixes | Candidate fitted fixes | "
              "ALGO08v3 / candidate fitted P90 error among fixes (km) |", "|---|---:|---:|---:|---:|"]
    for name in ("Complete captures", "Interrupted captures"):
        group = summaries[name]
        a, b = (group[role]["fitted_c"] for role in BUILDS)
        lines.append(f"| {name} | {group['assigned']} | {a['fixes']} | {b['fixes']} | "
                     f"{number(a['error_km']['p90'],3)} / {number(b['error_km']['p90'],3)} |")
    worst = changes["fitted_c"]["largest_increases"]
    if worst:
        lines += ["", "The largest fitted-error increases on shared fixes were " +
                  ", ".join(f"{case} (+{delta:.3f} km)" for delta, case in worst) + "."]
    influence = influences["fitted_c"]
    if influence["remaining_rms_km"]:
        rms = influence["remaining_rms_km"]
        lines += ["", f"Excluding just {influence['largest']['case']}, the largest contributor to excess squared "
                  f"fitted error, leaves {influence['remaining_shared']} shared fixes. On those same fixes the RMS "
                  f"error is **{rms['installed']:.3f} km for ALGO08v3** and **{rms['successor']:.3f} km for the "
                  "candidate**. The primary results above retain this recording."]
    if regressions:
        lines += ["", f"The candidate's fitted error increased by more than 1 m on {len(regressions)} of "
                  f"{len(blendable)} shared fixes. On **{metadata['calibration_blend_bound']['regressions_remaining']} "
                  f"of those {len(regressions)}**, even the point closest to the reference on the shortest arc "
                  "between its fixed-zero and fitted solutions still exceeded ALGO08v3's fitted error by more "
                  "than 1 m. This retrospective bound applies to choosing or interpolating the published endpoints. "
                  "A fresh nonlinear fit can move beyond them."]
    lines += ["", "### Which receiver changes affected DS30-0049?", "",
              "A separate crossover on DS30-0049 tested both solvers on each saved receiver output. "
              "Both solvers returned 1.420 km fitted error on the installed detections and 4.040 km on the "
              "candidate detections. The receiver change accounted for the difference on this recording. "
              "[DS30-0049 crossover and verification](https://github.com/misko/leo-tracker-reduxredux/blob/"
              "5dad70d7d0c273b2aa17fa546d622bcd8e490789/reports/ALGO08/v3/ds30-0049-saved-crossover.md)"]
    lines += ["", "Each intervention below starts from the same candidate detections and uses the installed "
              "measurements as a diagnostic reference. Each row has its own complete saved-input solve. "
              "The field runtime plots use the original, unmodified pair.", "",
              "| DS30-0049 receiver input | Fixed-zero error (km) | Fitted error (km) |",
              "|---|---:|---:|",
              "| Original installed detections | 1.826 | 1.420 |",
              "| Original candidate detections | 4.472 | 4.040 |",
              "| Replace 284 closely matched short measurements | 4.196 | 3.847 |",
              "| Replace 72 short measurements that chose a different carrier | 3.942 | 3.779 |",
              "| Remove 161 candidate-only detections | 4.254 | 3.900 |",
              "| Restore all 104 installed detections on empty short lanes | 4.148 | 3.663 |", "",
              "Restoring all 104 detections recovered 41 of the 44 missing installed assignments with the "
              "same satellite and role. Fitted error improved by 377 m and remained 2.243 km above ALGO08v3. "
              "The four changes were tested independently. "
              "[Matched measurements](https://github.com/misko/leo-tracker-reduxredux/blob/"
              "2ab7167229369484196b4ae1ed32924c35585e86/reports/ALGO08/v3/ds30-0049-matched-donor.md) · "
              "[Different carrier selections](https://github.com/misko/leo-tracker-reduxredux/blob/"
              "8d92f39455a247a8f383de41438ffdd9d2766dc9/reports/ALGO08/v3/ds30-0049-shifted-winner-repair.md) · "
              "[Candidate-only detections](https://github.com/misko/leo-tracker-reduxredux/blob/"
              "e9536f1014191a14b83676ff88a2baf244f034cd/reports/ALGO08/v3/ds30-0049-sparse-only-drop.md) · "
              "[Missing detections](https://github.com/misko/leo-tracker-reduxredux/blob/"
              "abc05f858d5c05b99bc94ed36201f1826b611eec/reports/ALGO08/v3/ds30-0049-empty-recovery.md)"]
    lines += ["", "A second control started from the installed detections. Adding just 12 extra detections "
              "from the candidate’s full-length anchor visits increased fitted error from **1.420 to 2.453 km**. "
              "Four of the 12 received satellite assignments. The fitted RF residual moved by only 0.29 Hz. "
              "This isolates the effect of these anchors with installed short-visit evidence. "
              "[Anchor-only control](https://github.com/misko/leo-tracker-reduxredux/blob/"
              "9c881a8106ceb548efc032fbfd4883f39c8018b6/reports/ALGO08/v3/ds30-0049-anchor-only.md)"]
    lines += ["", "### RF fit and position on the same recordings", "",
              "Each RF residual uses that build’s own accepted observations. The counts below compare changes "
              "in conditional RF RMS with movement toward or away from the survey on shared scored fixes.", "",
              "| Calibration | Paired | Lower RF RMS, closer | Lower RF RMS, farther | Higher RF RMS, closer | Higher RF RMS, farther | Either tied |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for arm, label in (("c0", "Fixed zero"), ("fitted_c", "Fitted")):
        rf = metadata["paired_rf_and_error"][arm]
        lines.append(f"| {label} | {rf['comparable']} | {rf['rf_lower_closer']} | {rf['rf_lower_farther']} | "
                     f"{rf['rf_higher_closer']} | {rf['rf_higher_farther']} | {rf['tied']} |")
    lines += ["", "### Does the receiver effect repeat?", "",
              "Both solvers processed the same two saved detector packets on each of three recordings. "
              "The table gives horizontal position error in km with fitted calibration. "
              "These targeted replays explain particular recordings. The runtime distributions use the original "
              "end-to-end runs.", "",
              "| Recording | 20 ms receiver, ALGO08v3 solver | 20 ms receiver, candidate solver | Mixed receiver, ALGO08v3 solver | Mixed receiver, candidate solver |",
              "|---|---:|---:|---:|---:|", "| DS30-0049 | 1.420 | 1.420 | 4.040 | 4.040 |",
              "| DS30-0086 | 0.410 | 0.457 | 0.378 | 0.382 |", "| DS30-0220 | 0.369 | 0.369 | 0.546 | 1.371 |", "",
              "On DS30-0049 the error followed the receiver packet under either solver. On DS30-0086 the "
              "mixed receiver placed both estimates closer to survey. At fixed-zero calibration its gains were "
              "3 m with the ALGO08v3 solver and 80 m with the candidate solver. Conditional RF RMS increased "
              "by about 49–50 Hz despite the geographic improvement. "
              "[Paired solver inputs, position shifts and RF fits](https://github.com/misko/leo-tracker-reduxredux/blob/"
              "021fc1bca199524db12f05f5da233ab0a5dda0e8/reports/ALGO08/v3/field-receiver-solver-cross-0086.md)"]
    lines += ["", "On DS30-0220, switching receivers with the ALGO08v3 solver added 178 m of fitted error. "
              "Switching to the candidate solver on that same mixed packet added another 825 m. Both solvers "
              "gave exactly the same position on the original 20 ms packet, so the 825 m measures a "
              "receiver–solver interaction on this recording. At fixed-zero calibration the two steps added "
              "275 m and 819 m. The fitted estimate moved 1.625 km when switching solvers on the mixed packet. "
              "[DS30-0220 four-way comparison](https://github.com/misko/leo-tracker-reduxredux/blob/"
              "3258963eb3aa9c134c0081ae4ab40287a9c16668/reports/ALGO08/v3/field-receiver-solver-cross-0220.md)"]
    lines += ["", "On that same DS30-0220 packet, the candidate provisionally assigned all 179 detections "
              "used only by the original solver's conditional fit to the same satellites. The second "
              "screen removed 156 and the later repair removed the other 23. The same stages removed 38 "
              "and 29 on DS30-0086, where the final geographic difference was small. The counts identify "
              "when the paths diverged. [Detection-by-detection screen replay](https://github.com/misko/leo-tracker-reduxredux/blob/"
              "ca74fa45e5e16028aa1d6012cd415fe689c8271a/reports/ALGO08/v3/pre-screen-owner.md)"]
    lines += ["", "### What would another speedup require?", "",
              "On the first 30 pairs, halving everything ALGO08v3 did before writing its detector packet "
              "would give **1.48× summed** end-to-end speedup. Keeping the original solver and subsequent "
              "work at their measured costs would require a **4.29×** speedup across that whole initial "
              "stage to reach both 2× targets. The model includes startup, reading, verification, decoding and "
              "detection. [Measured stage boundaries and assumptions](https://github.com/misko/leo-tracker-reduxredux/blob/"
              "96451b64b82e48a1a0564816b45cec785c1f3f98/reports/ALGO08/v3/installed-receiver-first30.md)", "",
              "The two receivers agreed on 83,058 short-aperture peaks under the prespecified matching rule. "
              "A correction for when each receiver measured the carrier changed held disagreement from "
              "97.480 to 97.460 Hz RMS after subtracting the mean for each recording and radio. The same "
              "timing model increased disagreement in fractional-sample alignment. These are receiver "
              "measurements on matching peaks. [Held predictions and unmatched peaks](https://github.com/misko/leo-tracker-reduxredux/blob/"
              "8860e704a759e549666eaa29667f0314c91fce98/reports/ALGO08/v3/first30-native-agreement.md)"]
    lines += ["", "### Changing the offered search region", "",
              "Each recording keeps its original region and causal orbit inputs in both workers. "
              "Errors use the independently recorded site "
              "authority. All recordings come from the Gauss roof. The results measure repeatability at this site.", "",
              "Two saved replays on the same physical DS30-0086 recording changed only the offered region. "
              "Moving its center 12.5 km east kept the receiver inside and moved the candidate’s fitted position "
              "by 0.16 m. Moving it 12.5 km west excluded the receiver by 5.204 km. The candidate still published "
              "on the east boundary, 5.406 km from the receiver. Its fitted RF RMS improved from 180.08 to "
              "170.33 Hz on that false fix. These replays are outside the measured runtime distribution. "
              "[Offered regions, plotted fixes and sealed evidence](https://github.com/misko/leo-tracker-reduxredux/blob/"
              "f59d67e11d4a23615258b47cd2e042d5339dc1d4/reports/ALGO08/v3/field-offer-translation-0086.md)", "",
              "A separate South simulation tested a different offered region on previously authenticated detector "
              "packets. With the receiver 1 km inside the north face, fitted errors were 1,099 m for ALGO08v3 "
              "and 363 m for the candidate. With the receiver 1 km outside, both published a false fix. "
              "The candidate's two estimates reached the north face and its 25 exterior probes still allowed "
              "publication. These saved-input trials are separate from the measured DS30 distributions. "
              "[South region test and verified products](https://github.com/misko/leo-tracker-reduxredux/blob/"
              "b8bbee45a207f6de4e766ae925de15a3dbf0c804/reports/ALGO08/v3/frozen-south-north-face.md)", "",
              "### Outcomes on the same recording", ""]
    labels = {"complete": "Fix", "withheld": "Withheld", "solver_failed": "Solver failure",
              "worker_failed": "Worker failure", "invalid_publication": "Invalid publication"}
    states = [s for s in labels if full["installed"]["outcomes"][s] or full["successor"]["outcomes"][s]]
    lines += ["| ALGO08v3 ↓ / Candidate → | " + " | ".join(labels[s] for s in states) + " | Total |",
              "|---|" + "---:|" * (len(states) + 1)]
    for a in states:
        lines.append("| " + labels[a] + " | " + " | ".join(str(joint[a, b]) for b in states) +
                     f" | {full['installed']['outcomes'][a]} |")
    lines.append("| Total | " + " | ".join(str(full["successor"]["outcomes"][b]) for b in states) + f" | {k} |")
    recovered = next((b for a, b in pairs if a["case"] == "DS30-0397" and a["outcome"] == "solver_failed"
                      and b["outcome"] == "complete" and b["fitted_c_error_km"] is not None), None)
    if recovered:
        lines += ["", "On DS30-0397 the installed solver and its retry stopped at the orbit interpolator's "
                  "time boundary. The candidate extended its orbit grid with states propagated from the "
                  "causal orbital elements and retried the interpolation inside that grid. Its fitted "
                  f"position was {recovered['fitted_c_error_km']:.3f} km from the reference. "
                  "[DS30-0397 solver and publication audit](https://github.com/misko/leo-tracker-reduxredux/blob/"
                  "5bb0489d85435688e05c1b6f6419620e5565fe33/reports/ALGO08/v3/ds30-0397-orbit-support-audit.md)"]
    moved = metadata["relocated_recordings"]
    if moved:
        lines += ["", f"For {len(moved)} recordings, the original directory moved after DS30 enrollment. "
                  "Both builds reopened the same original data. The per-recording table retains the accession, "
                  "historical and reopened input identities and the digest of each relocation proof."]
    lines += ["", f"The combined per-recording input has SHA-256 `{receipt_digest}`."]
    if renderer_revision is not None:
        lines[-1] += (f" Report renderer `{renderer_revision[:12]}`. "
                      "[Reproduce the figures from the sealed export](https://github.com/misko/leo-tracker-reduxredux/"
                      f"blob/{renderer_revision}/reports/ALGO08/v3/full-successor-field-protocol.md)")
    lines += ["", "[Per-recording results](recordings.csv) · [Machine-readable summary and provenance](summary.json)", ""]
    (output / "README.md").write_text("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipts", type=Path, help="Final checked per-recording worker export, JSON lines")
    parser.add_argument("output", type=Path)
    parser.add_argument("--expected-sha256", help="Pin the complete JSON-lines export to the published SHA-256")
    parser.add_argument("--renderer-revision", help="Full Git revision of the checked-out renderer")
    parser.add_argument("--offered-region", type=Path, help="The frozen campaign offer.json for scoring the search center")
    args = parser.parse_args()
    path_bytes = args.receipts.read_bytes()
    export_sha256 = sha256(path_bytes).hexdigest()
    if args.expected_sha256 is not None and args.expected_sha256.removeprefix("sha256:") != export_sha256:
        parser.error("The worker export differs from the expected SHA-256")
    assigned = roster()
    raw_rows = [json.loads(line) for line in path_bytes.splitlines() if line.strip()]
    actual_pairs = paired_rows(raw_rows, assigned)
    prior = None
    if args.offered_region is not None:
        prior = compare_centers(actual_pairs, assigned, json.loads(checked(args.offered_region.read_bytes(), OFFER)))
        prior["offered_region_sha256"] = OFFER
    write_report(actual_pairs, args.output, {case: r["release_100"] for case, r in assigned.items()},
                 export_sha256, renderer_revision=args.renderer_revision,
                 position_moments=shared_position_moments(raw_rows, assigned), prior=prior,
                 capture_days=capture_day_sensitivity(actual_pairs, assigned))
