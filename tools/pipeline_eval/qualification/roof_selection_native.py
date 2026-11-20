"""Replay the exact DS26 all159 minus common127 complement without score inputs."""

import argparse
import gzip
import json
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from .. import corpus
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import validate_result
from . import native_clock_full as clock
from . import native_lean_eval as native

REPORT = clock.REPORT.parent.parent / "redesign/roof-selection/native"
CPUS = (12, 16)
WALL_CAP_S = 12 * 60
METHOD = "ds26_selection_native_clock"
RAW = "fresh-positions.jsonl.gz"


def roster():
    all_ids, seals = corpus._selection("ds26-all159")
    common_ids, prior_seals = corpus._selection("ds26-common127")
    excluded = set(all_ids) - set(common_ids)
    if (
        seals != prior_seals
        or len(all_ids) != len(set(all_ids))
        or len(all_ids) != 159
        or len(common_ids) != len(set(common_ids))
        or len(common_ids) != 127
        or len(excluded) != 32
    ):
        raise ValueError("expected the complete frozen DS26 159/127/32 decomposition")
    index = corpus._index(corpus._read_frozen("inputs.jsonl", seals))
    inputs = {ident: index[ident] for ident in all_ids}
    order = sorted(
        excluded, key=lambda ident: corpus._sha(("roof-selection-v1:" + ident).encode("ascii"))
    )
    return inputs, common_ids, order, seals


def bound_query(item):
    ident = item["id"]
    (tile,) = item["regions"]
    if tile["id"] != "original":
        raise ValueError(f"{ident} is missing its original tile offer")
    if not all(isinstance(item.get(key), dict) for key in ("native", "catalog", "track_config")):
        reason = item.get("unavailable")
        if not reason:
            raise ValueError(f"{ident} lacks native authority without a frozen reason")
        return dict(id=ident, recording=ident, cohort="excluded32", unavailable=reason, tile=tile)
    packet, _ = native.request(item, "native")
    return dict(id=ident, recording=ident, cohort="excluded32", packet=packet)


def unavailable(query):
    result = clock.failed("unavailable", query["unavailable"])
    return dict(
        id=query["id"],
        recording=query["recording"],
        cohort=query["cohort"],
        method=clock.METHOD,
        result=result,
        input_sha256=None,
        native_sha256=None,
        catalog_sha256=None,
        tile=query["tile"],
        worker_wall_s=None,
        worker_attempted=False,
    )


def pack(path, rows):
    write(path, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0))
    return clock.phase.digest(path)


def seal_sources(bundle):
    clock_plan, _ = clock.prepare(bundle)
    original = clock.phase._read(clock.REPORT / "plan.json")
    if clock_plan != original:
        raise ValueError("worker differs from the sealed native smooth-clock qualification")
    return original["source"]


def run(output, work):
    if not set(CPUS) <= os.sched_getaffinity(0):
        raise ValueError("expected CPUs 12 and 16")
    work.mkdir(parents=True, exist_ok=False)
    deployment = clock.phase._read(
        clock.base.native.ROOT
        / "reports/2026_11_19_receiver_screening/inference/native-lean/deployment.json"
    )
    bundle, _ = native.bundle_imports(
        [dict(imported_first_party=deployment["files"])], work / "source"
    )
    source = seal_sources(bundle)
    inputs, common, order, seals = roster()
    jobs = [bound_query(inputs[ident]) for ident in order]
    plan = dict(
        all159=list(inputs),
        common127=common,
        excluded32=order,
        jobs=jobs,
        source=source,
        input_inventory_sha256=seals["inputs.jsonl"],
        panel_inventory_sha256=seals["panels.json"],
        protocol_sha256=clock.phase.digest(REPORT / "PROTOCOL.md"),
        parent_prediction_lock_sha256=clock.phase.digest(clock.REPORT / "prediction-lock.json"),
        runner_sha256=clock.phase.digest(Path(__file__)),
        cpus=list(CPUS),
        wall_cap_s=WALL_CAP_S,
        worker_timeout_s=clock.base.CAP,
    )
    save_json(work / "plan.json", plan)
    started = perf_counter()

    def attempt(query, cpu):
        if "unavailable" in query:
            return unavailable(query)
        _, paths = native.request(inputs[query["id"]], "native")
        if perf_counter() - started >= WALL_CAP_S - clock.base.CAP - 5:
            return dict(
                clock.bindings(query),
                result=clock.failed("missing", "batch wall cap before dispatch"),
                worker_wall_s=None,
                worker_attempted=False,
            )
        return dict(clock.attempt(cpu, query, paths, bundle), worker_attempted=True)

    def lane(cpu, batch):
        for query in batch:
            row = attempt(query, cpu)
            validate_result(row["result"])
            save_json(work / f"{query['id']}.json", row)

    with ThreadPoolExecutor(max_workers=len(CPUS)) as pool:
        futures = [pool.submit(lane, cpu, jobs[i :: len(CPUS)]) for i, cpu in enumerate(CPUS)]
        for future in futures:
            future.result()
    elapsed = perf_counter() - started
    if elapsed > WALL_CAP_S or seal_sources(bundle) != source:
        raise ValueError("complement replay changed source or exceeded its batch cap")
    rows = [json.loads((work / f"{ident}.json").read_bytes()) for ident in order]
    save_json(output / "plan.json", plan)
    files = {RAW: pack(output / RAW, rows), "plan.json": clock.phase.digest(output / "plan.json")}
    save_json(
        output / "fresh-lock.json",
        dict(
            cases=order,
            files=files,
            attempted=sum(r["worker_attempted"] for r in rows),
            statuses=dict(Counter(r["result"]["status"] for r in rows)),
            wall_s=elapsed,
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=REPORT)
    args = parser.parse_args()
    run(local_output(args.out), local_output(args.work))


if __name__ == "__main__":
    main()
