"""Lock, run, seal and score the two compact v5 initial winner screens."""

import argparse
import fcntl
import gzip
import json
import os
import sys
from importlib import import_module
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from tools.pipeline_eval.__main__ import (
    ROOT,
    encoded,
    local_output,
    read_predictions,
    references,
    save_json,
    write,
)
from tools.pipeline_eval.qualification import phase_budget
from tools.pipeline_eval.qualification.broad_search_budget import (
    _archive_ranks,
    _case,
    frozen_inputs,
)
from tools.pipeline_eval.qualification.catalogue_memory_eval import cpu_elapsed
from tools.pipeline_eval.qualification.prefix_figures import TIMING_IDS, csv_file
from tools.pipeline_eval.qualification.projector_roof import input_hash
from tools.pipeline_eval.qualification.search_budget import digest
from tools.pipeline_eval.scoring import (
    ARMS,
    ROLES,
    distance_km,
    distribution,
    thresholds,
    validate_result,
)
from tools.pipeline_eval.variants import orbit_projector, v5_core, v5_lean, v5_secant_fit

REPORT = ROOT / "reports/2026_11_19_receiver_screening/winner"
METHODS = {"v5_screen_winner": "reference", "v5_screen_secant": "secant"}
CONTROLS = dict(zip(METHODS, ("orbit_projector", "v5_secant_fit"), strict=True))
PHASE = phase_budget.REPORT
POSITION = PHASE.parent / "position-fit"
DEADLINE = 480
SCHEDULE = {
    ident: dict(
        cpu=22 + next(lane for lane, cases in enumerate(phase_budget.SCHEDULE) if ident in cases),
        order=list(METHODS)[:: 1 if index % 2 == 0 else -1],
    )
    for index, ident in enumerate(TIMING_IDS)
}


def screening_module():
    return import_module("tools.pipeline_eval.variants.v5_screen_winner")


def read(path):
    return json.loads(path.read_bytes())


def source_tokens():
    modules = (screening_module(), v5_secant_fit, orbit_projector, v5_core, v5_lean)
    paths = [*(Path(module.__file__) for module in modules), orbit_projector.KERNEL, Path(__file__)]
    return {str(path.resolve().relative_to(ROOT)): digest(path) for path in paths}


def case_binding(item, case):
    request = read(Path(case["request_path"]))
    job = request["job"]
    names = ("native", "catalog")
    if any(digest(case[k + "_path"]) != item[k]["sha256"] for k in names):
        raise ValueError(f"{item['id']} frozen observations or catalogue changed")
    if (
        job["evaluation_reference"] is not None
        or job["native_input"]["sha256"] != "sha256:" + item["native"]["sha256"]
        or job["search_center"] != item["regions"][0]["center"]
    ):
        raise ValueError(f"{item['id']} does not use the frozen blind roof request")
    return dict(
        input_sha256=input_hash(case),
        request_sha256=item["request"]["sha256"],
        execution_request_sha256=digest(case["request_path"]),
        catalog_sha256=item["catalog"]["sha256"],
        native_sha256=item["native"]["sha256"],
        region=item["regions"],
        screen_center=job["screen_center"],
    )


def archived_controls(bindings):
    projector = phase_budget.sealed_pair(PHASE)["orbit_projector"]
    lock = read(POSITION / "prediction-lock.json")
    name = "secant-positions.jsonl.gz"
    if (
        set(lock["cases"]) != set(TIMING_IDS)
        or digest(POSITION / "seal.json") != lock["source_seal_sha256"]
        or digest(POSITION / name) != lock["files"][name]
    ):
        raise ValueError("archived secant timing and predictions differ from their seal")
    secant = read_predictions(POSITION / name)
    if list(secant) != lock["cases"]:
        raise ValueError("archived secant predictions do not cover their sealed roster")
    controls = {"orbit_projector": {}, "v5_secant_fit": {}}
    for ident, binding in bindings.items():
        for method, row, digest_name in (
            ("orbit_projector", projector[ident], "input_sha256"),
            ("v5_secant_fit", secant[ident], "request_sha256"),
        ):
            validate_result(row["result"])
            if row["input_sha256"] != binding[digest_name] or any(
                row[k] != binding[k] for k in ("native_sha256", "catalog_sha256")
            ):
                raise ValueError(f"{ident} archived control used different science inputs")
            if method == "v5_secant_fit" and (
                row["variant"] != method or row["source_seal_sha256"] != lock["source_seal_sha256"]
            ):
                raise ValueError(f"{ident} archived secant provenance changed")
            controls[method][ident] = dict(
                row,
                method=method,
                qualification="historical_control",
                archived_input_sha256=row["input_sha256"],
                **binding,
            )
    return controls


