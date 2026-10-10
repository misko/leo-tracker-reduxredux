"""Explicit serial shard controller; resumes pending slices, never failed attempts."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from execute import HERE, verify


def run_member(member, invoke, read_status):
    statuses = {}
    for phase, maximum in (("search", 6), ("native", 2), ("fixed", 2)):
        status = read_status(member["label"], phase)
        for _ in range(maximum):
            if status is not None and status != "pending":
                break
            status = invoke(member["label"], phase)
        statuses[phase] = status
    return statuses


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("shard", type=int, choices=(0, 1))
    parser.add_argument("--protocol", type=Path, default=HERE / "protocol.json")
    parser.add_argument("--output", type=Path, default=HERE / "results")
    args = parser.parse_args()
    plan = json.loads(args.protocol.read_text())
    verify(plan)
    from leo.contracts.digests import canonical_digest

    digest = canonical_digest(plan)
    args.output.mkdir(parents=True, exist_ok=True)
    result_path = args.output / f"batch-{args.shard}.json"
    if result_path.exists():
        if json.loads(result_path.read_text())["protocol_sha256"] != digest:
            raise ValueError("foreign batch")
        return
    claim = args.output / f"batch-{args.shard}.claim.json"
    with claim.open("x") as stream:
        json.dump(dict(protocol_sha256=digest, shard=args.shard), stream)

    def read_status(label, phase):
        path = args.output / label / phase / "result.json"
        if not path.exists():
            return None
        row = json.loads(path.read_text())
        if row["protocol_sha256"] != digest:
            raise ValueError("foreign phase result")
        return row["status"]

    def invoke(label, phase):
        subprocess.run(
            [
                sys.executable,
                str(HERE / "execute.py"),
                label,
                phase,
                "--protocol",
                str(args.protocol),
                "--output",
                str(args.output),
            ],
            check=True,
        )
        status = read_status(label, phase)
        # Pending slices have a durable done/finished receipt but no terminal result.
        return status or "pending"

    rows = []
    for member in plan["members"][args.shard :: 2]:
        try:
            rows.append(dict(label=member["label"], phases=run_member(member, invoke, read_status)))
        except Exception as error:
            # Preserve crashed claims, do not silently rerun. Other cohort members remain covered.
            rows.append(
                dict(label=member["label"], controller_failure=f"{type(error).__name__}: {error}")
            )
    with result_path.open("x") as stream:
        json.dump(dict(protocol_sha256=digest, shard=args.shard, members=rows), stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
