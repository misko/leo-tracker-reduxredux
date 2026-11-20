"""Measure matched stock and candidate v5 search over complete frozen recordings."""

import argparse
import gzip
import json
import os
import sys
from contextlib import nullcontext
from functools import partial
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

from tools.pipeline_eval.__main__ import (
    DEFAULT_OUT,
    encoded,
    local_output,
    public_cases,
    references,
    save_json,
    write,
)
from tools.pipeline_eval.qualification.catalogue_memory_eval import assert_frozen, cpu_elapsed
from tools.pipeline_eval.qualification.compact_finish_eval import verify_adapter
from tools.pipeline_eval.qualification.prefix_figures import REPORT as ARCHIVED_PREFIX
from tools.pipeline_eval.qualification.prefix_figures import load_rows
from tools.pipeline_eval.qualification.v5_postfit import sha256
from tools.pipeline_eval.scoring import ARMS, distance_km, validate_result
from tools.pipeline_eval.variants import (
    compact_finish,
    orbit_projector,
    v5_core,
    v5_lean,
    v5_shared_search,
)

METHOD = "v5_shared_search"
STOCK = "compact_finish"
RUNS = {
    "DS26-0036": ("ds26-common127", 20, (METHOD, STOCK)),
    "DS29-0082": ("roof16", 21, (STOCK, METHOD)),
    "DS26-0122": ("ds26-common127", 20, (STOCK, METHOD)),
    "DS29-0174": ("roof16", 21, (METHOD, STOCK)),
}
PRIMARY = tuple(RUNS)[:2]


def decision_token(rows, nominees):
    return sha256(
        encoded(
            [
                [r["component"], r["candidate_index"], r["compatible"], r["feasible_candidates"]]
                for r in rows
            ]
            + [int(v["j"]) for v in nominees.values()]
        )
    )[7:]


def traced_initial(original, measured, method, scan):
    association, curve = scan.association, scan.curve
    traces = []
    statistics = dict(
        association_cpu_s=0.0,
        association_wall_s=0.0,
        association_calls=0,
        profile_candidate_rows=0,
        profile_candidate_cells=0,
        curve_calls=0,
    )

    def timed_association(*args, **kwargs):
        began, start_cpu = perf_counter(), process_time()
        result = association(*args, **kwargs)
        statistics["association_wall_s"] += perf_counter() - began
        statistics["association_cpu_s"] += process_time() - start_cpu
        statistics["association_calls"] += 1
        traces.append(decision_token(result[1], result[2]))
        return result

    def count_curve(i, y, prediction, *args, **kwargs):
        statistics["curve_calls"] += 1
        statistics["profile_candidate_rows"] += len(prediction)
        statistics["profile_candidate_cells"] += prediction.size
        return curve(i, y, prediction, *args, **kwargs)

    began, start_cpu = perf_counter(), process_time()
    with (
        patch.object(scan, "association", timed_association),
        patch.object(scan, "curve", count_curve),
    ):
        policy = v5_shared_search.shared_associations(scan) if method == METHOD else nullcontext({})
        with policy as savings:
            result = original(scan)
    statistics.update(
        initial_wall_s=perf_counter() - began, initial_cpu_s=process_time() - start_cpu
    )
    chosen, branches = result
    row = chosen["choices"][0]
    initial_signature = dict(
        branches=branches,
        node_rows=[
            (r["component"], int(r["candidate_index"])) for r in row["node"]["seed"]["rows"]
        ],
        aliases=list(map(int, row["node"]["aliases"])),
        gated_rows=[
            (r["component"], r["compatible"]) for r in row["arms"]["c0"]["metrics"]["tracks"]
        ],
    )
    save_json(
        measured,
        dict(
            statistics, **savings, association_outcomes=traces, initial_signature=initial_signature
        ),
    )
    return result


def worker(request, result, library, log, method):
    initial = partial(traced_initial, v5_core.initial_selection, Path(log), method)
    with patch.object(v5_core, "initial_selection", initial):
        compact_finish.worker(request, result, library)


