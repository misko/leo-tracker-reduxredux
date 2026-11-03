#!/usr/bin/env python3
"""Compare every causal five-second prefix through two tracking CLIs."""

import argparse
import hashlib
import json
import pathlib
import subprocess
import tempfile
import time


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=pathlib.Path)
    parser.add_argument("baseline", type=pathlib.Path)
    parser.add_argument("experiment", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    args = parser.parse_args()

    lines = args.fixture.read_text().splitlines()
    if not lines:
        raise RuntimeError("empty fixture")
    header = lines[0]
    rows = []
    for line in lines[1:]:
        fields = line.split("\t")
        if len(fields) != 13:
            raise RuntimeError("invalid candidate row")
        rows.append((int(fields[8]), fields[0], line))
    rows.sort(key=lambda row: (row[0], row[1]))
    first, last = rows[0][0], rows[-1][0]
    cutoff = first
    cutoffs = []
    while cutoff < last:
        cutoff = min(cutoff + 5_000_000_000, last)
        cutoffs.append(cutoff)

    aggregate = hashlib.sha256()
    exact = 0
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="leo-fit-prefix-") as directory:
        prefix_path = pathlib.Path(directory) / "prefix.tsv"
        for prefix_index, cutoff in enumerate(cutoffs, 1):
            selected = [row[2] for row in rows if row[0] <= cutoff]
            prefix_path.write_text(header + "\n" + "\n".join(selected) + "\n")
            baseline = subprocess.run(
                [args.baseline, prefix_path], check=True, capture_output=True
            ).stdout
            experiment = subprocess.run(
                [args.experiment, prefix_path], check=True, capture_output=True
            ).stdout
            if baseline != experiment:
                raise RuntimeError(f"serialized mismatch at prefix {prefix_index}")
            exact += 1
            aggregate.update(len(baseline).to_bytes(8, "little"))
            aggregate.update(baseline)

    result = {
        "schema": "leo-tracking-exact-fit-cache-oracle-prefix-parity-v1",
        "cutoff_authority": "support-end-utc",
        "candidate_order": "support-end-utc,candidate-id",
        "prefixes": len(cutoffs),
        "exact_serialized_prefixes": exact,
        "aggregate_serialized_sha256": aggregate.hexdigest(),
        "elapsed_seconds": time.monotonic() - started,
        "baseline_binary_sha256": sha256(args.baseline),
        "experiment_binary_sha256": sha256(args.experiment),
        "input_sha256": sha256(args.fixture),
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
