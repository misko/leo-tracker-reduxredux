"""Qualify one-entry reuse of the exact post-fit native likelihood result."""

import argparse
import gzip
import json
import os
import sys
from contextlib import ExitStack
from functools import partial
from importlib import import_module
from pathlib import Path
from time import perf_counter
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
from tools.pipeline_eval.qualification.catalogue_memory_eval import cpu_elapsed
from tools.pipeline_eval.qualification.prefix_figures import REPORT as ARCHIVED_PREFIX
from tools.pipeline_eval.qualification.prefix_figures import load_rows
from tools.pipeline_eval.qualification.v5_postfit import sha256
from tools.pipeline_eval.scoring import ARMS, distance_km, validate_result
from tools.pipeline_eval.variants import orbit_projector, v5_core, v5_lean, v5_likelihood_reuse

METHOD = "v5_likelihood_reuse"
STOCK = "orbit_projector"
DEADLINE_S = 600
RUNS = {
    "DS26-0036": ("ds26-common127", 4, (METHOD, STOCK)),
    "DS29-0082": ("roof16", 5, (STOCK, METHOD)),
    "DS26-0122": ("ds26-common127", 4, (STOCK, METHOD)),
    "DS29-0174": ("roof16", 5, (METHOD, STOCK)),
}
PRIMARY = tuple(RUNS)[:2]
LOC = "leo.analysis.localization_v3"
STAGES = (
    ("conservative_recovery", "conservative_recovery"),
    ("history_policy", "history_policy"),
    ("signed_context", "signed_context"),
    ("family_cavity", "nominate_families"),
    ("family_cavity", "cavity_policy"),
)


def bare(raw):
    return sha256(raw)[7:]


def picked(data, *keys):
    return {key: data[key] for key in keys if key in data}


def arms_summary(pair):
    result = {}
    for arm, row in pair.items():
        summary = picked(row, "endpoint_latlon", "RMS_hz", "active_points", "association")
        retained = row.get("gates", row.get("metrics", {}))
        summary["accepted_points"] = retained.get("accepted_points")
        gate_lists = dict(
            curved=retained.get("tracks", []),
            linear=row.get("linear_gates", []),
            extended=row.get("association_tracks", []),
        )
        for kind, gates in gate_lists.items():
            summary[kind] = [
                picked(
                    g,
                    "component",
                    "candidate_index",
                    "norad",
                    "compatible",
                    "points",
                    "observation_ids",
                    "support",
                    "alias",
                    "aliases_changed",
                )
                for g in gates
            ]
        result[arm] = summary
    return result


def decision(name, value):
    if name == "conservative_recovery":
        result = picked(
            value,
            "status",
            "final_mask",
            "initial_failed_components",
            "exclusion_history",
            "post_salvage_history",
        )
        if "final_node" in value:
            result["selected"] = [
                picked(row, "component", "candidate_index", "candidate_norad", "observation_ids")
                for row in value["final_node"]["seed"]["rows"]
            ]
            result["aliases"] = value["final_node"]["aliases"]
        result["trims"] = [r.get("selected") for r in value.get("trims", [])]
        result["arms"] = arms_summary(value.get("arms", {}))
        return result
    if name == "history_policy":
        return dict(
            picked(
                value,
                "status",
                "mask",
                "linear_paired_valid",
                "fallback",
                "linear_offered_tracks",
                "linear_offered_points",
                "linear_used_points",
            ),
            arms=arms_summary(value["policy_arms"]),
        )
    if name == "signed_context":
        return dict(
            picked(value["signed"], "accepted", "selection"), arms=arms_summary(value["arms"])
        )
    if name == "nominate_families":
        return dict(
            status=value["status"],
            families=[
                dict(
                    picked(
                        row,
                        "original_norad",
                        "original_index",
                        "held_observation_ids",
                        "held_points",
                        "coarse_candidate_count",
                        "predictive_gain",
                    ),
                    candidate=None if row["best"] is None else row["best"]["candidate_index"],
                )
                for row in value.get("families", [])
            ],
        )
    if name == "cavity_policy":
        selected = value.get("selected")
        return dict(
            picked(value, "status", "accepted"),
            selected=None if selected is None else selected.get("offers"),
            arms=arms_summary(value.get("policy_arms", {})),
        )
    raise ValueError(name)


