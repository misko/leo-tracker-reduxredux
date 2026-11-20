"""Measure immutable orbital state reuse from native factors to the v5 endpoint."""

import argparse
import gzip
import json
import os
import sys
from contextlib import ExitStack
from functools import partial
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
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
from tools.pipeline_eval.qualification.broad_search_budget import _case, frozen_inputs
from tools.pipeline_eval.qualification.full_v5_check import _sha
from tools.pipeline_eval.qualification.prefix_figures import csv_file
from tools.pipeline_eval.qualification.projector_roof import roster
from tools.pipeline_eval.qualification.pruned_finish_eval import execution_binding
from tools.pipeline_eval.qualification.secant_end_to_end_worker import cpu_s, measured, stamp
from tools.pipeline_eval.qualification.v5_postfit import sha256
from tools.pipeline_eval.scoring import ARMS, ROLES, distance_km, validate_result
from tools.pipeline_eval.variants import (
    compact_finish,
    orbit_projector,
    v5_core,
    v5_lean,
    v5_recovery_bank_reuse,
)

REPORT = ROOT / "reports/2026_11_19_receiver_screening/factors/v5-reuse"
CANDIDATE, STOCK = v5_recovery_bank_reuse.METHOD, "compact_finish"
WORKER_LIMIT, STUDY_LIMIT, STRESS_MIN_REMAINING = 480, 1080, 780
RUNS = {
    "DS26-0036": (20, (CANDIDATE, STOCK)),
    "DS29-0082": (22, (STOCK, CANDIDATE)),
    "DS26-0066": (20, (STOCK, CANDIDATE)),
}
CASES = tuple(RUNS)[:2]
STRESS = tuple(RUNS)[2]
FILES = {CANDIDATE: "positions.jsonl.gz", STOCK: "stock-positions.jsonl.gz"}


def read(path):
    return json.loads(path.read_bytes())


def source_tokens():
    modules = (v5_recovery_bank_reuse, compact_finish, orbit_projector, v5_core, v5_lean)
    paths = [*(Path(m.__file__) for m in modules), orbit_projector.KERNEL, Path(__file__)]
    return {str(p.relative_to(ROOT)): _sha(p) for p in paths}


def lock(destination):
    inputs = frozen_inputs()
    bindings = {i: execution_binding(inputs[i], _case(inputs[i])) for i in RUNS}
    path = local_output(destination)
    if path.exists():
        raise FileExistsError(path)
    save_json(
        path,
        dict(
            cases=CASES,
            optional_stress=STRESS,
            schedule=RUNS,
            bindings=bindings,
            source=source_tokens(),
            frozen_source=v5_lean.SOURCE_SHA256,
            frozen_runner=v5_lean.RUNNER_SHA256,
            protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
            cap_s=WORKER_LIMIT,
            study_cap_s=STUDY_LIMIT,
            locked_ns=time_ns(),
        ),
    )


def observe_finish(original, report, *args, **kwargs):
    from leo.analysis.localization_v3 import (
        reassociation_admission,
        reassociation_catalogue,
        reassociation_context,
        reassociation_screen,
        residual_screen,
    )

    from leo.analysis.research import orbit_phase_geometry

    stages, counts, audits = report["stages"], report["work"], report["audits"]

    def propagate(key, operation, *a, **kw):
        counts[key] += 1
        return operation(*a, **kw)

    def audit(operation, *a, **kw):
        result = operation(*a, **kw)
        audits.append(sha256(encoded(result))[7:])
        return result

    def adopt(operation, *a, **kw):
        result = operation(*a, **kw)
        vote = result["replay"]["recovery"]
        report["addition"] = {k: vote.get(k) for k in ("status", "source")}
        return result

    def screen(operation, context, old, nums, bank):
        interp = orbit_phase_geometry.interpolate_states
        grids = reassociation_screen.phase_frequency_grids

        def check(received, times):
            if received is bank and len(times) == 0:
                counts["full_bank_validations"] += 1
            return interp(received, times)

        with (
            patch.object(orbit_phase_geometry, "interpolate_states", check),
            patch.object(
                reassociation_screen,
                "phase_frequency_grids",
                partial(propagate, "coarse_projections", grids),
            ),
        ):
            return operation(context, old, nums, bank)

    with ExitStack() as stack:
        for module, name, label in (
            (residual_screen, "ecef_states", "residual_ecef"),
            (reassociation_catalogue, "ecef_states", "reassociation_ecef"),
        ):
            operation = partial(propagate, label, getattr(module, name))
            stack.enter_context(patch.object(module, name, measured(operation, label, stages)))
        for module, name, label, wrapper in (
            (reassociation_context, "adopt_additional", "addition_decision", adopt),
            (reassociation_catalogue, "audit", "raw_audit", audit),
            (reassociation_admission, "screen", "reassociation_screen", screen),
            (reassociation_admission, "prepare_catalogue", "prepare_reassociation", None),
            (residual_screen, "screen_candidates", "residual_screen", None),
        ):
            operation = getattr(module, name)
            if wrapper is not None:
                operation = partial(wrapper, operation)
            stack.enter_context(patch.object(module, name, measured(operation, label, stages)))
        return original(*args, **kwargs)


