"""Replay fresh and archived complete factors through the held predictive gate."""

import argparse
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from ..__main__ import local_output, save_json
from ..variants import outside_predictive
from . import region_halo_trial as base

phase = base.phase
REPORT = base.REPORT.parent.parent / "acquisition-support/outside-predictive"
WORK = base.WORK.with_name("outside-predictive")
WORKER = Path(__file__).with_name("outside_predictive_worker.py")
CPUS = (16, 17)
METHOD = outside_predictive.METHOD
BOXES = ((12, 36), (-22, -58))
AGES = (1.75, 6.0)
BASE_COMMAND = base.command


def sources(bundle):
    base_source, jobs = base.sources(bundle)
    paths = (Path(__file__), WORKER, Path(outside_predictive.__file__), REPORT / "PROTOCOL.md")
    return dict(base_source=base_source, source={p.name: phase.digest(p) for p in paths}), jobs


def roof_offers(jobs):
    paths = {q["recording"]: p for q, p in jobs if q["cohort"] == "roof"}
    cases, prior = base.exterior.prior_cases()
    labels = {}
    for folder in base.exterior.SOURCE_COHORTS:
        path = folder / "evaluator.json"
        if phase.digest(path) != phase._read(folder / "prediction-lock.json")["evaluator_sha256"]:
            raise ValueError("archived roof offers differ from their sealed geometry")
        labels.update({r["id"]: r for r in phase._read(path)["labels"]})
    out = []
    for query in cases:
        ident, recording = query["id"], query["recording"]
        if recording not in {"DS26-0102", "DS26-0070"}:
            continue
        label = labels[ident]
        if prior[ident]["input_sha256"] != base.clock.bindings(query)["input_sha256"]:
            raise ValueError("archived roof native inputs do not match the retained smooth result")
        out.append(
            (
                dict(query, cohort="archived-roof"),
                paths[recording],
                dict(
                    truth=label["truth"],
                    source_label=recording,
                    condition=label["condition"],
                    margin_km=label["true_margin_km"],
                ),
            )
        )
    if len(out) != 8:
        raise ValueError("the diagnostic roof input roster must be complete")
    return out


def command(cpu, paths, bundle):
    argv = BASE_COMMAND(cpu, paths, bundle)
    argv[argv.index(str(base.WORKER))] = str(WORKER)
    argv[-3:-3] = [
        "--ro-bind",
        str(Path(outside_predictive.__file__)),
        "/worker/tools/pipeline_eval/variants/outside_predictive.py",
    ]
    return argv


def run(work, output, bundle):
    start = perf_counter()
    if not set(CPUS) <= os.sched_getaffinity(0):
        raise ValueError("the replay expects CPU16 and CPU17")
    work = local_output(work)
    work.mkdir(parents=True, exist_ok=False)
    lock, jobs = sources(bundle)
    save_json(output / "source-lock.json", lock)
    seed = secrets.token_bytes(32)
    with patch.object(base, "BOXES", BOXES), patch.object(base, "AGES_H", AGES):
        items = base.synthetic(work, seed)
    items.extend(roof_offers(jobs))
    items.sort(key=lambda job: (job[0]["cohort"] != "fresh-synthetic", job[0]["id"]))
    queries = [q for q, _, _ in items]
    save_json(
        work / "evaluator.json", dict(seed_hex=seed.hex(), labels={q["id"]: r for q, _, r in items})
    )
    save_json(
        output / "roster.json",
        dict(
            cases=queries,
            cpus=list(CPUS),
            worker_cap_s=base.TIMEOUT,
            batch_cap_s=base.WALL_S,
            evaluator_sha256=phase.digest(work / "evaluator.json"),
            source_sha256=phase.digest(output / "source-lock.json"),
        ),
    )

    def lane(index):
        rows = []
        for query, paths, _ in items[index :: len(CPUS)]:
            if perf_counter() - start <= base.WALL_S - base.TIMEOUT - 5:
                record = base.attempt(query, paths, bundle, CPUS[index])
            else:
                record = base.clock.bindings(query) | dict(
                    method=METHOD,
                    worker_wall_s=None,
                    result=base.clock.failed("missing", "batch cap before admission"),
                )
            print(query["id"], record.get("outside_decision"), flush=True)
            rows.append(record)
        return rows

    with (
        patch.object(base, "command", command),
        patch.object(base, "METHOD", METHOD),
        ThreadPoolExecutor(len(CPUS)) as pool,
    ):
        # The command closure calls the original native halo launcher, then swaps its entrypoint.
        rows = [r for group in pool.map(lane, range(len(CPUS))) for r in group]
    if sources(bundle)[0] != lock:
        raise ValueError("sources changed during blind replay")
    name = f"{METHOD}.jsonl.gz"
    files = {name: base.pack(output, name, rows)}
    files.update(
        {name: phase.digest(output / name) for name in ("roster.json", "source-lock.json")}
    )
    save_json(
        output / "prediction-lock.json",
        dict(
            cases=[q["id"] for q in queries],
            files=files,
            elapsed_s=perf_counter() - start,
        ),
    )


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--work", type=Path, default=WORK)
    cli.add_argument("--output", type=Path, default=REPORT)
    cli.add_argument("--bundle", type=Path, default=base.clock.base.BUNDLE)
    args = cli.parse_args()
    run(args.work, args.output, args.bundle)


if __name__ == "__main__":
    main()
