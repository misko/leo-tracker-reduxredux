"""Score the frozen receiver duty trials and waveform timings from saved receipts."""

import argparse
import gzip
import json
import math
import re
from itertools import permutations, product
from pathlib import Path
from statistics import median

from ..scoring import ARMS, NUMERICAL_TOLERANCE_KM, distance_km, distribution, validate_result
from ..variants.channel_schedule import SCHEDULES, scheduled
from .prefix_figures import REPORT as CHECKPOINTS
from .prefix_figures import TIMING_IDS, csv_file, fresh_pairs, load_rows

REPORT = CHECKPOINTS.with_name("2026_11_19_receiver_duty")
CHANNELS = ("v5_core", *SCHEDULES)
PROJECTOR = ("v5_lean", "orbit_projector")
STUDIES = {"channel": CHANNELS, "projector": PROJECTOR}
IQ_CASES = ("DS26-0036", "DS29-0082")
IQ_MODES = tuple(product(("original", "accelerated"), ("all", *SCHEDULES)))


def _sha256(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _positive(value):
    return _finite(value) and value > 0


def _count(value):
    return type(value) is int and value >= 0


def _paired_receipts(path, orders):
    roster = dict(zip(TIMING_IDS, orders, strict=True))
    expected = {(case, method) for case, order in roster.items() for method in order}
    with gzip.open(path, "rt") as stream:
        rows = list(map(json.loads, stream))
    pairs = {(r["id"], r["method"]): r for r in rows}
    if len(rows) != len(pairs) or pairs.keys() != expected:
        raise ValueError(f"{path.name} must contain exactly the frozen recording and method pairs")
    for case, order in roster.items():
        for index, method in enumerate(order):
            row = pairs[case, method]
            result = row["result"]
            validate_result(result)
            if type(row.get("execution_order")) is not int or row["execution_order"] != index:
                raise ValueError(f"{case} {method} did not follow the prescribed execution order")
            if not _count(row.get("cpu")) or row["cpu"] != pairs[case, order[0]]["cpu"]:
                raise ValueError(f"{case} {method} did not run on the paired CPU")
            wall, call = row.get("worker_wall_s"), row.get("call_s")
            if not _positive(wall) or (call is not None and (not _positive(call) or call > wall)):
                raise ValueError(f"{case} {method} recorded an invalid worker time")
            bound = call is not None and _sha256(row.get("implementation_sha256"))
            if result["status"] in {"ok", "withheld"} and (not bound or "arms" not in result):
                raise ValueError(f"{case} {method} is missing its bound worker result")
            for arm in ARMS:
                _, rms, score = _position_values(result, arm)
                if rms is not None and (not _finite(rms) or rms < 0):
                    raise ValueError(f"{case} {method} {arm} recorded an invalid frequency RMS")
                if score is not None and not _finite(score):
                    raise ValueError(f"{case} {method} {arm} recorded an invalid frequency score")
    if len({pairs[c, order[0]]["cpu"] for c, order in roster.items()}) != len(roster):
        raise ValueError(f"{path.name} requires a different pinned CPU for each recording")
    return pairs


def _versions(pairs, method):
    return {pairs[case, method].get("implementation_sha256") for case in TIMING_IDS} - {None}


def _validate_channel_counts(case, channel):
    metrics = []
    for schedule, channels in SCHEDULES.items():
        result = channel[case, schedule]["result"]
        if result["status"] not in {"ok", "withheld"}:
            continue
        m = result["metrics"]
        counts = m.get("valid_visits_by_channel", [])
        if (
            m.get("schedule") != schedule
            or m.get("channels") != list(channels)
            or len(counts) != 8
            or not all(map(_count, counts))
            or m.get("original_valid_visits") != sum(counts)
            or m.get("kept_valid_visits") != sum(counts[c - 1] for c in channels)
            or not all(_count(m.get(k)) for k in ("original_probes", "kept_probes"))
            or m["kept_probes"] > m["original_probes"]
        ):
            raise ValueError(f"{case} {schedule} has inconsistent channel counts")
        metrics.append(m)
    if len(metrics) == 2:
        odd, even = metrics
        if (
            odd["valid_visits_by_channel"] != even["valid_visits_by_channel"]
            or odd["original_probes"] != even["original_probes"]
            or odd["kept_probes"] + even["kept_probes"] != odd["original_probes"]
        ):
            raise ValueError(f"{case} odd and even schedules do not partition the archive probes")


def _measurements(directory, checkpoints, cases):
    previous, _ = fresh_pairs(checkpoints / "paired.jsonl.gz", cases)
    channel = _paired_receipts(directory / "channel-pairs.jsonl.gz", tuple(permutations(CHANNELS)))
    projector = _paired_receipts(
        directory / "projector-pairs.jsonl.gz",
        tuple(PROJECTOR if i % 2 == 0 else PROJECTOR[::-1] for i in range(len(TIMING_IDS))),
    )
    pairs = channel | projector
    for case in TIMING_IDS:
        input_digest = previous[case]["input_sha256"]
        cpu = channel[case, "v5_core"]["cpu"]
        for method in (*CHANNELS, *PROJECTOR):
            row = pairs[case, method]
            if not _sha256(input_digest) or row.get("input_sha256") != input_digest:
                raise ValueError(f"{case} {method} input differs from the frozen paired input")
            if row["cpu"] != cpu:
                raise ValueError(f"{case} {method} changed the pinned CPU between studies")
        _validate_channel_counts(case, channel)
        stages = cases[case][2]["stages"]
        for method, stage in (("v5_core", "cavity"), ("v5_lean", "final")):
            result = pairs[case, method]["result"]
            for arm in ARMS:
                point = result.get("arms", {}).get(arm, {}).get("latlon")
                separation = distance_km(point, stages[stage][arm]["latlon"])
                if separation is None or separation > 1e-6:
                    raise ValueError(f"{case} {method} {arm} differs from the archived {stage}")
    for method in ("v5_core", *PROJECTOR):
        if len(_versions(pairs, method)) > 1:
            raise ValueError(f"{method} changed implementation within the trial")
    return pairs


def measurements(directory, checkpoints=CHECKPOINTS):
    """Return validated raw location receipts keyed by recording ID and method."""
    return _measurements(directory, checkpoints, load_rows(checkpoints))


def _difference(value, baseline):
    return None if value is None or baseline is None else value - baseline


def _position_values(result, arm):
    values = result.get("arms", {}).get(arm, {})
    metrics = result["metrics"]
    return (
        values.get("latlon"),
        values.get("rf_rms_hz", metrics.get(f"{arm}_conditional_rms_hz")),
        metrics.get(f"{arm}_frequency_score"),
    )


def error_rows(pairs, cases):
    rows = []
    for study, methods in STUDIES.items():
        control = methods[0]
        for case, method in product(TIMING_IDS, methods):
            ref, _, checkpoint = cases[case]
            result = pairs[case, method]["result"]
            comparator = pairs[case, control]["result"]
            c0_point, c0_rms, c0_score = _position_values(result, "c0")
            c0_error = distance_km(c0_point, ref["truth"])
            for arm in ARMS:
                point, rms, score = _position_values(result, arm)
                control_point, control_rms, _ = _position_values(comparator, arm)
                cavity = checkpoint["stages"]["cavity"][arm]["latlon"]
                v5 = checkpoint["stages"]["final"][arm]["latlon"]
                error = distance_km(point, ref["truth"])
                control_error = distance_km(control_point, ref["truth"])
                v5_error = distance_km(v5, ref["truth"])
                fitted = arm == "fitted_c"
                rows.append(
                    dict(
                        study=study,
                        recording=case,
                        dataset=ref["group"],
                        method=method,
                        arm=arm,
                        status=result["status"],
                        reason=result.get("reason"),
                        error_km=error,
                        control=control,
                        control_error_km=control_error,
                        delta_error_vs_control_km=_difference(error, control_error),
                        v5_error_km=v5_error,
                        delta_error_vs_v5_km=_difference(error, v5_error),
                        moved_from_v5_km=distance_km(point, v5),
                        moved_from_cavity_km=distance_km(point, cavity),
                        conditional_rms_hz=rms,
                        control_conditional_rms_hz=control_rms,
                        delta_rms_vs_control_hz=_difference(rms, control_rms),
                        frequency_score=score,
                        fitted_minus_c0_error_km=_difference(error, c0_error) if fitted else None,
                        fitted_minus_c0_rms_hz=_difference(rms, c0_rms) if fitted else None,
                        fitted_minus_c0_frequency_score=(
                            _difference(score, c0_score) if fitted else None
                        ),
                    )
                )
    return rows


def distributions(rows):
    groups = {}
    for row in rows:
        for dataset in ("all", row["dataset"]):
            groups.setdefault((row["study"], dataset, row["method"], row["arm"]), []).append(row)
    out = []
    for (study, dataset, method, arm), entries in groups.items():
        stats = distribution(r["error_km"] for r in entries)
        v5 = distribution(r["v5_error_km"] for r in entries)
        within5 = sum(r["error_km"] is not None and r["error_km"] <= 5 for r in entries)
        v5_within5 = sum(r["v5_error_km"] is not None and r["v5_error_km"] <= 5 for r in entries)
        losses = distribution(r["delta_error_vs_v5_km"] for r in entries)
        control_losses = distribution(r["delta_error_vs_control_km"] for r in entries)
        rms = distribution(r["conditional_rms_hz"] for r in entries)
        keep = stats["n"] >= v5["n"] and within5 >= v5_within5 and stats["n"] > 0 and v5["n"] > 0
        out.append(
            dict(
                study=study,
                dataset=dataset,
                method=method,
                arm=arm,
                attempts=len(entries),
                fixes=stats["n"],
                within5=within5,
                p50_km=stats["p50"],
                p95_km=stats["p95"],
                worst_km=stats["max"],
                v5_fixes=v5["n"],
                v5_within5=v5_within5,
                v5_p50_km=v5["p50"],
                v5_p95_km=v5["p95"],
                lost_v5_fixes=sum(
                    r["error_km"] is None and r["v5_error_km"] is not None for r in entries
                ),
                max_delta_vs_v5_km=losses["max"],
                max_delta_vs_control_km=control_losses["max"],
                cavity_within_1m=sum(
                    r["moved_from_cavity_km"] is not None
                    and r["moved_from_cavity_km"] <= NUMERICAL_TOLERANCE_KM
                    for r in entries
                ),
                median_conditional_rms_hz=rms["p50"],
                rms_recordings=rms["n"],
                median_fitted_minus_c0_error_km=distribution(
                    r["fitted_minus_c0_error_km"] for r in entries
                )["p50"],
                median_fitted_minus_c0_rms_hz=distribution(
                    r["fitted_minus_c0_rms_hz"] for r in entries
                )["p50"],
                median_fitted_minus_c0_frequency_score=distribution(
                    r["fitted_minus_c0_frequency_score"] for r in entries
                )["p50"],
                keeps_v5_5pct=keep and all(stats[k] <= v5[k] * 1.05 for k in ("p50", "p95")),
                keeps_v5_10pct=keep and all(stats[k] <= v5[k] * 1.10 for k in ("p50", "p95")),
            )
        )
    return out


def runtime_rows(pairs, cases):
    out = []
    for study, methods in STUDIES.items():
        hashes = {method: len(_versions(pairs, method)) for method in methods}
        for case, method in product(TIMING_IDS, methods):
            row, control = pairs[case, method], pairs[case, methods[0]]
            result = row["result"]
            metrics = result["metrics"]
            paired = result["status"] == control["result"]["status"] == "ok"
            out.append(
                dict(
                    study=study,
                    recording=case,
                    dataset=cases[case][0]["group"],
                    method=method,
                    control=methods[0],
                    status=result["status"],
                    cpu=row["cpu"],
                    execution_order=row["execution_order"],
                    implementation_sha256=row.get("implementation_sha256"),
                    implementation_versions=hashes[method],
                    input_sha256=row["input_sha256"],
                    wall_s=row["worker_wall_s"],
                    control_wall_s=control["worker_wall_s"],
                    speedup=control["worker_wall_s"] / row["worker_wall_s"] if paired else None,
                    observations=metrics.get("observations", metrics.get("native_observations")),
                    tracks=metrics.get("tracks"),
                    original_valid_visits=metrics.get("original_valid_visits"),
                    kept_valid_visits=metrics.get("kept_valid_visits"),
                    kept_probes=metrics.get("kept_probes"),
                    original_probes=metrics.get("original_probes"),
                    compact_projection_bytes=metrics.get("max_prepared_bytes"),
                    original_grid_bytes=metrics.get("original_grid_bytes_at_largest_shape"),
                )
            )
    return out


def _iq_receipt(path, case):
    with gzip.open(path, "rt") as stream:
        data = json.load(stream)
    rows, cpus = data["rows"], data["cpus"]
    if data["case"] != case or len(cpus) != 1 or not _count(cpus[0]):
        raise ValueError(f"{case} IQ receipt has the wrong recording or CPU affinity")
    if [(r["segment"], r["sequence"]) for r in rows] != list(product((3, 10), range(8))):
        raise ValueError(f"{case} IQ receipt does not have the 16 prescribed windows")
    if len({r["visit"] for r in rows}) != len(rows):
        raise ValueError(f"{case} IQ receipt repeats a visit")
    mode_names = {f"{engine}/{schedule}" for engine, schedule in IQ_MODES}
    n_modes = len(IQ_MODES)
    for i, row in enumerate(rows):
        shift = i % n_modes
        order = IQ_MODES[shift:] + IQ_MODES[:shift]
        if i // n_modes % 2:
            order = order[::-1]
        if [tuple(pair) for pair in row["order"]] != list(order):
            raise ValueError(f"{case} visit {row['visit']} IQ timing order changed")
        if any(set(row[field]) != mode_names for field in ("timing", "equal")):
            raise ValueError(f"{case} visit {row['visit']} is missing an IQ mode")
        digest = row.get("iq_sha256")
        if not isinstance(digest, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
            raise ValueError(f"{case} visit {row['visit']} is missing its waveform digest")
        for engine, schedule in IQ_MODES:
            name = f"{engine}/{schedule}"
            called = schedule == "all" or scheduled(schedule, row["channel"])
            times, equal = row["timing"][name], row["equal"][name]
            label = f"{case} visit {row['visit']} {name}"
            valid_comparison = isinstance(equal, bool) if called else equal is None
            if times["called"] is not called or not valid_comparison:
                raise ValueError(f"{label} detector invocation changed")
            if not all(_positive(times.get(field)) for field in ("wall_s", "cpu_s")):
                raise ValueError(f"{label} recorded an invalid detector time")
        if row["equal"]["original/all"] is not True:
            raise ValueError(f"{case} IQ reference disagrees with itself")
    return data


def iq_rows(directory):
    out = []
    data = [_iq_receipt(directory / f"{case}-iq.json.gz", case) for case in IQ_CASES]
    for field in ("kernel_sha256", "kernel_source_sha256", "anchor_grid_sha256"):
        digests = {d.get(field) for d in data}
        if len(digests) != 1 or not all(map(_sha256, digests)):
            raise ValueError(f"{field} differs between waveform clips")
    for receipt in data:
        rows, audit = receipt["rows"], receipt["archive_audit"]
        baseline_wall = sum(r["timing"]["original/all"]["wall_s"] for r in rows)
        baseline_cpu = sum(r["timing"]["original/all"]["cpu_s"] for r in rows)
        for engine, schedule in IQ_MODES:
            name = f"{engine}/{schedule}"
            called = [r for r in rows if r["timing"][name]["called"]]
            processed = [r for r in called if r["policy_status"] == "processed"]
            processed_times = [r["timing"][name]["wall_s"] for r in processed]
            wall = sum(r["timing"][name]["wall_s"] for r in rows)
            cpu = sum(r["timing"][name]["cpu_s"] for r in rows)
            same_schedule_wall = sum(r["timing"][f"original/{schedule}"]["wall_s"] for r in rows)
            out.append(
                dict(
                    recording=receipt["case"],
                    pinned_cpu=receipt["cpus"][0],
                    engine=engine,
                    schedule=schedule,
                    windows=len(rows),
                    detector_calls=len(called),
                    processed=len(processed),
                    invalid_capture=sum(r["policy_status"] == "invalid_capture" for r in called),
                    equal_reference=sum(r["equal"][name] is True for r in called),
                    unequal_reference=sum(r["equal"][name] is False for r in called),
                    retained_reference_candidates=sum(r["n_candidates"] for r in processed),
                    wall_s=wall,
                    cpu_s=cpu,
                    original_all_wall_s=baseline_wall,
                    original_all_cpu_s=baseline_cpu,
                    speedup_wall_vs_original_all=baseline_wall / wall,
                    speedup_cpu_vs_original_all=baseline_cpu / cpu,
                    speedup_wall_vs_original_schedule=same_schedule_wall / wall,
                    median_processed_call_wall_s=median(processed_times)
                    if processed_times
                    else None,
                    archived_probe_rows=audit["archived_probe_rows"],
                    exact_archived_probe_rows=audit["exact_probe_rows"],
                    differing_archived_probe_rows=len(audit["different_probe_keys"]),
                    archive_exclusions_equal=audit["archive_exclusions_equal"],
                )
            )
    return out


def build(directory, checkpoints, output):
    cases = load_rows(checkpoints)
    pairs = _measurements(directory, checkpoints, cases)
    errors = error_rows(pairs, cases)
    tables = {
        "paired-errors": errors,
        "paired-runtime": runtime_rows(pairs, cases),
        "paired-distributions": distributions(errors),
        "iq-timing": iq_rows(directory),
    }
    for name, rows in tables.items():
        csv_file(output / f"{name}.csv", rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=REPORT)
    parser.add_argument("--checkpoints", type=Path, default=CHECKPOINTS)
    parser.add_argument("--out", type=Path, default=REPORT)
    args = parser.parse_args()
    build(args.data, args.checkpoints, args.out)


if __name__ == "__main__":
    main()
