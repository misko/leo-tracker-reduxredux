"""Lock and measure one held-component reclassification on nine archived RF captures."""

import argparse
import gzip
import os
from hashlib import sha256
from pathlib import Path
from time import perf_counter, time_ns
from unittest.mock import patch

from tools.pipeline_eval.__main__ import (
    ROOT,
    encoded,
    local_output,
    read_predictions,
    save_json,
    write,
)
from tools.pipeline_eval.qualification import bridge_cavity_eval as previous
from tools.pipeline_eval.qualification.aligned_confirmation import _request_proof
from tools.pipeline_eval.qualification.broad_search_budget import (
    _case,
    _stock_archive,
    frozen_inputs,
)
from tools.pipeline_eval.qualification.full_v5_check import _sha
from tools.pipeline_eval.qualification.prefix_figures import csv_file
from tools.pipeline_eval.qualification.projector_roof import roster, validate_prediction
from tools.pipeline_eval.qualification.pruned_finish_eval import execution_binding
from tools.pipeline_eval.qualification.secant_end_to_end_worker import cpu_s, stamp
from tools.pipeline_eval.scoring import ARMS, ROLES, distance_km, distribution, validate_result
from tools.pipeline_eval.variants import bridge_support, orbit_projector, v5_lean

REPORT = ROOT / "reports/2026_11_19_receiver_screening/recovery/bridge-support"
CANDIDATE, PRIOR, STOCK = bridge_support.METHOD, previous.METHOD, previous.STOCK
SEED = "bridge-support-roof-v1:"
EXCLUDE = {*previous.CASES, *previous.TIMING_IDS, *previous.DIAGNOSTIC, "DS26-0175", "DS29-0357"}
COHORTS = {
    "diagnosed": ("DS26-0066", "DS29-0082"),
    "comparison": ("DS26-0036",),
    "confirmation": ("DS26-0032", "DS26-0146", "DS26-0080", "DS29-0127", "DS29-0316", "DS29-0519"),
}
CASES = tuple(i for rows in COHORTS.values() for i in rows)
SCHEDULE = {
    "DS26-0066": (20, (CANDIDATE, PRIOR)),
    "DS26-0032": (20, (PRIOR, CANDIDATE)),
    "DS29-0519": (20, (CANDIDATE, PRIOR)),
    "DS29-0082": (21, (PRIOR, CANDIDATE, STOCK)),
    "DS26-0146": (21, (CANDIDATE, PRIOR)),
    "DS26-0036": (22, (CANDIDATE, PRIOR, STOCK)),
    "DS29-0127": (22, (PRIOR, CANDIDATE)),
    "DS26-0080": (23, (CANDIDATE, PRIOR)),
    "DS29-0316": (23, (PRIOR, CANDIDATE)),
}
FILES = {
    CANDIDATE: "positions.jsonl.gz",
    PRIOR: "prior-positions.jsonl.gz",
    STOCK: "stock-positions.jsonl.gz",
}
LIMITS = {CANDIDATE: 180, PRIOR: 180, STOCK: 250}
TOTAL = 900
read = previous.read


def holdouts(available):
    eligible = set(available) - EXCLUDE
    return tuple(
        i
        for dataset in ("DS26", "DS29")
        for i in sorted(
            (i for i in eligible if i.startswith(dataset)),
            key=lambda i: sha256((SEED + i).encode()).digest(),
        )[:3]
    )


def sources():
    prior_lock = read(previous.REPORT / "source-lock.json")
    if prior_lock["source"] != previous.source_tokens():
        raise ValueError("prior bridge changed")
    return {
        **prior_lock["source"],
        str(Path(bridge_support.__file__).relative_to(ROOT)): _sha(Path(bridge_support.__file__)),
        str(Path(__file__).relative_to(ROOT)): _sha(Path(__file__)),
    }


def archives(bindings):
    stock, hashes = _stock_archive()
    prior_receipt = read(previous.REPORT / "receipt.json")
    path = previous.REPORT / previous.FILES[PRIOR]
    if prior_receipt["files"][path.name] != _sha(path):
        raise ValueError("prior position archive changed")
    prior = read_predictions(path)
    rows = {}
    for ident, binding in bindings.items():
        row = stock[ident]
        if row["input_sha256"] != binding["input_sha256"]:
            raise ValueError(f"{ident} archive differs from current input")
        validate_prediction(row, hashes, allow_failure=True)
        rows[ident] = dict(
            row, **{**binding, "method": STOCK, "qualification": "historical_control"}
        )
        if ident in prior and prior[ident]["input_sha256"] != binding["input_sha256"]:
            raise ValueError(f"{ident} prior bridge used a different input")
    return rows, prior


