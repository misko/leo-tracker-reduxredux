"""Lock and measure the analytic blind seed bridge to the paired v5 cavity."""

import argparse
import gzip
import json
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
from tools.pipeline_eval.qualification.aligned_confirmation import _request_proof
from tools.pipeline_eval.qualification.broad_search_budget import (
    _case,
    _stock_archive,
    frozen_inputs,
)
from tools.pipeline_eval.qualification.full_v5_check import _sha
from tools.pipeline_eval.qualification.prefix_figures import TIMING_IDS, csv_file
from tools.pipeline_eval.qualification.projector_roof import roster, validate_prediction
from tools.pipeline_eval.qualification.pruned_finish_eval import execution_binding
from tools.pipeline_eval.qualification.secant_end_to_end_worker import cpu_s, stamp
from tools.pipeline_eval.scoring import ARMS, ROLES, distance_km, distribution, validate_result
from tools.pipeline_eval.variants import (
    bridge_cavity,
    orbit_projector,
    portable_gate,
    v5_armijo_fit,
    v5_core,
    v5_lean,
    v5_shared_search,
)

REPORT = ROOT / "reports/2026_11_19_receiver_screening/refinement/bridge-cavity"
METHOD, STOCK = bridge_cavity.METHOD, "orbit_projector"
SEED = "bridge-cavity-confirm-v1:"
DIAGNOSTIC = ("DS26-0066", "DS26-0287", "DS26-0152", "DS26-0283", "DS26-0092", "DS26-0072")
COHORTS = dict(
    development=("DS26-0036", "DS29-0082"),
    stress=("DS26-0066",),
    confirmation=("DS26-0313", "DS26-0279", "DS29-0604"),
)
CASES = tuple(i for cohort in COHORTS.values() for i in cohort)
RUNS = {
    "DS26-0036": (20, (METHOD, STOCK)),
    "DS29-0082": (22, (STOCK, METHOD)),
    "DS26-0066": (20, (METHOD,)),
    "DS26-0313": (22, (METHOD,)),
    "DS26-0279": (20, (METHOD,)),
    "DS29-0604": (22, (METHOD,)),
}
DEADLINES = {METHOD: 180, STOCK: 300}
TOTAL = 900
FILES = {METHOD: "positions.jsonl.gz", STOCK: "stock-positions.jsonl.gz"}


def read(path):
    return json.loads(path.read_bytes())


def source_tokens():
    modules = (
        bridge_cavity,
        portable_gate,
        v5_armijo_fit,
        v5_core,
        v5_lean,
        orbit_projector,
        v5_shared_search,
    )
    paths = [*(Path(m.__file__) for m in modules), orbit_projector.KERNEL, Path(__file__)]
    return {str(p.relative_to(ROOT)): _sha(p) for p in paths}


def select_holdouts(ids):
    eligible = set(ids) - set(TIMING_IDS) - set(DIAGNOSTIC)
    return tuple(
        ident
        for dataset, count in (("DS26", 2), ("DS29", 1))
        for ident in sorted(
            (i for i in eligible if i.startswith(dataset)),
            key=lambda i: sha256((SEED + i).encode()).digest(),
        )[:count]
    )


def archived_controls(bindings):
    archive, hashes = _stock_archive()
    controls = {}
    for ident in CASES:
        row = archive[ident]
        expected = bindings[ident]
        if row["input_sha256"] != expected["input_sha256"]:
            raise ValueError(f"{ident} archive differs from the candidate inputs")
        validate_prediction(row, hashes, allow_failure=True)
        controls[ident] = dict(
            row, **{**expected, "method": STOCK, "qualification": "historical_control"}
        )
    return controls


def lock(path, budget_from=None):
    rows = frozen_inputs()
    if select_holdouts(rows) != COHORTS["confirmation"]:
        raise ValueError("blind confirmation differs from locked roster")
    bindings = {i: execution_binding(rows[i], _case(rows[i])) for i in CASES}
    archived_controls(bindings)
    path = local_output(path)
    if path.is_file():
        raise FileExistsError(path)
    save_json(
        path,
        dict(
            cases=CASES,
            cohorts=COHORTS,
            seed=SEED,
            schedule=RUNS,
            bindings=bindings,
            source=source_tokens(),
            frozen_source=v5_lean.SOURCE_SHA256,
            frozen_runner=v5_lean.RUNNER_SHA256,
            deadlines=DEADLINES,
            total_s=TOTAL,
            protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
            locked_ns=time_ns() if budget_from is None else read(budget_from)["locked_ns"],
            source_locked_ns=time_ns(),
        ),
    )


