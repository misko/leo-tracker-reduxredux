"""Measure and seal matched numerical replays of the pruned aligned finish."""

import argparse
import fcntl
import gzip
import json
import os
import sys
from contextlib import ExitStack
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
from tools.pipeline_eval.qualification import aligned_confirmation, armijo_aligned_trial
from tools.pipeline_eval.qualification.broad_search_budget import _case, frozen_inputs
from tools.pipeline_eval.qualification.full_v5_check import _sha
from tools.pipeline_eval.qualification.prefix_figures import csv_file
from tools.pipeline_eval.qualification.projector_roof import roster
from tools.pipeline_eval.qualification.secant_end_to_end_worker import cpu_s, measured, stamp
from tools.pipeline_eval.qualification.secant_full import _binding
from tools.pipeline_eval.scoring import ARMS, ROLES, distance_km, validate_result
from tools.pipeline_eval.variants import (
    compact_finish,
    orbit_projector,
    v5_armijo_aligned_finish,
    v5_lean,
    v5_pruned_finish,
)

REPORT = ROOT / "reports/2026_11_19_receiver_screening/inference/pruned-finish"
HISTORICAL = armijo_aligned_trial.REPORT
STOCK, CANDIDATE = armijo_aligned_trial.METHOD, v5_pruned_finish.METHOD
DEADLINE, TOTAL = 480, 1200
SEED = "pruned-finish-normal-v1:"
KNOWN = tuple(armijo_aligned_trial.PINS)
NORMALS = ("DS26-0175", "DS29-0357")
CASES = KNOWN + NORMALS
SCHEDULE = {
    "DS26-0066": (20, (CANDIDATE,)),
    "DS26-0287": (20, (CANDIDATE,)),
    "DS26-0002": (22, (CANDIDATE,)),
    "DS29-0082": (22, (CANDIDATE,)),
    "DS26-0175": (20, (STOCK, CANDIDATE)),
    "DS29-0357": (22, (CANDIDATE, STOCK)),
}
FILES = {CANDIDATE: "positions.jsonl.gz", STOCK: "stock-positions.jsonl.gz"}


def read(path):
    return json.loads(path.read_bytes())


def source_tokens():
    aligned_lock = armijo_aligned_trial.read(armijo_aligned_trial.SEAL)
    if aligned_lock != armijo_aligned_trial.source_lock():
        raise ValueError("aligned control dependencies changed")
    return dict(
        candidate=_sha(Path(v5_pruned_finish.__file__)),
        qualification=_sha(Path(__file__)),
        aligned_lock=_sha(armijo_aligned_trial.SEAL),
        archive_lock=_sha(HISTORICAL / "prediction-lock.json"),
        protocol=_sha(REPORT / "PROTOCOL.md"),
        frozen_source=v5_lean.SOURCE_SHA256,
        frozen_runner=v5_lean.RUNNER_SHA256,
    )


def execution_binding(item, case):
    request = Path(case["request_path"])
    return dict(
        _binding(item, case),
        **aligned_confirmation._request_proof(case, request),
    )


def historical_controls(bindings):
    seal = read(HISTORICAL / "prediction-lock.json")
    file = HISTORICAL / "positions.jsonl.gz"
    request = HISTORICAL / "matched-requests.json"
    if (
        seal["cases"] != list(KNOWN)
        or seal["source_lock_sha256"] != _sha(armijo_aligned_trial.SEAL)
        or any(_sha(p) != seal["files"][p.name] for p in (file, request))
    ):
        raise ValueError("authentic aligned predictions or requests changed")
    rows, matched = read_predictions(file), read(request)
    if list(rows) != list(KNOWN):
        raise ValueError("unexpected authenticated challenge roster")
    for ident, row in rows.items():
        expected = bindings[ident]
        if (
            row["method"] != STOCK
            or row["source_lock_sha256"] != seal["source_lock_sha256"]
            or row["result"]["status"] != "ok"
            or any(
                row[k] != expected[k] for k in ("input_sha256", "native_sha256", "catalog_sha256")
            )
            or row["request_sha256"] != expected["frozen_request_sha256"]
            or matched[ident]["scientific_request_sha256"] != expected["scientific_request_sha256"]
        ):
            raise ValueError(f"{ident} archived aligned control used another request")
        rows[ident] = dict(row, **{**expected, "qualification": "historical_control"})
    return rows


