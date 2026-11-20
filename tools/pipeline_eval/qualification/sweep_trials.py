"""Evaluate a fixed alternate-sweep schedule against the matched archived controls."""

import argparse
import gzip
import hashlib
import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from ..__main__ import (
    DEFAULT_OUT,
    ROOT,
    encoded,
    local_output,
    public_cases,
    references,
    save_json,
    write,
)
from ..scoring import ARMS, distance_km, distribution, validate_result
from ..variants import sweep_schedule
from .duty_results import REPORT as DUTY_REPORT
from .prefix_figures import TIMING_IDS, csv_file

REPORT = ROOT / "reports/2026_11_19_receiver_streaming/sweep"
METHOD = sweep_schedule.METHOD
CONTROLS = ("v5_core", "glrt_odd_channels", "glrt_even_channels")
METHODS = (*CONTROLS, "original-baseline", METHOD)


def recording_refs():
    panels = {}
    for panel, prefix in (("ds26-common127", "DS26"), ("roof16", "DS29")):
        panels[panel] = references(panel, [c for c in TIMING_IDS if c.startswith(prefix)])[1]
    return panels


def historical_controls():
    with gzip.open(DUTY_REPORT / "channel-pairs.jsonl.gz", "rt") as stream:
        rows = list(map(json.loads, stream))
    controls = {(r["id"], r["method"]): r for r in rows}
    if len(controls) != len(rows) or controls.keys() != {
        (case, method) for case in TIMING_IDS for method in CONTROLS
    }:
        raise ValueError("archived controls must cover the frozen roster exactly")
    for case in TIMING_IDS:
        paired = [controls[case, method] for method in CONTROLS]
        if len({r["input_sha256"] for r in paired}) != 1:
            raise ValueError(f"{case} control inputs differ")
        if paired[0]["implementation_sha256"] != sweep_schedule.CAVITY_SHA256:
            raise ValueError(f"{case} full-channel solver differs from the pinned implementation")
    return controls


def trial(cavity, scratch, report, cpus):
    scratch = local_output(scratch)
    report = local_output(report)
    scratch.mkdir(parents=True, exist_ok=True)
    if (
        len(cpus) != len(TIMING_IDS)
        or len(set(cpus)) != len(cpus)
        or not set(cpus) <= os.sched_getaffinity(0)
    ):
        raise ValueError("choose a distinct available CPU for each recording")
    source = sweep_schedule.cavity_source(cavity)
    pinned = report / "cavity-source.py.gz"
    write(pinned, gzip.compress(source, mtime=0))
    controls = historical_controls()
    cases = {
        case["id"]: case
        for panel, refs in recording_refs().items()
        for case in public_cases(panel, refs, DEFAULT_OUT / "inputs")
    }
    for ident, case in cases.items():
        digest = hashlib.sha256(encoded(case)).hexdigest()
        if digest != controls[ident, "v5_core"]["input_sha256"]:
            raise ValueError(f"{ident} input differs from the archived control")
    digest = hashlib.sha256(Path(sweep_schedule.__file__).read_bytes()).hexdigest()

    def run(ident, cpu):
        affinity = os.sched_getaffinity(0)
        try:
            os.sched_setaffinity(0, {cpu})
            with tempfile.TemporaryDirectory(prefix=f"{ident}-", dir=scratch) as work:
                start = perf_counter()
                result = sweep_schedule.run(cases[ident], Path(work), pinned)
                elapsed = perf_counter() - start
        finally:
            os.sched_setaffinity(0, affinity)
        validate_result(result)
        row = dict(
            id=ident,
            method=METHOD,
            result=result,
            cpu=cpu,
            worker_wall_s=elapsed,
            implementation_sha256=digest,
            input_sha256=controls[ident, "v5_core"]["input_sha256"],
        )
        save_json(scratch / f"{ident}.json", row)
        print(ident, result["status"], round(elapsed, 2), flush=True)
        return row

    with ThreadPoolExecutor(max_workers=len(cpus)) as pool:
        jobs = [pool.submit(run, ident, cpu) for ident, cpu in zip(TIMING_IDS, cpus, strict=True)]
        rows = [job.result() for job in jobs]
    data = b"".join(encoded(row) + b"\n" for row in rows)
    write(report / "positions.jsonl.gz", gzip.compress(data, mtime=0))
    score(report)


def position_and_frequency(refs, controls, predictions):
    position, frequency = [], []
    for ident in TIMING_IDS:
        ref, prediction = refs[ident], predictions[ident]
        full = controls[ident, "v5_core"]["result"]
        for method in METHODS:
            if method == METHOD:
                result = prediction["result"]
            elif method in CONTROLS:
                result = controls[ident, method]["result"]
            else:
                result = {"status": "ok", "arms": ref["reference"]["baseline"]}
            for arm in ARMS:
                output = result.get("arms", {}).get(arm, {})
                error = distance_km(output.get("latlon"), ref["truth"])
                control_error = distance_km(full["arms"][arm]["latlon"], ref["truth"])
                position.append(
                    dict(
                        recording=ident,
                        method=method,
                        arm=arm,
                        status=result["status"],
                        error_km=error,
                        difference_vs_cavity_km=(
                            error - control_error if error is not None else None
                        ),
                    )
                )
                if method != "original-baseline":
                    frequency.append(
                        dict(
                            recording=ident,
                            method=method,
                            arm=arm,
                            status=result["status"],
                            conditional_rms_hz=output.get("rf_rms_hz"),
                        )
                    )
    return position, frequency


