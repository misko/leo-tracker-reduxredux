"""Benchmark queue-triggered pilot timing on paired host-arrival replays."""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from .. import iq_service, whole_iq
from ..__main__ import local_output, save_json, write
from ..variants import arrival_policy
from . import adaptive_arrival_worker as worker
from . import arrival_queue as pace
from .full_v5_check import _sha

REPORT = pace.REPORT.parent.parent / "arrival-and-timing/adaptive-arrival"
CPUS = {"DS26-0197": 16, "DS29-0316": 17}
ORDER = {"DS26-0197": ("stock", "adaptive", "fifth"), "DS29-0316": ("fifth", "adaptive", "stock")}
GEOMETRY = ("visit", "arrival_ns", "delivery_clock", "sample_start", "sample_end", "status")


def join_events(stock, fifth):
    events = []
    for number, (left, right) in enumerate(zip(stock, fifth, strict=True)):
        if left["visit"] != number or any(left[k] != right[k] for k in GEOMETRY):
            raise ValueError("detector references do not bind the same physical opportunity")
        row = {key: left[key] for key in GEOMETRY}
        for name, arm in (("stock", left), ("fifth", right)):
            digest = arm["full_visit_sha256"]
            if not isinstance(digest, str) or len(digest) != 64:
                raise ValueError("a branch lacks its authenticated native visit hash")
            row[name] = digest
        if row["status"] == "invalid_capture" and row["stock"] != row["fifth"]:
            raise ValueError("hardware exclusion differs across detector references")
        events.append(row)
    return events


def freeze(work, report):
    source = report / "source-lock.json"
    if work.exists() or source.exists():
        raise FileExistsError("use a new local working and evidence directory")
    archive = whole_iq.read(pace.REPORT / "stage-lock.json")
    original = pace.REPORT / "source-lock.json"
    original_sha = archive["files"]["source-lock.json"]
    prior = whole_iq.read(whole_iq.checked(original, original_sha))
    cases = {}
    for ident, cpu in CPUS.items():
        spec = prior["cases"][ident]
        sources = [
            pace.readgz(whole_iq.checked(pace.REPORT / doc["events"], doc["sha256"]))
            for doc in (spec["modes"]["control"], spec["modes"]["candidate"])
        ]
        events = report / f"{ident}-events.json.gz"
        pace.writegz(events, join_events(*sources))
        reference = dict(events=events.name, sha256=_sha(events))
        cases[ident] = dict(spec, cpu=cpu, modes={k: reference for k in ORDER[ident]})
    files = (
        Path(__file__),
        Path(worker.__file__),
        Path(arrival_policy.__file__),
        Path(pace.__file__),
        report / "PROTOCOL.md",
    )
    save_json(
        source,
        dict(
            cases=cases,
            assets=prior["assets"],
            order=ORDER,
            programs={str(p): _sha(p) for p in files},
            prior_arrival_source_sha256=original_sha,
            prior_stage_lock_sha256=_sha(pace.REPORT / "stage-lock.json"),
            parent_prediction_sha256=prior["parent_prediction_sha256"],
            waiting_slots=1,
            memory_max=whole_iq.MEMORY,
            memory_swap_max=0,
            limit_s=pace.LIMIT_S,
        ),
    )
    work.mkdir(parents=True)
    save_json(work / "launch-lock.json", dict(source_lock_sha256=_sha(source)))


