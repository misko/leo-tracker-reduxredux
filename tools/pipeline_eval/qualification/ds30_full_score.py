"""Verify DS30 predictions before unlocking reference coordinates and scoring both receivers."""

import argparse
from collections import Counter
from pathlib import Path

from ..scoring import ARMS, distance_km, distribution, validate_result
from . import blind_compact_run, ds30_panel, original_v5
from .blind_compact_roster import seal
from .ds30_full import verified_bytes
from .ds30_full_inputs import DS29, METHODS, OUT, WORK, checked_source, frozen_members
from .full_v5_check import _sha
from .reverse_glrt_reference import read_bound
from .reverse_glrt_report import read, write_csv
from .timing_first_position import full_identity

GROUPS = (
    "all",
    "new",
    "complete",
    "new_complete",
    "incomplete",
    "archived_original",
    "fresh_original",
    "fresh_original_complete",
    "previous",
)


def belongs(row, group):
    complete = row["recording_state"] == "complete"
    return {
        "all": True,
        "new": not row["previous"],
        "complete": complete,
        "new_complete": complete and not row["previous"],
        "incomplete": not complete,
        "previous": row["previous"],
        "archived_original": row["archived_original"],
        "fresh_original": not row["archived_original"],
        "fresh_original_complete": not row["archived_original"] and complete,
    }[group]


def comparable_request(request):
    job = dict(request["job"])
    del job["output_root"]
    return dict(request, job=job)