def worker(request, result, library, method):
    report = dict(
        stages={},
        audits=[],
        work=dict.fromkeys(
            ("coarse_projections", "full_bank_validations", "residual_ecef", "reassociation_ecef"),
            0,
        ),
    )
    variant = v5_recovery_bank_reuse if method == CANDIDATE else compact_finish
    with patch.object(
        compact_finish, "finish", partial(observe_finish, compact_finish.finish, report)
    ):
        variant.worker(request, result, library)
    destination = Path(result)
    output = read(destination)
    output["metrics"].update(
        recovery_bank_observer=report, worker_peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss
    )
    save_json(destination, output)


def replay(ident, plan_path, work):
    plan = read(plan_path)
    cpu, order = RUNS[ident]
    if os.sched_getaffinity(0) != {cpu} or plan["source"] != source_tokens():
        raise ValueError("initial source or CPU differs from the locked qualification")

    def remain():
        return (plan["locked_ns"] + STUDY_LIMIT * 10**9 - time_ns()) // 10**9

    if ident == STRESS and (
        remain() < STRESS_MIN_REMAINING
        or not all((work / i / f"{m}.json").is_file() for i in CASES for m in FILES)
    ):
        raise ValueError("optional stress pair is outside its locked schedule or budget")
    item = frozen_inputs()[ident]
    case = _case(item)
    binding = execution_binding(item, case)
    if binding != plan["bindings"][ident]:
        raise ValueError("receiver inputs changed after source lock")
    for index, method in enumerate(order):
        path = local_output(work) / ident / method
        path.mkdir(parents=True, exist_ok=False)
        lib = path / "orbit_projector.so"
        cap = min(WORKER_LIMIT, max(0, remain()))
        wall, cpu_start = perf_counter(), cpu_s()
        if cap <= 4:
            result = dict(
                status="timed_out",
                reason="study deadline elapsed before launch",
                boundary=compact_finish.BOUNDARY,
                metrics={},
            )
        else:
            orbit_projector.compile_kernel(lib)
            with patch.object(v5_lean, "TIMEOUT_S", cap - 4):
                result = v5_lean.run_bound_worker(
                    case,
                    path,
                    Path(__file__),
                    worker_args=(str(lib), method),
                )
            if "exceeded its " in result.get("reason", ""):
                result["status"] = "timed_out"
        resources = stamp(wall, cpu_start)
        if result["status"] != "ok":
            result["arms"] = {arm: {"latlon": None} for arm in ARMS}
        validate_result(result)
        from tools.pipeline_eval.qualification.aligned_confirmation import _request_proof

        request = path / "request.json"
        proof = _request_proof(case, request) if request.is_file() else None
        if (result["status"] == "ok" and proof is None) or plan["source"] != source_tokens():
            raise ValueError("worker request or source became unbound")
        save_json(
            path.parent / f"{method}.json",
            dict(
                binding,
                method=method,
                cpu=cpu,
                order=index,
                cap_s=cap,
                result=result,
                worker_wall_s=resources["wall_s"],
                worker_cpu_s=resources["cpu_s"],
                source_lock_sha256=_sha(plan_path),
                boundary_proof=proof,
            ),
        )
        print(ident, method, result["status"], round(resources["wall_s"], 2), flush=True)


