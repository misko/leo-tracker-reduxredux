"""Replay live smooth tentative jobs and retain matched earlier control evidence."""

import argparse
import json
import os
import subprocess
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from time import perf_counter

from leo.analysis import localization_deletion_spread

from ..__main__ import encoded, local_output, read_predictions, save_json
from ..scoring import validate_result
from ..variants import orbit_influence
from . import exterior_evidence_trial as exterior
from . import native_clock_full as clock
from . import native_clock_model_worker
from .armijo_finish_results import pack

phase = clock.phase
REPORT = clock.REPORT.parent.parent / "redesign/orbit-influence"
WORK = clock.WORK.with_name("orbit-influence")
WORKER = Path(__file__).with_name("orbit_influence_worker.py")
METHOD = orbit_influence.METHOD
COHORTS = ("diagnostic-stress", "reserve")
PUBLISH_S = 720
ATTEMPT_S = 60


def keyed(purpose, ident):
    return phase.corpus._sha(f"roof-orbit-influence-v1:{purpose}:{ident}".encode())


def load(bundle, cpus):
    bound, frames = clock.prepare(bundle)
    originals = {q["recording"]: (q, paths) for q, paths in frames if q["cohort"] == "roof"}
    parent = exterior.REPORT / "plan.json"
    plan = phase._read(parent)
    inputs, controls, outside, paths = {}, {}, {}, {}
    locks = {}
    for scope, key in zip(COHORTS, ("stress", "reserve"), strict=True):
        folder = exterior.REPORT / scope
        lock_file = folder / "prediction-lock.json"
        lock = phase._read(lock_file)
        locks[scope] = phase.digest(lock_file)
        if lock["plan_sha256"] != phase.digest(parent):
            raise ValueError("earlier exterior cohort changed inputs")
        clock.base.secant_full._verify_files(folder, lock["files"])
        smooth = read_predictions(folder / f"{clock.METHOD}.jsonl.gz")
        gate = read_predictions(folder / f"{exterior.METHOD}.jsonl.gz")
        rows = plan[key]
        if set(smooth) != set(gate) or set(smooth) != {q["id"] for q in rows}:
            raise ValueError("the exterior and smooth prediction rosters differ")
        inputs[scope] = rows
        for query in rows:
            ident, recording = query["id"], query["recording"]
            original, paths[ident] = originals[recording]
            packet = query["packet"]
            if packet != dict(original["packet"], offer=packet["offer"]):
                raise ValueError("the challenge differs from the authentic native assets")
            expected = clock.bindings(query)
            if any(smooth[ident].get(k) != v for k, v in expected.items()) or any(
                gate[ident].get(k) != smooth[ident].get(k)
                for k in (
                    "input_sha256",
                    "native_sha256",
                    "catalog_sha256",
                    "tile",
                    "observation_sha256",
                )
            ):
                raise ValueError("earlier controls changed their supplied tile or native binding")
        controls[scope], outside[scope] = smooth, gate
    tentatives = [
        q
        for row in inputs.values()
        for q in row
        if any(
            c.get(q["id"], {}).get("result", {}).get("status") == "ok" for c in controls.values()
        )
    ]
    names = set(controls["diagnostic-stress"])
    exact_checks = sorted(
        (q["id"] for q in tentatives if q["id"] in names), key=lambda i: keyed("diagnostic", i)
    )[:2]
    ordered = sorted(
        tentatives, key=lambda q: (q["id"] not in exact_checks, keyed("queue", q["id"]))
    )
    files = (
        Path(__file__),
        WORKER,
        Path(orbit_influence.__file__),
        Path(localization_deletion_spread.__file__),
        REPORT / "PROTOCOL.md",
    )
    receipt = dict(
        original_source=bound["source"],
        protocol_and_source={p.name: phase.digest(p) for p in files},
        exterior_plan_sha256=phase.digest(parent),
        exterior_prediction_locks=locks,
        cases=inputs,
        tentative_order=[q["id"] for q in ordered],
        exact_checks=exact_checks,
        cpus=list(cpus),
        worker_cap_s=ATTEMPT_S,
        batch_cap_s=PUBLISH_S,
    )
    return receipt, ordered, controls, outside, paths


def command(cpu, assets, bundle, *, exact):
    argv = clock.command(cpu, assets, bundle)
    argv[argv.index(str(clock.WORKER))] = str(WORKER)
    for module, destination in (
        (
            native_clock_model_worker,
            "/worker/tools/pipeline_eval/qualification/native_clock_model_worker.py",
        ),
        (orbit_influence, "/worker/tools/pipeline_eval/variants/orbit_influence.py"),
        (
            localization_deletion_spread,
            "/worker/tools/pipeline_eval/variants/localization_deletion_spread.py",
        ),
    ):
        argv[-3:-3] = ["--ro-bind", str(Path(module.__file__)), destination]
    return [*argv, "--exact-check"] if exact else argv


