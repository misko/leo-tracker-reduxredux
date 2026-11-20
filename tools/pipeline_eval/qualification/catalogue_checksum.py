"""Compare both checksum implementations on every line of a bound causal input catalogue."""

import argparse
import hashlib
import json
import os
import statistics
import time
from pathlib import Path

from tools.pipeline_eval.__main__ import local_output, save_json
from tools.pipeline_eval.qualification.full_v5_check import BULK, PRODUCERS, _load_case
from tools.pipeline_eval.variants.catalogue_checksum import checksum


def scalar_checksum(line):
    """The scalar reference used for the original timing series."""
    return sum(int(char) if char.isdigit() else 1 if char == "-" else 0 for char in line[:68]) % 10


def measure(lines, repeats=5):
    if not lines:
        raise ValueError("no orbital element lines in the catalogue")
    expected = [scalar_checksum(line) for line in lines]
    if [checksum(line) for line in lines] != expected:
        raise ValueError("checksum differs from the original on the input catalogue")
    if any(
        len(line) != 69 or int(line[-1]) != value
        for line, value in zip(lines, expected, strict=True)
    ):
        raise ValueError("an original orbital element line fails its checksum")
    pair = (("original", scalar_checksum), ("bytewise", checksum))
    records = []
    for repeat in range(repeats):
        seconds = {}
        order = pair if repeat % 2 == 0 else reversed(pair)
        for name, function in order:
            start = time.perf_counter()
            total = sum(map(function, lines))
            seconds[name] = time.perf_counter() - start
            if total != sum(expected):
                raise ValueError("checksum differs across timing repetitions")
        records.append(seconds)
    return dict(
        lines=len(lines),
        repeats=records,
        median_paired_speedup=statistics.median(r["original"] / r["bytewise"] for r in records),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=PRODUCERS)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cpus = sorted(os.sched_getaffinity(0))
    if len(cpus) != 1:
        parser.error("pin this timing run to one available CPU")
    entry = _load_case(args.case)
    locator = entry["catalog"]
    data = (BULK / locator["path"]).read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    if sha != locator["sha256"] or entry["catalog_timestamp_ns"] > entry["cutoff_utc_ns"]:
        raise ValueError("catalogue content or causal cutoff differs from the bound request")
    lines = [s for s in data.decode("utf-8").splitlines() if s.startswith(("1 ", "2 "))]
    result = dict(id=args.case, cpu=cpus[0], catalogue_sha256=sha, **measure(lines))
    save_json(local_output(args.out), result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
