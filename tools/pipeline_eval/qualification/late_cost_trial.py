"""Same-core CPU and wall measurements for complete aligned late-preflight pairs."""

import argparse
import gzip
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from functools import partial
from pathlib import Path
from time import monotonic, perf_counter
from unittest.mock import patch

from tools.pipeline_eval.__main__ import local_output, save_json
from tools.pipeline_eval.qualification import full_receiver_comparison as authority
from tools.pipeline_eval.qualification import late_preflight_trial as archive
from tools.pipeline_eval.qualification import late_preflight_worker as guarded
from tools.pipeline_eval.qualification import pruned_finish_eval as matched
from tools.pipeline_eval.qualification.broad_search_budget import _case, frozen_inputs
from tools.pipeline_eval.qualification.secant_end_to_end_worker import cpu_s, measured, stamp
from tools.pipeline_eval.scoring import ARMS, validate_result
from tools.pipeline_eval.variants import (
    compact_finish,
    late_preflight,
    orbit_projector,
    v5_armijo_aligned_finish,
    v5_core,
    v5_lean,
)

REPORT = authority.SCREEN / "redesign/late-cost"
CANDIDATE, STOCK = guarded.METHOD, matched.STOCK
SEED = "late-rf-cost-v1:"
REPAIR = "DS26-0066"
MAX_WORKER_S = 280
MAX_STUDY_S = 720
GUARD = "late_rf_preflight"


def decide_roster(rows):
    bypasses = [r["id"] for r in rows if not r["preflight"]["run"] and r["id"] != "DS29-0082"]
    first, second = sorted(bypasses, key=lambda k: authority.corpus._sha((SEED + k).encode()))[:2]
    return {
        first: dict(cpu=19, methods=[STOCK, CANDIDATE], branch="bypass"),
        second: dict(cpu=19, methods=[CANDIDATE, STOCK], branch="bypass"),
        REPAIR: dict(cpu=11, methods=[CANDIDATE, STOCK], branch="retained_repair"),
    }


def source_inputs():
    lock = authority.seal(archive.REPORT, "roof-lock.json", ("predecision.json.gz",))
    raw = gzip.decompress((archive.REPORT / "predecision.json.gz").read_bytes())
    frozen = authority.read(archive.REPORT / "predecision-lock.json")
    if authority.corpus._sha(raw) != frozen["files"]["predecision.json"]:
        raise ValueError("archived RF features differ from the predecision lock")
    for name, checksum in frozen["source_sha256"].items():
        if authority.sha(authority.ROOT / name) != checksum:
            raise ValueError(f"{name} differs from the frozen RF rule or extraction")
    schedule = decide_roster(json.loads(raw))
    cases = frozen_inputs()
    files = (
        Path(__file__),
        Path(guarded.__file__),
        Path(late_preflight.__file__),
        Path(matched.__file__),
        REPORT / "PROTOCOL.md",
    )
    return cases, dict(
        seed=SEED,
        live_bypass_excluded="DS29-0082",
        schedule=schedule,
        original_roof_receipt_sha256=authority.sha(archive.REPORT / "roof-lock.json"),
        predecision_sha256=lock["files"]["predecision.json.gz"],
        prior_sources=matched.source_tokens(),
        sources={str(p.relative_to(authority.ROOT)): authority.sha(p) for p in files},
        bindings={k: matched.execution_binding(cases[k], _case(cases[k])) for k in schedule},
    )


def observe_finish(operation, report, *args, **kwargs):
    from leo.analysis.localization_v3 import (
        reassociation_context,
        recovery_inventory,
        residual_preflight,
        selected_incumbent,
    )

    from leo.application import localization_v3

    with ExitStack() as stack:
        for mod, name, stage in (
            (localization_v3, "prepare_additional_catalogue", "recovery_catalogue"),
            (recovery_inventory, "recovery_context", "cavity_replay"),
            (recovery_inventory, "baseline_pair", "cavity_replay"),
            (recovery_inventory, "publication_support", "cavity_replay"),
            (residual_preflight, "rank_targets", "residual_target_rank"),
            (selected_incumbent, "reconstruct_incumbent", "incumbent_reconstruct"),
            (reassociation_context, "adopt_additional", "incumbent"),
        ):
            wrapped = measured(getattr(mod, name), stage, report.setdefault("stages", {}))
            stack.enter_context(patch.object(mod, name, wrapped))
        return matched.observe_finish(operation, report, *args, **kwargs)