def lock_inputs(output):
    output = local_output(output)
    inputs = frozen_inputs()
    bindings = {ident: case_binding(inputs[ident], _case(inputs[ident])) for ident in TIMING_IDS}
    archived_controls(bindings)
    ranks = _archive_ranks(inputs)
    archives = (
        PHASE / "receipt.json",
        POSITION / "prediction-lock.json",
        ROOT / "reports/2026_11_19_short_receiver/search-budget/initial-checkpoints/receipt.json",
    )
    plan = dict(
        cases=list(TIMING_IDS),
        schedule=SCHEDULE,
        modes=METHODS,
        deadline_s=DEADLINE,
        inputs=bindings,
        original_rank={ident: ranks[ident] for ident in TIMING_IDS},
        frozen_source=v5_lean.SOURCE_SHA256,
        source=source_tokens(),
        archived_control_locks={str(p.relative_to(ROOT)): digest(p) for p in archives},
    )
    if output.exists() and read(output) != plan:
        raise ValueError("the winner screen has already been locked to different inputs or source")
    save_json(output, plan)


def check_lock(plan):
    if (
        plan["cases"] != list(TIMING_IDS)
        or plan["schedule"] != SCHEDULE
        or plan["modes"] != METHODS
        or plan["deadline_s"] != DEADLINE
        or plan["frozen_source"] != v5_lean.SOURCE_SHA256
        or plan["source"] != source_tokens()
        or any(digest(ROOT / path) != sha for path, sha in plan["archived_control_locks"].items())
    ):
        raise ValueError("winner screen inputs, schedule or source changed after locking")


def observe_initial(original, timing, *args, select_initial, **kwargs):
    began = cpu_elapsed()

    def measured(scan):
        answer = select_initial(scan)
        timing["initial_screen_cpu_s"] = cpu_elapsed() - began
        return answer

    return original(*args, select_initial=measured, **kwargs)


def worker(request, result, library, mode):
    from functools import partial

    timing = {}
    observer = partial(observe_initial, v5_core.infer, timing)
    with patch.object(v5_core, "infer", observer):
        screening_module().worker(request, result, library, mode)
    path = Path(result)
    outcome = read(path)
    outcome["metrics"].update(timing)
    save_json(path, outcome)


def verify_row(row, plan, ident, method, lock_sha):
    schedule = plan["schedule"][ident]
    expected = dict(
        id=ident,
        method=method,
        mode=METHODS[method],
        cpu=schedule["cpu"],
        order=schedule["order"].index(method),
        source_lock_sha256=lock_sha,
        cap_s=DEADLINE,
        **plan["inputs"][ident],
    )
    if any(row.get(k) != v for k, v in expected.items()):
        raise ValueError(f"{ident} {method} does not match the blind source lock")
    if row["worker_wall_s"] <= 0 or row["worker_cpu_s"] < 0:
        raise ValueError(f"{ident} {method} has invalid runtime measurements")
    result = row["result"]
    validate_result(result)
    if set(result.get("arms", {})) != set(ARMS):
        raise ValueError(f"{ident} {method} did not declare both calibration arms")
    if result["status"] == "ok":
        metrics = result["metrics"]
        screen = metrics["initial_screen"]
        scores = screen["screen_c0_scores"]
        fallback = None in scores
        rank = None if fallback or not scores else min(range(len(scores)), key=scores.__getitem__)
        if (
            metrics["kernel_sha256"]
            != plan["source"][str(orbit_projector.KERNEL.relative_to(ROOT))]
            or metrics["initial_screen_cpu_s"] <= 0
            or metrics["stage_s"]["initial"] <= 0
            or screen["ranks"] != [0, 1, 2]
            or screen["winning_rank"] != rank
            or len(scores) != 3
            or screen["early_fits"] != 6
            or screen["fallback"] is not fallback
            or screen["initial_phase_fits"] != screen["early_fits"] + screen["finish_fits"]
            or screen["finish_fits"] != (15 if fallback else 3)
        ):
            raise ValueError(f"{ident} {method} has an invalid initial screening receipt")
    return row