def json_array(value):
    return value.tolist()


def observe(name, operation, telemetry, *args, **kwargs):
    began = perf_counter(), cpu_elapsed()
    result = operation(*args, **kwargs)
    row = dict(wall_s=perf_counter() - began[0], cpu_s=cpu_elapsed() - began[1])
    decision_value = decision(name, result)
    row["decision_sha256"] = bare(
        json.dumps(
            decision_value,
            default=json_array,
            sort_keys=True,
            allow_nan=True,
        ).encode()
    )
    telemetry[name] = row
    return result


def worker(request, result, library, log, method):
    telemetry = {}
    with ExitStack() as stack:
        endpoint = stack.enter_context(v5_likelihood_reuse.endpoint_reuse(enabled=method == METHOD))
        for module, name in STAGES:
            mod = import_module(f"{LOC}.{module}")
            wrapper = partial(observe, name, getattr(mod, name), telemetry)
            stack.enter_context(patch.object(mod, name, wrapper))
        orbit_projector.worker(request, result, library)
    save_json(Path(log), dict(endpoints=endpoint, stages=telemetry))


def source_tokens():
    return {
        p.__name__: bare(Path(p.__file__).read_bytes())
        for p in (orbit_projector, v5_core, v5_likelihood_reuse, sys.modules[__name__])
    }


def replay(ident, output):
    panel, cpu, order = RUNS[ident]
    if os.sched_getaffinity(0) != {cpu}:
        raise ValueError(f"Both replays of {ident} must run on CPU {cpu}")
    source, refs = references(panel, [ident])
    (case,) = public_cases(source, refs, DEFAULT_OUT / "inputs")
    sources = source_tokens()
    for method in order:
        run = local_output(output) / ident / method
        run.mkdir(parents=True, exist_ok=False)
        library, log = run / "orbit_projector.so", run / "likelihood.json"
        began, started_cpu = perf_counter(), cpu_elapsed()
        orbit_projector.compile_kernel(library)
        with patch.object(v5_lean, "TIMEOUT_S", DEADLINE_S):
            result = v5_lean.run_bound_worker(
                case,
                run / "worker",
                Path(__file__),
                worker_args=(str(library), str(log), method),
            )
        wall, cpu_s = perf_counter() - began, cpu_elapsed() - started_cpu
        result["boundary"] = orbit_projector.BOUNDARY
        variant = v5_likelihood_reuse if method == METHOD else orbit_projector
        record = dict(
            id=ident,
            method=method,
            cpu=cpu,
            result=result,
            input_sha256=bare(encoded(case)),
            implementation_sha256=sources[variant.__name__],
            source_files=sources,
            worker_wall_s=wall,
            worker_cpu_s=cpu_s,
        )
        save_json(run / "result.json", record)
        if sources != source_tokens():
            raise ValueError("A bound numerical source changed during replay")
        print(ident, method, result["status"], round(wall, 2), round(cpu_s, 2), flush=True)