def replay(ident, output, *, confirm_missing=False):
    panel, cpu, order = RUNS[ident]
    if os.sched_getaffinity(0) != {cpu}:
        raise ValueError(f"Both replays of {ident} must use CPU {cpu}")
    if ident not in PRIMARY:
        primary = next(case for case in PRIMARY if RUNS[case][0] == panel)
        control, candidate = (output / primary / method for method in (STOCK, METHOD))
        verify_adapter(
            *(json.loads((p / "result.json").read_bytes()) for p in (control, candidate))
        )
        verify_search(*(json.loads((p / "search.json").read_bytes()) for p in (control, candidate)))
    if confirm_missing:
        if ident != "DS26-0122" or not (output / ident / STOCK / "result.json").is_file():
            raise ValueError("Standalone confirmation requires the completed DS26-0122 stock leg")
        prior = output / ident / METHOD / "result.json"
        if prior.is_file() and json.loads(prior.read_bytes())["result"]["status"] == "ok":
            raise ValueError("The original paired candidate already completed")
        order = (METHOD,)
    source, refs = references(panel, [ident])
    (case,) = public_cases(source, refs, DEFAULT_OUT / "inputs")
    core_sha256 = sha256(Path(v5_core.__file__).read_bytes())[7:]
    projector_sha256 = sha256(Path(orbit_projector.__file__).read_bytes())[7:]
    for method in order:
        run = (
            local_output(output) / ident / (method + "-confirmation" if confirm_missing else method)
        )
        run.mkdir(parents=True, exist_ok=False)
        library = run / "orbit_projector.so"
        log = run / "search.json"
        start, cpu_start = perf_counter(), cpu_elapsed()
        orbit_projector.compile_kernel(library)
        result = v5_lean.run_bound_worker(
            case, run / "worker", Path(__file__), worker_args=(str(library), str(log), method)
        )
        wall, cpu_time = perf_counter() - start, cpu_elapsed() - cpu_start
        variant = v5_shared_search if method == METHOD else compact_finish
        record = dict(
            id=ident,
            method=method,
            cpu=cpu,
            result=result,
            input_sha256=sha256(encoded(case))[7:],
            implementation_sha256=sha256(Path(variant.__file__).read_bytes())[7:],
            core_sha256=core_sha256,
            projector_sha256=projector_sha256,
            worker_wall_s=wall,
            worker_cpu_s=cpu_time,
        )
        if confirm_missing:
            record["qualification"] = "standalone_corroboration"
        save_json(run / "result.json", record)
        if ident in PRIMARY:
            assert_frozen(case, record)
        if (
            core_sha256 != sha256(Path(v5_core.__file__).read_bytes())[7:]
            or projector_sha256 != (sha256(Path(orbit_projector.__file__).read_bytes())[7:])
        ):
            raise ValueError("Shared core or projection wrapper changed during the paired trial")
        print(ident, method, round(wall, 2), round(cpu_time, 2), flush=True)


def adjacent_unique(sequence):
    return [x for i, x in enumerate(sequence) if i == 0 or x != sequence[i - 1]]


def verify_search(stock, candidate):
    if stock["initial_signature"] != candidate["initial_signature"]:
        raise ValueError("Candidate changed the selected initial branch or its c0 gates")
    if adjacent_unique(stock["association_outcomes"]) != adjacent_unique(
        candidate["association_outcomes"]
    ):
        raise ValueError("Candidate changed discovery associations")
    if (
        stock["association_calls"]
        != candidate["association_calls"] + candidate["association_reused"]
    ):
        raise ValueError("Candidate changed the association trial budget")


def seal_positions(output, schedule, filename, rows):
    for row in rows:
        validate_result(row["result"])
    data = gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0)
    write(output / filename, data)
    schedule[filename] = sha256(data)[7:]


def no_endpoint(stock, status, reason, qualification, **metrics):
    return dict(
        id=stock["id"],
        method=METHOD,
        cpu=stock["cpu"],
        input_sha256=stock["input_sha256"],
        qualification=qualification,
        result=dict(
            status=status,
            reason=reason,
            boundary=stock["result"]["boundary"],
            arms={a: {"latlon": None} for a in ARMS},
            metrics=metrics,
        ),
    )


def package_original(runs, output):
    output = local_output(output)
    deadline = json.loads((output / "DS26-0122-deadline-attempt.json").read_bytes())
    if deadline["supervisor_exit_code"] != 124 or deadline["candidate"]["position_completed"]:
        raise ValueError("Expected the recorded original deadline without a candidate endpoint")
    stock_rows, candidate_rows = [], []
    for ident in RUNS:
        source = runs / ident
        stock = json.loads((source / STOCK / "result.json").read_bytes())
        if ident == deadline["id"]:
            if stock != deadline["stock"]:
                raise ValueError("Recorded original deadline uses a different stock worker")
            candidate = no_endpoint(
                stock,
                "timed_out",
                "The 650 s corroboration-pair deadline elapsed before the candidate "
                "produced a position.",
                "original_schedule",
                position_attempted=True,
                pair_deadline_wall_s=650,
                completed_initial_search=True,
            )
        else:
            candidate = json.loads((source / METHOD / "result.json").read_bytes())
            verify_adapter(stock, candidate)
        stock_rows.append(stock)
        candidate_rows.append(candidate)
    files = {}
    seal_positions(output, files, "original-positions.jsonl.gz", candidate_rows)
    seal_positions(output, files, "original-stock-positions.jsonl.gz", stock_rows)
    save_json(output / "original-receipt.json", dict(cases=list(RUNS), files=files))