def validate_event(actual, expected, mode):
    if any(actual.get(k) != expected[k] for k in GEOMETRY if k != "delivery_clock"):
        raise ValueError("paced result changed a scheduled physical opportunity")
    if actual["released_ns"] < actual["arrival_ns"]:
        raise ValueError("an arrival was dispatched early")
    outcome = actual["outcome"]
    policy = actual["policy"]
    if expected["status"] == "invalid_capture":
        if outcome != "invalid_capture" or policy is not None:
            raise ValueError("hardware-invalid visit entered the policy")
        reference = expected["stock"]
    else:
        before = actual["outstanding_at_admission"]
        if outcome == "queue_drop":
            if before != 2 or policy is not None or actual.get("actual_sha256") is not None:
                raise ValueError("dropped visit has an available slot or a detector result")
            return
        branch = ("stock" if before else "fifth") if mode == "adaptive" else mode
        if outcome != "emitted" or before not in (0, 1) or policy != branch:
            raise ValueError("detector choice disagrees with the causal admission rule")
        reference = expected[policy]
    if actual["actual_sha256"] != reference:
        raise ValueError("emitted envelope differs from the selected detector")
    if not actual["released_ns"] <= actual["started_ns"] <= actual["emitted_ns"]:
        raise ValueError("noncausal native packet timing")


def seal(work, report, ident, mode, source):
    spec = source["cases"][ident]
    out = work / ident / mode
    ref = spec["modes"][mode]
    events = pace.readgz(whole_iq.checked(report / ref["events"], ref["sha256"]))
    service = whole_iq.read(out / "service.json")
    log = whole_iq.checked(out / "service.log", service["log_sha256"])
    finished, trace = out / "end.json", out / "visits.jsonl"
    end = whole_iq.read(finished) if finished.exists() else None
    complete = iq_service.succeeded(service) and end is not None
    rows = (
        sorted(
            (json.loads(line) for line in trace.read_bytes().splitlines()), key=lambda r: r["visit"]
        )
        if trace.exists()
        else []
    )
    if complete:
        whole_iq.checked(trace, end["output_sha256"])
        if [r["visit"] for r in rows] != list(range(len(events))):
            raise ValueError("complete paced run omitted a physical opportunity")
        resource = end["end"]
        if (
            end["raw_recording_sha256"] != spec["raw_recording_sha256"]
            or resource["memory.max"] != whole_iq.MEMORY
            or resource["memory.swap.max"]
            or resource["memory.events.oom_kill"]
            or resource["cpus"] != [spec["cpu"]]
        ):
            raise ValueError("work escaped its authenticated input or resource cap")
    for row in rows:
        validate_event(row, events[row["visit"]], mode)
    prefix = f"{ident}-{mode}"
    output = report / f"{prefix}-trace.json.gz"
    pace.writegz(output, rows)
    times = report / f"{prefix}-service.json"
    save_json(
        times, dict(service=service, worker=end, launch=whole_iq.read(out / "service-launch.json"))
    )
    copied_log = report / f"{prefix}-service.log"
    write(copied_log, log.read_bytes())
    save_json(
        report / f"{prefix}-lock.json",
        dict(
            id=ident,
            mode=mode,
            status="complete" if complete else "failed",
            raw_verified=complete,
            source_lock_sha256=_sha(report / "source-lock.json"),
            files={p.name: _sha(p) for p in (output, times, copied_log)},
            available_events=len(rows),
        ),
    )
    print(ident, mode, f"{sum(r['outcome'] == 'queue_drop' for r in rows)} dropped", flush=True)


def run(work, report):
    source = pace.plan(work, report)

    def recording(ident):
        spec = source["cases"][ident]
        for mode in source["order"][ident]:
            with_path = work / ident / mode
            pace.launch(with_path, spec, mode, source["assets"], report)
            seal(work, report, ident, mode, source)

    with (
        patch.object(pace, "MODULE", worker.MODULE),
        patch.object(iq_service, "MODULE", worker.MODULE),
        ThreadPoolExecutor(max_workers=len(CPUS)) as pool,
    ):
        list(pool.map(recording, CPUS))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("freeze", "replay", "worker"))
    cli.add_argument("work", type=local_output)
    cli.add_argument("--out", type=local_output, default=REPORT)
    args = cli.parse_args()
    if args.action == "worker":
        worker.execute(args.work)
    elif args.action == "freeze":
        freeze(args.work, args.out)
    else:
        run(args.work, args.out)


if __name__ == "__main__":
    main()
