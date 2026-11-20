"""Bind four actual paced native inputs and compare two whole-track curvature policies."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from . import drop_mechanism_trial as launch
from . import fresh_adaptive, fresh_replay
from .bracketed_position import check_release
from .fractional_runtime_whole import verify_request
from .full_v5_check import _sha
from .portable_gate_trials import compressed_rows
from .rescue_attribution import sealed
from .whole_pressure_trial import rows_from

REPORT = launch.REPORT.parent.parent / "latency-and-support/track-support"
PINS = {"DS26-0026": 8, "DS29-0047": 9, "DS26-0197": 8, "DS29-0316": 9}
STOCK, CANDIDATE = "stock", "corrected-time"
ORDERS = {
    k: (STOCK, CANDIDATE) if k in {"DS26-0026", "DS29-0316"} else (CANDIDATE, STOCK) for k in PINS
}
METHODS = dict.fromkeys((STOCK, CANDIDATE), "paced")
LIMIT = 215
FRESH_WORK = Path("/var/tmp/leo-fresh-adaptive-position-20261119")
WORKER = Path(__file__).with_name("track_support_worker.py")
read = whole_iq.read


def sources():
    names = (
        Path(__file__),
        WORKER,
        REPORT / "PROTOCOL.md",
        WORKER.parent.parent / "variants/time_curvature.py",
        *(ROOT / key for key in launch.sources()),
    )
    return {str(p.relative_to(ROOT)): _sha(p) for p in names}


def fresh_records(fresh_path):
    report = fresh_adaptive.REPORT
    expected = rows_from(sealed(report, "prediction-lock.json", "predictions.jsonl.gz"))
    lock = read(sealed(report, "prediction-lock.json", "preregister.json"))
    parent = read(
        whole_iq.checked(
            fresh_replay.REPORT / "source-lock.json",
            lock["source_receipt_sha256"],
        )
    )
    cases = {}
    for row in expected:
        if row["condition"] != "fifth":
            continue
        ident = row["id"]
        raw_lock = whole_iq.checked(report / f"{ident}-fifth-lock.json", row["raw_lock_sha256"])
        trace_name = f"{ident}-fifth-trace.json.gz"
        receipt = read(raw_lock)
        trace_path = whole_iq.checked(report / trace_name, receipt["files"][trace_name])
        ledger = fresh_adaptive.arrival_queue.readgz(trace_path)
        emitted = {r["visit"] for r in ledger if r["outcome"] == "emitted"}
        directory = fresh_path / ident / "fifth"
        native = whole_iq.checked(directory / "recording/native.json", row["native_sha256"])
        prior = whole_iq.checked(
            directory / "recording/request.json",
            row["prepared_request_sha256"],
        )
        with fresh_replay.patched_case(parent):
            case, request = whole_iq.binding(ident)
        verify_request(read(prior), request, native_path=native, native_sha256=row["native_sha256"])
        actual = read(native)["source"]["probes"]
        if (
            receipt["status"] != "complete"
            or not receipt["raw_verified"]
            or not row["raw_verified"]
            or row["matched_raw_envelopes"] != len(emitted)
            or len(actual) != 2 * len(emitted)
            or {p["visit_index"] for p in actual} != emitted
        ):
            raise ValueError("fresh native file differs from its exact paced emissions")
        cases[ident] = (
            native,
            case,
            request,
            row,
            dict(
                trace_sha256=_sha(trace_path),
                dropped_visits=row["counts"]["queue_drop"],
                emitted_visits=len(emitted),
                capture="fresh",
            ),
        )
    return parent, cases


def earlier_records():
    q = launch.arrival
    release = read(sealed(q.PARENT, "prediction-lock.json", "source-lock.json"))
    archive = rows_from(
        sealed(q.REPORT, "positions-candidate-lock.json", "positions-candidate.jsonl.gz")
    )
    old_inputs = read(
        sealed(
            q.REPORT,
            "positions-candidate-lock.json",
            "position-candidate-input-lock.json",
        )
    )
    cases = {}
    for row in archive:
        ident = row["id"]
        frozen = old_inputs["cases"][ident]
        case, request = whole_iq.binding(ident)
        native = whole_iq.checked(Path(frozen["out"]) / "native.json", row["native_sha256"])
        observed = read(native)["source"]["probes"]
        visits = {p["visit_index"] for p in observed}
        if (
            not frozen["complete"]
            or len(observed) != 2 * len(visits)
            or visits & {r["visit"] for r in frozen["dropped"]}
            or row["dropped"] != len(frozen["dropped"])
        ):
            raise ValueError("old factors include missing visits or disrupted stereo support")
        cases[ident] = (
            native,
            case,
            request,
            row,
            dict(
                trace_sha256=frozen["trace_sha256"],
                dropped_visits=len(frozen["dropped"]),
                emitted_visits=len(visits),
                capture="earlier",
            ),
        )
    return release, cases


def stage(work, fresh_folder):
    work.mkdir(exist_ok=False)
    if (REPORT / "plan.json").exists():
        raise FileExistsError("curvature comparison already frozen")
    fresh, recent = fresh_records(fresh_folder)
    older, earlier = earlier_records()
    check_release(fresh)
    check_release(older)
    for key in ("receiver", "receiver_files", "native_sources"):
        if fresh[key] != older[key]:
            raise ValueError("the four cases require the same installed numerical release")
    cases = {}
    for ident, (from_path, case, request, row, slice_) in (recent | earlier).items():
        job = request["job"]
        if (
            row["catalog_sha256"] != case["catalog"]["sha256"]
            or row["original_request_sha256"] != case["request"]["sha256"]
            or row["paired_capture_sha256"] != case["native"]["sha256"]
            or row["tile"]["center"] != job["search_center"]
        ):
            raise ValueError("paired position and paced factors differ in causal offer")
        path = work / ident / "input"
        native = path / "native.json"
        write(native, from_path.read_bytes())
        whole_iq.checked(native, row["native_sha256"])
        dummy = path / "empty.json"
        save_json(dummy, [])
        cases[ident] = dict(
            source=dict(
                paced=dict(
                    native=str(native),
                    native_sha256=row["native_sha256"],
                    gaps=str(dummy),
                    gaps_sha256=_sha(dummy),
                )
            ),
            tile=row["tile"],
            screen=job["screen_center"],
            session=case["session_id"],
            config=job["track_config"],
            archive=job["tle_root"],
            catalogue=case["catalog"]["sha256"],
            request_sha256=case["request"]["sha256"],
            paired_capture_sha256=case["native"]["sha256"],
            paced=slice_,
        )
    if cases.keys() != PINS.keys():
        raise ValueError("incomplete fresh/earlier paced cohort")
    paths = (
        fresh_adaptive.REPORT / "prediction-lock.json",
        fresh_replay.REPORT / "all-figure-lock.json",
        fresh_replay.REPORT / "reference-prediction-lock.json",
        launch.arrival.REPORT / "positions-candidate-lock.json",
    )
    save_json(
        REPORT / "plan.json",
        dict(
            cases=cases,
            orders=ORDERS,
            pins=PINS,
            limit_s=LIMIT,
            memory_bytes=whole_iq.MEMORY,
            receiver=fresh["receiver"],
            receiver_files=fresh["receiver_files"],
            native_sources=fresh["native_sources"],
            sources=sources(),
            parents={str(p.relative_to(ROOT)): _sha(p) for p in paths},
        ),
    )
    print("Frozen paced support comparison", _sha(REPORT / "plan.json"), flush=True)


def run(work):
    plan = read(REPORT / "plan.json")
    if sources() != plan["sources"]:
        raise ValueError("curvature source drift")
    check_release(plan)

    def lane(pair):
        all_rows = []
        for ident in pair:
            result = [launch.launch(work, plan, ident, method) for method in ORDERS[ident]]
            path = REPORT / f"{ident}-pair-lock.json"
            save_json(
                path, dict(cases=[ident], plan_sha256=_sha(REPORT / "plan.json"), attempts=result)
            )
            all_rows.extend(result)
        return all_rows

    lanes = (("DS26-0026", "DS26-0197"), ("DS29-0047", "DS29-0316"))
    with (
        patch.multiple(launch, REPORT=REPORT, WORKER=WORKER, METHODS=METHODS, LIMIT=LIMIT),
        ThreadPoolExecutor(2) as pool,
    ):
        rows = [record for lane_results in pool.map(lane, lanes) for record in lane_results]
    write(REPORT / "attempts.jsonl.gz", compressed_rows(rows))
    files = ("plan.json", "attempts.jsonl.gz", *(f"{i}-pair-lock.json" for i in PINS))
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=list(PINS),
            files={name: _sha(REPORT / name) for name in files},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--fresh", type=Path, default=FRESH_WORK)
    args = parser.parse_args()
    stage(args.work, args.fresh)
    run(args.work)