def replay(lock, ident, output):
    plan = read(lock)
    check_lock(plan)
    lock_sha = digest(lock)
    schedule = plan["schedule"][ident]
    if os.sched_getaffinity(0) != {schedule["cpu"]}:
        raise ValueError(f"{ident} pair must run on CPU {schedule['cpu']}")
    item = frozen_inputs()[ident]
    case = _case(item)
    if case_binding(item, case) != plan["inputs"][ident]:
        raise ValueError(f"{ident} inputs changed after source lock")
    directory = local_output(output) / ident
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "pair.lock").open("a") as ownership:
        fcntl.flock(ownership, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for index, method in enumerate(schedule["order"]):
            path = directory / f"{method}.json"
            if path.exists():
                verify_row(read(path), plan, ident, method, lock_sha)
                continue
            work = directory / method
            work.mkdir(exist_ok=False)
            check_lock(plan)
            library = work / "orbit_projector.so"
            started = perf_counter(), cpu_elapsed()
            orbit_projector.compile_kernel(library)
            with patch.object(v5_lean, "TIMEOUT_S", DEADLINE):
                result = v5_lean.run_bound_worker(
                    case,
                    work / "worker",
                    Path(__file__),
                    worker_args=(str(library), METHODS[method]),
                )
            wall, cpu = perf_counter() - started[0], cpu_elapsed() - started[1]
            if "inference exceeded its" in result.get("reason", ""):
                result["status"] = "timed_out"
            if result["status"] != "ok":
                result["arms"] = {arm: {"latlon": None} for arm in ARMS}
            check_lock(plan)
            row = dict(
                id=ident,
                method=method,
                mode=METHODS[method],
                cpu=schedule["cpu"],
                order=index,
                source_lock_sha256=lock_sha,
                cap_s=DEADLINE,
                worker_wall_s=wall,
                worker_cpu_s=cpu,
                result=result,
                **plan["inputs"][ident],
            )
            save_json(path, verify_row(row, plan, ident, method, lock_sha))
            print(ident, method, result["status"], round(wall, 2), round(cpu, 2), flush=True)


def seal(lock, runs, output):
    plan = read(lock)
    check_lock(plan)
    lock_sha = digest(lock)
    output = local_output(output)
    predictions = {
        method: {
            ident: verify_row(read(runs / ident / f"{method}.json"), plan, ident, method, lock_sha)
            for ident in TIMING_IDS
        }
        for method in METHODS
    }
    predictions.update(archived_controls(plan["inputs"]))
    files, artifacts = {}, {}
    for method, group in predictions.items():
        name = f"{method}-positions.jsonl.gz"
        path = output / name
        content = b"".join(encoded(group[ident]) + b"\n" for ident in TIMING_IDS)
        write(path, gzip.compress(content, mtime=0))
        files[name] = digest(path)
        artifacts[method] = dict(method=method, positions=name, position_sha256=files[name])
    write(output / "source-lock.json", lock.read_bytes())
    save_json(
        output / "receipt.json",
        dict(
            cases=list(TIMING_IDS),
            files=files,
            runs=artifacts,
            source_lock_sha256=lock_sha,
            comparisons=[dict(id=ident, **plan["inputs"][ident]) for ident in TIMING_IDS],
            controls=CONTROLS,
            frozen_source=v5_lean.SOURCE_SHA256,
        ),
    )


def sealed_predictions(output):
    receipt = read(output / "receipt.json")
    lock = output / "source-lock.json"
    plan = read(lock)
    names = METHODS.keys() | CONTROLS.values()
    if (
        receipt["cases"] != list(TIMING_IDS)
        or receipt["runs"].keys() != names
        or receipt["source_lock_sha256"] != digest(lock)
        or receipt["comparisons"]
        != [dict(id=ident, **plan["inputs"][ident]) for ident in TIMING_IDS]
    ):
        raise ValueError("sealed winner comparison roster or blind bindings changed")
    rows = {}
    for method, item in receipt["runs"].items():
        name = f"{method}-positions.jsonl.gz"
        if (
            item["positions"] != name
            or item["method"] != method
            or digest(output / name) != receipt["files"][name]
            or item["position_sha256"] != receipt["files"][name]
        ):
            raise ValueError(f"{method} prediction bytes differ from the seal")
        rows[method] = read_predictions(output / name)
        if list(rows[method]) != list(TIMING_IDS) or any(
            row["method"] != method or row["input_sha256"] != plan["inputs"][ident]["input_sha256"]
            for ident, row in rows[method].items()
        ):
            raise ValueError(f"{method} sealed prediction input or roster changed")
    return plan, rows


def compare_endpoint(arm, point, control, ref):
    a, b = point.get("latlon"), control.get("latlon")
    rms, control_rms = point.get("rf_rms_hz"), control.get("rf_rms_hz")
    separation = distance_km(a, b)
    delta_hz = None if None in (rms, control_rms) else rms - control_rms
    row = dict(
        position_error_km=distance_km(a, ref["truth"]),
        control_error_km=distance_km(b, ref["truth"]),
        shift_from_control_m=None if separation is None else 1000 * separation,
        conditional_rms_hz=rms,
        control_conditional_rms_hz=control_rms,
        rms_delta_hz=delta_hz,
        within_control_limits=(
            separation is not None
            and separation <= 0.050
            and delta_hz is not None
            and abs(delta_hz) <= 1.0
        ),
    )
    for role in ROLES:
        original = ref["reference"].get(role, {}).get(arm, {})
        row[f"{role}_v5_error_km"] = distance_km(ref["truth"], original.get("latlon"))
        row[f"{role}_v5_shift_km"] = distance_km(a, original.get("latlon"))
    return row


def timing(row):
    metrics = row["result"]["metrics"]
    return dict(
        worker_wall_s=row["worker_wall_s"],
        worker_cpu_s=row.get("worker_cpu_s"),
        initial_wall_s=metrics.get("stage_s", {}).get("initial"),
        initial_cpu_s=metrics.get("initial_screen_cpu_s"),
        cpu=row.get("cpu"),
    )


def score(output):
    output = local_output(output)
    plan, rows = sealed_predictions(output)
    # Evaluation coordinates are accessed only after the complete prediction seal is verified.
    refs = {
        r["id"]: r for panel in ("roof16", "ds26-common127") for r in references(panel, None)[1]
    }
    scientific, operational = [], []
    for method, control in CONTROLS.items():
        for ident in TIMING_IDS:
            candidate, prior = rows[method][ident], rows[control][ident]
            new, old = candidate["result"], prior["result"]
            for arm in ARMS:
                point, baseline = (p.get("arms", {}).get(arm, {}) for p in (new, old))
                scientific.append(
                    dict(
                        id=ident,
                        dataset=refs[ident]["group"],
                        method=method,
                        arm=arm,
                        status=new["status"],
                        control_status=old["status"],
                        **compare_endpoint(arm, point, baseline, refs[ident]),
                    )
                )
            operational.append(
                dict(
                    id=ident,
                    method=method,
                    control=control,
                    status=new["status"],
                    control_status=old["status"],
                    candidate_timing=timing(candidate),
                    historical_control_timing=timing(prior),
                    initial_screen=new["metrics"].get("initial_screen"),
                    initial_original_branch_rank=plan["original_rank"][ident],
                    candidate_counts={
                        key: new["metrics"].get(key) for key in ("observations", "tracks")
                    },
                    control_counts={
                        key: old["metrics"].get(key) for key in ("observations", "tracks")
                    },
                    cavity_offered=new["metrics"].get("cavity_offered"),
                    historical_cavity_offered=old["metrics"].get("cavity_offered"),
                )
            )
    groups = []
    for method in METHODS:
        for arm in ARMS:
            selected = [r for r in scientific if (r["method"], r["arm"]) == (method, arm)]
            error_keys = (
                "position_error_km",
                "control_error_km",
                *(f"{r}_v5_error_km" for r in ROLES),
            )
            groups.append(
                dict(
                    method=method,
                    arm=arm,
                    scheduled=len(selected),
                    errors={k: distribution(r[k] for r in selected) for k in error_keys},
                    within_km={k: thresholds([r[k] for r in selected]) for k in error_keys},
                    conditional_rms_hz=distribution(r["conditional_rms_hz"] for r in selected),
                    historical_control_rms_hz=distribution(
                        r["control_conditional_rms_hz"] for r in selected
                    ),
                    same_optimizer_gate_passes=sum(r["within_control_limits"] for r in selected),
                )
            )
    csv_file(output / "per-recording.csv", scientific)
    save_json(output / "scores.json", dict(groups=groups, measurements=operational))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_subparsers(dest="action", required=True)
    action.add_parser("lock").add_argument("destination", type=Path)
    pair = action.add_parser("pair")
    pair.add_argument("case", choices=TIMING_IDS)
    pair.add_argument("lock", type=Path)
    pair.add_argument("runs", type=Path)
    publish = action.add_parser("seal")
    publish.add_argument("lock", type=Path)
    publish.add_argument("runs", type=Path)
    publish.add_argument("output", type=Path)
    action.add_parser("score").add_argument("output", type=Path)
    args = parser.parse_args()
    if args.action == "lock":
        lock_inputs(args.destination)
    elif args.action == "pair":
        replay(args.lock, args.case, args.runs)
    elif args.action == "seal":
        seal(args.lock, args.runs, args.output)
    else:
        score(args.output)


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[-1] in METHODS.values():
        worker(*sys.argv[1:])
    else:
        main()
