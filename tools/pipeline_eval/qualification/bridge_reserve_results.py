"""Seal and score every scheduled recording in the unchanged bridge reserve."""

import argparse
from collections import Counter
from pathlib import Path

from ..__main__ import local_output, read_predictions, save_json, write
from ..scoring import ARMS, ROLES, distance_km, distribution, thresholds, validate_result
from . import bridge_reserve as trial
from . import full_receiver_comparison as common
from .native_agreement_cascade_eval import compact_wall
from .phase_support_results import pack
from .prefix_figures import csv_file
from .short_receiver_figures import _frozen_roof

REPORT, CANDIDATE, STOCK = trial.REPORT, trial.CANDIDATE, trial.STOCK
POSITIONS, CONTROLS = "positions.jsonl.gz", "stock-positions.jsonl.gz"
NATIVE_RECEIPTS = "native-receipts.jsonl.gz"
CHART = "bridge-support-reserve-roof24"
STAGES = ("native_preparation", "initial", "conservative", "family", "signed", "cavity")
RELATIVE = (("5pct", 1.05), ("10pct", 1.10))
MATERIAL_KM = 0.50


def read_measurement(ident, cpu, binding, folder, source_sha):
    path = folder / "measurement.json"
    if not path.is_file():
        request = (folder / "request.json").is_file()
        return dict(
            binding,
            method=CANDIDATE,
            qualification="no_measurement",
            cpu=cpu,
            source_lock_sha256=source_sha,
            result=trial.unavailable(
                "failed" if request else "missing",
                "materialized worker produced no sealed result" if request else "not started",
            ),
        )
    row = common.read(path)
    common.require_fields(
        row, dict(binding, method=CANDIDATE, cpu=cpu, source_lock_sha256=source_sha)
    )
    result = row["result"]
    validate_result(result)
    counts, receipts = trial.native_counts(folder)
    if counts != row["native_counts"] or receipts != row["native_receipts_sha256"]:
        raise ValueError(f"{ident} native receipts changed")
    if result["status"] == "ok" and (
        row["boundary_proof"] is None
        or set(result["arms"]) != set(ARMS)
        or not set(STAGES) <= result["metrics"]["stage_s"].keys()
        or not row["native_counts"]["calls"] > 0
        or row["worker_wall_s"] > row["cap_s"]
    ):
        raise ValueError(f"{ident} lacks its measured worker boundary")
    return row


def seal(plan_path, work, output):
    plan = common.read(plan_path)
    if plan["source"] != trial.source() or plan["cases"] != trial.select(trial.frozen_inputs()):
        raise ValueError("the bridge source or reserve roster changed")
    stock, ledger = trial.controls()
    if ledger != plan["compact_ledger"]:
        raise ValueError("the canonical compact source changed")
    pins = {ident: int(cpu) for cpu, lane in plan["lanes"].items() for ident in lane}
    common.roster_matches(pins, plan["cases"], "pinned plan")
    cold, archived, native = [], [], []
    source_sha = common.sha(plan_path)
    for ident in plan["cases"]:
        binding = plan["bindings"][ident]
        row = read_measurement(ident, pins[ident], binding, work / ident, source_sha)
        prior = stock[ident]
        common.require_fields(prior, {k: binding[k] for k in trial.MATCH})
        cold.append(row)
        archived.append(prior)
        for filename, digest in row.get("native_receipts_sha256", {}).items():
            path = work / ident / "receipts" / "native" / filename
            native.append(
                dict(
                    id=ident,
                    filename=filename,
                    sha256=digest,
                    receipt_json=path.read_bytes().decode("utf-8"),
                )
            )
    pack(output / POSITIONS, cold)
    pack(output / CONTROLS, archived)
    pack(output / NATIVE_RECEIPTS, native)
    write(output / "source-lock.json", plan_path.read_bytes())
    acted = [r for r in cold if r.get("worker_wall_s") is not None]
    finish = max(
        ((work / r["id"] / "measurement.json").stat().st_mtime_ns for r in acted),
        default=plan["locked_ns"],
    )
    save_json(
        output / "receipt.json",
        dict(
            cases=plan["cases"],
            files={
                name: common.sha(output / name)
                for name in (
                    POSITIONS,
                    CONTROLS,
                    NATIVE_RECEIPTS,
                )
            },
            source_lock_sha256=source_sha,
            controls=ledger,
            elapsed_to_last_measured_receipt_s=(finish - plan["locked_ns"]) / 1e9,
            planned=len(cold),
            measured=len(acted),
            statuses=dict(Counter(r["result"]["status"] for r in cold)),
        ),
    )


