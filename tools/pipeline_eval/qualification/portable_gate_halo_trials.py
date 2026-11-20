"""Replay the original offers and independently draw a three-query halo control."""

import argparse
import os
import secrets
from pathlib import Path
from unittest.mock import patch

from ..__main__ import local_output, save_json, write
from ..variants import orbit_projector, portable_gate, portable_gate_halo
from . import portable_gate_trials as primary

REPORT = primary.REPORT / "halo"
WORKER = Path(__file__).with_name("portable_gate_halo_worker.py")


def source():
    files = (Path(__file__), WORKER, Path(portable_gate_halo.__file__))
    return dict(primary=primary.lock(), halo={p.name: primary.checksum(p) for p in files})


def infer(scratch, report, cpus, seed_hex):
    lock = source()
    save_json(report / "source-lock.json", lock)
    seed = bytes.fromhex(seed_hex) if seed_hex else secrets.token_bytes(32)
    history, old_labels, old_history = primary.historical_jobs()
    fresh, new_labels, new_history = primary.synthesise(seed)
    if old_history != new_history:
        raise ValueError("actual causal catalogue history must be shared across the replay")
    jobs = [*history, *fresh[:2], fresh[-1]]
    kernel = scratch / "projector.so"
    orbit_projector.compile_kernel(kernel)
    command = primary.worker_command

    def halo_command(cpu, objects, library, worker, modules):
        return command(cpu, objects, library, worker, (*modules, portable_gate))

    with (
        patch.object(primary, "worker_command", halo_command),
        patch.object(primary, "WORKER", WORKER),
        patch.object(primary, "portable_gate", portable_gate_halo),
    ):
        rows = primary.trial(jobs, kernel, cpus)
    if source() != lock:
        raise ValueError("halo receiver sources changed since their prospective lock")
    seal = {}
    groups = ("historical.jsonl.gz", rows[: len(history)]), ("fresh.jsonl.gz", rows[len(history) :])
    for name, group in groups:
        write(report / name, primary.compressed_rows(group))
        seal[name] = primary.checksum(report / name)
    save_json(report / "prediction-lock.json", dict(files=seal))
    save_json(
        report / "labels.json", dict(historical=old_labels, fresh=new_labels, seed_hex=seed.hex())
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--cpus", type=int, nargs=2, default=(4, 5))
    parser.add_argument("--seed-hex")
    parser.add_argument("--score", action="store_true")
    args = parser.parse_args()
    scratch, report = local_output(args.scratch), local_output(args.report)
    if args.score:
        primary.score(report)
    else:
        if len(set(args.cpus)) != 2 or not set(args.cpus) <= os.sched_getaffinity(0):
            parser.error("choose two distinct available CPUs")
        scratch.mkdir(exist_ok=True, parents=True)
        infer(scratch, report, args.cpus, args.seed_hex)


if __name__ == "__main__":
    main()
