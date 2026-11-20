"""Run the matched capture-era Armijo compact-finish challenge."""

import argparse
import json
import os
from pathlib import Path
from time import perf_counter

from ..__main__ import local_output, save_json
from ..scoring import validate_result
from ..variants import (
    compact_finish,
    orbit_projector,
    v5_armijo_finish,
    v5_armijo_fit,
    v5_core,
    v5_lean,
)
from .armijo_confirmation import binding
from .broad_search_budget import _case
from .full_v5_check import REPO, _load_case, _sha
from .secant_end_to_end_worker import cpu_s, stamp

REPORT = REPO / "reports/2026_11_19_receiver_screening/armijo-finish"
SEAL = REPORT / "source-lock.json"
SCREEN = REPORT.parent / "solver"
ARCHIVE = REPO / "reports/2026_11_19_receiver_streaming/finish"
LANES = {1: ("DS26-0287", "DS29-0082"), 6: ("DS26-0066", "DS26-0002")}
CASES = ("DS26-0066", "DS26-0287", "DS26-0002", "DS29-0082")
CPUS = {case: cpu for cpu, lane in LANES.items() for case in lane}
CASE_LIMIT_S = 480
METHOD = "v5_armijo_finish"


def source_lock():
    armijo_lock = SCREEN / "seal.json"
    armijo = json.loads(armijo_lock.read_bytes())
    finish_lock = ARCHIVE / "source-versions.json"
    finish = json.loads(finish_lock.read_bytes())
    cavity_lock = REPO / "reports/2026_11_19_receiver_convergence/position-fit/seal.json"
    cavity = json.loads(cavity_lock.read_bytes())["compact_source_sha256"]
    files = (v5_armijo_finish, v5_armijo_fit, compact_finish, orbit_projector, v5_core, v5_lean)
    sources = {Path(m.__file__).name: _sha(Path(m.__file__)) for m in files}
    kernel = _sha(orbit_projector.KERNEL)
    if (
        armijo["armijo_source_sha256"] != sources["v5_armijo_fit.py"]
        or finish["delivered_source"] != sources["compact_finish.py"]
        or armijo["control_source_seal_sha256"] != _sha(cavity_lock)
        or any(
            cavity[name] != sources[name]
            for name in ("v5_core.py", "orbit_projector.py", "v5_lean.py")
        )
        or finish["projector_kernel"] != kernel
        or finish["frozen_v5_source"] != v5_lean.SOURCE_SHA256
    ):
        raise ValueError("input optimizer or compact finish source differs from its qualification")
    return dict(
        cases={ident: public_binding(ident) for ident in CASES},
        lanes={str(k): list(v) for k, v in LANES.items()},
        case_limit_s=CASE_LIMIT_S,
        sources=dict(sources, **{orbit_projector.KERNEL.name: kernel}),
        armijo_source_lock_sha256=_sha(armijo_lock),
        cavity_lock_sha256=_sha(cavity_lock),
        compact_finish_source_versions_sha256=_sha(finish_lock),
        frozen_v5_source_sha256=v5_lean.SOURCE_SHA256,
        frozen_v5_runner_sha256=v5_lean.RUNNER_SHA256,
    )


def public_binding(ident):
    row = binding(ident)
    row.pop("variant")
    row["mode"] = "matched-tile"
    return row


def run(ident, work):
    locked = json.loads(SEAL.read_bytes())
    path = local_output(work) / ident
    if locked != source_lock() or os.sched_getaffinity(0) != {CPUS[ident]}:
        raise ValueError("bounded run differs from the source, case or CPU lock")
    case = _case(_load_case(ident))
    path.mkdir(parents=True, exist_ok=False)
    wall, cpu = perf_counter(), cpu_s()
    timeout = v5_lean.TIMEOUT_S
    try:
        v5_lean.TIMEOUT_S = CASE_LIMIT_S - 4
        result = v5_armijo_finish.run(case, path / "position")
    finally:
        v5_lean.TIMEOUT_S = timeout
    duration = stamp(wall, cpu)
    if "exceeded its " in result.get("reason", ""):
        result["status"] = "timed_out"
    validate_result(result)
    receipt = dict(
        public_binding(ident),
        method=METHOD,
        cpu=CPUS[ident],
        worker_wall_s=duration["wall_s"],
        worker_cpu_s=duration["cpu_s"],
        resources=duration,
        source_lock_sha256=_sha(SEAL),
        result=result,
    )
    if locked != source_lock():
        raise ValueError("locked source or input changed during the replay")
    save_json(path / "prediction.json", receipt)
    print(ident, result["status"], round(receipt["worker_wall_s"], 3), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("lock")
    fit = sub.add_parser("run")
    fit.add_argument("case", choices=CASES)
    fit.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "lock":
        if SEAL.exists():
            raise ValueError("the source lock already exists")
        save_json(SEAL, source_lock())
    else:
        run(args.case, args.work)


if __name__ == "__main__":
    main()
