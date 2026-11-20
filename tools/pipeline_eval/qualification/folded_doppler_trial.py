"""Run both folded Doppler policies and seal their outputs before scoring."""

import argparse
import gzip
import os
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time

from ..__main__ import encoded, save_json, write
from ..scoring import validate_result
from ..variants import folded_doppler
from .cold_input import load, matched_offers

SMOKE = ("DS26-0036", "DS29-0082")
TIMING = ("DS26-0036", "DS26-0122", "DS26-0237", "DS29-0082", "DS29-0174", "DS29-0247")
MODES = ("global", "matched-tile")


def predict(case, mode, cpu):
    os.sched_setaffinity(0, {cpu})
    started, cpu_started = perf_counter(), process_time()
    authority = {}
    try:
        capture = load(case)
        tile = matched_offers(case)[0]["center"] if mode == "matched-tile" else None
        authority = dict(native_sha256=capture.native_sha256, catalog_sha256=capture.catalog_sha256)
        input_digest = sha256(encoded([authority, tile])).hexdigest()
        authority["input_sha256"] = input_digest
        result = folded_doppler.solve(capture, tile=tile)
    except (OSError, ValueError, MemoryError, subprocess.SubprocessError) as error:
        result = dict(
            status="failed", boundary=folded_doppler.BOUNDARY, reason=str(error), metrics={}
        )
    validate_result(result)
    implementation = sha256(Path(folded_doppler.__file__).read_bytes())
    implementation.update(folded_doppler.KERNEL.read_bytes())
    return dict(
        id=case,
        method="folded_doppler",
        mode=mode,
        cpu=cpu,
        **authority,
        worker_wall_s=perf_counter() - started,
        worker_cpu_s=process_time() - cpu_started,
        implementation_sha256=implementation.hexdigest(),
        result=result,
    )


def execute(cases, cpus):
    records = {}
    jobs = [(case, mode) for case in cases for mode in MODES]
    with ProcessPoolExecutor(max_workers=len(cpus)) as pool:
        for start in range(0, len(jobs), len(cpus)):
            batch = jobs[start : start + len(cpus)]
            futures = [
                pool.submit(predict, *job, cpu) for job, cpu in zip(batch, cpus, strict=False)
            ]
            for done in as_completed(futures):
                row = done.result()
                records[row["id"], row["mode"]] = row
                print(
                    row["id"],
                    row["mode"],
                    row["result"]["status"],
                    round(row["worker_wall_s"], 2),
                    flush=True,
                )
    return records


def write_predictions(directory, cases, records):
    locks = {}
    for mode in MODES:
        payload = b"".join(encoded(records[case, mode]) + b"\n" for case in cases)
        data = gzip.compress(payload, mtime=0)
        name = f"{mode}.jsonl.gz"
        write(directory / name, data)
        locks[name] = sha256(data).hexdigest()
    save_json(directory / "prediction-lock.json", dict(cases=cases, files=locks))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--cases", nargs="+", choices=TIMING, default=SMOKE)
    parser.add_argument("--cpus", type=int, nargs="+", default=(0, 1, 2, 3))
    args = parser.parse_args()
    if (
        len(set(args.cases)) != len(args.cases)
        or not set(args.cpus) <= os.sched_getaffinity(0)
        or len(set(args.cpus)) != len(args.cpus)
    ):
        parser.error("use distinct physical recordings and available CPU indexes")
    if any((args.out / name).exists() for name in ("prediction-lock.json", "global.jsonl.gz")):
        parser.error("choose a new output directory")
    args.out.mkdir(parents=True, exist_ok=True)
    write_predictions(args.out, args.cases, execute(args.cases, args.cpus))


if __name__ == "__main__":
    main()