def lock(path):
    inputs = frozen_inputs()
    blind = aligned_confirmation.roster(inputs)["confirmation"]
    selected = tuple(
        min(
            (ident for ident in blind if ident.startswith(dataset)),
            key=lambda ident: aligned_confirmation.phase.corpus._sha((SEED + ident).encode()),
        )
        for dataset in ("DS26", "DS29")
    )
    if selected != NORMALS:
        raise ValueError("the independent recordings differ from their predeclared blind selector")
    bindings = {ident: execution_binding(inputs[ident], _case(inputs[ident])) for ident in CASES}
    historical_controls(bindings)
    path = local_output(path)
    if path.exists():
        raise FileExistsError(path)
    save_json(
        path,
        dict(
            cases=CASES,
            bindings=bindings,
            source=source_tokens(),
            schedule=SCHEDULE,
            cohorts=dict(known=KNOWN, normals=NORMALS),
            seed=SEED,
            worker_deadline_s=DEADLINE,
            study_deadline_s=TOTAL,
            locked_ns=time_ns(),
        ),
    )


def observe_finish(operation, report, *args, **kwargs):
    from leo.analysis.localization_v3 import (
        additional_recovery,
        reassociation_context,
        residual_preflight,
        residual_screen,
    )

    from leo.application import localization_v3

    stages = report.setdefault("stages", {})
    calls = report.setdefault("work", dict(arm_omissions=0, nomination_grids=0, ecef_states=0))

    def count(name, original, *, omitted=False):
        def run(*a, **kw):
            if not omitted or kw.get("omit") is not None:
                calls[name] = calls.get(name, 0) + 1
            return original(*a, **kw)

        return run

    rank = reassociation_context.rank_families

    def ranked(context):
        build = reassociation_context.build
        with patch.object(
            reassociation_context, "build", count("arm_omissions", build, omitted=True)
        ):
            rows, selected = rank(context)
        report["eligible_scores"] = [
            {k: row[k] for k in ("norad", "points", "tracks", "rank_score")}
            for row in rows
            if row["points"] >= 30 and row["tracks"] >= 2
        ]
        report["selected"] = selected
        return rows, selected

    with ExitStack() as stack:
        for owner, name, label, fn in (
            (residual_preflight, "preflight", "residual_preflight", None),
            (residual_screen, "screen_candidates", "residual_screen", None),
            (additional_recovery, "recover_additional", "addition", None),
            (reassociation_context, "rank_families", "ranking", ranked),
            (localization_v3, "screen_reassociation_candidates", "admission", None),
            (localization_v3, "fit_reassociation", "final", None),
        ):
            stack.enter_context(
                patch.object(owner, name, measured(fn or getattr(owner, name), label, stages))
            )
        for name in ("_nomination_grids", "ecef_states"):
            wrapper = count(name.removeprefix("_"), getattr(residual_screen, name))
            stack.enter_context(patch.object(residual_screen, name, wrapper))
        return operation(*args, **kwargs)


def worker(request, target, library, method):
    from functools import partial

    variant = v5_pruned_finish if method == CANDIDATE else v5_armijo_aligned_finish
    report = {}
    with patch.object(
        compact_finish, "finish", partial(observe_finish, compact_finish.finish, report)
    ):
        variant.worker(request, target, library)
    target = Path(target)
    result = read(target)
    result["metrics"]["measured_finish"] = report
    if result["status"] == "ok" and set(report) != {
        "stages",
        "work",
        "eligible_scores",
        "selected",
    }:
        raise ValueError("successful qualification omitted finish instrumentation")
    save_json(target, result)