def replay(ident, lock_path, output):
    plan = read(lock_path)
    cpu, order = RUNS[ident]
    if os.sched_getaffinity(0) != {cpu} or plan["source"] != source_tokens():
        raise ValueError("locked sources or CPU changed")
    item = frozen_inputs()[ident]
    case = _case(item)
    binding = execution_binding(item, case)
    if binding != plan["bindings"][ident]:
        raise ValueError(f"{ident} changed scientific input")
    folder = local_output(output) / ident
    folder.mkdir(parents=True, exist_ok=False)
    for index, method in enumerate(order):
        entry = bridge_cavity if method == METHOD else orbit_projector
        work = folder / method
        remain = (plan["locked_ns"] + TOTAL * 10**9 - time_ns()) // 10**9
        cap = min(DEADLINES[method], max(0, remain))
        start, cpu_start = perf_counter(), cpu_s()
        if cap <= 4:
            result = dict(
                status="timed_out",
                reason="study window expired before inference",
                boundary=entry.BOUNDARY,
                metrics={},
            )
        else:
            work.mkdir()
            with patch.object(v5_lean, "TIMEOUT_S", cap - 4):
                result = entry.run(case, work)
            if "exceeded its " in result.get("reason", ""):
                result["status"] = "timed_out"
            elif result["status"] == "unavailable":
                log = work / "worker.log"
                if log.is_file() and b"Traceback" in log.read_bytes():
                    result["status"] = "failed"
        usage = stamp(start, cpu_start)
        if result["status"] != "ok":
            result["arms"] = {arm: dict(latlon=None) for arm in ARMS}
        validate_result(result)
        request = work / "request.json"
        proof = _request_proof(case, request) if request.is_file() else None
        if (result["status"] == "ok" and proof is None) or plan["source"] != source_tokens():
            raise ValueError("completed result differs from its exact source or request")
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
                source_lock_sha256=_sha(lock_path),
                boundary_proof=proof,
                result=result,
            ),
        )
        print(ident, method, result["status"], round(usage["wall_s"], 3), flush=True)


def seal(plan_path, work, output):
    plan = read(plan_path)
    if plan["source"] != source_tokens():
        raise ValueError("locked worker implementation is different")
    output = local_output(output)
    groups = {STOCK: archived_controls(plan["bindings"]), METHOD: {}}
    for ident, (cpu, order) in RUNS.items():
        for i, method in enumerate(order):
            row = read(work / ident / f"{method}.json")
            if (
                (row["id"], row["method"], row["cpu"], row["order"]) != (ident, method, cpu, i)
                or row["source_lock_sha256"] != _sha(plan_path)
                or any(row[k] != v for k, v in plan["bindings"][ident].items())
            ):
                raise ValueError(f"{ident} different input, schedule or method")
            validate_result(row["result"])
            groups[method][ident] = row
    files, runs = {}, {}
    for role, method in (("candidate", METHOD), ("control", STOCK)):
        name = FILES[method]
        records = []
        for cohort, cases in COHORTS.items():
            records.extend(dict(groups[method][i], cohort=cohort) for i in cases)
        raw = b"".join(encoded(r) + b"\n" for r in records)
        write(output / name, gzip.compress(raw, mtime=0))
        files[name] = _sha(output / name)
        runs[role] = dict(method=method, positions=name, position_sha256=files[name])
    write(output / "source-lock.json", plan_path.read_bytes())
    save_json(
        output / "receipt.json",
        dict(
            cases=CASES,
            cohorts=COHORTS,
            files=files,
            runs=runs,
            source_lock_sha256=_sha(plan_path),
            comparisons=[
                dict(id=i, input_sha256=plan["bindings"][i]["input_sha256"]) for i in CASES
            ],
        ),
    )


def score(output):
    lock = read(output / "receipt.json")
    if any(_sha(output / name) != sha for name, sha in lock["files"].items()):
        raise ValueError("sealed bridge predictions changed")
    refs = {r["id"]: r for r in roster()}
    predictions = {m: read_predictions(output / name) for m, name in FILES.items()}
    rows = []
    for ident in CASES:
        ref = refs[ident]
        for method, records in predictions.items():
            row = records[ident]
            result = row["result"]
            for arm in ARMS:
                point = result["arms"][arm]
                rows.append(
                    dict(
                        id=ident,
                        method=method,
                        cohort=row["cohort"],
                        arm=arm,
                        status=result["status"],
                        error_km=distance_km(ref["truth"], point["latlon"]),
                        conditional_rms_hz=point.get("rf_rms_hz"),
                        cpu=row.get("cpu"),
                        qualification=row["qualification"],
                        worker_wall_s=row.get("worker_wall_s"),
                        worker_cpu_s=row.get("worker_cpu_s"),
                        **{
                            f"{stage}_s": result["metrics"].get("stage_s", {}).get(stage)
                            for stage in (
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
    summaries = []
    for cohort in COHORTS:
        for arm in ARMS:
            data = [
                r for r in rows if (r["method"], r["cohort"], r["arm"]) == (METHOD, cohort, arm)
            ]
            pred = distribution(r["error_km"] for r in data)
            original = distribution(r["baseline_km"] for r in data)
            summaries.append(
                dict(
                    cohort=cohort,
                    arm=arm,
                    candidate=pred,
                    original=original,
                    within_10_percent=(
                        pred["n"] == original["n"] == len(data)
                        and all(pred[k] <= 1.1 * original[k] for k in ("p50", "p95"))
                    ),
                )
            )
    csv_file(output / "scores.csv", rows)
    save_json(output / "summary.json", summaries)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    freeze = commands.add_parser("lock")
    freeze.add_argument("plan", type=Path)
    freeze.add_argument("--budget-from", type=Path)
    run = commands.add_parser("run")
    run.add_argument("case", choices=CASES)
    run.add_argument("plan", type=Path)
    run.add_argument("work", type=Path)
    pack = commands.add_parser("seal")
    pack.add_argument("plan", type=Path)
    pack.add_argument("work", type=Path)
    pack.add_argument("output", type=Path, nargs="?", default=REPORT)
    commands.add_parser("score").add_argument("output", type=Path, nargs="?", default=REPORT)
    args = parser.parse_args()
    if args.action == "lock":
        lock(args.plan, args.budget_from)
    elif args.action == "run":
        replay(args.case, args.plan, args.work)
    elif args.action == "seal":
        seal(args.plan, args.work, args.output)
    else:
        score(local_output(args.output))


if __name__ == "__main__":
    main()
