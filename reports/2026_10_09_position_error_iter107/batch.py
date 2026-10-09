"""Two deterministic metadata-interleaved shards; serial bounded members."""

import argparse
import hashlib
import importlib.util
import json
import os
from itertools import zip_longest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("cohort107_controller", HERE / "controller.py")
CONTROLLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTROLLER)
DATASETS = ("DS16", "DS17", "DS18", "POST18-development")


def label(member):
    return member["member"].get("inventory_label", member["member"].get("dataset_label"))


def interleave(members):
    groups = {
        name: sorted(
            [m for m in members if m.get("dataset", m["member"].get("dataset")) == name],
            key=label,
        )
        for name in DATASETS
    }
    ordered = [member for row in zip_longest(*groups.values()) for member in row if member]
    if len(ordered) != len(members):
        raise ValueError("Unknown dataset or incomplete membership")
    labels = [label(member) for member in ordered]
    if len(set(labels)) != len(labels):
        raise ValueError("Duplicate membership label")
    return ordered


def run_shard(plan, shard, *, maximum_members=None, here=HERE, invoke=None):
    if shard not in (0, 1) or plan["maximum_workers"] != 2:
        raise ValueError("Expected one of two frozen shards")
    if maximum_members is not None and maximum_members < 0:
        raise ValueError("Negative member cap")
    if invoke is None:
        invoke = CONTROLLER.CONTROLLER.run_member
    selected = plan["labels"][shard::2]
    if maximum_members is not None:
        selected = selected[:maximum_members]
    return [dict(label=name, outcome=invoke(name, here=here)) for name in selected]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", required=True, type=int, choices=(0, 1))
    parser.add_argument("--max-members", type=int)
    arguments = parser.parse_args()
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        if os.environ.get(name) != "1":
            raise ValueError(name + "=1 required")
    plan = json.loads((HERE / "protocol.json").read_text())
    root = HERE.parents[1]
    for name, expected in plan["source_sha256"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name
    outcomes = run_shard(plan, arguments.shard, maximum_members=arguments.max_members)
    print(json.dumps(outcomes), flush=True)


if __name__ == "__main__":
    main()
