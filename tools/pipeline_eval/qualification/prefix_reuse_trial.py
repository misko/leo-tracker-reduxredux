"""Replay verified native prefixes in fresh and persistent workers."""

import argparse
import json
import os
import select
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS
from . import online_full as full
from . import online_prefix_trial as pilot
from .full_v5_check import BULK, _load_case
from .portable_gate_trials import checksum, compressed_rows

OUT = full.SCREEN / "redesign/prefix-reuse"
HERE = Path(__file__).parent
WORKER = HERE / "prefix_reuse_worker.py"
ROOF = ("DS26-0036", "DS26-0122", "DS26-0261", "DS29-0082", "DS29-0174", "DS29-0357")
OMITTED = ("DS26-0102", "DS26-0235")


def source():
    paths = (
        Path(__file__),
        WORKER,
        HERE / "prefix_reuse_cache.py",
        Path(full.__file__),
        OUT / "PROTOCOL.md",
    )
    return dict(stock=pilot.source(), files={p.name: checksum(p) for p in paths})


def predeclared():
    rows = full.roster()
    return [
        next(j for j in rows if j["recording"] == ident and j["condition"] == condition)
        for condition, ids in (("matched", ROOF), ("near-omitted", OMITTED))
        for ident in ids
    ]


def command(cpu, files):
    cmd = pilot.clock.command(cpu, files, pilot.native.BUNDLE)
    cmd[cmd.index(str(pilot.clock.WORKER))] = str(WORKER)
    cmd[-3:-3] = [
        arg
        for p in (pilot.WORKER, pilot.clock.WORKER, HERE / "prefix_reuse_cache.py")
        for arg in ("--ro-bind", str(p), f"/worker/tools/pipeline_eval/qualification/{p.name}")
    ]
    return cmd


def choices(rows):
    pick = {}
    for arm in ARMS:
        full.decision(rows, pick, arm)
    return pick


