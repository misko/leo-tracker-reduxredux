"""Serially resume bounded invocations; launch only after prior shard exits."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def pending(here, shard, digest):
    plan = json.loads((here / "protocol.json").read_text())
    assert 0 <= shard < plan["shards"]
    remaining = []
    for ordinal, binding in enumerate(plan["members"]):
        if ordinal % plan["shards"] != shard:
            continue
        label = binding["member"]["inventory_label"]
        path = here / "results" / f"{label}.json"
        if not path.exists():
            remaining.append(label)
        else:
            result = json.loads(path.read_text())
            assert result["protocol_sha256"] == digest
            assert result["member"] == binding["member"]
            assert result["status"] in ("retained", "complete", "failed")
    return remaining


def run(here, shard, maximum_invocations, invoke=subprocess.run):
    assert maximum_invocations > 0
    digest = hashlib.sha256((here / "protocol.json").read_bytes()).hexdigest()
    for invocation in range(maximum_invocations):
        assert hashlib.sha256((here / "protocol.json").read_bytes()).hexdigest() == digest
        remaining = pending(here, shard, digest)
        if not remaining:
            print("Shard complete", shard, flush=True)
            return
        print("Resume", shard, "invocation", invocation + 1,
              "pending members", len(remaining), flush=True)
        # Blocking here is intentional: never overlap two invocations of one shard.
        # Nonzero exits propagate; only a verified successful process exit resumes.
        invoke([sys.executable, str(here / "evaluate.py"), "--shard", str(shard)], check=True)
    print("Runner bound reached; pending", len(pending(here, shard, digest)), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", type=int, required=True)
    parser.add_argument("--maximum-invocations", type=int, default=3)
    args = parser.parse_args()
    run(HERE, args.shard, args.maximum_invocations)