def package_followup(runs, output, exit_code):
    output = local_output(output)
    ident = "DS26-0122"
    stock_path = runs / ident / STOCK
    candidate_path = runs / ident / (METHOD + "-confirmation")
    stock = json.loads((stock_path / "result.json").read_bytes())
    result_path = candidate_path / "result.json"
    search_path = candidate_path / "search.json"
    search = json.loads(search_path.read_bytes()) if search_path.is_file() else None
    check = None
    if result_path.is_file():
        candidate = json.loads(result_path.read_bytes())
        if candidate["result"]["status"] == "ok":
            try:
                if search is None:
                    raise ValueError("Standalone result lacks the initial-search trace")
                verify_adapter(stock, candidate)
                verify_search(json.loads((stock_path / "search.json").read_bytes()), search)
            except ValueError as exc:
                check = dict(passed=False, reason=str(exc))
            else:
                check = dict(passed=True)
    else:
        status = "timed_out" if exit_code == 124 else "failed"
        reason = f"Standalone candidate exited with status {exit_code} before emitting a position."
        candidate = no_endpoint(
            stock,
            status,
            reason,
            "standalone_corroboration",
            position_attempted=True,
            worker_deadline_wall_s=650,
            completed_initial_search=search is not None,
        )
    files = {}
    seal_positions(output, files, "followup-position.jsonl.gz", [candidate])
    save_json(output / "followup-receipt.json", dict(cases=[ident], files=files))
    save_json(
        output / "DS26-0122-followup-attempt.json",
        dict(
            supervisor_exit_code=exit_code,
            deadline_wall_s=650,
            candidate=candidate,
            initial_search=search,
            matched_stock=check,
        ),
    )


def package(runs, output, ids):
    output = local_output(output)
    positions = {STOCK: [], METHOD: []}
    comparisons = []
    prefix = load_rows(ARCHIVED_PREFIX)
    for ident in ids:
        panel, cpu, _ = RUNS[ident]
        _, (ref,) = references(panel, [ident])
        data, receipts = {}, {}
        for method in positions:
            source = runs / ident / method
            if (
                method == METHOD
                and (confirmation := source.with_name(method + "-confirmation")).is_dir()
            ):
                source = confirmation
            item = json.loads((source / "result.json").read_bytes())
            search = json.loads((source / "search.json").read_bytes())
            receipts[method] = item
            data[method] = dict(
                search=search,
                worker_wall_s=item["worker_wall_s"],
                worker_cpu_s=item["worker_cpu_s"],
                geographic_error_km={
                    arm: distance_km(ref["truth"], item["result"]["arms"][arm]["latlon"])
                    for arm in ARMS
                },
                conditional_rms_hz={
                    arm: item["result"]["metrics"][f"{arm}_conditional_rms_hz"] for arm in ARMS
                },
            )
            positions[method].append(item)
        a, b = (receipts[m] for m in (STOCK, METHOD))
        verify_adapter(a, b)
        if any(a[k] != b[k] for k in ("core_sha256", "projector_sha256")):
            raise ValueError("Pair loaded different core search code")
        for arm in ARMS:
            expected = prefix[ident][2]["stages"]["final"][arm]
            if (
                b["result"]["arms"][arm]["latlon"] != expected["latlon"]
                or data[METHOD]["conditional_rms_hz"][arm] != expected["conditional_rms_hz"]
            ):
                raise ValueError(f"{ident} {arm} differs from archived original v5")
        verify_search(data[STOCK]["search"], data[METHOD]["search"])
        comparisons.append(
            dict(
                id=ident,
                cpu=cpu,
                input_sha256=b["input_sha256"],
                methods=data,
                qualification=b.get("qualification", "paired"),
            )
        )
    archives = {}
    for role, method, filename in (
        ("control", STOCK, "stock-positions.jsonl.gz"),
        ("candidate", METHOD, "positions.jsonl.gz"),
    ):
        files = {}
        seal_positions(output, files, filename, positions[method])
        archives[role] = dict(method=method, positions=filename, position_sha256=files[filename])
    save_json(
        output / "receipt.json",
        dict(
            cases=list(ids),
            runs=archives,
            comparisons=comparisons,
            method=METHOD,
            control=STOCK,
            frozen_source=v5_lean.SOURCE_SHA256,
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=RUNS)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--primary-only", action="store_true")
    parser.add_argument("--confirm-missing-candidate", action="store_true")
    parser.add_argument("--original-schedule", action="store_true")
    parser.add_argument("--followup-exit", type=int)
    args = parser.parse_args()
    if args.case:
        replay(args.case, args.out, confirm_missing=args.confirm_missing_candidate)
    elif args.package and args.original_schedule:
        package_original(args.package, args.out)
    elif args.package and args.followup_exit is not None:
        package_followup(args.package, args.out, args.followup_exit)
    elif args.package:
        package(args.package, args.out, PRIMARY if args.primary_only else tuple(RUNS))
    else:
        parser.error("provide a recording or paired run directory")


if __name__ == "__main__":
    if len(sys.argv) == 6 and sys.argv[-1] in (METHOD, STOCK):
        worker(*sys.argv[1:])
    else:
        main()