def replay(plan_path, ident, work):
    lock_data = read(plan_path)
    if lock_data["source"] != source_tokens() or lock_data["cases"] != list(CASES):
        raise ValueError("pruned finish source or roster changed")
    cpu, methods = SCHEDULE[ident]
    if os.sched_getaffinity(0) != {cpu}:
        raise ValueError(f"{ident} must remain on CPU {cpu}")
    item = frozen_inputs()[ident]
    case = _case(item)
    binding = execution_binding(item, case)
    if binding != lock_data["bindings"][ident]:
        raise ValueError(f"{ident} inputs differ from the pre-inference lock")
    directory = local_output(work) / ident
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "pair.lock").open("a") as lockfile:
        fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for order, method in enumerate(methods):
            target = directory / f"{method}.json"
            if target.exists():
                raise FileExistsError(target)
            position = directory / method
            position.mkdir(exist_ok=False)
            remain = (lock_data["locked_ns"] + TOTAL * 10**9 - time_ns()) // 10**9
            cap = min(DEADLINE, max(0, remain))
            wall, start_cpu = perf_counter(), cpu_s()
            if cap <= 4:
                result = dict(
                    status="timed_out",
                    reason="study deadline elapsed before launch",
                    boundary=v5_pruned_finish.BOUNDARY,
                    metrics={},
                )
            else:
                library = position / "orbit_projector.so"
                orbit_projector.compile_kernel(library)
                with patch.object(v5_lean, "TIMEOUT_S", cap - 4):
                    result = v5_lean.run_bound_worker(
                        case,
                        position,
                        Path(__file__),
                        worker_args=(str(library), method),
                    )
                if "exceeded its " in result.get("reason", ""):
                    result["status"] = "timed_out"
                elif result["status"] == "unavailable":
                    log = position / "worker.log"
                    if log.is_file() and b"Traceback" in log.read_bytes():
                        result["status"] = "failed"
            resources = stamp(wall, start_cpu)
            if result["status"] != "ok":
                result["arms"] = {a: dict(latlon=None) for a in ARMS}
            launched = position / "request.json"
            proof = (
                aligned_confirmation._request_proof(case, launched) if launched.is_file() else None
            )
            if result["status"] == "ok" and proof is None:
                raise ValueError("successful worker omitted its exact request")
            if lock_data["source"] != source_tokens():
                raise ValueError("pruned finish source changed during inference")
            validate_result(result)
            row = dict(
                binding,
                method=method,
                cpu=cpu,
                order=order,
                cap_s=cap,
                qualification="fresh",
                source_lock_sha256=_sha(plan_path),
                boundary_proof=proof,
                worker_wall_s=resources["wall_s"],
                worker_cpu_s=resources["cpu_s"],
                resources=resources,
                result=result,
            )
            save_json(target, row)
            print(ident, method, result["status"], round(row["worker_wall_s"], 2), flush=True)


def verify_science(candidate, control):
    a, b = (r["result"] for r in (candidate, control))
    if a["status"] != "ok" or b["status"] != "ok":
        return dict(compared=False, exact=False)
    ma, mb = a["metrics"], b["metrics"]
    expected = (
        "checked_residual_addition",
        "addition_status",
        "reassociation_selected",
        "reassociation_targets",
        "reassociation_admitted",
        "residual_targets",
        "ordered_phase_seeds",
        "native_observations",
        "tracks",
    )
    decisions = all(ma[k] == mb[k] for k in expected)
    for arm in ARMS:
        decisions &= ma[f"{arm}_associated_observations"] == mb[f"{arm}_associated_observations"]
    objective = {arm: ma[f"{arm}_frequency_score"] == mb[f"{arm}_frequency_score"] for arm in ARMS}
    rms = {
        arm: ma.get(f"{arm}_conditional_rms_hz") == mb.get(f"{arm}_conditional_rms_hz")
        for arm in ARMS
    }
    endpoint = a["arms"] == b["arms"]
    ranks = None
    if control["qualification"] == "fresh":
        ranks = ma["measured_finish"]["eligible_scores"] == mb["measured_finish"]["eligible_scores"]
    exact = (
        endpoint
        and decisions
        and all(objective.values())
        and all(rms.values())
        and ranks is not False
    )
    return dict(
        compared=True,
        exact=exact,
        endpoint=endpoint,
        decisions=decisions,
        objective=objective,
        rms=rms,
        eligible_scores=ranks,
    )