def stage_total(t, names):
    values = [t.get(k) for k in names]
    return sum(values) if all(x is not None for x in values) else None


def timing_row(row):
    metrics = row["result"]["metrics"]
    stages = metrics.get("stage_s", {})
    info = metrics.get("bridge_support", {})
    fresh = row["method"] == CANDIDATE
    wall = row.get("worker_wall_s") if fresh else compact_wall(row)
    return dict(
        id=row["id"],
        method=row["method"],
        status=row["result"]["status"],
        timing_origin="fresh" if fresh else row["source"],
        cpu=row.get("cpu"),
        full_worker_wall_s=wall,
        full_worker_cpu_s=row.get("worker_cpu_s"),
        native_preparation_s=stages.get("native_preparation"),
        initial_conservative_s=stage_total(stages, ("initial", "conservative")),
        late_family_signed_cavity_s=stage_total(stages, ("family", "signed", "cavity")),
        reclassification_s=info.get("reclassification_s"),
        stored_native_bound_calls=row.get("native_counts", {}).get("calls"),
        native_activation_calls=row.get("native_counts", {}).get("activated"),
        compact_projection_calls=metrics.get("compact_projections"),
        retained_points=metrics.get("center_bridge", {}).get("retained_points"),
        compact_optimizer_calls=metrics.get("position_optimizer", {}).get("calls"),
        **{f"{k}_s": stages.get(k) for k in STAGES if k != "native_preparation"},
    )


def geography(refs, candidate, stock):
    for ident, ref in refs.items():
        loc = ref["truth"]
        for arm in ARMS:
            original = ref["reference"]
            a = distance_km(original["baseline"][arm]["latlon"], loc)
            b = distance_km(stock[ident]["result"]["arms"][arm]["latlon"], loc)
            for name in (*ROLES, CANDIDATE, STOCK):
                if name in ROLES:
                    point = original[name][arm]
                    status = point["status"]
                else:
                    row = candidate[ident] if name == CANDIDATE else stock[ident]
                    point = row["result"]["arms"][arm]
                    status = row["result"]["status"]
                error = distance_km(point["latlon"], loc)
                yield dict(
                    id=ident,
                    dataset=ref["group"],
                    arm=arm,
                    method=name,
                    status=status,
                    error_km=error,
                    conditional_rms_hz=point.get("rf_rms_hz"),
                    delta_v5_km=error - a if error is not None else None,
                    delta_compact_km=error - b if error is not None else None,
                    **{
                        f"within_{limit}_of_{control}": common.paired_threshold(error, base, factor)
                        for control, base in (("v5", a), ("compact", b))
                        for limit, factor in RELATIVE
                    },
                )


def summarize(rows):
    result, pairs = [], {}
    for dataset in ("all", "DS26", "DS29"):
        subsets = rows if dataset == "all" else [r for r in rows if r["dataset"] == dataset]
        for method in (*ROLES, CANDIDATE, STOCK):
            by_arm = {
                a: [r for r in subsets if r["method"] == method and r["arm"] == a] for a in ARMS
            }
            tick = [
                f"within_{limit}_of_{base}" for base in ("v5", "compact") for limit, _ in RELATIVE
            ]
            passed = {
                key: set.intersection(
                    *[{r["id"] for r in group if r[key]} for group in by_arm.values()]
                )
                for key in tick
            }
            pairs[dataset, method] = {k: sorted(v) for k, v in passed.items()}
            for arm, group in by_arm.items():
                errors = [r["error_km"] for r in group]
                fixes = [r for r in group if r["error_km"] is not None]
                dist = distribution(errors)
                result.append(
                    dict(
                        dataset=dataset,
                        method=method,
                        arm=arm,
                        offered=len(group),
                        fixes=len(fixes),
                        median_km=dist["p50"],
                        p95_km=dist["p95"],
                        worst_km=dist["max"],
                        **{f"within_{k}km": v for k, v in thresholds(errors).items()},
                        **{k: sum(r[k] for r in group) for k in tick},
                        **{f"{k}_both": len(v) for k, v in passed.items()},
                    )
                )
    return result, [dict(dataset=d, method=m, cases=values) for (d, m), values in pairs.items()]


