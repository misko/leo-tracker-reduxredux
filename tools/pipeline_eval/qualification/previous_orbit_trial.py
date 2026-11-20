"""Freeze and replay the isolated prior-decay test from authenticated complete inputs."""

import argparse
import json
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from time import perf_counter

from ..__main__ import local_output, save_json
from ..scoring import validate_result
from ..variants import v5_lean, v5_previous_orbit
from . import orbit_domain_trial as domain
from . import previous_orbit_diagnostic, projector_roof
from .compact_roof_selection_results import normalize_attempt
from .full_v5_check import _sha
from .orbit_domain_results import BINDING_FIELDS
from .secant_end_to_end_worker import cpu_s, stamp

REPORT = domain.REPORT.with_name("previous-orbit")
METHOD = "v5_previous_orbit"
FAILED = domain.ASSERTIONS
CONTROLS = domain.CONTROLS[:2]
CASES = tuple(sorted(FAILED + CONTROLS))
WORK = Path("/tmp/leo-previous-orbit-candidate")
DIAG = Path("/tmp/leo-previous-orbit-diagnostics")
CACHE = Path("/tmp/leo-roof-compact-complement-20261119/cases.json")


def source_lock():
    stock = domain.archived()
    roster = domain.compact.REPORT / "roster.json"
    bindings = json.loads(roster.read_bytes())["bindings"]
    for ident in CASES:
        if (
            any(stock[ident][key] != bindings[ident][key] for key in BINDING_FIELDS)
            or stock[ident]["result"]["status"] != ("failed" if ident in FAILED else "ok")
            or (ident in FAILED and stock[ident]["result"]["reason"] != "AssertionError")
        ):
            raise ValueError(f"{ident} archived compact decision does not match its trial record")
    source = REPORT / "source-lock.json"
    return dict(
        method=METHOD, cases=list(CASES), caps=dict(worker_s=195, numeric_tranche_s=480),
        failed=list(FAILED), controls=list(CONTROLS), bindings={k: bindings[k] for k in CASES},
        worker_sha256=_sha(Path(v5_previous_orbit.__file__)), driver_sha256=_sha(Path(__file__)),
        diagnosis_sha256=_sha(Path(previous_orbit_diagnostic.__file__)),
        protocol_sha256=_sha(source.with_name("PROTOCOL.md")),
        archived_compact_prediction_sha256=_sha(domain.COMPLETION / "all32-prediction-lock.json"),
        orbit_domain_prediction_sha256=_sha(domain.REPORT / "prediction-lock.json"),
        compact_source_sha256=domain.secant_confirmation.frozen_sources(),
        frozen_numerical_sha256=v5_lean.SOURCE_SHA256,
    )


def worker(work, case, stock, binding, cpu, source):
    os.sched_setaffinity(0, {cpu})
    if os.getpriority(os.PRIO_PROCESS, 0) < 10:
        os.setpriority(os.PRIO_PROCESS, 0, 10)
    ident = case["id"]
    if (
        projector_roof.input_hash(case) != binding["input_sha256"]
        or _sha(Path(case["request_path"])) != binding["prepared_request_sha256"]
        or _sha(Path(case["native_path"])) != binding["native_sha256"]
        or _sha(Path(case["catalog_path"])) != binding["catalog_sha256"]
        or case["regions"] != [binding["tile"]]
    ):
        raise ValueError(f"{ident} differs from its authenticated complete native request")
    v5_lean.TIMEOUT_S = 195
    wall, cpu_start = perf_counter(), cpu_s()
    folder = work / ident
    result = v5_previous_orbit.run(case, folder)
    timing = stamp(wall, cpu_start)
    support = folder / "previous-orbit.json"
    row = normalize_attempt(dict(
        id=ident, **{k: stock[k] for k in BINDING_FIELDS},
        method=METHOD, source="fresh-compact-with-missing-old-orbit", mode="matched-tile", cpu=cpu,
        source_lock_sha256=source, attempted=True, worker_returned=True, result=result,
        worker_wall_s=result["metrics"].get("candidate_s", timing["wall_s"]),
        attempt_resource=timing,
        previous_orbit=json.loads(support.read_bytes()) if support.is_file() else None,
    ))
    validate_result(result)
    save_json(folder / "prediction.json", row)
    print(ident, result["status"], result.get("reason"), row["worker_wall_s"], flush=True)


def replay(work, cache):
    seal = REPORT / "source-lock.json"
    lock = json.loads(seal.read_bytes())
    if lock != source_lock():
        raise ValueError("isolated previous-orbit source differs from its registered trial")
    work.mkdir(parents=True, exist_ok=False)
    cases, stock = json.loads(cache.read_bytes()), domain.archived()
    with ProcessPoolExecutor(max_workers=4, max_tasks_per_child=1) as pool:
        futures = [pool.submit(
            worker, work, cases[ident], stock[ident], lock["bindings"][ident], cpu, _sha(seal)
        ) for cpu, ident in enumerate(FAILED + CONTROLS)]
        for job in futures:
            job.result()
    if lock != source_lock():
        raise ValueError("isolated previous-orbit source changed during replay")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", "replay"))
    parser.add_argument("--work", type=Path, default=WORK)
    parser.add_argument("--cases", type=Path, default=CACHE)
    args = parser.parse_args()
    if args.stage == "freeze":
        seal = REPORT / "source-lock.json"
        if seal.exists():
            raise ValueError("the isolated previous-orbit sources were already registered")
        save_json(seal, source_lock())
    else:
        replay(local_output(args.work), args.cases)


if __name__ == "__main__":
    main()