def lock():
    cohort = read(OUT / "cohort.json")
    build = read(OUT / "build.json")
    verified_bytes(OUT / "PROTOCOL.md", cohort["protocol_sha256"])
    verified_bytes(OUT / "cohort.json", build["roster_sha256"])
    for name in ("original", "cancellation"):
        verified_bytes(blind_compact_run.LIBS[name], build["libraries"][name])
    for edge, expected in build["assets"].items():
        verified_bytes(blind_compact_run.TWO_WORK / "embedded" / (edge + ".f32"), expected)
    ds_sha, members = frozen_members()
    originals = {m["dataset_label"]: m for m in members}
    if cohort["dataset_sha256"] != ds_sha or len(cohort["members"]) != len(originals):
        raise ValueError("validation roster differs from frozen membership")
    locked, records, sessions = [], [], set()
    for assignment in cohort["members"]:
        name = assignment["id"]
        member = originals.pop(name)
        if not member["tracking_inputs"]:
            for entry in member["source_inputs"]:
                checked_source(entry)
        if (
            assignment["content"] != member["raw_recording"]["identity_sha256"]
            or assignment["windows"] != member["window_count"]
            or assignment["archived_original"] != bool(member["tracking_inputs"])
            or assignment["recording_state"] != member["recording_state"]
        ):
            raise ValueError("assignment differs from the frozen recording")
        entry = WORK / "bindings" / (name + ".json")
        record = read(entry)
        case = record["case"]
        if (
            record["roster_sha256"] != build["roster_sha256"]
            or record["archived_original"] != assignment["archived_original"]
        ):
            raise ValueError("incorrect case-binding parent")
        parent = read_bound(case["request"])
        if (
            parent["role"] != "baseline"
            or parent["job"]["evaluation_reference"] is not None
            or parent["job"]["identity"]["run_id"] != full_identity(name, parent)
            or parent["job"]["scan_identities"] != [case["session_id"]]
            or case["id"] != name
            or case["session_id"] in sessions
        ):
            raise ValueError(
                "incorrect baseline identity, duplicate session or disclosed reference"
            )
        sessions.add(case["session_id"])
        native = read_bound(case["native"])
        case["hardware_span_s"] = (
            native["last_sample_counter"] - native["clock_anchor"]["sample_counter"]
        ) / native["source"]["sample_rate_hz"]
        if (
            native["source"]["raw_recording_authority_digest"] != case["raw_authority"]
            or case["hardware_span_s"] < 0
        ):
            raise ValueError("native timing and recording authority disagree")
        del native
        for method in METHODS:
            root = WORK / "runs" / name / method
            outcome = root / "outcome.json"
            receipt = read(outcome)
            if (
                (receipt["case"], receipt["method"]) != (name, method)
                or receipt["raw_authority"] != case["raw_authority"]
                or receipt["case_binding_sha256"] != _sha(entry)
                or receipt["build_sha256"] != _sha(OUT / "build.json")
            ):
                raise ValueError("outcome differs from frozen recording and receiver " + name)
            pred_path = Path(receipt["prediction_path"])
            if not pred_path.is_relative_to(root) or pred_path.name != "prediction.json":
                raise ValueError("prediction is outside the recording evidence directory")
            verified_bytes(pred_path, receipt["prediction_sha256"])
            prediction = read(pred_path)
            validate_result(prediction)
            if (prediction["status"], prediction.get("reason")) != (
                receipt["status"],
                receipt["reason"],
            ):
                raise ValueError("receipt and locked position disagree")
            archived = method == "algo07v5" and assignment["archived_original"]
            if receipt["source"] != ("archived_original_glrt" if archived else "fresh_raw"):
                raise ValueError("wrong input acquisition mode")
            source = parent
            if case["valid_visits"]:
                if not archived:
                    capture = read(root / "acquisition.json")
                    if (
                        capture["input_sha256"] != case["native"]["sha256"]
                        or capture["build_sha256"] != receipt["build_sha256"]
                        or capture["raw_authority"] != case["raw_authority"]
                        or capture["visits"] != assignment["windows"]
                        or capture["antenna_probes"] != 2 * case["valid_visits"]
                        or capture["excluded"] + case["valid_visits"] != capture["visits"]
                    ):
                        raise ValueError(
                            "fresh detector did not see exactly the frozen opportunities"
                        )
                    verified_bytes(capture["native_path"], capture["native_sha256"])
                    binding = pred_path.parent / "binding.json"
                    verified_bytes(binding, receipt["binding_sha256"])
                    source = read(binding)
                    job = dict(
                        parent["job"],
                        native_input=dict(
                            path=capture["native_path"], sha256="sha256:" + capture["native_sha256"]
                        ),
                    )
                    job["identity"] = dict(
                        parent["job"]["identity"],
                        input_sha256=job["native_input"]["sha256"],
                        run_id=full_identity(name, source),
                    )
                    if comparable_request(source) != comparable_request(dict(parent, job=job)):
                        raise ValueError("detector substitution changed scientific settings")
                elif (
                    receipt["binding_sha256"] != case["request"]["sha256"]
                    or receipt["end_to_end_wall_s"] is not None
                ):
                    raise ValueError(
                        "archived acquisition has a different input or timing boundary"
                    )
                if source["job"]["native_input"]["sha256"] != receipt["native_sha256"]:
                    raise ValueError("wrong native input passed to solver")
                solver = pred_path.parent / "solver"
                request = solver / (
                    "experimental-request.json" if method == "algo07v5" else "request.json"
                )
                if comparable_request(read(request)) != comparable_request(source):
                    raise ValueError("effective solver binding differs from its committed input")
                policy = prediction["metrics"].get("applied_orbit_policy", "stock")
                if policy != "stock" and comparable_request(
                    read(solver.parent / policy / "request.json")
                ) != comparable_request(source):
                    raise ValueError("orbit retry changed scientific inputs")
                if method == "algo07v5" and prediction["status"] == "ok":
                    verified_bytes(solver / original_v5.EVIDENCE, prediction["evidence"]["sha256"])
            elif receipt["status"] != "withheld" or receipt["end_to_end_wall_s"] is not None:
                raise ValueError("unsupported recording emitted an estimate or a raw timing")
            locked.append(
                dict(
                    case=name,
                    method=method,
                    input_binding_sha256=_sha(entry),
                    outcome_sha256=_sha(outcome),
                    prediction_sha256=_sha(pred_path),
                    raw_authority=case["raw_authority"],
                )
            )
            records.append((assignment, case, receipt, prediction))
    if originals:
        raise ValueError("unaccounted DS30 members")
    seal(
        OUT / "prediction-lock.json",
        dict(build_sha256=_sha(OUT / "build.json"), predictions=locked),
    )
    return records, members


def survey(members):
    station = Path("/etc/leo/station-authority/gauss-r20-lt3d-004b-20261001-v1.json")
    verified_bytes(station, _sha(DS29 / "site-authority.json"))
    authority = read(station)
    adapter = ds30_panel.snapshot_tools()
    cases = [adapter.site_audit(m, authority) for m in members]
    seal(
        OUT / "reference-audit.json",
        dict(
            prediction_lock_sha256=_sha(OUT / "prediction-lock.json"),
            authority_sha256=_sha(station),
            cases=cases,
        ),
    )
    return {
        c["dataset_label"]: (
            [c["reference"]["latitude_deg"], c["reference"]["longitude_deg"]]
            if c["reference"]
            else None
        )
        for c in cases
    }


