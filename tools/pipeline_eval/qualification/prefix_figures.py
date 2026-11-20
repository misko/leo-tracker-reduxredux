"""Compare archived v5 stopping points and fresh, timed v5 workers on matched recordings."""

import argparse
import csv
import gzip
import io
import json
import math
from pathlib import Path
from statistics import median

from ..__main__ import encoded, read_predictions, write
from ..figure_books import Page, write_book
from ..position_figure import marks
from ..scoring import ARMS, distance_km, distribution, validate_result
from .v5_prefix_audit import STAGES, cohorts

REPORT = Path(__file__).resolve().parents[3] / "reports/2026_11_19_receiver_simplification"
TIMING_IDS = ("DS26-0036", "DS26-0122", "DS26-0237", "DS29-0082", "DS29-0174", "DS29-0247")
METHODS = ("v5_lean", "v5_core")


def load_rows(directory):
    cases = {}
    for split, refs in cohorts().items():
        with gzip.open(directory / f"{split}.jsonl.gz", "rt") as stream:
            data = list(map(json.loads, stream))
        if [r["id"] for r in data] != [r["id"] for r in refs]:
            raise ValueError(f"{split} checkpoint roster differs from frozen selection")
        for ref, row in zip(refs, data, strict=True):
            if ref["id"] in cases or row["group"] != ref["group"]:
                raise ValueError("duplicate recording or inconsistent dataset")
            for arm in ARMS:
                distance = distance_km(
                    row["stages"]["final"][arm]["latlon"],
                    ref["reference"]["baseline"][arm]["latlon"],
                )
                if distance is None or distance > 1e-6:
                    raise ValueError(f"{ref['id']} final checkpoint differs from the v5 reference")
            cases[ref["id"]] = (ref, split, row)
    return cases


def csv_file(path, rows):
    stream = io.StringIO(newline="")
    table = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    table.writeheader()
    table.writerows(rows)
    write(path, stream.getvalue().encode())


def collect_runs(root, path):
    pairs = {}
    for method in METHODS:
        for file in sorted(root.glob(f"*/{method}/subset-*/current/predictions.jsonl")):
            for case, record in read_predictions(file).items():
                if case not in TIMING_IDS:
                    continue
                if (case, method) in pairs:
                    raise ValueError(f"ambiguous timing runs for {case} {method}")
                pairs[case, method] = dict(method=method, **record)
    if set(pairs) != {(case, method) for case in TIMING_IDS for method in METHODS}:
        raise ValueError("the timing experiment requires both workers on all six cases")
    data = b"".join(encoded(pairs[k]) + b"\n" for k in sorted(pairs))
    write(path, gzip.compress(data, mtime=0))


def archived_rows(cases):
    errors = []
    for ref, split, record in cases.values():
        for stage in (*STAGES, "final"):
            for arm in ARMS:
                point = record["stages"][stage][arm]
                final = record["stages"]["final"][arm]["latlon"]
                error = distance_km(point["latlon"], ref["truth"])
                reference = distance_km(final, ref["truth"])
                errors.append(
                    dict(
                        recording=ref["id"],
                        dataset=ref["group"],
                        split=split,
                        stage=stage,
                        arm=arm,
                        error_km=error,
                        final_error_km=reference,
                        delta_error_km=None if error is None else error - reference,
                        moved_km=distance_km(point["latlon"], final),
                        conditional_rms_hz=point["conditional_rms_hz"],
                    )
                )
    return errors


def summarize(rows):
    result = []
    for dataset, split in dict.fromkeys(
        (r["dataset"], s) for r in rows for s in (r["split"], "all")
    ):
        for stage in (*STAGES, "final"):
            for arm in ARMS:
                group = [
                    r
                    for r in rows
                    if r["dataset"] == dataset
                    and r["stage"] == stage
                    and r["arm"] == arm
                    and (split == "all" or r["split"] == split)
                ]
                errors = [r["error_km"] for r in group]
                rms = [
                    r["conditional_rms_hz"] for r in group if r["conditional_rms_hz"] is not None
                ]
                stats = distribution(errors)
                result.append(
                    dict(
                        dataset=dataset,
                        split=split,
                        stage=stage,
                        arm=arm,
                        n=len(group),
                        fixes=stats["n"],
                        within5=sum(e is not None and e <= 5 for e in errors),
                        p50_km=stats["p50"],
                        p95_km=stats["p95"],
                        worst_km=stats["max"],
                        moved_over_1m=sum(
                            r["moved_km"] is not None and r["moved_km"] > 0.001 for r in group
                        ),
                        median_conditional_rms_hz=median(rms) if rms else None,
                        rms_recordings=len(rms),
                    )
                )
    return result


