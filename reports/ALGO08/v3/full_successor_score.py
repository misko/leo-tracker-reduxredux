"""Score immutable DS30 predictions after benchmark workers finish."""

import argparse
from collections import Counter
import csv
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


def score_arms(arms, reference):
    output = {}
    for name in ARMS:
        arm = arms[name]
        point, rms = coordinate(arm["latlon"]), arm["rf_rms_hz"]
        if rms is not None and (not math.isfinite(rms) or rms < 0):
            raise ValueError("Invalid calibrated RF residual")
        output.update({name + "_fix": point is not None, name + "_error_km": distance_km(reference, point),
                       name + "_rf_rms_hz": rms})
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


def write_report(pairs, output, enrollment, receipt_digest):
    from reports.ALGO08.v3.full_successor_figures import render_distribution_figures

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
        stats = dict(assigned=len(group), wall=paired_timing(group, "elapsed_s"), cpu=paired_timing(group, "cpu_s"))
        for i, role in enumerate(BUILDS):
            rows = [p[i] for p in group]
            stats[role] = dict(outcomes=Counter(r["outcome"] for r in rows), wall_s=distribution([r["elapsed_s"] for r in rows]),
                               cpu_s=distribution([r["cpu_s"] for r in rows]), **outcomes_summary(rows, population))
        summaries[name] = stats
    metadata = dict(source_manifest_sha256=MANIFEST, reference_audit_sha256=REFERENCE, attempt_export_sha256=receipt_digest,
                    builds={r["algorithm"]: r["build_sha256"] for r in pairs[0]}, cohorts=summaries)
    full = summaries["All DS30 recordings"]
    gates = {metric: full["wall"][metric] >= 2.0 for metric in ("summed_speedup", "median_paired_speedup")}
    metadata["twofold_wall_time_target"] = {"required_speedup": 2.0, **gates, "both_met": all(gates.values())}
    changes = {}
    for arm in ARMS:
        key = arm + "_error_km"
        delta = [(b[key] - a[key], a["case"]) for a, b in pairs if a[key] is not None and b[key] is not None]
        changes[arm] = dict(shared=len(delta), candidate_minus_installed_km=distribution([d for d, _ in delta]),
                            gained=sum(not a[arm + "_fix"] and b[arm + "_fix"] for a, b in pairs),
                            lost=sum(a[arm + "_fix"] and not b[arm + "_fix"] for a, b in pairs),
                            largest_increases=sorted((item for item in delta if item[0] > 0), reverse=True)[:5])
    metadata["paired_error_changes"] = changes
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

    lines = ["# DS30 field report · ALGO08v3 and its single-core successor", "",
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
              "The second worker can benefit from pages cached by the first.", "", "## Position error", "",
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
    lines += ["", "| Paired change | Shared scored fixes | Fixes gained / lost | Median / P90 candidate minus ALGO08v3 error (m) |",
              "|---|---:|---:|---:|"]
    for arm in ARMS:
        c = changes[arm]
        delta = c["candidate_minus_installed_km"]
        metres = [number(1000 * delta[p], 1) if delta[p] is not None else "—" for p in ("p50", "p90")]
        lines.append(f"| {dict(c0='Fixed zero', fitted_c='Fitted')[arm]} | {c['shared']} | {c['gained']} / {c['lost']} | "
                     f"{metres[0]} / {metres[1]} |")
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
    lines += ["", "A separate crossover on DS30-0049 tested both solvers on each saved receiver output. "
              "Both solvers returned 1.420 km fitted error on the installed detections and 4.040 km on the "
              "candidate detections. The receiver change accounted for the difference on this recording. "
              "[DS30-0049 crossover and verification](https://github.com/misko/leo-tracker-reduxredux/blob/"
              "5dad70d7d0c273b2aa17fa546d622bcd8e490789/reports/ALGO08/v3/ds30-0049-saved-crossover.md)"]
    lines += ["",
              "Each recording keeps its original region and causal orbit inputs in both workers. "
              "Errors use the independently recorded site "
              "authority. All recordings come from the Gauss roof. The results measure repeatability at this site.", "",
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
    lines += ["", "[Per-recording results](recordings.csv) · [Machine-readable summary and provenance](summary.json)", ""]
    (output / "README.md").write_text("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipts", type=Path, help="Final checked per-recording worker export, JSON lines")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    path_bytes = args.receipts.read_bytes()
    assigned = roster()
    actual_pairs = paired_rows([json.loads(line) for line in path_bytes.splitlines() if line.strip()], assigned)
    write_report(actual_pairs, args.output, {case: r["release_100"] for case, r in assigned.items()},
                 sha256(path_bytes).hexdigest())