def join(records, references):
    rows = []
    for assignment, case, receipt, prediction in records:
        name = assignment["id"]
        for arm in ARMS:
            point = prediction["arms"][arm]["latlon"]
            metrics = prediction["metrics"]
            rows.append(
                dict(
                    case=name,
                    session=case["session_id"],
                    method=receipt["method"],
                    calibration=arm,
                    recording_state=assignment["recording_state"],
                    previous=assignment["previous"],
                    archived_original=assignment["archived_original"],
                    windows=assignment["windows"],
                    valid_visits=case["valid_visits"],
                    hardware_span_s=case["hardware_span_s"],
                    reference_eligible=references[name] is not None,
                    fix=point is not None,
                    latitude=point[0] if point else None,
                    longitude=point[1] if point else None,
                    error_km=distance_km(references[name], point),
                    frequency_rms_hz=metrics.get(
                        arm + "_conditional_rms_hz", prediction["arms"][arm].get("rf_rms_hz")
                    ),
                    frequency_score=metrics.get(arm + "_frequency_score"),
                    associated_observations=metrics.get(arm + "_associated_observations"),
                    orbit_policy=metrics.get("applied_orbit_policy", "stock"),
                    prediction_sha256=receipt["prediction_sha256"],
                    **{
                        k: receipt[k]
                        for k in (
                            "source",
                            "status",
                            "reason",
                            "cpu",
                            "solver_wall_s",
                            "acquisition_wall_s",
                            "detector_cpu_s",
                            "end_to_end_wall_s",
                        )
                    },
                )
            )
    return rows


def paired(rows):
    lookup = {(r["case"], r["method"], r["calibration"]): r for r in rows}
    both = []
    for a in rows:
        if a["method"] != METHODS[0]:
            continue
        b = lookup[a["case"], METHODS[1], a["calibration"]]
        known = a["error_km"] is not None and b["error_km"] is not None
        timed = (
            a["cpu"] == b["cpu"]
            and a["end_to_end_wall_s"] is not None
            and b["end_to_end_wall_s"] is not None
        )
        solved = (
            a["cpu"] == b["cpu"]
            and a["solver_wall_s"] is not None
            and b["solver_wall_s"] is not None
        )
        both.append(
            dict(
                case=a["case"],
                calibration=a["calibration"],
                previous=a["previous"],
                archived_original=a["archived_original"],
                recording_state=a["recording_state"],
                original_fix=a["fix"],
                compact_fix=b["fix"],
                original_km=a["error_km"],
                compact_km=b["error_km"],
                delta_km=b["error_km"] - a["error_km"] if known else None,
                same_core=a["cpu"] == b["cpu"],
                end_to_end_speedup=a["end_to_end_wall_s"] / b["end_to_end_wall_s"]
                if timed
                else None,
                solver_speedup=a["solver_wall_s"] / b["solver_wall_s"] if solved else None,
            )
        )
    return both