def paired_calibration(rows, metric):
    arms = {(r["recording"], r["arm"]): r[metric] for r in rows}
    return distribution(
        fitted - zero if fitted is not None and zero is not None else None
        for case in TIMING_IDS
        for zero, fitted in [(arms[case, "c0"], arms[case, "fitted_c"])]
    )


def workload_rows(predictions):
    workload, track_rows = [], []
    for ident in TIMING_IDS:
        metrics = predictions[ident]["result"]["metrics"]
        row = {"recording": ident}
        for name in ("scheduled_visits", "processed_visits", "probes", "delivery_span_s"):
            for prefix in ("original", "kept"):
                key = f"{prefix}_{name}"
                row[key] = metrics.get(key)
        for prefix in ("original", "kept"):
            row[f"{prefix}_excluded_visits"] = (
                sum(metrics[f"{prefix}_exclusions"].values())
                if f"{prefix}_exclusions" in metrics
                else None
            )
        workload.append(row)
        support = metrics.get("full_track_support", [])
        samples = metrics.get("half_track_sizes", [])
        track_rows.append(
            dict(
                recording=ident,
                full_observations=metrics.get("full_observations"),
                half_observations=metrics.get("half_observations"),
                full_graph_points=metrics.get("full_graph_points"),
                half_graph_points=metrics.get("half_graph_points"),
                full_curved_tracks=metrics.get("full_curved_tracks"),
                half_curved_tracks=metrics.get("half_curved_tracks"),
                full_tracks=len(support),
                half_tracks=len(samples),
                full_median_points_per_track=distribution(r["full_points"] for r in support)["p50"],
                half_median_points_per_track=distribution(samples)["p50"],
                full_tracks_with_one_or_zero_retained_points=sum(
                    r["retained_points"] < 2 for r in support
                ),
                full_tracks_with_no_overlap_after_retracking=sum(
                    r["retracked_points"] == 0 for r in support
                ),
                full_tracks_overlapping_multiple_new_tracks=sum(
                    r["retracked_fragments"] > 1 for r in support
                ),
                median_original_track_fraction_retained=distribution(
                    r["retained_points"] / r["full_points"] for r in support
                )["p50"],
                median_original_track_fraction_in_best_overlap=distribution(
                    r["largest_overlap"] / r["full_points"] for r in support
                )["p50"],
            )
        )
    return workload, track_rows


def score(report):
    with gzip.open(report / "positions.jsonl.gz", "rt") as stream:
        rows = list(map(json.loads, stream))
    if [r["id"] for r in rows] != list(TIMING_IDS) or any(r["method"] != METHOD for r in rows):
        raise ValueError("sweep predictions must cover the fixed roster in order")
    predictions = {r["id"]: r for r in rows}
    refs = {r["id"]: r for rows in recording_refs().values() for r in rows}
    controls = historical_controls()
    for ident, row in predictions.items():
        result = row["result"]
        validate_result(result)
        control = controls[ident, "v5_core"]
        if row["input_sha256"] != control["input_sha256"]:
            raise ValueError(f"{ident} sweep and control inputs differ")
        metrics = result["metrics"]
        if result["status"] in ("ok", "withheld") and (
            metrics["cavity_sha256"] != control["implementation_sha256"]
            or metrics.get("full_observations") != control["result"]["metrics"]["observations"]
            or len(metrics["full_track_support"]) != control["result"]["metrics"]["tracks"]
        ):
            raise ValueError(f"{ident} used a different full-channel graph or solver")
    position, frequency = position_and_frequency(refs, controls, predictions)
    csv_file(report / "position-errors.csv", position)
    csv_file(report / "conditional-frequency-rms.csv", frequency)
    workload, track_rows = workload_rows(predictions)
    csv_file(report / "visit-load.csv", workload)
    csv_file(report / "track-support.csv", track_rows)
    summary = {}
    for method in METHODS:
        location_rows = [r for r in position if r["method"] == method]
        frequency_rows = [r for r in frequency if r["method"] == method]
        location, rms = {}, {}
        for arm in ARMS:
            errors = [r["error_km"] for r in location_rows if r["arm"] == arm]
            deltas = [r["difference_vs_cavity_km"] for r in location_rows if r["arm"] == arm]
            location[arm] = dict(
                error_km=distribution(errors),
                within_5_km=sum(v is not None and v <= 5 for v in errors),
                difference_vs_cavity_km=distribution(deltas),
                roster_size=len(errors),
            )
            if frequency_rows:
                rms[arm] = distribution(
                    r["conditional_rms_hz"] for r in frequency_rows if r["arm"] == arm
                )
        location["fitted_minus_zero_km"] = paired_calibration(location_rows, "error_km")
        if frequency_rows:
            rms["fitted_minus_zero_hz"] = paired_calibration(frequency_rows, "conditional_rms_hz")
        summary[method] = dict(position=location, conditional_rms_hz=rms)
    save_json(report / "summary.json", summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--cavity-source", type=Path)
    parser.add_argument("--scratch", type=Path)
    parser.add_argument("--cpus", nargs=6, type=int)
    parser.add_argument("--score-only", action="store_true")
    args = parser.parse_args()
    if args.score_only:
        score(local_output(args.report))
    else:
        if args.scratch is None or args.cpus is None:
            parser.error("--scratch and --cpus are required when running the workers")
        trial(
            args.cavity_source or args.report / "cavity-source.py.gz",
            args.scratch,
            args.report,
            args.cpus,
        )
