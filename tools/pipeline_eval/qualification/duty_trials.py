"""Counterbalanced paired channel-scheduling trials on the existing six timing recordings."""

import argparse
import gzip
import os
from concurrent.futures import ThreadPoolExecutor
from itertools import permutations
from pathlib import Path

from ..__main__ import DEFAULT_OUT, encoded, local_output, public_cases, references, run_one, write
from ..variants.channel_schedule import SCHEDULES
from .prefix_figures import TIMING_IDS


def trials(out, cpus, study="channels"):
    out = local_output(out)
    out.mkdir(parents=True, exist_ok=True)
    if (
        len(cpus) != len(TIMING_IDS)
        or len(set(cpus)) != len(cpus)
        or not set(cpus) <= os.sched_getaffinity(0)
    ):
        raise ValueError("choose six different permitted CPUs for the six concurrent pairs")
    if study == "channels":
        orders = permutations(("v5_core", *SCHEDULES))
    elif study == "projector":
        pair = ("v5_lean", "orbit_projector")
        orders = [pair if i % 2 == 0 else pair[::-1] for i in range(len(TIMING_IDS))]
    else:
        raise ValueError("unknown paired study")
    cases = {}
    for panel, prefix in (("ds26-common127", "DS26"), ("roof16", "DS29")):
        source, refs = references(panel, [k for k in TIMING_IDS if k.startswith(prefix)])
        cases.update({c["id"]: c for c in public_cases(source, refs, DEFAULT_OUT / "inputs")})

    def series(item):
        ident, cpu, order = item
        rows = []
        for index, method in enumerate(order):
            result = run_one(method, cases[ident], out, 720, cpu)
            result.update(method=method, cpu=cpu, execution_order=index)
            write(out / (ident + "-" + method + ".json"), encoded(result) + b"\n")
            print(
                ident,
                method,
                result["result"]["status"],
                round(result["worker_wall_s"], 2),
                flush=True,
            )
            rows.append(result)
        return rows

    with ThreadPoolExecutor(max_workers=len(cpus)) as pool:
        jobs = zip(TIMING_IDS, cpus, orders, strict=True)
        batches = list(pool.map(series, jobs))
    data = b"".join(encoded(r) + b"\n" for rows in batches for r in rows)
    write(out / "paired.jsonl.gz", gzip.compress(data, mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cpus", type=int, nargs=6, required=True)
    parser.add_argument("--study", choices=("channels", "projector"), default="channels")
    args = parser.parse_args()
    trials(args.out, args.cpus, args.study)