def lock(path, budget_from=None):
    inputs = frozen_inputs()
    if holdouts(inputs) != COHORTS["confirmation"]:
        raise ValueError("unexpected holdout roster")
    bindings = {i: execution_binding(inputs[i], _case(inputs[i])) for i in CASES}
    archives(bindings)
    tokens = sources()
    target = local_output(path)
    if target.exists():
        raise FileExistsError(target)
    save_json(
        target,
        dict(
            cases=CASES,
            cohorts=COHORTS,
            schedule=SCHEDULE,
            seed=SEED,
            excluded=sorted(EXCLUDE),
            bindings=bindings,
            source=tokens,
            scientific_source=v5_lean.SOURCE_SHA256,
            protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
            limits=LIMITS,
            total_s=TOTAL,
            prior_receipt_sha256=_sha(previous.REPORT / "receipt.json"),
            locked_ns=time_ns() if budget_from is None else read(budget_from)["locked_ns"],
            source_locked_ns=time_ns(),
        ),
    )


def replay(ident, plan_path, output):
    plan = read(plan_path)
    cpu, order = SCHEDULE[ident]
    if os.sched_getaffinity(0) != {cpu} or plan["source"] != sources():
        raise ValueError("locked source or CPU changed")
    item = frozen_inputs()[ident]
    case = _case(item)
    binding = execution_binding(item, case)
    if binding != plan["bindings"][ident]:
        raise ValueError(f"{ident} scientific binding changed")
    folder = local_output(output) / ident
    folder.mkdir(parents=True, exist_ok=False)
    for index, method in enumerate(order):
        entry = orbit_projector if method == STOCK else bridge_support
        mode = {} if method == STOCK else {"mode": "candidate" if method == CANDIDATE else "prior"}
        work = folder / method
        remain = (plan["locked_ns"] + TOTAL * 10**9 - time_ns()) // 10**9
        cap = min(LIMITS[method], max(0, remain))
        start, cpu_start = perf_counter(), cpu_s()
        if cap <= 4:
            result = dict(
                status="timed_out",
                reason="study window expired",
                boundary=entry.BOUNDARY,
                metrics={},
            )
        else:
            work.mkdir()
            with patch.object(v5_lean, "TIMEOUT_S", cap - 4):
                result = entry.run(case, work, **mode)
            if "exceeded its " in result.get("reason", ""):
                result["status"] = "timed_out"
            elif result["status"] == "unavailable":
                log = work / "worker.log"
                if log.is_file() and b"Traceback" in log.read_bytes():
                    result["status"] = "failed"
        usage = stamp(start, cpu_start)
        if result["status"] != "ok":
            result["arms"] = {a: dict(latlon=None) for a in ARMS}
        validate_result(result)
        request = work / "request.json"
        proof = _request_proof(case, request) if request.is_file() else None
        if (result["status"] == "ok" and proof is None) or plan["source"] != sources():
            raise ValueError("replay differs from locked numerical source or input")
        save_json(
            folder / f"{method}.json",
            dict(
                binding,
                method=method,
                cpu=cpu,
                order=index,
                qualification="fresh",
                cap_s=cap,
                worker_wall_s=usage["wall_s"],
                worker_cpu_s=usage["cpu_s"],
                resources=usage,
                source_lock_sha256=_sha(plan_path),
                boundary_proof=proof,
                result=result,
            ),
        )
        print(ident, method, result["status"], round(usage["wall_s"], 3), flush=True)