def fresh_pairs(path, cases):
    with gzip.open(path, "rt") as stream:
        rows = list(map(json.loads, stream))
    pairs = {(r["id"], r["method"]): r for r in rows}
    if len(rows) != len(pairs) or set(pairs) != {(c, m) for c in TIMING_IDS for m in METHODS}:
        raise ValueError("incomplete or duplicated paired recording")
    for method in METHODS:
        versions = {pairs[c, method].get("implementation_sha256") for c in TIMING_IDS}
        if len(versions) != 1 or None in versions:
            raise ValueError(f"{method} timing pairs used different worker versions")
    timings = []
    for case in TIMING_IDS:
        ref, _, record = cases[case]
        full, core = (pairs[case, m] for m in METHODS)
        if not full["input_sha256"] or full["input_sha256"] != core["input_sha256"]:
            raise ValueError(f"{case} workers received different inputs")
        for item, stage in ((full, "final"), (core, "cavity")):
            validate_result(item["result"])
            for arm in ARMS:
                sep = distance_km(
                    item["result"]["arms"][arm]["latlon"], record["stages"][stage][arm]["latlon"]
                )
                if sep is None or sep > 1e-6:
                    raise ValueError(
                        f"{case} live {item['method']} disagrees with archived {stage}, {arm}"
                    )
        a, b = (r["worker_wall_s"] for r in (full, core))
        if not all(math.isfinite(s) and s > 0 for s in (a, b)):
            raise ValueError("invalid worker wall time")
        metrics = core["result"]["metrics"]
        timings.append(
            dict(
                recording=case,
                dataset=ref["group"],
                full_v5_s=a,
                core_s=b,
                speedup=a / b,
                initial_c0_fits=metrics["initial_arm_fits"],
                cavity_offered=metrics["cavity_offered"],
            )
        )
    return {c: pairs[c, "v5_core"] for c in TIMING_IDS}, timings


def checkpoint_pages(cases, fresh, arm):
    refs = sorted((r for r, _, _ in cases.values()), key=lambda r: r["id"])
    pages = []
    for stage in STAGES:
        pred = {}
        name = "v5_stop_" + stage
        for case, (_, _, r) in cases.items():
            pair = {a: {"latlon": r["stages"][stage][a]["latlon"]} for a in ARMS}
            ok = any(val["latlon"] is not None for val in pair.values())
            pred[case] = {
                "result": dict(
                    status="ok" if ok else "withheld",
                    reason="checkpoint",
                    boundary="archived v5 checkpoint",
                    metrics={},
                    arms=pair,
                )
            }
        subtitle = (
            "Position extracted at this stage of the original v5 run "
            "on 127 DS26 and eight DS29 recordings."
        )
        pages.append(Page(name, name, subtitle, marks(refs, pred, None, name, arm)))
    timing_refs = [r for r in refs if r["id"] in fresh]
    pages.append(
        Page(
            "v5_core",
            "v5_core",
            "Fresh execution from native detections on the six paired timing recordings.",
            marks(timing_refs, fresh, None, "v5_core", arm),
        )
    )
    return pages


def build(directory, output):
    cases = load_rows(directory)
    scores = archived_rows(cases)
    csv_file(output / "checkpoint-errors.csv", scores)
    csv_file(output / "checkpoint-distributions.csv", summarize(scores))
    fresh, times = fresh_pairs(directory / "paired.jsonl.gz", cases)
    csv_file(output / "paired-runtime.csv", times)
    for arm in ARMS:
        pages = checkpoint_pages(cases, fresh, arm)
        write_book(pages, output / "figures" / arm, "stopping-points", arm)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, default=REPORT)
    p.add_argument("--out", type=Path, default=REPORT)
    p.add_argument(
        "--collect",
        type=Path,
        help="import the six completed pairs from the common benchmark output root",
    )
    args = p.parse_args()
    if args.collect:
        collect_runs(args.collect, args.data / "paired.jsonl.gz")
    build(args.data, args.out)


if __name__ == "__main__":
    main()
