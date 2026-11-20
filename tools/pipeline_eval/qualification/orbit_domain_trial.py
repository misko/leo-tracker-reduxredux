"""Freeze and run the eight-case causal orbit support qualification."""

import argparse
import gzip
import json
import os
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from ..__main__ import local_output, save_json
from ..scoring import validate_result
from ..variants import v5_lean, v5_orbit_domain
from . import compact_roof_selection as compact
from . import orbit_domain_diagnostic, projector_roof, secant_confirmation
from .compact_roof_selection_results import normalize_attempt
from .full_v5_check import _sha
from .secant_end_to_end_worker import cpu_s, stamp

REPORT = compact.REPORT.parents[2] / "deployment/orbit-domain"
COMPLETION = compact.REPORT.with_name("completion")
METHOD = "v5_orbit_domain"
FAILED = ("DS26-0132", "DS26-0156", "DS26-0181", "DS26-0281")
ASSERTIONS = ("DS26-0285", "DS26-0289")
CONTROLS = ("DS26-0034", "DS26-0126", "DS26-0179", "DS26-0265")
CASES = tuple(sorted(FAILED + CONTROLS))
CPUS = (0, 1, 2, 3)
CAP_S = 195


def archived():
    seal = json.loads((COMPLETION / "all32-prediction-lock.json").read_bytes())
    name = "all32-positions.jsonl.gz"
    archive = COMPLETION / name
    if _sha(archive) != seal["files"][name]:
        raise ValueError("matched compact archive disagrees with its prediction lock")
    lines = gzip.decompress(archive.read_bytes()).splitlines()
    rows = {row["id"]: row for row in map(json.loads, lines)}
    if list(rows) != seal["cases"] or any(
        rows[ident]["result"]["status"] != "failed"
        or rows[ident]["result"]["reason"] != "ValueError: " + v5_orbit_domain.OUTSIDE
        for ident in FAILED
    ):
        raise ValueError("matched compact archive lost the recorded orbit-support failures")
    eligible = sorted(
        (row["id"] for row in rows.values()
         if row["result"]["status"] == "ok" and row["worker_wall_s"] < 95),
        key=lambda ident: sha256(f"orbit-domain-control-v1:{ident}".encode()).hexdigest(),
    )
    if tuple(sorted(eligible[:4])) != CONTROLS:
        raise ValueError("unchanged controls disagree with fixed status-and-hash selection")
    return rows


def source_lock():
    rows = archived()
    base = json.loads((compact.REPORT / "roster.json").read_bytes())
    bindings = {ident: base["bindings"][ident] for ident in CASES}
    for ident in CASES:
        if any(rows[ident][field] != bindings[ident][field] for field in (
            "native_sha256", "catalog_sha256", "input_sha256", "frozen_request_sha256", "tile"
        )):
            raise ValueError("compact control does not agree with the selected scientific request")
    return dict(
        method=METHOD, cases=CASES, mandatory_failures=FAILED, unchanged_controls=CONTROLS,
        separate_unmodified_assertion_traces=ASSERTIONS,
        pinned_cpus=CPUS, niceness=10, worker_limit_s=CAP_S, numeric_budget_s=720,
        phase_limit_s=v5_orbit_domain.PHASE_LIMIT_S,
        protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
        revision_sha256=_sha(REPORT / "SAMPLING-GRID.md"),
        sampling_grid_attempt_sha256=_sha(REPORT / "sampling-grid-attempt/prediction-lock.json"),
        variant_sha256=_sha(Path(v5_orbit_domain.__file__)),
        runner_sha256=_sha(Path(__file__)),
        diagnosis_sha256=_sha(Path(orbit_domain_diagnostic.__file__)),
        compact_dependencies=secant_confirmation.frozen_sources(),
        compact_prediction_lock_sha256=_sha(COMPLETION / "all32-prediction-lock.json"),
        original_role_score_lock_sha256=_sha(compact.REPORT / "score-lock.json"),
        original_compact_roster_sha256=_sha(compact.REPORT / "roster.json"),
        frozen_v5_sha256=v5_lean.SOURCE_SHA256, bindings=bindings,
    )


def _worker(work, case, original, binding, lock_sha256, cpu):
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
        raise ValueError(f"{ident} does not bind the archived complete scientific request")
    v5_lean.TIMEOUT_S = CAP_S
    wall, cpu_s0 = perf_counter(), cpu_s()
    folder = work / ident
    result = v5_orbit_domain.run(case, folder)
    timing = stamp(wall, cpu_s0)
    receipt = folder / "orbit-support.json"
    row = normalize_attempt(dict(
        **{key: original[key] for key in (
            "id", "native_sha256", "catalog_sha256", "input_sha256", "frozen_request_sha256", "tile"
        )},
        mode="matched-tile", method=METHOD, source="fresh-compact-causal-support", cpu=cpu,
        worker_wall_s=result["metrics"].get("candidate_s", timing["wall_s"]),
        attempt_resource=timing,
        attempted=True, worker_returned=True, source_lock_sha256=lock_sha256,
        support=json.loads(receipt.read_bytes()) if receipt.is_file() else None,
        result=result,
    ))
    validate_result(row["result"])
    save_json(folder / "prediction.json", row)
    print(ident, result["status"], row["worker_wall_s"], result.get("reason"), flush=True)


def replay(work, cases_file, cpus):
    lock_file = REPORT / "source-lock.json"
    lock = json.loads(lock_file.read_bytes())
    if lock != json.loads(json.dumps(source_lock())):
        raise ValueError("orbit support source or matched requests changed after registration")
    cases = json.loads(cases_file.read_bytes())
    work.mkdir(parents=True, exist_ok=False)
    originals = archived()
    lock_hash = _sha(lock_file)
    if not cpus or len(set(cpus)) != len(cpus) or not set(cpus) <= set(CPUS):
        raise ValueError("replay CPUs must be a unique subset of the four registered lanes")
    pending = iter(FAILED + CONTROLS)
    with ProcessPoolExecutor(max_workers=len(cpus), max_tasks_per_child=1) as pool:
        def submit(ident, cpu):
            return pool.submit(
                _worker, work, cases[ident], originals[ident], lock["bindings"][ident], lock_hash,
                cpu,
            )

        futures = {submit(next(pending), cpu): cpu for cpu in cpus}
        while futures:
            done, _ = wait(futures, return_when=FIRST_COMPLETED)
            for result in done:
                cpu = futures.pop(result)
                result.result()
                if ident := next(pending, None):
                    futures[submit(ident, cpu)] = cpu
    if lock != json.loads(json.dumps(source_lock())):
        raise ValueError("orbit support source or matched requests changed during replay")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("freeze", "replay"))
    parser.add_argument("--work", type=Path, default=Path("/tmp/leo-orbit-domain-candidate-v2"))
    parser.add_argument("--cpus", type=int, nargs="+", default=(1, 2, 3))
    parser.add_argument(
        "--cases", type=Path, default=Path("/tmp/leo-roof-compact-complement-20261119/cases.json")
    )
    args = parser.parse_args()
    if args.stage == "freeze":
        file = REPORT / "source-lock.json"
        if file.exists():
            raise ValueError("orbit support protocol is already registered")
        save_json(file, source_lock())
    else:
        replay(local_output(args.work), args.cases, args.cpus)


if __name__ == "__main__":
    main()