def seal(plan_path, work):
    plan = read(plan_path)
    if plan["source"] != sources():
        raise ValueError("implementation differs from source lock")
    controls, prior = archives(plan["bindings"])
    groups = {STOCK: controls, PRIOR: {}, CANDIDATE: {}}
    for ident, (cpu, order) in SCHEDULE.items():
        for i, method in enumerate(order):
            row = read(work / ident / f"{method}.json")
            if (
                (row["id"], row["method"], row["cpu"], row["order"]) != (ident, method, cpu, i)
                or row["source_lock_sha256"] != _sha(plan_path)
                or any(row[key] != val for key, val in plan["bindings"][ident].items())
            ):
                raise ValueError("worker differed from the sealed case")
            validate_result(row["result"])
            if method == PRIOR and ident in prior:
                row["prior_endpoint_exact"] = (
                    row["result"]["status"] == prior[ident]["result"]["status"]
                    and row["result"]["arms"] == prior[ident]["result"]["arms"]
                )
            groups[method][ident] = row
    files, runs = {}, {}
    for role, method in (("candidate", CANDIDATE), ("prior", PRIOR), ("control", STOCK)):
        name = FILES[method]
        rows = [
            dict(groups[method][i], cohort=cohort)
            for cohort, roster_cases in COHORTS.items()
            for i in roster_cases
        ]
        write(REPORT / name, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0))
        files[name] = _sha(REPORT / name)
        runs[role] = dict(method=method, positions=name, position_sha256=files[name])
    write(REPORT / "source-lock.json", plan_path.read_bytes())
    receipt = dict(
        cases=CASES,
        cohorts=COHORTS,
        files=files,
        runs=runs,
        source_lock_sha256=_sha(plan_path),
        comparisons=[dict(id=i, input_sha256=plan["bindings"][i]["input_sha256"]) for i in CASES],
    )
    save_json(REPORT / "receipt.json", receipt)
    for cohort, roster_cases in COHORTS.items():
        save_json(REPORT / f"{cohort}-receipt.json", dict(receipt, cases=roster_cases))


def score():
    receipt = read(REPORT / "receipt.json")
    if any(_sha(REPORT / name) != digest for name, digest in receipt["files"].items()):
        raise ValueError("sealed predictions changed")
    refs = {r["id"]: r for r in roster()}
    rows = []
    for method, name in FILES.items():
        for ident, row in read_predictions(REPORT / name).items():
            ref, result = refs[ident], row["result"]
            info = result["metrics"].get("bridge_support", {})
            for arm in ARMS:
                endpoint = result["arms"][arm]
                support = info.get("final_support", {}).get(arm, {})
                points = sum(t["points"] for t in support["curved"]) if support else None
                rows.append(
                    dict(
                        id=ident,
                        method=method,
                        cohort=row["cohort"],
                        arm=arm,
                        status=result["status"],
                        error_km=distance_km(ref["truth"], endpoint["latlon"]),
                        conditional_rms_hz=endpoint.get("rf_rms_hz"),
                        cpu=row.get("cpu"),
                        qualification=row["qualification"],
                        worker_wall_s=row.get("worker_wall_s"),
                        worker_cpu_s=row.get("worker_cpu_s"),
                        prior_exact=row.get("prior_endpoint_exact"),
                        curved_points=points,
                        curved_tracks=len(support["curved"]) if support else None,
                        predictive_points=support.get("predictive_points"),
                        readmitted=len(info["readmitted"]) if "readmitted" in info else None,
                        reassigned=len(info["reassigned"]) if "reassigned" in info else None,
                        reclassification_s=info.get("reclassification_s"),
                        **{
                            f"{s}_s": result["metrics"].get("stage_s", {}).get(s)
                            for s in (
                                "native_preparation",
                                "initial",
                                "conservative",
                                "family",
                                "signed",
                                "cavity",
                            )
                        },
                        **{
                            f"{role}_km": ref["reference"][role][arm].get("error_km")
                            for role in ROLES
                        },
                    )
                )
    csv_file(REPORT / "scores.csv", rows)
    results = []
    for cohort in COHORTS:
        for arm in ARMS:
            data = [r for r in rows if r["cohort"] == cohort and r["arm"] == arm]
            positions = {
                m: distribution(r["error_km"] for r in data if r["method"] == m) for m in FILES
            }
            original = distribution(r["baseline_km"] for r in data if r["method"] == CANDIDATE)
            candidate = positions[CANDIDATE]
            results.append(
                dict(
                    cohort=cohort,
                    arm=arm,
                    methods=positions,
                    original=original,
                    within_10_percent=candidate["n"] == original["n"] == len(COHORTS[cohort])
                    and all(candidate[k] <= 1.1 * original[k] for k in ("p50", "p95")),
                )
            )
    save_json(REPORT / "summary.json", results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_subparsers(dest="action", required=True)
    freeze = command.add_parser("lock")
    freeze.add_argument("plan", type=Path)
    freeze.add_argument("--budget-from", type=Path)
    job = command.add_parser("run")
    job.add_argument("case", choices=CASES)
    job.add_argument("plan", type=Path)
    job.add_argument("work", type=Path)
    package = command.add_parser("seal")
    package.add_argument("plan", type=Path)
    package.add_argument("work", type=Path)
    command.add_parser("score")
    args = parser.parse_args()
    if args.action == "lock":
        lock(args.plan, args.budget_from)
    elif args.action == "run":
        replay(args.case, args.plan, args.work)
    elif args.action == "seal":
        seal(args.plan, args.work)
    else:
        score()


if __name__ == "__main__":
    main()
