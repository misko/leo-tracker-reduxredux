"""Measure and seal paired compact-v5 runs with two or five early phase fits."""

import argparse
import fcntl
import gzip
import json
import os
import resource
from pathlib import Path

from ..__main__ import (
    encoded,
    local_output,
    read_predictions,
    references,
    run_one,
    save_json,
    write,
)
from ..scoring import ARMS, distance_km, distribution, validate_result
from ..variants import orbit_projector, v5_core, v5_lean, v5_two_refresh
from .broad_search_budget import _case, _pair_summary, frozen_inputs
from .prefix_figures import TIMING_IDS, csv_file
from .projector_roof import input_hash
from .search_budget import digest

REPORT = (
    Path(__file__).resolve().parents[3] / "reports/2026_11_19_receiver_convergence/phase-budget"
)
METHODS = ("v5_two_refresh", "orbit_projector")
DEADLINE = 480
SCHEDULE = (
    ("DS26-0036", "DS29-0174", "DS26-0122"),
    ("DS29-0082", "DS26-0237", "DS29-0247"),
)


def source_lock():
    files = [Path(m.__file__) for m in (v5_two_refresh, v5_core, orbit_projector, v5_lean)]
    return {p.name: digest(p) for p in [*files, orbit_projector.KERNEL]}


def check_record(row, case, item, method, source):
    result = row["result"]
    validate_result(result)
    if (
        row["id"] != case["id"]
        or row["method"] != method
        or row["source_sha256"] != source
        or row["input_sha256"] != input_hash(case)
        or row["worker_wall_s"] <= 0
        or row["worker_cpu_s"] < 0
        or row["cap_s"] != DEADLINE
        or any(row[k + "_sha256"] != item[k]["sha256"] for k in ("catalog", "native"))
    ):
        raise ValueError("phase comparison recording, runtime, source or observation mismatch")
    if result["status"] == "ok" and (
        row["implementation_sha256"] != source[method + ".py"]
        or result["metrics"].get("kernel_sha256") != source["orbit_projector.c"]
        or set(result.get("arms", {})) != set(ARMS)
        or (method == METHODS[0] and result["metrics"].get("outer_phase_limit") != 2)
    ):
        raise ValueError("phase comparison worker or numerical budget mismatch")
    return row


