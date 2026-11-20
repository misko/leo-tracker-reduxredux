"""Run the frozen marginal-offset and zero-variance receivers over all archived queries."""

import argparse
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Empty, SimpleQueue
from time import perf_counter
from unittest.mock import patch

from ..__main__ import encoded, local_output, save_json
from ..scoring import ARMS
from . import marginal_offset as small
from .marginal_offset_results import _rows
from .phase_confirmation import _read, digest
from .secant_full import _verify_files

REPORT = small.REPORT.with_name("marginal-full")
CPUS = (0, 2, 3, 6, 7, 10, 11, 17)
PAIR_START_LIMIT_S = 7 * 60
WORKER = Path(__file__).with_name("marginal_offset_full_worker.py")
ORIGINAL_COMMAND = small.command


def command(cpu, paths, bundle):
    argv = ORIGINAL_COMMAND(cpu, paths, bundle)
    argv[argv.index(str(small.WORKER))] = str(WORKER)
    argv[-3:-3] = [
        "--ro-bind",
        str(small.WORKER),
        "/worker/tools/pipeline_eval/qualification/marginal_offset_worker.py",
    ]
    return argv


def roster(bundle):
    old = _read(small.REPORT / "prediction-lock.json")
    _verify_files(small.REPORT, old["files"])
    inherited = _read(small.REPORT / "source-lock.json")
    if small.sources(bundle) != inherited:
        raise ValueError("both offset fits must use the sealed earlier sources")
    previous = {q["id"]: q["cohort"] for q in _read(small.REPORT / "plan.json")["cases"]}
    _, jobs = small.full.prepare(bundle)
    fixed = []
    for row, paths in jobs:
        roof = row["cohort"] == "roof"
        group = previous.get(row["id"])
        fixed.append(
            (dict(row, membership=group or "unseen", scope="roof" if roof else "omitted"), paths)
        )
    counts = {k: sum(row["scope"] == k for row, _ in fixed) for k in ("roof", "omitted")}
    if counts != {"roof": 135, "omitted": 9} or len(previous) != 13:
        raise ValueError("unexpected complete or earlier-cohort roster")
    return fixed, inherited


def _unstarted(query, method, reason):
    packet = query["packet"]
    return dict(
        id=query["id"],
        recording=query["recording"],
        cohort=query["cohort"],
        method=method,
        input_sha256=small.corpus._sha(encoded(packet)),
        native_sha256=packet["native"]["sha256"],
        catalog_sha256=packet["catalogue"]["sha256"],
        tile=packet["offer"],
        result=dict(
            status="missing",
            reason=reason,
            boundary=small.variant.BOUNDARY,
            metrics={},
            arms={arm: dict(latlon=None) for arm in ARMS},
        ),
    )


def run(work, bundle, out):
    if not set(CPUS) <= os.sched_getaffinity(0):
        raise ValueError("all frozen replay CPUs must be available")
    work, out = local_output(work), local_output(out)
    work.mkdir(parents=True, exist_ok=False)
    jobs, base = roster(bundle)
    source = dict(
        original=base,
        files={
            name: digest(path)
            for name, path in (
                (str(Path(__file__).relative_to(small.corpus.REPO)), Path(__file__)),
                (str(WORKER.relative_to(small.corpus.REPO)), WORKER),
                ("PROTOCOL.md", REPORT / "PROTOCOL.md"),
            )
        },
    )
    prior = small.full.REPORT
    archive_lock = _read(prior / "prediction-lock.json")
    _verify_files(prior, archive_lock["files"])
    archived = _rows(prior / "positions.jsonl.gz")
    plan = dict(
        cases=[q for q, _ in jobs],
        cpus=CPUS,
        both_fresh=True,
        pair_start_limit_s=PAIR_START_LIMIT_S,
        source=source,
        paired_reference_sha256=digest(prior / "prediction-lock.json"),
        prior_offset_receipt_sha256=digest(small.REPORT / "prediction-lock.json"),
    )
    save_json(out / "plan.json", plan)
    save_json(out / "source-lock.json", source)
    queue = SimpleQueue()
    for index, job in enumerate(jobs):
        queue.put((index, job))
    start = perf_counter()

    def replay(cpu):
        while perf_counter() - start < PAIR_START_LIMIT_S:
            try:
                index, (query, paths) = queue.get_nowait()
            except Empty:
                return
            ident = query["id"]
            scales = (0.0, small.variant.SIGMA_HZ)
            for scale in scales if index % 2 == 0 else scales[::-1]:
                row = small.attempt(query, paths, archived[ident], cpu, bundle, scale)
                save_json(work / f"{ident}-{row['method']}.json", row)

    with patch.object(small, "command", command), ThreadPoolExecutor(len(CPUS)) as pool:
        list(pool.map(replay, CPUS))
    if (
        small.sources(bundle) != base
        or digest(WORKER) != source["files"][str(WORKER.relative_to(small.corpus.REPO))]
    ):
        raise ValueError("the sealed worker changed during replay")
    for method, filename in zip(
        (small.variant.METHOD, small.variant.STOCK), small.FILES, strict=True
    ):
        rows = []
        for query, _ in jobs:
            path = work / f"{query['id']}-{method}.json"
            result = _read(path) if path.exists() else _unstarted(query, method, "pair start cap")
            rows.append(dict(result, membership=query["membership"], scope=query["scope"]))
        small._write_predictions(out / filename, rows)
    names = (*small.FILES, "plan.json", "source-lock.json")
    save_json(
        out / "prediction-lock.json",
        dict(
            cases=[q["id"] for q, _ in jobs],
            files={name: digest(out / name) for name in names},
            worker_wall_s=perf_counter() - start,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--out", default=REPORT, type=Path)
    parser.add_argument("--bundle", default=small.base.BUNDLE, type=Path)
    args = parser.parse_args()
    run(args.work, args.bundle, args.out)