def run_one(query, assets, bundle, cpu, exact):
    start = perf_counter()
    try:
        worker = subprocess.run(
            command(cpu, assets, bundle, exact=exact),
            input=encoded(query["packet"]),
            timeout=ATTEMPT_S,
            check=True,
            capture_output=True,
        )
        output = json.loads(worker.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        detail = (getattr(error, "stderr", None) or b"").decode(errors="replace")[-1800:]
        status = "timed_out" if isinstance(error, subprocess.TimeoutExpired) else "failed"
        output = dict(result=clock.failed(status, detail or str(error)))
    validate_result(output["result"])
    row = (
        clock.bindings(query)
        | output
        | dict(
            method=METHOD,
            worker_wall_s=perf_counter() - start,
            cpu=cpu,
            source="fresh_live_influence",
        )
    )
    if row["result"]["status"] in ("ok", "withheld") and (
        row.get("address_space_limit_mib") != 512
        or row["proc_memory_kib"]["VmPeak"] > 512 * 1024
        or any("localization_v3" in k or "/v5_" in k for k in row["imported_first_party"])
    ):
        raise ValueError("fresh influence worker violated its capped native boundary")
    print(query["id"], row["result"]["status"], round(row["worker_wall_s"], 3), flush=True)
    return row


def bind_fresh(row, stock):
    keys = ("id", "recording", "input_sha256", "native_sha256", "catalog_sha256", "tile")
    if any(row[k] != stock[k] for k in keys):
        raise ValueError("a fresh influence row changed the original native request")
    if row["result"]["status"] in ("ok", "withheld"):
        old, first = stock["result"], row["ungated"]
        if (
            row["observation_sha256"] != stock["observation_sha256"]
            or any(first.get(k) != old.get(k) for k in ("status", "reason", "arms"))
            or first["metrics"]["clock_fit"] != old["metrics"]["clock_fit"]
        ):
            raise ValueError(
                "the live slope and orbit evidence differs from the archived smooth fit"
            )
    else:
        row["observation_sha256"] = stock["observation_sha256"]
    return row


def run(work, output, bundle, cpus):
    start = perf_counter()
    if not cpus or not set(cpus) <= os.sched_getaffinity(0):
        raise ValueError("the selected pins are outside this worker affinity")
    work = local_output(work)
    work.mkdir(exist_ok=False, parents=True)
    plan, queue, controls, exterior_rows, assets = load(bundle, cpus)
    save_json(output / "plan.json", plan)
    pending, lock = deque(queue), Lock()
    live = work / "predictions"
    live.mkdir()

    def lane(cpu):
        while perf_counter() - start < PUBLISH_S - ATTEMPT_S - 5:
            with lock:
                if not pending:
                    return
                request = pending.popleft()
            ident = request["id"]
            result = run_one(request, assets[ident], bundle, cpu, ident in plan["exact_checks"])
            save_json(live / f"{ident}.json", result)

    with ThreadPoolExecutor(len(cpus)) as pool:
        list(pool.map(lane, cpus))
    if load(bundle, cpus)[0] != plan:
        raise ValueError("scientific source or input binding changed during replay")
    for scope in COHORTS:
        rows = []
        for query in plan["cases"][scope]:
            ident = query["id"]
            original = controls[scope][ident]
            candidate = live / f"{ident}.json"
            if candidate.is_file():
                row = bind_fresh(phase._read(candidate), original)
            elif original["result"]["status"] == "ok":
                row = dict(
                    original,
                    method=METHOD,
                    worker_wall_s=None,
                    source="unattempted",
                    result=clock.failed("missing", "bounded influence replay not reached"),
                )
            else:
                row = dict(original, method=METHOD, source="inherited_initial_withholding")
            rows.append(row)
        dest = output / scope
        pairing = (
            (METHOD, rows),
            (clock.METHOD, controls[scope].values()),
            (exterior.METHOD, exterior_rows[scope].values()),
        )
        files = {f"{m}.jsonl.gz": pack(dest, f"{m}.jsonl.gz", items) for m, items in pairing}
        save_json(
            dest / "prediction-lock.json",
            dict(
                cases=[r["id"] for r in rows],
                files=files,
                plan_sha256=phase.digest(output / "plan.json"),
                fresh=sum((live / f"{r['id']}.json").is_file() for r in rows),
                statuses=dict(Counter(r["result"]["status"] for r in rows)),
                batch_wall_s=perf_counter() - start,
            ),
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=WORK)
    parser.add_argument("--output", type=Path, default=REPORT)
    parser.add_argument("--bundle", type=Path, default=clock.base.BUNDLE)
    parser.add_argument("--cpus", type=int, nargs="+", default=[18])
    args = parser.parse_args()
    run(args.work, args.output, args.bundle, args.cpus)


if __name__ == "__main__":
    main()