def tails(rows):
    def order(r):
        return (-r["delta_compact_km"], r["id"], r["arm"])

    candidate = [r for r in rows if r["method"] == CANDIDATE]
    ranked = sorted([r for r in candidate if r["delta_compact_km"] is not None], key=order)
    return dict(
        nonfixes=[r for r in candidate if r["error_km"] is None],
        largest_error={
            a: sorted([r for r in ranked if r["arm"] == a], key=lambda r: -r["error_km"])[:5]
            for a in ARMS
        },
        regressions_vs_compact=ranked[:8],
        audit=ranked[0] if ranked and ranked[0]["delta_compact_km"] >= MATERIAL_KM else None,
    )


def score(output):
    receipt = common.seal(output, "receipt.json", (POSITIONS, CONTROLS))
    if receipt["source_lock_sha256"] != common.sha(output / "source-lock.json"):
        raise ValueError("reserved scientific source seal changed")
    case_ids = receipt["cases"]
    refs, _ = _frozen_roof()
    refs = {i: refs[i] for i in case_ids}
    candidate, stock = [read_predictions(output / file) for file in (POSITIONS, CONTROLS)]
    for records in (candidate, stock):
        common.roster_matches(records, case_ids, "sealed reserve")
    rows = list(geography(refs, candidate, stock))
    summary, pairs = summarize(rows)
    csv_file(output / "scores.csv", rows)
    csv_file(output / "summary.csv", summary)
    csv_file(
        output / "timings.csv",
        [timing_row(r) for pack in (candidate, stock) for r in pack.values()],
    )
    save_json(
        output / "summary.json",
        dict(
            geography=summary,
            conditional_rms_hz={
                name: {
                    arm: distribution(
                        r["conditional_rms_hz"]
                        for r in rows
                        if r["method"] == name and r["arm"] == arm
                    )
                    for arm in ARMS
                }
                for name in (*ROLES, CANDIDATE, STOCK)
            },
            pairings=pairs,
        ),
    )
    save_json(output / "tails.json", tails(rows))
    files = ("scores.csv", "summary.csv", "timings.csv", "summary.json", "tails.json")
    save_json(
        output / "roof-lock.json",
        dict(
            cases=case_ids,
            source_lock_sha256=receipt["source_lock_sha256"],
            scorer_sha256=common.sha(Path(__file__)),
            files={**receipt["files"], **{n: common.sha(output / n) for n in files}},
        ),
    )
    save_json(
        output / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id=CHART,
                    method=CANDIDATE,
                    scope="roof",
                    cases=case_ids,
                    seal="roof-lock.json",
                    title="Unchanged whole-track bridge on 24 reserved roof recordings",
                    caption=(
                        "The same complete GLRT records, causal catalogue and original roof tile. "
                        "Every scheduled case is retained. Compact secant and original v5 "
                        "are archived controls."
                    ),
                    provenance=list(files),
                    source_lock=dict(file="source-lock.json", digest_key="source_lock_sha256"),
                    series=[
                        dict(
                            key="one",
                            label="Whole-track bridge · reserve",
                            value=CANDIDATE,
                            file=POSITIONS,
                        ),
                        dict(
                            key="stock",
                            label="Archived compact secant",
                            value=STOCK,
                            file=CONTROLS,
                            match=list(trial.MATCH),
                        ),
                    ],
                )
            ],
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    freeze = sub.add_parser("seal")
    freeze.add_argument("plan", type=Path)
    freeze.add_argument("work", type=Path)
    sub.add_parser("score")
    parser.add_argument("--out", type=Path, default=REPORT)
    args = parser.parse_args()
    out = local_output(args.out)
    if args.operation == "seal":
        seal(args.plan, args.work, out)
    else:
        score(out)


if __name__ == "__main__":
    main()