def worker(request, target, library, method):
    from leo.analysis.localization_v3 import (
        conservative_recovery,
        family_cavity,
        history_policy,
        signed_context,
    )

    from leo.application import localization_v3
    from leo.operations import localization_v3_job

    variant = {STOCK: v5_armijo_aligned_finish, CANDIDATE: guarded}[method]
    raw = authority.read(Path(request))["job"]["native_input"]
    original_read = localization_v3_job.read_bound
    upstream, late = {}, {}
    read_native = measured(original_read, "native_factor_decode", upstream)

    def read_bound(record):
        return (read_native if record == raw else original_read)(record)

    wall, cpu = perf_counter(), cpu_s()
    with ExitStack() as stack:
        stack.enter_context(patch.object(localization_v3_job, "read_bound", read_bound))
        stack.enter_context(
            patch.object(
                compact_finish, "finish", partial(observe_finish, compact_finish.finish, late)
            )
        )
        for mod, name, stage in (
            (localization_v3, "prepare_tracks", "graph_tracks"),
            (localization_v3, "prepare_native_scan", "native_plus_sky_history"),
            (v5_core, "infer", "compact_cavity_numerics"),
            (v5_core, "initial_selection", "initial_position"),
            (conservative_recovery, "conservative_recovery", "conservative"),
            (history_policy, "history_policy", "family"),
            (signed_context, "signed_context", "signed"),
            (family_cavity, "nominate_families", "cavity_nomination"),
            (family_cavity, "cavity_policy", "cavity_fit"),
            (late_preflight, "rf_rows", GUARD),
            (late_preflight, "preflight", GUARD),
        ):
            stack.enter_context(
                patch.object(mod, name, measured(getattr(mod, name), stage, upstream))
            )
        variant.worker(request, target, library)
    resources = stamp(wall, cpu)
    target = Path(target)
    result = authority.read(target)
    if result["status"] == "ok" and (
        not {"native_factor_decode", "graph_tracks", "compact_cavity_numerics"} <= upstream.keys()
        or not set(archive.STAGES) <= late.get("stages", {}).keys()
        or ((GUARD in upstream) != (method == CANDIDATE))
    ):
        raise ValueError("the complete measured boundaries were not executed")
    result["metrics"]["paired_cost"] = dict(worker=resources, upstream=upstream, late=late)
    save_json(target, result)


def nonresult(reason):
    return dict(
        status="timed_out",
        reason=reason,
        boundary="complete aligned stored-native worker",
        metrics={},
        arms={arm: dict(latlon=None) for arm in ARMS},
    )


def attempt(plan_path, ident, method):
    plan = authority.read(plan_path)
    item = plan["schedule"][ident]
    if os.sched_getaffinity(0) != {item["cpu"]} or method not in item["methods"]:
        raise ValueError("attempt differs from locked same-core schedule")
    case = _case(frozen_inputs()[ident])
    work = plan_path.parent / ident / method
    work.mkdir(parents=True)
    remaining = min(MAX_WORKER_S, int(plan["deadline_monotonic"] - monotonic()) - 3)
    wall, cpu = perf_counter(), cpu_s()
    proof = {}
    if remaining < 2:
        result = nonresult("study deadline reached before this worker started")
    else:
        v5_lean.TIMEOUT_S = remaining
        library = work / "orbit_projector.so"
        orbit_projector.compile_kernel(library)
        result = v5_lean.run_bound_worker(
            case, work, Path(__file__), worker_args=(str(library), method)
        )
        if "exceeded its" in result.get("reason", ""):
            result["status"] = "timed_out"
        request = work / "request.json"
        if request.exists():
            proof = matched.aligned_confirmation._request_proof(case, request)
    resources = stamp(wall, cpu)
    validate_result(result)
    if (
        proof
        and proof["scientific_request_sha256"]
        != plan["bindings"][ident]["scientific_request_sha256"]
    ):
        raise ValueError("attempt changed the exact scientific request")
    save_json(
        work / "attempt.json",
        dict(
            **plan["bindings"][ident],
            method=method,
            cpu=item["cpu"],
            branch=item["branch"],
            order=item["methods"].index(method),
            resources=resources,
            request_proof=proof,
            result=result,
            cap_s=max(0, remaining),
        ),
    )
    print(ident, method, result["status"], round(resources["wall_s"], 3), flush=True)


def start(work, seconds):
    began = monotonic()
    work = local_output(work)
    work.mkdir(parents=True, exist_ok=False)
    _, plan = source_inputs()
    plan.update(study_s=seconds, deadline_monotonic=began + seconds, worker_cap_s=MAX_WORKER_S)
    plan_path = work / "plan.json"
    save_json(plan_path, plan)
    if not {11, 19} <= os.sched_getaffinity(0):
        raise ValueError("both dedicated cores are required")
    os.nice(7)

    def lane(cpu):
        for ident, entry in plan["schedule"].items():
            if cpu != entry["cpu"]:
                continue
            for method in entry["methods"]:
                subprocess.run(
                    [
                        "taskset",
                        "-c",
                        str(cpu),
                        sys.executable,
                        "-m",
                        "tools.pipeline_eval.qualification.late_cost_trial",
                        "attempt",
                        str(plan_path),
                        ident,
                        method,
                    ],
                    check=False,
                )

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lane, (11, 19)))
    save_json(
        work / "run-receipt.json", dict(study_wall_s=monotonic() - began, study_cap_s=seconds)
    )


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] not in {"start", "attempt"}:
        worker(*sys.argv[1:])
    elif sys.argv[1:2] == ["attempt"]:
        attempt(Path(sys.argv[2]), *sys.argv[3:])
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("work", type=Path)
        parser.add_argument(
            "--seconds",
            type=int,
            default=MAX_STUDY_S,
            choices=range(1, MAX_STUDY_S + 1),
            metavar="1–720",
        )
        options = parser.parse_args()
        start(options.work, options.seconds)