def verify(stock, candidate, logs, archived):
    ident = stock["id"]
    for key in ("id", "cpu", "input_sha256", "source_files"):
        if stock[key] != candidate[key]:
            raise ValueError(f"{ident} disagreed in {key}")
    for row in (stock, candidate):
        validate_result(row["result"])
        if row["result"]["status"] != "ok":
            raise ValueError(f"{ident} {row['method']} has no computed endpoint")
    if stock["result"]["arms"] != candidate["result"]["arms"]:
        raise ValueError(f"{ident} endpoint or frequency RMS changed")
    counts = (
        "observations",
        "tracks",
        "initial_branches",
        "initial_arm_fits",
        "cavity_offered",
        "compact_projections",
        "max_prepared_bytes",
        "original_grid_bytes_at_largest_shape",
    )
    if picked(stock["result"]["metrics"], *counts) != picked(
        candidate["result"]["metrics"], *counts
    ):
        raise ValueError(f"{ident} counts or cavity eligibility changed")
    results = [{k: v["decision_sha256"] for k, v in log["stages"].items()} for log in logs]
    if results[0] != results[1]:
        raise ValueError(f"{ident} post-initial decisions changed")
    for arm in ARMS:
        position = candidate["result"]["arms"][arm]
        expected = archived["stages"]["cavity"][arm]
        if position != {"latlon": expected["latlon"], "rf_rms_hz": expected["conditional_rms_hz"]}:
            raise ValueError(f"{ident} {arm} differs from archived cavity checkpoint")
    a, b = [log["endpoints"] for log in logs]
    if a.keys() != b.keys():
        raise ValueError(f"{ident} changed fit stages")
    for stage, x in a.items():
        y = b[stage]
        if (x["models"], x["calls"]) != (y["models"], y["calls"]):
            raise ValueError(f"{ident} {stage} changed endpoint call count")
        if x["hits"] or x["solves"] != x["calls"] or y["solves"] + y["hits"] != x["calls"]:
            raise ValueError(f"{ident} {stage} endpoint calls were not accounted for")


def package(directory, output, ids):
    output = local_output(output)
    predictions = {STOCK: [], METHOD: []}
    archive = load_rows(ARCHIVED_PREFIX)
    comparisons, telemetry = [], {}
    for ident in ids:
        panel, cpu, _ = RUNS[ident]
        _, (ref,) = references(panel, [ident])
        pair = dict(id=ident, cpu=cpu, methods={})
        logs = []
        for method in predictions:
            run = directory / ident / method
            row = json.loads((run / "result.json").read_bytes())
            predictions[method].append(row)
            raw = (run / "likelihood.json").read_bytes()
            log = json.loads(raw)
            logs.append(log)
            filename = f"{ident}-{method}-likelihood.json"
            write(output / filename, raw)
            telemetry[filename] = bare(raw)
            arms = row["result"]["arms"]
            pair["methods"][method] = dict(
                endpoint_likelihood=log["endpoints"],
                stage_s=row["result"]["metrics"]["stage_s"],
                wall_s=row["worker_wall_s"],
                cpu_s=row["worker_cpu_s"],
                conditional_rms_hz={arm: arms[arm]["rf_rms_hz"] for arm in ARMS},
                geographic_error_km={
                    arm: distance_km(ref["truth"], arms[arm]["latlon"]) for arm in ARMS
                },
            )
        verify(predictions[STOCK][-1], predictions[METHOD][-1], logs, archive[ident][2])
        pair["input_sha256"] = row["input_sha256"]
        comparisons.append(pair)
    artifacts = {}
    for role, method, filename in (
        ("control", STOCK, "stock-positions.jsonl.gz"),
        ("candidate", METHOD, "positions.jsonl.gz"),
    ):
        raw = gzip.compress(b"".join(encoded(r) + b"\n" for r in predictions[method]), mtime=0)
        write(output / filename, raw)
        artifacts[role] = dict(method=method, positions=filename, position_sha256=bare(raw))
    save_json(
        output / "receipt.json",
        dict(
            cases=list(ids),
            comparisons=comparisons,
            runs=artifacts,
            telemetry=telemetry,
            frozen_source=v5_lean.SOURCE_SHA256,
            deadline_s=DEADLINE_S,
            primary_cases=PRIMARY,
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=RUNS)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--corroborate", action="store_true")
    args = parser.parse_args()
    if args.case:
        replay(args.case, args.out)
    elif args.package:
        package(args.package, args.out, RUNS if args.corroborate else PRIMARY)
    else:
        parser.error("provide a recording or paired run directory")


if __name__ == "__main__":
    if len(sys.argv) == 6 and sys.argv[-1] in (METHOD, STOCK):
        worker(*sys.argv[1:])
    else:
        main()