def parity(candidate, stock):
    a, b = (row["result"] for row in (candidate, stock))
    if a["status"] != "ok" or b["status"] != "ok":
        return dict(compared=False, exact=False)
    am, bm = a["metrics"], b["metrics"]
    keys = [
        "native_observations",
        "tracks",
        "residual_targets",
        "addition_status",
        "reassociation_targets",
        "reassociation_admitted",
        "reassociation_selected",
    ]
    keys += [
        f"{arm}_{m}"
        for arm in ARMS
        for m in (
            "associated_observations",
            "conditional_rms_hz",
            "frequency_score",
        )
    ]
    exact = a["arms"] == b["arms"] and all(am.get(k) == bm.get(k) for k in keys)
    ma, mb = (m["recovery_bank_observer"] for m in (am, bm))
    audit = ma["audits"] == mb["audits"] and len(ma["audits"]) == 1
    return dict(
        compared=True,
        exact=exact and audit and ma["addition"] == mb["addition"],
        same_propagation_audit=audit,
    )


def seal(plan_path, work, output):
    plan = read(plan_path)
    if plan["source"] != source_tokens():
        raise ValueError("numerical sources changed before sealing")
    cases = CASES + (STRESS,) if (work / STRESS).is_dir() else CASES
    output = local_output(output)
    pairs, comparisons = {m: [] for m in FILES}, []
    for ident in cases:
        case_rows = {}
        for method in FILES:
            row = read(work / ident / f"{method}.json")
            cpu, order = RUNS[ident]
            if (
                (row["id"], row["cpu"], row["order"], row["method"])
                != (ident, cpu, order.index(method), method)
                or row["source_lock_sha256"] != _sha(plan_path)
                or any(row.get(k) != v for k, v in plan["bindings"][ident].items())
            ):
                raise ValueError(f"{ident} prediction has no matching locked input")
            validate_result(row["result"])
            pairs[method].append(row)
            case_rows[method] = row
        comparisons.append(
            dict(
                id=ident,
                input_sha256=row["input_sha256"],
                parity=parity(case_rows[CANDIDATE], case_rows[STOCK]),
            )
        )
    files, artifacts = {}, {}
    for role, method in (("candidate", CANDIDATE), ("control", STOCK)):
        name = FILES[method]
        write(
            output / name,
            gzip.compress(b"".join(encoded(r) + b"\n" for r in pairs[method]), mtime=0),
        )
        files[name] = _sha(output / name)
        artifacts[role] = dict(method=method, positions=name, position_sha256=files[name])
    write(output / "source-lock.json", plan_path.read_bytes())
    save_json(
        output / "receipt.json",
        dict(
            cases=cases,
            files=files,
            runs=artifacts,
            comparisons=comparisons,
            source_lock_sha256=_sha(plan_path),
        ),
    )


def score(output):
    receipt = read(output / "receipt.json")
    if any(_sha(output / p) != sha for p, sha in receipt["files"].items()):
        raise ValueError("sealed predictions changed before truth attachment")
    refs = {r["id"]: r for r in roster()}
    rows = []
    for method, filename in FILES.items():
        records = read_predictions(output / filename)
        for ident in receipt["cases"]:
            ref, result = refs[ident], records[ident]["result"]
            for arm in ARMS:
                rows.append(
                    dict(
                        id=ident,
                        arm=arm,
                        method=method,
                        status=result["status"],
                        error_km=distance_km(ref["truth"], result["arms"][arm]["latlon"]),
                        rms_hz=result["metrics"].get(f"{arm}_conditional_rms_hz"),
                        objective=result["metrics"].get(f"{arm}_frequency_score"),
                        **{
                            f"{role}_km": ref["reference"][role][arm].get("error_km")
                            for role in ROLES
                        },
                    )
                )
    csv_file(output / "scores.csv", rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("lock").add_argument("plan", type=Path)
    run = sub.add_parser("run")
    run.add_argument("case", choices=RUNS)
    run.add_argument("plan", type=Path)
    run.add_argument("work", type=Path)
    pack = sub.add_parser("seal")
    pack.add_argument("plan", type=Path)
    pack.add_argument("work", type=Path)
    pack.add_argument("output", type=Path, nargs="?", default=REPORT)
    sub.add_parser("score").add_argument("output", type=Path, nargs="?", default=REPORT)
    args = parser.parse_args()
    if args.action == "lock":
        lock(args.plan)
    elif args.action == "run":
        replay(args.case, args.plan, args.work)
    elif args.action == "seal":
        seal(args.plan, args.work, args.output)
    else:
        score(local_output(args.output))


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[-1] in FILES:
        worker(*sys.argv[1:])
    else:
        main()
