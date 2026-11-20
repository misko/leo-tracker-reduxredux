"""Run the original full v5 and compact five-refresh secant on a matched pinned host."""

import argparse
import json
import os
from hashlib import sha256
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
from time import perf_counter, time_ns
from unittest.mock import patch

from ..__main__ import local_output, save_json
from ..scoring import validate_result
from ..variants import v5_lean, v5_secant_fit
from . import full_receiver_comparison as common
from . import original_v5
from .aligned_confirmation import _request_proof
from .bridge_cavity_eval import _case, execution_binding, frozen_inputs
from .native_agreement_cascade_eval import compact_wall
from .secant_end_to_end_worker import cpu_s, stamp
from .short_receiver_figures import _frozen_roof

REPORT = common.SCREEN / "deployment/same-core-baseline"
ORIGINAL, COMPACT = "original-baseline", common.COMPACT
SALT = "same-core-no-repair-v1:"
CPUS = (20, 21, 22, 23)
TOTAL_S, NICE = 720, 10
CAP = {ORIGINAL: 500, COMPACT: 185}
MATCH = ("input_sha256", "native_sha256", "catalog_sha256", "tile", "resolved_request_sha256")


def selection(refs, compact):
    cases, strata = [], []
    for dataset in ("DS26", "DS29"):
        eligible = sorted(
            (ref["reference"]["baseline"]["c0"]["wall_s"], ident, compact_wall(compact[ident]))
            for ident, ref in refs.items()
            if ref["group"] == dataset
            and all(r["latlon"] is not None for r in ref["reference"]["baseline"].values())
            and 100 <= ref["reference"]["baseline"]["c0"]["wall_s"] <= 340
            and compact_wall(compact[ident]) < 145
        )
        mid = len(eligible) // 2
        if not mid:
            raise ValueError(f"insufficient eligible {dataset} archived successes")
        for label, half in (("low", eligible[:mid]), ("high", eligible[mid:])):
            stock_s, ident, compact_s = min(
                half, key=lambda r: sha256((SALT + r[1]).encode()).digest()
            )
            cases.append(ident)
            strata.append(
                dict(
                    id=ident,
                    dataset=dataset,
                    half=label,
                    eligible=len(half),
                    historical_original_s=stock_s,
                    historical_compact_s=compact_s,
                )
            )
    return cases, strata


def sources():
    files = (Path(__file__), REPORT / "PROTOCOL.md", Path(original_v5.__file__))
    digests = {str(p.relative_to(common.ROOT)): common.sha(p) for p in files}
    # The ordinary original and compact workers each independently recheck the frozen engine.
    return dict(
        callers=digests,
        engine=v5_lean.SOURCE_SHA256,
        runners=original_v5.RUNNER_DIGESTS,
        compact=common.secant_full.secant.frozen_sources(),
    )


def lock(path):
    refs, inventory = _frozen_roof()
    inputs = common.full_roster(refs, inventory)
    compact, ledger = common.compact_predictions(inputs, refs, audit_archive=True)
    cases, strata = selection(refs, compact)
    bindings = {i: execution_binding(inputs[i], _case(inputs[i])) for i in cases}
    for ident, binding in bindings.items():
        common.require_fields(compact[ident], {k: binding[k] for k in MATCH})
    schedule = {
        str(cpu): dict(id=ident, methods=[ORIGINAL, COMPACT] if j % 2 == 0 else [COMPACT, ORIGINAL])
        for j, (cpu, ident) in enumerate(zip(CPUS, cases, strict=True))
    }
    path = local_output(path)
    if path.exists():
        raise FileExistsError(path)
    save_json(
        path,
        dict(
            cases=cases,
            schedule=schedule,
            strata=strata,
            salt=SALT,
            bindings=bindings,
            sources=sources(),
            stock=ledger,
            nice=NICE,
            total_s=TOTAL_S,
            limit_s=CAP,
            locked_ns=time_ns(),
        ),
    )


def stages_log(path):
    stages = []
    if path.is_file():
        for line in path.read_text(errors="replace").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("event") == "stage":
                stages.append({k: row[k] for k in ("stage", "seconds")})
    return stages


def replay(cpu, method, plan_path, output):
    plan = common.read(plan_path)
    assignment = plan["schedule"][str(cpu)]
    ident = assignment["id"]
    order = assignment["methods"].index(method)
    if os.sched_getaffinity(0) != {cpu} or os.nice(0) < plan["nice"]:
        raise ValueError("wrong affinity or scheduler priority for a locked pair")
    if plan["sources"] != sources():
        raise ValueError("locked runner or compact science changed")
    item = frozen_inputs()[ident]
    case = _case(item)
    binding = execution_binding(item, case)
    if binding != plan["bindings"][ident]:
        raise ValueError("frozen input differs from the locked case")
    output = local_output(output)
    work = output / ident / method
    if order and not (work.parent / assignment["methods"][0] / "measurement.json").is_file():
        raise ValueError("the first scheduled attempt has not finished")
    work.mkdir(parents=True, exist_ok=False)
    cap = min(CAP[method], (plan["locked_ns"] + TOTAL_S * 10**9 - time_ns()) // 10**9)
    start, cpu_start = perf_counter(), cpu_s()
    before = getrusage(RUSAGE_CHILDREN)
    if cap <= 5:
        result = v5_lean._no_fix("Not started by common deadline", status="missing")
    else:
        with patch.object(v5_lean, "TIMEOUT_S", cap - 5):
            if method == ORIGINAL:
                result = original_v5.run(case, work, "baseline")
            else:
                result = v5_secant_fit.run(case, work, "secant")
        if "exceeded its " in result.get("reason", ""):
            result["status"] = "timed_out"
    usage = stamp(start, cpu_start)
    children = getrusage(RUSAGE_CHILDREN)
    usage.update(
        child_user_s=children.ru_utime - before.ru_utime,
        child_system_s=children.ru_stime - before.ru_stime,
    )
    request = work / ("experimental-request.json" if method == ORIGINAL else "request.json")
    proof = _request_proof(case, request) if request.is_file() else None
    if result["status"] == "ok" and (
        proof is None
        or any(
            proof[k] != binding[k] for k in ("resolved_request_sha256", "scientific_request_sha256")
        )
    ):
        raise ValueError(f"{ident} ordinary worker used a different scientific request")
    if (
        result["status"] == "ok"
        and method == COMPACT
        and set(result["metrics"]["initial_phase_refresh_counts"]) != {5}
    ):
        raise ValueError("compact worker did not retain the canonical five-refresh search")
    validate_result(result)
    if plan["sources"] != sources():
        raise ValueError("ordinary worker closure changed")
    save_json(
        work / "measurement.json",
        dict(
            binding,
            method=method,
            cpu=cpu,
            nice=os.nice(0),
            order=order,
            cap_s=max(cap, 0),
            source_lock_sha256=common.sha(plan_path),
            boundary_proof=proof,
            resources=usage if cap > 5 else {},
            result=result,
            original_stage_log=stages_log(work / "v5-worker.log"),
        ),
    )
    print(ident, method, result["status"], round(usage["wall_s"], 3), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    sub.add_parser("lock").add_argument("plan", type=Path)
    job = sub.add_parser("run")
    job.add_argument("cpu", type=int, choices=CPUS)
    job.add_argument("method", choices=(ORIGINAL, COMPACT))
    job.add_argument("plan", type=Path)
    job.add_argument("work", type=Path)
    args = p.parse_args()
    if args.action == "lock":
        lock(args.plan)
    else:
        replay(args.cpu, args.method, args.plan, args.work)


if __name__ == "__main__":
    main()
