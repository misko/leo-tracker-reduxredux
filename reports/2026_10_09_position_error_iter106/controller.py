"""Bounded two-shard launcher for the frozen full-membership width experiment."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def launch(shard, maximum_members=8, *, here=HERE, invoke=subprocess.run):
    if shard not in (0, 1) or maximum_members < 1:
        raise ValueError("Use shard 0 or 1 and a positive member cap")
    protocol = json.loads((here / "protocol.json").read_text())
    digest = hashlib.sha256((here / "protocol.json").read_bytes()).hexdigest()
    labels = protocol["labels"]
    if protocol["shards"] != 2 or len(labels) != len(set(labels)):
        raise ValueError("Invalid frozen membership/shards")
    completed, launched = [], 0
    for index, label in enumerate(labels):
        if index % 2 != shard:
            continue
        if Path(label).name != label or label in (".", ".."):
            raise ValueError("Label is not a membership identifier")
        result_path = here / "results" / f"{label}.json"
        if not result_path.exists():
            if launched == maximum_members:
                break
            claim = here / "controller-claims" / f"{label}.json"
            claim.parent.mkdir(parents=True, exist_ok=True)
            # A crash consumes the launch. Never infer a retry from an absent result.
            with claim.open("x") as stream:
                json.dump(dict(label=label, shard=shard, protocol_sha256=digest), stream)
            child = invoke(
                [sys.executable, str(here / "engine.py"), "--label", label],
                cwd=ROOT,
                check=False,
            )
            launched += 1
            with claim.with_suffix(".exit.json").open("x") as stream:
                json.dump(dict(returncode=child.returncode, protocol_sha256=digest), stream)
            if child.returncode:
                raise RuntimeError(f"{label}: child exited {child.returncode}; receipts preserved")
            if not result_path.exists():
                raise RuntimeError(f"{label}: no terminal receipt; refusing retry")
        result = json.loads(result_path.read_text())
        if result.get("protocol_sha256") != digest:
            raise ValueError(f"{label}: result belongs to another protocol")
        if result.get("status") not in ("complete", "failed", "input-failed"):
            raise ValueError(f"{label}: unknown terminal status")
        completed.append(dict(label=label, status=result["status"]))
    return dict(shard=shard, launched=launched, completed=completed)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", type=int, required=True)
    parser.add_argument("--maximum-members", type=int, default=8)
    args = parser.parse_args()
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        if os.environ.get(name) != "1":
            raise ValueError(f"{name}=1 is required")
    print(json.dumps(launch(args.shard, args.maximum_members)), flush=True)


if __name__ == "__main__":
    main()