def seal(plan_path, work, output):
    plan = read(plan_path)
    if plan["source"] != source_tokens():
        raise ValueError("worker source changed before sealing")
    output = local_output(output)
    groups = {STOCK: historical_controls(plan["bindings"]), CANDIDATE: {}}
    for ident, (cpu, methods) in SCHEDULE.items():
        for order, method in enumerate(methods):
            row = read(work / ident / f"{method}.json")
            binding = plan["bindings"][ident]
            if (
                any(row[key] != value for key, value in binding.items())
                or (row["method"], row["cpu"], row["order"]) != (method, cpu, order)
                or row["source_lock_sha256"] != _sha(plan_path)
                or row["boundary_proof"]
                and row["boundary_proof"]["scientific_request_sha256"]
                != binding["scientific_request_sha256"]
            ):
                raise ValueError(f"{ident} {method} unbound prediction")
            validate_result(row["result"])
            groups[method][ident] = row
    for group in groups.values():
        for ident, row in group.items():
            row["cohort"] = "known-challenge" if ident in KNOWN else "independent-normal"
    files, roles = {}, {}
    for role, method in (("candidate", CANDIDATE), ("control", STOCK)):
        name = FILES[method]
        raw = b"".join(encoded(groups[method][i]) + b"\n" for i in CASES)
        write(output / name, gzip.compress(raw, mtime=0))
        files[name] = _sha(output / name)
        roles[role] = dict(method=method, positions=name, position_sha256=files[name])
    write(output / "source-lock.json", plan_path.read_bytes())
    save_json(
        output / "receipt.json",
        dict(
            files=files,
            runs=roles,
            cases=CASES,
            cohorts=plan["cohorts"],
            source_lock_sha256=_sha(plan_path),
            comparisons=[
                dict(
                    id=i,
                    input_sha256=plan["bindings"][i]["input_sha256"],
                    parity=verify_science(groups[CANDIDATE][i], groups[STOCK][i]),
                )
                for i in CASES
            ],
        ),
    )


def score(output):
    seal = read(output / "receipt.json")
    if seal["cases"] != list(CASES) or any(_sha(output / p) != d for p, d in seal["files"].items()):
        raise ValueError("sealed six-recording positions changed before scoring")
    references = {row["id"]: row for row in roster()}
    groups = {m: read_predictions(output / name) for m, name in FILES.items()}
    rows = []
    for ident in CASES:
        ref = references[ident]
        for method, group in groups.items():
            row, result = group[ident], group[ident]["result"]
            for arm in ARMS:
                point = result.get("arms", {}).get(arm, {}).get("latlon")
                rows.append(
                    dict(
                        id=ident,
                        method=method,
                        arm=arm,
                        qualification=row.get("qualification"),
                        status=result["status"],
                        position_error_km=distance_km(ref["truth"], point),
                        conditional_rms_hz=result["metrics"].get(f"{arm}_conditional_rms_hz"),
                        frequency_objective=result["metrics"].get(f"{arm}_frequency_score"),
                        **{f"{r}_km": ref["reference"][r][arm].get("error_km") for r in ROLES},
                    )
                )
    csv_file(output / "scores.csv", rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("lock").add_argument("plan", type=Path)
    run = sub.add_parser("run")
    run.add_argument("case", choices=CASES)
    run.add_argument("plan", type=Path)
    run.add_argument("work", type=Path)
    pack = sub.add_parser("seal")
    pack.add_argument("plan", type=Path)
    pack.add_argument("work", type=Path)
    pack.add_argument("output", type=Path, default=REPORT, nargs="?")
    sub.add_parser("score").add_argument("output", type=Path, default=REPORT, nargs="?")
    args = parser.parse_args()
    if args.action == "lock":
        lock(args.plan)
    elif args.action == "run":
        replay(args.plan, args.case, args.work)
    elif args.action == "seal":
        seal(args.plan, args.work, args.output)
    else:
        score(local_output(args.output))


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[-1] in FILES:
        worker(*sys.argv[1:])
    else:
        main()