def summarize(rows, pairs):
    import numpy as np

    metrics, comparisons = [], []
    for group in GROUPS:
        for arm in ARMS:
            sample = [r for r in rows if r["calibration"] == arm and belongs(r, group)]
            for method in METHODS:
                part = [r for r in sample if r["method"] == method]
                errors = distribution(r["error_km"] for r in part)
                summary = dict(
                    group=group,
                    method=method,
                    calibration=arm,
                    assigned=len(part),
                    reference_eligible=sum(r["reference_eligible"] for r in part),
                    fixes=sum(r["fix"] for r in part),
                    scored_fixes=errors["n"],
                    **{k + "_km": errors[k] for k in ("p50", "p90", "p95", "p99", "max")},
                )
                for limit in (1, 2, 5):
                    summary[f"within_{limit}km"] = sum(
                        r["error_km"] is not None and r["error_km"] <= limit for r in part
                    )
                for field in (
                    "frequency_rms_hz",
                    "frequency_score",
                    "solver_wall_s",
                    "acquisition_wall_s",
                    "detector_cpu_s",
                    "end_to_end_wall_s",
                ):
                    d = distribution(r[field] for r in part)
                    for k in ("n", "p50", "p95"):
                        summary[f"{field}_{k}"] = d[k]
                summary["fixes_within_capture_span"] = sum(
                    r["fix"]
                    and r["end_to_end_wall_s"] is not None
                    and r["end_to_end_wall_s"] <= r["hardware_span_s"]
                    for r in part
                )
                metrics.append(summary)
            p = [r for r in pairs if r["calibration"] == arm and belongs(r, group)]
            shared = [r for r in p if r["delta_km"] is not None]
            d = np.array([r["delta_km"] for r in shared])
            interval = [None, None]
            if len(d):
                rng = np.random.default_rng(30261121)
                intervals = np.median(rng.choice(d, size=(5000, len(d)), replace=True), axis=1)
                interval = np.quantile(intervals, [0.025, 0.975]).tolist()
            time = distribution(r["end_to_end_speedup"] for r in p)
            solve = distribution(r["solver_speedup"] for r in p)
            comparisons.append(
                dict(
                    group=group,
                    calibration=arm,
                    assigned=len(p),
                    common_scored=len(d),
                    original_only_fixes=sum(r["original_fix"] and not r["compact_fix"] for r in p),
                    compact_only_fixes=sum(r["compact_fix"] and not r["original_fix"] for r in p),
                    neither_fixes=sum(not r["compact_fix"] and not r["original_fix"] for r in p),
                    compact_closer=int(np.sum(d < 0)),
                    original_closer=int(np.sum(d > 0)),
                    tied=int(np.sum(d == 0)),
                    original_common_p50_km=distribution(r["original_km"] for r in shared)["p50"],
                    compact_common_p50_km=distribution(r["compact_km"] for r in shared)["p50"],
                    paired_median_delta_km=distribution(d)["p50"],
                    bootstrap_low_km=interval[0],
                    bootstrap_high_km=interval[1],
                    actual_paired_end_to_end_n=time["n"],
                    actual_paired_end_to_end_median_speedup=time["p50"],
                    actual_paired_solver_n=solve["n"],
                    actual_paired_solver_median_speedup=solve["p50"],
                )
            )
    return metrics, comparisons


def repeated_panel(rows):
    from .ds30_full_verify import csv_rows

    previous = ds30_panel.OUT / "recordings.csv"
    verified_bytes(
        previous, read(ds30_panel.OUT / "result-verification.json")["files"]["recordings.csv"]
    )
    prior = {
        (r["case"], r["calibration"]): r
        for r in csv_rows(previous)
        if r["method"] == "cancellation"
    }
    repeated = []
    for r in rows:
        if not r["previous"] or r["method"] != "compact_two_scan":
            continue
        old = prior.pop((r["case"], r["calibration"]))
        old_point = (
            [float(old["latitude_deg"]), float(old["longitude_deg"])]
            if old["fix"] == "True"
            else None
        )
        current = [r["latitude"], r["longitude"]] if r["fix"] else None
        repeated.append(
            dict(
                case=r["case"],
                calibration=r["calibration"],
                old_fix=old_point is not None,
                current_fix=r["fix"],
                endpoint_difference_km=distance_km(old_point, current),
            )
        )
    if prior:
        raise ValueError("missing previous DS30 session in full validation")
    return repeated


def score():
    records, members = lock()
    rows = join(records, survey(members))
    rows.sort(key=lambda r: (r["case"], METHODS.index(r["method"]), ARMS.index(r["calibration"])))
    pairs = paired(rows)
    metrics, comparisons = summarize(rows, pairs)
    for filename, data in (
        ("recordings", rows),
        ("paired", pairs),
        ("summary", metrics),
        ("paired-summary", comparisons),
        ("repeated-panel", repeated_panel(rows)),
    ):
        write_csv(OUT / (filename + ".csv"), data)
    failures = Counter(
        (r["method"], r["recording_state"], r["status"], r["reason"])
        for r in rows
        if r["calibration"] == "fitted_c" and not r["fix"]
    )
    write_csv(
        OUT / "failures.csv",
        [
            dict(method=k[0], recording_state=k[1], status=k[2], reason=k[3], recordings=v)
            for k, v in failures.most_common()
        ],
    )
    from .ds30_full_figures import figures
    from .ds30_full_verify import verify

    figures(rows, pairs)
    verify()
    print(
        "Scored", len(records), "pipeline outcomes and", len(rows), "calibration arms", flush=True
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("lock", "score"))
    if parser.parse_args().action == "lock":
        lock()
    else:
        score()
