"""Run the native track-time null on newly sealed simulations and matched roof offers."""

import argparse
import hashlib
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import numpy as np

from ..__main__ import local_output, save_json
from ..variants import region_null
from . import outside_predictive_trial as diagnostic
from . import region_halo_trial as base

phase = base.phase
REPORT = base.REPORT.parent.parent / "receiver-core/region-null"
WORK = Path("/var/tmp/leo-region-null-20261119")
WORKER = Path(__file__).with_name("region_null_worker.py")
CPUS = (16, 17)
METHOD = region_null.METHOD
BOXES = ((31, 76), (-32, 147))
AGES = (2.25, 7.5)
BASE_COMMAND = base.command


def sources(bundle):
    upstream, jobs = base.sources(bundle)
    paths = (
        Path(__file__),
        WORKER,
        Path(region_null.__file__),
        Path(diagnostic.__file__),
        REPORT / "PROTOCOL.md",
    )
    return dict(upstream=upstream, source={p.name: phase.digest(p) for p in paths}), jobs


def negative_controls(work, sites, seed):
    rng = np.random.default_rng(int.from_bytes(hashlib.sha256(seed + b"peak-lists").digest()))
    entries = []
    for planet, files, label in sites:
        if label["condition"] != "centered":
            continue
        doc = phase._read(files["native"])
        ident, recording = rng.bytes(10).hex(), rng.bytes(10).hex()
        doc["source"]["probes"] = base.simulator._shuffled(doc["source"]["probes"], rng)
        path = work / f"{recording}.native.json"
        save_json(path, doc)
        media = files | {"native": path}
        tile = planet["packet"]["offer"] | {"id": ident}
        entries.append(
            (
                base.native_query(
                    ident,
                    recording,
                    "shuffled-native",
                    doc,
                    media,
                    tile,
                    planet["packet"]["catalog_timestamp"],
                ),
                media,
                dict(
                    truth=None,
                    source_label=label["source_label"],
                    condition="shuffled",
                    margin_km=None,
                ),
            )
        )
    if len(entries) != 2:
        raise ValueError("one negative control is required per new site")
    return entries


def command(cpu, paths, bundle):
    argv = BASE_COMMAND(cpu, paths, bundle)
    argv[argv.index(str(base.WORKER))] = str(WORKER)
    argv[-3:-3] = [
        "--ro-bind",
        str(Path(region_null.__file__)),
        "/worker/tools/pipeline_eval/variants/region_null.py",
    ]
    return argv


def run(work, output, bundle):
    start = perf_counter()
    if not set(CPUS) <= os.sched_getaffinity(0):
        raise ValueError("the replay expects CPU16 and CPU17")
    work = local_output(work)
    work.mkdir(mode=0o700, parents=True, exist_ok=False)
    lock, jobs = sources(bundle)
    save_json(output / "source-lock.json", lock)
    seed = secrets.token_bytes(32)
    with patch.object(base, "BOXES", BOXES), patch.object(base, "AGES_H", AGES):
        items = base.synthetic(work, seed)
    items.extend(negative_controls(work, items, seed))
    items.extend(diagnostic.roof_offers(jobs))
    items.sort(
        key=lambda item: (
            {"fresh-synthetic": 0, "shuffled-native": 1, "archived-roof": 2}[item[0]["cohort"]],
            item[0]["id"],
        )
    )
    queries = [query for query, _, _ in items]
    save_json(
        work / "evaluator.json",
        dict(seed_hex=seed.hex(), labels={query["id"]: label for query, _, label in items}),
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
                row = base.attempt(query, paths, bundle, CPUS[index])
            else:
                row = base.clock.bindings(query) | dict(
                    method=METHOD,
                    worker_wall_s=None,
                    result=base.clock.failed("missing", "batch cap before admission"),
                )
            print(query["id"], row.get("gate", {}).get("state"), flush=True)
            rows.append(row)
        return rows

    with (
        patch.object(base, "command", command),
        patch.object(base, "METHOD", METHOD),
        ThreadPoolExecutor(len(CPUS)) as pool,
    ):
        rows = [row for group in pool.map(lane, range(len(CPUS))) for row in group]
    if sources(bundle)[0] != lock:
        raise ValueError("sources changed during blind replay")
    name = f"{METHOD}.jsonl.gz"
    files = {name: base.pack(output, name, rows)}
    files.update(
        {name: phase.digest(output / name) for name in ("roster.json", "source-lock.json")}
    )
    save_json(
        output / "prediction-lock.json",
        dict(cases=[q["id"] for q in queries], files=files, elapsed_s=perf_counter() - start),
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