def streamed(cpu, job, files, doc, stages, *, stop):
    anchor = doc["clock_anchor"]
    request = dict(
        job["request"],
        probe_limit=24_000,
        native=dict(path="/input/not-delivered", sha256="0" * 64),
    )
    begin = perf_counter()
    rows, previous = [], 0
    with subprocess.Popen(
        command(cpu, {k: v for k, v in files.items() if k != "native"}),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ) as child:
        try:
            child.stdin.write(encoded(dict(request=request, anchor=anchor)) + b"\n")
            child.stdin.flush()
            for _, _, binding in stages:
                start = perf_counter()
                audit = binding["capture"]
                count = audit["expected_probes"]
                frame = (
                    encoded(
                        dict(
                            checkpoint=binding["checkpoint"],
                            previous_probes=previous,
                            expected_probes=count,
                            last_sample_counter=audit["last_sample_counter"],
                            probes=doc["source"]["probes"][previous:count],
                        )
                    )
                    + b"\n"
                )
                child.stdin.write(frame)
                child.stdin.flush()
                if not select.select([child.stdout], [], [], pilot.CAP_S)[0]:
                    raise TimeoutError("persistent checkpoint reached its wall cap")
                data = child.stdout.readline(2_000_000)
                if not data.endswith(b"\n"):
                    raise ValueError(child.stderr.read(4000).decode(errors="replace"))
                result = json.loads(data)
                if (
                    result["counts"]["probes"] != count
                    or result["last_sample_counter"] != audit["last_sample_counter"]
                    or result["latest_graph_time_s"] > audit["actual_last_sample_s"]
                    or any(
                        item["latest_s"] > audit["actual_last_sample_s"]
                        for arm in result["orbit_support"].values()
                        for item in arm.values()
                    )
                ):
                    raise ValueError("persistent worker reported a different cutoff")
                rows.append(
                    dict(
                        binding,
                        **result,
                        input_delta_bytes=len(frame),
                        worker_wall_s=perf_counter() - start,
                    )
                )
                print(
                    job["id"],
                    "persistent",
                    binding["checkpoint"],
                    result["result"]["status"],
                    flush=True,
                )
                previous = count
                if stop and len(choices(rows)) == len(ARMS):
                    break
        finally:
            child.stdin.close()
            if child.poll() is None:
                try:
                    child.wait(3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
    return dict(rows=rows, picked=choices(rows), wall_s=perf_counter() - begin)


def comparison(fresh, cached):
    return dict(
        checkpoint=fresh["checkpoint"],
        output=all(fresh["result"][k] == cached["result"][k] for k in ("arms", "status", "reason")),
        graph=all(fresh[k] == cached[k] for k in ("latest_graph_time_s", "graph_tracks"))
        and fresh["result"]["metrics"].get("graph_sha256")
        == cached["result"]["metrics"].get("graph_sha256"),
        support=fresh["orbit_support"] == cached["orbit_support"],
        native=all(fresh["counts"][k] == cached["counts"][k] for k in ("probes", "winning_peaks")),
    )


def run_case(job, cpu, work, *, reverse=False):
    item = _load_case(job["recording"])
    files = {
        k: BULK / item[v]["path"]
        for k, v in (
            ("native", "native"),
            ("catalogue", "catalog"),
            ("track_config", "track_config"),
        )
    }
    if any(checksum(path) != job["request"][k]["sha256"] for k, path in files.items()):
        raise ValueError("source archive digest mismatch")
    doc = full.read(files["native"])
    with TemporaryDirectory(dir=work) as folder:
        stages = []
        for h in full.prefix.HORIZONS:
            path = Path(folder) / str(h)
            path.mkdir()
            stages.append(full.snapshot_job(job, doc, files, h, path))
        if reverse:
            stopped = streamed(cpu, job, files, doc, stages, stop=True)
        fresh = [pilot.attempt(cpu, stage, pilot.CAP_S) for stage in stages]
        if not reverse:
            stopped = streamed(cpu, job, files, doc, stages, stop=True)
        audited = (
            stopped
            if len(stopped["rows"]) == len(stages)
            else streamed(cpu, job, files, doc, stages, stop=False)
        )
    return dict(
        fresh=fresh,
        fresh_picked=choices(fresh),
        persistent=stopped,
        audit=None if audited is stopped else audited,
        parity=[comparison(f, c) for f, c in zip(fresh, audited["rows"], strict=True)],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--cpus", nargs="+", type=int, required=True)
    parser.add_argument("--budget-s", type=int, default=290)
    args = parser.parse_args()
    work = local_output(args.work)
    work.mkdir(exist_ok=False, parents=True)
    start = perf_counter()
    frozen = source()
    save_json(OUT / "source-lock.json", frozen)
    jobs = predeclared()
    save_json(
        OUT / "plan.json",
        dict(
            jobs=[{k: v for k, v in j.items() if k != "terminal"} for j in jobs],
            cpus=args.cpus,
            budget_s=args.budget_s,
        ),
    )

    def lane(items, cpu):
        for i, job in items:
            row = {k: job[k] for k in ("id", "recording", "condition")}
            try:
                if perf_counter() - start >= args.budget_s - 25:
                    raise TimeoutError("replay budget reached before launch")
                row.update(run_case(job, cpu, work, reverse=bool(i % 2)))
            except (AssertionError, OSError, ValueError, KeyError) as exc:
                row["error"] = str(exc) or type(exc).__name__
                print(job["id"], row["error"], flush=True)
            save_json(work / f"{i}.json", row)

    n = len(args.cpus)
    assert len(set(args.cpus)) == n and set(args.cpus) <= os.sched_getaffinity(0)
    indexed = list(enumerate(jobs))
    with ThreadPoolExecutor(n) as pool:
        tasks = [pool.submit(lane, indexed[i::n], cpu) for i, cpu in enumerate(args.cpus)]
        for task in tasks:
            task.result()
    assert source() == frozen
    raw = OUT / "replay.jsonl.gz"
    write(raw, compressed_rows([full.read(work / f"{i}.json") for i in range(len(jobs))]))
    save_json(
        OUT / "prediction-lock.json",
        dict(
            files={p.name: checksum(p) for p in (raw, OUT / "plan.json", OUT / "source-lock.json")},
            wall_s=perf_counter() - start,
        ),
    )


if __name__ == "__main__":
    main()
