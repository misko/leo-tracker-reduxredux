"""Paired native-GLRT replays and scoring for a one-branch compact v5 fit."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from .. import corpus
from ..__main__ import (
    DEFAULT_OUT,
    encoded,
    local_output,
    public_cases,
    references,
    run_one,
    save_json,
    write,
)
from ..scoring import ARMS, distance_km, distribution, validate_result
from ..variants import orbit_projector, v5_core, v5_lean, v5_search_budget
from .prefix_figures import TIMING_IDS, csv_file

REPORT = Path(__file__).resolve().parents[3] / "reports/2026_11_19_short_receiver/search-budget"
METHODS = ("v5_one_seed", "v5_first_ranked", "orbit_projector")
PAIRS = {
    16: ("DS29-0174", "DS26-0237"),
    22: ("DS26-0122", "DS29-0082"),
    23: ("DS29-0247", "DS26-0036"),
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_lock():
    sources = [m.__file__ for m in (v5_search_budget, v5_core, orbit_projector, v5_lean)]
    return {Path(p).name: digest(p) for p in [*sources, orbit_projector.KERNEL]}


def replay(out, cpu):
    out = local_output(out)
    out.mkdir(parents=True, exist_ok=True)
    seal = source_lock()
    for case_id in PAIRS[cpu]:
        panel = "ds26-common127" if case_id.startswith("DS26") else "roof16"
        source, refs = references(panel, [case_id])
        (case,) = public_cases(source, refs, DEFAULT_OUT / "inputs")
        native = digest(case["native_path"])
        if native != case["native_sha256"].removeprefix("sha256:"):
            raise ValueError(f"changed native GLRT for {case_id}")
        catalogue = digest(case["catalog_path"])
        rotation = TIMING_IDS.index(case_id) % len(METHODS)
        for method in METHODS[rotation:] + METHODS[:rotation]:
            target = out / case_id / (method + ".json")
            if target.exists():
                raise FileExistsError(target)
            result = run_one(method, case, out, 600, cpu)
            if source_lock() != seal:
                raise ValueError(
                    "the initial-search implementation changed during the paired replay"
                )
            result.update(
                method=method,
                cpu=cpu,
                native_sha256=native,
                catalog_sha256=catalogue,
                source_sha256=seal,
            )
            save_json(target, result)
            print(
                case_id,
                method,
                result["result"]["status"],
                round(result["worker_wall_s"], 2),
                flush=True,
            )


def distribution_rows(rows):
    stock = {(r["recording"], r["arm"]): r for r in rows if r["method"] == "orbit_projector"}
    results = []
    for method in METHODS:
        for arm in ARMS:
            for dataset in ("DS26", "DS29", "all"):
                group = [
                    r
                    for r in rows
                    if r["method"] == method
                    and r["arm"] == arm
                    and dataset in ("all", r["dataset"])
                ]
                if not group:
                    continue
                errors = distribution(r["position_error_km"] for r in group)
                baseline = distribution(r["v5_error_km"] for r in group)
                paired = [
                    (r["position_error_km"], r["v5_error_km"])
                    for r in group
                    if r["position_error_km"] is not None and r["v5_error_km"] is not None
                ]
                # Failed attempts keep their elapsed time in the source table. Speedup describes
                # completed pairs only, so a timeout cannot appear as an improvement.
                successes = [
                    (r, stock[r["recording"], arm])
                    for r in group
                    if r["status"] == stock[r["recording"], arm]["status"] == "ok"
                ]
                results.append(
                    dict(
                        method=method,
                        arm=arm,
                        dataset=dataset,
                        scheduled=len(group),
                        published=errors["n"],
                        median_km=errors["p50"],
                        p95_km=errors["p95"],
                        worst_km=errors["max"],
                        v5_published=baseline["n"],
                        v5_median_km=baseline["p50"],
                        v5_p95_km=baseline["p95"],
                        paired_positions=len(paired),
                        paired_at_most_105pct_v5=sum(a <= 1.05 * b for a, b in paired),
                        paired_at_most_110pct_v5=sum(a <= 1.10 * b for a, b in paired),
                        passes_10pct_gate=(
                            len(paired) == len(group)
                            and errors["p50"] <= 1.10 * baseline["p50"]
                            and errors["p95"] <= 1.10 * baseline["p95"]
                        ),
                        median_conditional_rms_hz=distribution(
                            r["conditional_rms_hz"] for r in group
                        )["p50"],
                        speed_pairs=len(successes),
                        median_paired_worker_speedup=distribution(
                            s["wall_s"] / r["wall_s"] for r, s in successes
                        )["p50"],
                        median_worker_s=distribution(r["wall_s"] for r in group)["p50"],
                        median_initial_s=distribution(r["initial_s"] for r in group)["p50"],
                    )
                )
    return results


def package(runs, report):
    report = local_output(report)
    summary = []
    payloads = {}
    refs = {r["id"]: r for p in ("ds26-common127", "roof16") for r in references(p, None)[1]}
    _, bound = corpus._selection("roof16")
    frozen = corpus._index(corpus._read_frozen("inputs.jsonl", bound))
    source = source_lock()
    inputs = {}
    for method in METHODS:
        records = []
        for case in TIMING_IDS:
            row = json.loads((runs / case / (method + ".json")).read_bytes())
            result = row["result"]
            validate_result(result)
            module = "orbit_projector.py" if method == "orbit_projector" else "v5_search_budget.py"
            if (
                row["id"] != case
                or row["method"] != method
                or row["source_sha256"] != source
                or case not in PAIRS.get(row["cpu"], ())
                or row["native_sha256"] != frozen[case]["native"]["sha256"]
                or row["catalog_sha256"] != frozen[case]["catalog"]["sha256"]
                or (
                    result["status"] == "ok"
                    and (
                        row["implementation_sha256"] != source[module]
                        or result["metrics"]["kernel_sha256"] != source["orbit_projector.c"]
                        or result["metrics"].get("initial_policy", "orbit_projector") != method
                    )
                )
            ):
                raise ValueError(
                    f"mismatched input, method, processor or source for {case}/{method}"
                )
            binding = tuple(
                row[k] for k in ("input_sha256", "native_sha256", "catalog_sha256", "cpu")
            )
            if binding != inputs.setdefault(case, binding):
                raise ValueError(f"paired input or processor differs for {case}")
            for arm in ARMS:
                endpoint = result.get("arms", {}).get(arm, {})
                ref = refs[case]
                stages = result["metrics"].get("stage_s", {})
                summary.append(
                    dict(
                        recording=case,
                        dataset=ref["group"],
                        method=method,
                        arm=arm,
                        status="withheld"
                        if result["status"] == "ok" and endpoint.get("latlon") is None
                        else result["status"],
                        position_error_km=distance_km(endpoint.get("latlon"), ref["truth"]),
                        v5_error_km=ref["reference"]["baseline"][arm]["error_km"],
                        conditional_rms_hz=endpoint.get("rf_rms_hz"),
                        initial_s=stages.get("initial"),
                        wall_s=row["worker_wall_s"],
                        fitted_initial_branches=result["metrics"].get("initial_arm_fits"),
                    )
                )
            records.append(row)
        payloads[method + ".jsonl.gz"] = gzip.compress(
            b"".join(encoded(r) + b"\n" for r in records), mtime=0
        )
    for name, data in payloads.items():
        write(report / name, data)
    csv_file(report / "per-recording.csv", summary)
    csv_file(report / "distributions.csv", distribution_rows(summary))
    save_json(
        report / "receipt.json",
        dict(
            cases=TIMING_IDS,
            files={name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()},
            source=source,
            scientific_source=v5_lean.SOURCE_SHA256,
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("replay")
    run.add_argument("--cpu", type=int, choices=PAIRS, required=True)
    run.add_argument("--out", type=Path, required=True)
    score = sub.add_parser("score")
    score.add_argument("--runs", type=Path, required=True)
    score.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args()
    if args.command == "replay":
        replay(args.out, args.cpu)
    else:
        package(args.runs, args.report)


if __name__ == "__main__":
    main()
