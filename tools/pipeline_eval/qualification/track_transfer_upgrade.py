"""Replay identical sealed geographic transfer packets with the locked exact geometry fit."""

import argparse
import gzip
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..__main__ import THREAD_ENV, encoded, save_json, write
from . import robust_orbit_fit_trials as upgrade
from . import track_transfer as original

METHOD = "robust_orbit_fit"
EXPECTED = "934221dd9747bc984ad15b6a0a537a534584db24a6f73e0815aac1f37a199125"
STAGES = ("observation_s", "orbit_s", "shortlist_s", "fit_s")


def modeled_stages(result):
    metrics = result["metrics"]
    return sum(metrics.get(key, 0) for key in STAGES) if "observation_s" in metrics else None


def bound_packet(raw, binding):
    packet = json.loads(raw)
    if original._sha(raw) != binding["input_sha256"] or encoded(packet) != raw:
        raise ValueError("transfer packet changed after the original prediction seal")
    return packet


def _run(cpu, binding, raw, keys):
    receipt = upgrade.execute(
        METHOD,
        binding["id"],
        binding["dataset"],
        "sealed-transfer",
        bound_packet(raw, binding),
        {},
        cpu,
        keys,
    )
    receipt["fit_wall_s"] = modeled_stages(receipt["result"])
    return receipt


def run(transfer, scratch, fresh):
    os.environ.update(THREAD_ENV)
    os.sched_setaffinity(0, original.CPUS)
    output = transfer / "robust-orbit-fit"
    if (output / "prediction-lock.json").exists():
        raise FileExistsError("the range-rate transfer run is sealed")
    keys = upgrade.locked_sources()
    if (
        keys != original._read(upgrade.OUTPUT / "source-lock.json")
        or keys[f"{METHOD}.py"] != EXPECTED
    ):
        raise ValueError("fixed-assignment receiver differs from its recorded release")
    plan = (transfer / "plan.json").read_bytes()
    prior = original._read(transfer / "prediction-lock.json")
    if original._sha(plan) != prior["plan_sha256"]:
        raise ValueError("original transfer plan changed")
    jobs = [(b, (scratch / f"{b['id']}.json").read_bytes()) for b in json.loads(plan)["queries"]]
    for binding, raw in jobs:
        bound_packet(raw, binding)
    write(output / "plan.json", plan)
    save_json(
        output / "source-lock.json",
        dict(
            method=METHOD,
            exact_release=keys,
            harness_sha256=original._hash(Path(__file__)),
            protocol_sha256=original._hash(output / "PROTOCOL.md"),
            prior_transfer_sha256=original._hash(transfer / "prediction-lock.json"),
        ),
    )
    with ThreadPoolExecutor(max_workers=len(original.CPUS)) as pool:
        tasks = [
            pool.submit(_run, original.CPUS[i % len(original.CPUS)], b, raw, keys)
            for i, (b, raw) in enumerate(jobs)
        ]
        rows = [task.result() for task in tasks]
    path = output / "predictions.jsonl.gz"
    write(path, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0))
    save_json(
        output / "prediction-lock.json",
        dict(
            predictions_sha256=original._hash(path),
            source_lock_sha256=original._hash(output / "source-lock.json"),
            plan_sha256=original._hash(output / "plan.json"),
        ),
    )
    original.score(output, fresh)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transfer", type=Path, default=original.OUTPUT)
    parser.add_argument("--fresh", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    args = parser.parse_args()
    run(args.transfer, args.scratch, args.fresh)


if __name__ == "__main__":
    main()
