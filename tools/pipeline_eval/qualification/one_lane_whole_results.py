"""Bind direct one-lane replays, exact projected factors, and historical four-center controls."""

import argparse
import csv
import gzip
import json
from collections import Counter
from hashlib import sha256
from itertools import zip_longest
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..variants import one_lane_schedule as policy
from ..variants.selective_capture import same_support
from . import fresh_replay_results as paired
from . import one_lane_whole as trial
from . import screening_figures
from . import whole_band_results as measured
from . import whole_center_union_results as union
from .exact_wide_iq_results import detector_rows, timing_rows
from .frontier_whole_replay_results import trace_rows
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

TIMING = trial.union.SCREEN / "latency-and-support/complete-timing"
METHODS = {"control": trial.STOCK, "candidate": trial.METHOD}


def control_source(spec):
    path = whole_iq.checked(Path(spec["path"]), spec["transport_sha256"])
    payload = path.read_bytes()
    body = gzip.decompress(payload) if path.suffix == ".gz" else payload
    if sha256(body).hexdigest() != spec["native_sha256"]:
        raise ValueError("control native content conflicts with its historical position row")
    return json.loads(body)


def projection_witness(control, actual, mapped):
    expected, dispatch = policy.project(control, mapped)
    rows, real = (doc["source"]["probes"] for doc in (expected, actual))
    mismatches = {rx: [] for rx in (0, 1)}
    chosen = {row["visit"]: row["selected_receiver"] for row in dispatch}
    for before, after in zip_longest(rows, real):
        if before != after:
            present = before if before is not None else after
            rx, visit = present["receiver_id"], present["visit_index"]
            mismatches[int(rx != chosen.get(visit))].append((visit, rx))
    try:
        same_support(expected, actual)
    except ValueError as exc:
        support_failure = str(exc)
    else:
        support_failure = None
    by_rf = Counter((p["rf_center_hz"], p["selected_receiver"]) for p in dispatch)
    counts = Counter(p["selected_receiver"] for p in dispatch)
    return dict(
        full_projection_matches=expected == actual,
        physical_support_matches=support_failure is None,
        support_failure=support_failure,
        selected_lane_equal=not mismatches[0],
        empty_partner_equal=not mismatches[1],
        selected_lane_mismatches=mismatches[0],
        empty_partner_mismatches=mismatches[1],
        valid_visits=len(dispatch),
        invalid_visits=expected["provenance"]["invalid_capture"],
        receiver_calls=[counts[rx] for rx in (0, 1)],
        receiver_calls_by_rf={
            str(hz): [by_rf[hz, rx] for rx in (0, 1)] for hz in sorted(set(mapped.values()))
        },
        stock_positive_probes=sum(positive(p) for p in control["source"]["probes"]),
        selected_positive_probes=sum(positive(p) for p in real),
        projected_native_sha256=sha256(
            (whole_iq.recording.encoded(expected) + "\n").encode()
        ).hexdigest(),
    )


def positive(probe):
    return any(row["passed_fractional_margin_gate"] for row in probe["candidates"])


def historical_timing(plan):
    lock = paired.sealed(TIMING, "prediction-lock.json")
    with (TIMING / "resources.csv").open(newline="") as stream:
        rows = [
            row
            for row in csv.DictReader(stream)
            if row["method"] == trial.parent.roster.FOUR and row["id"] in plan["cases"]
        ]
    if len(rows) != len(plan["cases"]) or {r["id"] for r in rows} != set(plan["cases"]):
        raise ValueError("missing original measured four-center control resources")
    for row in rows:
        spec = plan["cases"][row["id"]]
        if (
            row["native_sha256"] != spec["control"]["native_sha256"]
            or row["clock_authority"] != spec["clock_authority"]
            or row["detector_sha256"] != plan["detectors"][row["id"]]["sha256"]
        ):
            raise ValueError("historical resources differ from the authentic stock control")
    return dict(
        receipt_sha256=_sha(TIMING / "prediction-lock.json"),
        source_sha256=lock["files"]["resources.csv"],
        rows=rows,
    )


def seal(work, report):
    if (report / "prediction-lock.json").exists():
        raise FileExistsError("terminal positions already sealed")
    plan = trial.source(work)
    controls, _, stocks, _ = trial.parent.load_controls()
    if controls["files"]["all-positions.jsonl.gz"] != plan["prior_stock_prediction_sha256"]:
        raise ValueError("historical position archive changed after freeze")
    rows, resources, audits, visits, files = [], {}, {}, [], []
    for ident, spec in plan["cases"].items():
        case = work / ident / "candidate"
        ref = dict(plan, detectors={"candidate": plan["detectors"][ident]})
        row, details, native = measured.attempt(work, ident, "candidate", ref, method=trial.METHOD)
        archived = dict(stocks[ident], method=trial.STOCK, cohort=spec["cohort"])
        trial.parent.roster.same_capture(row, archived)
        resources[ident] = dict(candidate=details)
        rows.extend((archived, row))
        audit = audits[ident] = dict(
            raw_complete=native is not None, position_status=row["result"]["status"]
        )
        if native is not None:
            mapped, _, _ = trial.parent.tune_plan(spec)
            audit.update(
                projection_witness(control_source(spec["control"]), whole_iq.read(native), mapped)
            )
            audit["measured_native_sha256"] = _sha(native)
            audit["same_native_bytes"] = (
                audit["measured_native_sha256"] == audit["projected_native_sha256"]
            )
            audit["stock_native_sha256"] = spec["control"]["native_sha256"]
            name = f"native/{ident}.json.gz"
            write(report / name, gzip.compress(native.read_bytes(), mtime=0))
            files.append(name)
            visits.extend(trace_rows(ident, "candidate", detector_rows(case)))
        if (log := case / "service.log").is_file():
            name = f"{ident}.service.log"
            write(
                report / name, whole_iq.checked(log, details["service"]["log_sha256"]).read_bytes()
            )
            files.append(name)
    pack(report / "positions.jsonl.gz", rows)
    pack(report / "visits.jsonl.gz", visits)
    save_json(report / "resources.json", resources)
    save_json(report / "parity.json", audits)
    save_json(report / "stock-runtime.json", historical_timing(plan))
    files.extend(
        (
            "positions.jsonl.gz",
            "visits.jsonl.gz",
            "resources.json",
            "parity.json",
            "stock-runtime.json",
            "source-lock.json",
            "PROTOCOL.md",
        )
    )
    files.extend(
        str(p.relative_to(report)) for p in (report / "startup-incident").rglob("*") if p.is_file()
    )
    save_json(
        report / "prediction-lock.json",
        dict(
            cases=list(plan["cases"]),
            files={n: _sha(report / n) for n in files},
            publisher_sha256=_sha(Path(__file__)),
        ),
    )