def replay(directory, lane, cpu):
    if cpu not in os.sched_getaffinity(0):
        raise ValueError("worker CPU outside this host's affinity")
    directory = local_output(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / f"lane-{lane}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        measure_lane(directory, lane, cpu)


def measure_lane(directory, lane, cpu):
    source, inputs = source_lock(), frozen_inputs()
    for ident in SCHEDULE[lane]:
        item = inputs[ident]
        case = _case(item)
        if any(digest(case[k + "_path"]) != item[k]["sha256"] for k in ("catalog", "native")):
            raise ValueError(f"recorded source differs for {ident}")
        order = METHODS if TIMING_IDS.index(ident) % 2 == 0 else METHODS[::-1]
        for index, method in enumerate(order):
            dest = directory / ident / (method + ".json")
            if dest.exists():
                row = check_record(json.loads(dest.read_bytes()), case, item, method, source)
                if (row["cpu"], row["order"]) != (cpu, index):
                    raise ValueError("cached pair was measured on a different CPU or order")
                continue
            before = resource.getrusage(resource.RUSAGE_CHILDREN)
            row = run_one(method, case, directory, DEADLINE, cpu)
            after = resource.getrusage(resource.RUSAGE_CHILDREN)
            if source != source_lock():
                raise ValueError("phase fit source changed during replay")
            row.update(
                method=method,
                cpu=cpu,
                order=index,
                cap_s=DEADLINE,
                source_sha256=source,
                native_sha256=item["native"]["sha256"],
                catalog_sha256=item["catalog"]["sha256"],
                worker_cpu_s=after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime,
            )
            check_record(row, case, item, method, source)
            save_json(dest, row)
            print(
                ident, method, row["result"]["status"], round(row["worker_wall_s"], 2), flush=True
            )


def seal(directory, output):
    source, inputs = source_lock(), frozen_inputs()
    groups = {m: [] for m in METHODS}
    for ident in TIMING_IDS:
        item = inputs[ident]
        case = _case(item)
        pair = [
            check_record(
                json.loads((directory / ident / f"{m}.json").read_bytes()), case, item, m, source
            )
            for m in METHODS
        ]
        orders = [0, 1] if TIMING_IDS.index(ident) % 2 == 0 else [1, 0]
        if [p["order"] for p in pair] != orders or pair[0]["cpu"] != pair[1]["cpu"]:
            raise ValueError("phase fit timing pair differs from its schedule")
        for m, row in zip(METHODS, pair, strict=True):
            groups[m].append(row)
    files = {}
    for method, records in groups.items():
        path = output / f"{method}.jsonl.gz"
        write(path, gzip.compress(b"".join(encoded(r) + b"\n" for r in records), mtime=0))
        files[path.name] = digest(path)
    save_json(
        output / "receipt.json",
        dict(cases=TIMING_IDS, files=files, source=source, scientific_source=v5_lean.SOURCE_SHA256),
    )


def sealed_pair(output):
    receipt = json.loads((output / "receipt.json").read_bytes())
    names = {method + ".jsonl.gz" for method in METHODS}
    if (
        receipt["files"].keys() != names
        or receipt["cases"] != list(TIMING_IDS)
        or any(digest(output / name) != receipt["files"][name] for name in names)
    ):
        raise ValueError("phase study predictions differ from the sealed roster or bytes")
    pairs = {}
    for method in METHODS:
        records = read_predictions(output / (method + ".jsonl.gz"))
        if list(records) != receipt["cases"] or any(
            row["method"] != method or row["source_sha256"] != receipt["source"]
            for row in records.values()
        ):
            raise ValueError("incorrect phase comparison roster or method")
        pairs[method] = records
    for index, ident in enumerate(receipt["cases"]):
        candidate, stock = (pairs[method][ident] for method in METHODS)
        same = ("cpu", "input_sha256", "native_sha256", "catalog_sha256")
        if (candidate["order"], stock["order"]) != (index % 2, 1 - index % 2) or any(
            candidate[key] != stock[key] for key in same
        ):
            raise ValueError("phase comparison did not use the same input and paired CPU schedule")
    return pairs


def summarize(rows, pairs):
    groups = []
    for dataset in ("DS26", "DS29", "all"):
        for arm in ARMS:
            for method in METHODS:
                group = [
                    r
                    for r in rows
                    if (r["arm"], r["method"]) == (arm, method) and dataset in ("all", r["dataset"])
                ]
                errors = distribution(r["position_error_km"] for r in group)
                original = distribution(r["v5_error_km"] for r in group)
                matched = [
                    (r["position_error_km"], r["v5_error_km"])
                    for r in group
                    if r["position_error_km"] is not None and r["v5_error_km"] is not None
                ]
                groups.append(
                    dict(
                        dataset=dataset,
                        arm=arm,
                        method=method,
                        scheduled=len(group),
                        error_km=errors,
                        v5_error_km=original,
                        paired_v5=_pair_summary(matched),
                        conditional_rms_hz=distribution(r["conditional_rms_hz"] for r in group),
                        meets_10pct_distribution_gate=(
                            bool(matched)
                            and errors["n"] == original["n"] == len(matched)
                            and all(errors[key] <= 1.1 * original[key] for key in ("p50", "p95"))
                        ),
                    )
                )
    timing = {}
    completed = [
        (candidate, pairs[METHODS[1]][ident])
        for ident, candidate in pairs[METHODS[0]].items()
        if candidate["result"]["status"] == pairs[METHODS[1]][ident]["result"]["status"] == "ok"
    ]
    for clock in ("worker_wall_s", "worker_cpu_s"):
        same = [(c[clock], s[clock]) for c, s in completed if c[clock] > 0 and s[clock] > 0]
        timing[clock] = dict(
            candidate=distribution(c for c, _ in same),
            stock=distribution(s for _, s in same),
            stock_over_candidate=distribution(s / c for c, s in same),
        )
    return dict(groups=groups, scheduled_pairs=len(pairs[METHODS[0]]), paired_timing=timing)


def score(output):
    pairs = sealed_pair(output)
    refs = {r["id"]: r for p in ("roof16", "ds26-common127") for r in references(p, None)[1]}
    rows = []
    for method, records in pairs.items():
        for ident, row in records.items():
            ref, result = refs[ident], row["result"]
            for arm in ARMS:
                endpoint = result.get("arms", {}).get(arm, {})
                status = result["status"]
                if status == "ok" and endpoint.get("latlon") is None:
                    status = "withheld"
                rows.append(
                    dict(
                        recording=ident,
                        dataset=ref["group"],
                        arm=arm,
                        method=method,
                        status=status,
                        reason=result.get("reason"),
                        position_error_km=distance_km(endpoint.get("latlon"), ref["truth"]),
                        v5_error_km=ref["reference"]["baseline"][arm]["error_km"],
                        conditional_rms_hz=endpoint.get("rf_rms_hz"),
                        worker_wall_s=row["worker_wall_s"],
                        worker_cpu_s=row["worker_cpu_s"],
                        **{
                            s + "_s": result["metrics"].get("stage_s", {}).get(s)
                            for s in (
                                "native_preparation",
                                "initial",
                                "conservative",
                                "family",
                                "signed",
                                "cavity",
                            )
                        },
                    )
                )
    csv_file(output / "per-recording.csv", rows)
    save_json(output / "summary.json", summarize(rows, pairs))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("replay", "seal", "score"))
    parser.add_argument("--runs", type=Path)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--cpu", type=int)
    parser.add_argument("--lane", type=int, choices=(0, 1))
    args = parser.parse_args()
    if args.action in ("replay", "seal") and args.runs is None:
        parser.error("replay and seal require --runs")
    if args.action == "replay":
        if args.cpu is None or args.lane is None:
            parser.error("replay requires --cpu and --lane")
        replay(args.runs, args.lane, args.cpu)
    elif args.action == "seal":
        seal(args.runs, local_output(args.report))
    else:
        score(local_output(args.report))


if __name__ == "__main__":
    main()
