"""Replay sealed one-offer native roof requests without reading evaluator labels."""

import argparse
import fcntl
import json
import os
import subprocess
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from time import perf_counter

from ..__main__ import encoded, local_output, save_json
from ..scoring import validate_result
from . import boundary_roof_offers as offers
from . import native_clock_full as clock
from . import train_update_trial as fixed
from .armijo_finish_results import pack

phase = clock.phase
METHODS = (clock.METHOD, fixed.train_update.METHOD)
CPUS = clock.CPUS
WALL_CAP_S = 12 * 60


def prepare(work, bundle):
    source = phase._read(work / "requests.json")
    plan, jobs = clock.prepare(bundle)
    authorities = dict(
        source=plan["source"],
        clock_plan_sha256=phase.digest(clock.REPORT / "plan.json"),
        protocol_sha256=phase.digest(offers.REPORT / "PROTOCOL.md"),
        generator_sha256=phase.digest(Path(offers.__file__)),
    )
    if any(source.get(k) != v for k, v in authorities.items()):
        raise ValueError("roof challenge requests differ from their prospective source")
    train = fixed.sources(bundle)
    trained = phase._read(fixed.REPORT / "plan.json")
    if train != trained["sources"]:
        raise ValueError("the frozen training update source has changed")
    by_recording = {q["recording"]: (q, paths) for q, paths in jobs if q["cohort"] == "roof"}
    cohort = source["cohort"]
    ids = offers.roster(plan)[cohort]
    counts = Counter(q["recording"] for q in source["cases"])
    if counts != dict.fromkeys(ids, 4):
        raise ValueError("requests do not match the frozen four-offer roster")
    jobs = []
    for query in source["cases"]:
        original, files = by_recording[query["recording"]]
        packet = dict(query["packet"])
        tile = packet.pop("offer")
        expected = {k: v for k, v in original["packet"].items() if k != "offer"}
        if (
            packet != expected
            or query["cohort"] != cohort
            or set(tile) != {"id", "center", "width_km"}
            or tile["width_km"] != 25
            or len(tile["id"]) != 20
            or len(query["id"]) != 20
        ):
            raise ValueError("non-offer fields changed from the frozen native packet")
        jobs.extend((method, query, files) for method in METHODS)
    return dict(
        **source,
        cpus=list(CPUS),
        worker_cap_s=clock.base.CAP,
        wall_cap_s=WALL_CAP_S,
        fixed_training=trained["sources"],
        runner_sha256=phase.digest(Path(__file__)),
        requests_sha256=phase.digest(work / "requests.json"),
        methods=list(METHODS),
    ), jobs


def attempt(method, query, files, cpu, bundle):
    launch = clock.command if method == clock.METHOD else fixed.command
    start = perf_counter()
    try:
        process = subprocess.run(
            launch(cpu, files, bundle),
            input=encoded(query["packet"]),
            capture_output=True,
            timeout=clock.base.CAP,
            check=True,
        )
        out = json.loads(process.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        message = (getattr(error, "stderr", None) or b"").decode(errors="replace")[-1500:]
        status = "timed_out" if isinstance(error, subprocess.TimeoutExpired) else "failed"
        out = dict(result=clock.failed(status, message or str(error)))
    validate_result(out["result"])
    row = (
        clock.bindings(query)
        | out
        | dict(method=method, cpu=cpu, worker_wall_s=perf_counter() - start)
    )
    if row["result"]["status"] in ("ok", "withheld") and (
        not row.get("observation_sha256")
        or row.get("address_space_limit_mib") != 512
        or row["proc_memory_kib"]["VmPeak"] > 512 * 1024
        or any("localization_v3" in p or "/v5_" in p for p in row["imported_first_party"])
    ):
        raise ValueError("worker retained an unauthenticated or out-of-budget state")
    print(method, query["id"], row["result"]["status"], round(row["worker_wall_s"], 3), flush=True)
    return row


def run(work, bundle, output):
    start = perf_counter()
    if not set(CPUS) <= os.sched_getaffinity(0):
        raise ValueError("expected all four pinned CPUs")
    work = local_output(work)
    with (work / "runner.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan, jobs = prepare(work, bundle)
        journal = work / "predictions"
        journal.mkdir()
        save_json(output / "roster.json", plan)
        pending, guard = deque(jobs), Lock()

        def lane(cpu):
            while perf_counter() - start < WALL_CAP_S - clock.base.CAP - 5:
                with guard:
                    if not pending:
                        return
                    method, query, files = pending.popleft()
                row = attempt(method, query, files, cpu, bundle)
                save_json(journal / f"{method}-{query['id']}.json", row)

        with ThreadPoolExecutor(len(CPUS)) as pool:
            list(pool.map(lane, CPUS))
        if prepare(work, bundle)[0] != plan:
            raise ValueError("roof challenge requests or attached sources changed")
        files = {"roster.json": phase.digest(output / "roster.json")}
        statuses = {}
        for method in METHODS:
            rows = []
            for query in plan["cases"]:
                path = journal / f"{method}-{query['id']}.json"
                expected = clock.bindings(query) | dict(method=method)
                if path.is_file():
                    row = phase._read(path)
                    if any(row.get(k) != v for k, v in expected.items()):
                        raise ValueError("the worker used a different frozen input")
                else:
                    row = dict(
                        expected,
                        worker_wall_s=None,
                        result=clock.failed("missing", "no attempt before batch limit"),
                    )
                rows.append(row)
            name = f"{method}.jsonl.gz"
            statuses[method] = dict(Counter(r["result"]["status"] for r in rows))
            files[name] = pack(output, name, rows)
        save_json(
            output / "prediction-lock.json",
            dict(
                cases=[q["id"] for q in plan["cases"]],
                files=files,
                statuses=statuses,
                wall_s=perf_counter() - start,
                evaluator_sha256=plan["evaluator_sha256"],
            ),
        )


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("cohort", choices=("primary", "reserve"))
    cli.add_argument("--work", type=Path, default=offers.WORK)
    cli.add_argument("--output", type=Path, default=offers.REPORT)
    cli.add_argument("--bundle", type=Path, default=clock.base.BUNDLE)
    args = cli.parse_args()
    run(args.work / args.cohort, args.bundle, args.output / args.cohort)


if __name__ == "__main__":
    main()