def report_timing(out):
    plan = whole_iq.read(out / "source-lock.json")
    resources = whole_iq.read(out / "resources.json")
    visits = [r for r in rows_from(out / "visits.jsonl.gz") if r["status"] == "processed"]
    actual = timing_rows(resources, visits)
    for row in actual:
        case = plan["cases"][row["id"]]
        details = resources[row["id"]][row["role"]]
        counts = details.get("counts", {})
        row.update(
            cores=case["cpus"],
            scheduled_windows=case["recording"]["window_count"],
            invalid_visits=counts.get("invalid_capture"),
            detected_receiver_lanes=row["calls"],
            recorded_clock_span_s=counts.get("window_delivery_span_s"),
            service_wall_s=details["service"].get("service_wall_s"),
        )
    stock = {row["id"]: row for row in whole_iq.read(out / "stock-runtime.json")["rows"]}
    rows = []
    for real in actual:
        old = stock[real["id"]]
        prior = dict.fromkeys(real) | dict(
            id=real["id"],
            role="control",
            service_status=old["service_result"],
            cores=old["cores"],
            calls=int(old["detector_calls"]),
            wall_within_20ms=old["detector_wall_within_20"],
            detected_receiver_lanes=2 * int(old["detector_calls"]),
            call_wall_p50_ms=old["detector_call_wall_p50_ms"],
            call_wall_p95_ms=old["detector_call_wall_p95_ms"],
            raw_s=old["raw_s"],
            assembly_s=old["assembly_s"],
            position_s=old["position_s"],
            full_s=old["worker_s"],
            cpu_s=old["worker_cpu_s"],
            detector_cpu_s=old["detector_cpu_s"],
            peak_mib=int(old["peak_bytes"]) / 2**20,
            deadline_s=old["service_deadline_s"],
            service_wall_s=old["service_journal_s"],
            scheduled_windows=old["scheduled_windows"],
            invalid_visits=old["invalid_visits"],
            recorded_clock_span_s=old["recorded_clock_span_s"],
        )
        rows.extend((prior, real))
    csv_file(out / "deadlines.csv", rows)


def score(out):
    receipt = paired.sealed(out, "prediction-lock.json")
    ids = receipt["cases"]
    rows = rows_from(out / "positions.jsonl.gz")
    _, original = held_references(None, ids)
    scores = paired.geographic(rows, {row["id"]: row for row in original})
    csv_file(out / "scores.csv", scores)
    groups = dict(all=ids, ds26=ids[:1], ds29=ids[1:])
    save_json(out / "summary.json", paired.distribution_rows(scores, groups))
    ablation, _ = union.paired_scores(scores)
    csv_file(out / "calibration.csv", ablation)
    report_timing(out)
    evidence = (
        "prediction-lock.json",
        "parity.json",
        "stock-runtime.json",
        "scores.csv",
        "summary.json",
        "calibration.csv",
        "deadlines.csv",
    )
    charts = []
    for group, cases in groups.items():
        title = (
            "One physical antenna at each RF revisit on two complete recordings"
            if group == "all"
            else f"One physical antenna per RF revisit on {cases[0]}"
        )
        chart = paired.chart(out, group, title, cases, rows, evidence, False)
        chart["id"] = f"one-lane-whole-{group}"
        chart["caption"] = (
            "Same complete recorded IQ, clocks, original causal request and compact fit. "
            "One lane alternates at each RF center. The stock receiver analyzes both lanes."
        )
        chart["series"][0]["label"] = "Alternating single antenna"
        charts.append(chart)
    save_json(out / "figures.json", dict(version=2, charts=charts))
    screening_figures.generate(out / "charts", evidence=out)
    files = (*evidence, "figures.json", *(f"{group}-figure-lock.json" for group in groups))
    save_json(
        out / "score-lock.json", dict(cases=ids, files={name: _sha(out / name) for name in files})
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "score"))
    parser.add_argument("--work", type=local_output, default=trial.WORK)
    parser.add_argument("--out", type=local_output, default=trial.REPORT)
    args = parser.parse_args()
    if args.action == "seal":
        seal(args.work, args.out)
    else:
        with (
            patch.multiple(paired.trial, METHOD=trial.METHOD, CONTROL=trial.STOCK),
            patch.object(paired, "METHODS", METHODS),
        ):
            score(args.out)
