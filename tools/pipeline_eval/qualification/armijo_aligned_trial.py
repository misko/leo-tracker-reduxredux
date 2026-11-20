"""Replay the four known compact-finish regressions through the reusable slot guard."""

import argparse
import json
import os
from pathlib import Path
from time import perf_counter

from ..__main__ import local_output, save_json
from ..scoring import validate_result
from ..variants import v5_armijo_aligned_finish as aligned
from ..variants import v5_lean
from . import armijo_finish_phase_retry as retry
from . import armijo_finish_trial as primary
from .broad_search_budget import _case
from .full_v5_check import _load_case, _sha
from .secant_end_to_end_worker import cpu_s, stamp

METHOD = "v5_armijo_aligned_finish"
REPORT = primary.REPORT / "aligned"
SEAL = REPORT / "source-lock.json"
PINS = {"DS26-0066": 6, "DS26-0287": 0, "DS26-0002": 2, "DS29-0082": 3}


def read(path):
    return json.loads(path.read_bytes())


def source_lock():
    primary_lock = primary.REPORT / "prediction-lock.json"
    alignment_lock = read(retry.LOCK)
    if (
        read(primary.SEAL) != primary.source_lock()
        or alignment_lock["retry_source_sha256"] != _sha(Path(retry.__file__))
        or alignment_lock["primary_source_lock_sha256"] != _sha(primary.SEAL)
        or read(primary_lock)["cases"] != list(PINS)
    ):
        raise ValueError("known primary or guarded alignment dependencies changed")
    return dict(
        cases={ident: primary.public_binding(ident) for ident in PINS},
        pins=PINS,
        case_limit_s=primary.CASE_LIMIT_S,
        source_sha256=_sha(Path(aligned.__file__)),
        primary_source_lock_sha256=_sha(primary.SEAL),
        primary_prediction_lock_sha256=_sha(primary_lock),
        validated_alignment_source_sha256=alignment_lock["retry_source_sha256"],
        relative_protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
    )


def run(ident, output):
    locked = read(SEAL)
    if locked != source_lock() or os.sched_getaffinity(0) != {PINS[ident]}:
        raise ValueError("source, archive or CPU differs from the retrospective run lock")
    case = _case(_load_case(ident))
    path = local_output(output) / ident
    path.mkdir(parents=True, exist_ok=False)
    wall, cpu = perf_counter(), cpu_s()
    timeout = v5_lean.TIMEOUT_S
    try:
        v5_lean.TIMEOUT_S = primary.CASE_LIMIT_S - 4
        result = aligned.run(case, path / "position")
    finally:
        v5_lean.TIMEOUT_S = timeout
    duration = stamp(wall, cpu)
    if "exceeded its " in result.get("reason", ""):
        result["status"] = "timed_out"
    validate_result(result)
    if locked != source_lock():
        raise ValueError("retrospective source or inputs changed during inference")
    save_json(
        path / "prediction.json",
        dict(
            primary.public_binding(ident),
            method=METHOD,
            cpu=PINS[ident],
            worker_wall_s=duration["wall_s"],
            worker_cpu_s=duration["cpu_s"],
            resources=duration,
            source_lock_sha256=_sha(SEAL),
            result=result,
        ),
    )
    print(ident, result["status"], round(duration["wall_s"], 3), flush=True)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    actions = cli.add_subparsers(dest="action", required=True)
    actions.add_parser("lock")
    replay = actions.add_parser("run")
    replay.add_argument("case", choices=PINS)
    replay.add_argument("--work", type=Path, required=True)
    options = cli.parse_args()
    if options.action == "lock":
        if SEAL.exists():
            raise ValueError("the aligned source is already locked")
        save_json(SEAL, source_lock())
    else:
        run(options.case, options.work)


if __name__ == "__main__":
    main()
