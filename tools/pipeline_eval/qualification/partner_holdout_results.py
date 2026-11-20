"""Verify and score the disjoint partner-on-hit holdout and pooled panels."""

import argparse
import gzip
from hashlib import sha256

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..scoring import ARMS, ROLES, distribution, validate_result
from . import one_lane_roster_results as one_results
from . import partner_holdout as cohort
from . import partner_on_hit_results as original
from . import screening_figures, staggered_benchmark
from .fresh_replay_results import sealed
from .full_held_scores import held_references
from .full_v5_check import _sha
from .partner_on_hit_trial import certificate, verify_request
from .phase_support_results import pack
from .prefix_figures import csv_file
from .staggered_reconstruction_results import original_rows
from .whole_pressure_trial import rows_from

REPORT = cohort.REPORT
METHODS, HIT, STOCK = original.METHODS, original.HIT, original.STOCK
read = whole_iq.read


def verified(work, plan, rows, proof, parents, audits, extensions):
    jobs = {r["id"]: r for r in plan["schedule"]}
    if len(rows) != len(jobs) or {r["id"] for r in rows} != set(plan["cases"]):
        raise ValueError("each holdout fit must remain visible exactly once")
    for row in rows:
        ident = row["id"]
        validate_result(row["result"])
        if any(row[k] != v for k, v in jobs[ident].items()):
            raise ValueError(f"{ident} changed its prespecified numerical input")
        folder = work / ident / HIT
        if read(folder / "attempt.json") != row:
            raise ValueError(f"{ident} differs from its actual worker receipt")
        native = whole_iq.checked(folder / "recording/native.json", row["native_sha256"])
        projected, witness = certificate(ident, parents, audits)
        if witness != proof[ident] or sha256(encoded(projected) + b"\n").hexdigest() != _sha(
            native
        ):
            raise ValueError(f"{ident} frozen packet selection did not reproduce")
        request = whole_iq.checked(
            folder / "recording/request.json", row["prepared_request_sha256"]
        )
        with cohort.binding_context(ident, extensions):
            _, archived = whole_iq.binding(ident)
        verify_request(
            read(request), archived, native_path=native, native_sha256=row["native_sha256"]
        )
        sample = row.get("position_resources") or {}
        if row["terminal"] == "success" and (
            not sample or row["result"]["metrics"]["observations"] != witness["observations"][HIT]
        ):
            raise ValueError("post-detector solve has inconsistent resource or input observations")
        for stage in ("start", "end"):
            if sample and (
                sample[stage]["cpus"] != [row["cpu"]]
                or sample[stage]["nice"] != 10
                or sample[stage]["memory.max"] != plan["memory_bytes"]
                or sample[stage]["memory.swap.max"] != 0
                or sample[stage]["memory.swap.current"] != 0
            ):
                raise ValueError("system service was outside the frozen resource assignment")
        log = whole_iq.checked(folder / "service.log", row["log_sha256"])
        write(REPORT / "logs" / f"{ident}.log.gz", gzip.compress(log.read_bytes(), mtime=0))


def references(cases):
    authority, original_v5 = staggered_benchmark.fresh_references()
    spec, extra = staggered_benchmark.export_references(
        REPORT, "paired", cases, authority, original_v5
    )
    _, old = held_references(None, [ident for ident in cases if ident not in extra])
    for row in original_v5:
        if row["id"] not in extra:
            continue
        ref = extra[row["id"]]["reference"][row["method"]]
        for arm in ARMS:
            result = row["result"].get("arms", {}).get(arm, {})
            ref[arm].update(latlon=result.get("latlon"), rf_rms_hz=result.get("rf_rms_hz"))
    return spec, {r["id"]: r for r in old} | extra


def paired_scores(rows, refs, proof, groups):
    data = one_results.comparisons(rows, refs)
    results = {(r["id"], r["method"]): r for r in rows}
    index = {(r["id"], r["arm"], r["method"]): r for r in data}
    effects = []
    for row in data:
        ident, method = row["id"], row["method"]
        source = results[ident, method]["result"]
        row.update(
            cohort="holdout" if ident in groups["holdout"] else "discovery",
            observations=source["metrics"].get("observations"),
            tracks=source["metrics"].get("tracks"),
            scheduled_calls=proof[ident]["calls"][method],
            predicted_gated_probes=proof[ident]["observations"][method],
        )
    for ident in groups["pooled"]:
        for arm in ARMS:
            for metric in ("error_km", "rf_rms_hz", "tracks"):
                values = [index[ident, arm, method][metric] for method in METHODS]
                effects.append(
                    dict(
                        id=ident,
                        arm=arm,
                        measure=metric,
                        cohort=index[ident, arm, HIT]["cohort"],
                        **dict(zip(METHODS, values, strict=True)),
                        **original.effects(*values),
                    )
                )
    return data, effects


def summarize(data, effects, refs, groups):
    receiver_summary, paired = [], []
    for label, cases in groups.items():
        for arm in ARMS:
            group = [r for r in data if r["id"] in cases and r["arm"] == arm]
            for method in (*METHODS, *ROLES):
                base = cohort.trial.fixed.summary_row(group, cases, label, arm, method)
                selected = [r for r in group if r["method"] == method]
                rf = distribution(
                    [r["rf_rms_hz"] for r in selected]
                    if method in METHODS
                    else [refs[i]["reference"][method][arm].get("rf_rms_hz") for i in cases]
                )
                receiver_summary.append(
                    dict(
                        base,
                        conditional_rf_count=rf["n"],
                        median_rf_rms_hz=rf["p50"],
                        at_most_5pct_above_stock=sum(
                            r["at_most_5pct_above_stock"] for r in selected
                        )
                        if selected
                        else None,
                        at_most_10pct_above_stock=sum(
                            r["at_most_10pct_above_stock"] for r in selected
                        )
                        if selected
                        else None,
                    )
                )
            for metric in ("error_km", "rf_rms_hz", "tracks"):
                matches = [
                    r
                    for r in effects
                    if r["id"] in cases and r["arm"] == arm and r["measure"] == metric
                ]
                for name in original.CONTRASTS:
                    values = [r[name] for r in matches if r[name] is not None]
                    dist = distribution(values)
                    paired.append(
                        dict(
                            cohort=label,
                            arm=arm,
                            measure=metric,
                            contrast=name,
                            scheduled=len(cases),
                            paired=dist["n"],
                            improved=sum(v < 0 for v in values),
                            median=dist["p50"],
                            min=dist["min"],
                            max=dist["max"],
                        )
                    )
    return receiver_summary, paired


def resources(rows, held):
    output = []
    for row in rows:
        stat = row.get("position_resources") or {}
        output.append(
            dict(
                id=row["id"],
                cohort="holdout" if row["id"] in held else "discovery",
                cpu=row["cpu"],
                terminal=row["terminal"],
                status=row["result"]["status"],
                position_wall_s=stat.get("wall_s"),
                position_cpu_s=stat.get("cpu_s"),
                peak_bytes=stat.get("peak_bytes"),
                swap_bytes=stat.get("end", {}).get("memory.swap.current"),
                supervisor_wall_s=row.get("supervisor_wall_s"),
                detector_wall_s=None,
            )
        )
    return output


def figures(rows, groups, roof):
    charts = []
    for label, title in (
        ("holdout", "Partner-on-hit on fourteen untouched roof recordings"),
        ("pooled", "Partner-on-hit across all twenty-two fixed-four recordings"),
    ):
        cases = groups[label]
        name, lock = f"{label}-matched-positions.jsonl.gz", f"{label}-figure-lock.json"
        pack(REPORT / name, [r for r in rows if r["id"] in cases])
        source = (
            "prediction-lock.json",
            "scores.csv",
            "effects.csv",
            "effects-summary.csv",
            "summary.csv",
            "resources.csv",
            "support.csv",
            "capture-era-v5.csv",
            *roof.values(),
        )
        save_json(
            REPORT / lock, dict(cases=cases, files={n: _sha(REPORT / n) for n in (name, *source)})
        )
        note = (
            "The holdout excludes all eight discovery recordings."
            if label == "holdout"
            else "The unchanged eight discovery endpoints are pooled with fourteen new fits."
        )
        charts.append(
            dict(
                id=f"partner-on-hit-confirmation-{label}",
                method=HIT,
                scope="roof",
                cases="sealed",
                seal=lock,
                title=title,
                roof_references=roof,
                provenance=list(source),
                caption=f"{note} All four antenna policies use the same stored fixed-four body. "
                "Elapsed times apply to post-detector fits.",
                series=[
                    dict(
                        key=key,
                        label=description,
                        file=name,
                        value=method,
                        native_field="paired_capture_sha256",
                        match=[*cohort.trial.fixed.BINDINGS, "stock_native_sha256"],
                    )
                    for key, method, description in zip(
                        ("one_native_factors", "one", "all_visits", "stock"),
                        METHODS,
                        original.LABELS,
                        strict=True,
                    )
                ],
            )
        )
    save_json(REPORT / "figures.json", dict(version=2, charts=charts))


def publish(work):
    lock = sealed(REPORT, "prediction-lock.json")
    plan, proof = (read(REPORT / k) for k in ("plan.json", "packet-audit.json"))
    holdout, pooled, bindings, parents, audits, _, extensions, discovery, old_proof = (
        cohort.authority()
    )
    if (
        plan["cases"] != holdout
        or plan["pooled"] != pooled
        or plan["parents"] != bindings
        or lock["cases"] != pooled
        or lock["holdout"] != holdout
        or any(_sha(ROOT / n) != d for n, d in plan["sources"].items())
        or any(proof[k] != v for k, v in old_proof.items())
    ):
        raise ValueError("a frozen case, parent, procedure or discovery input changed")
    held = rows_from(REPORT / "holdout-predictions.jsonl.gz")
    all_candidates = rows_from(REPORT / "positions.jsonl.gz")
    if sorted(discovery + held, key=lambda row: row["id"]) != all_candidates:
        raise ValueError("pooled rows must preserve the exact holdout and discovery results")
    verified(work, plan, held, proof, parents, audits, extensions)
    groups = {"holdout": holdout, "pooled": pooled, "discovery": list(cohort.trial.CASES)}
    rows = all_candidates + [
        dict(parents[method][ident], stock_native_sha256=parents[STOCK][ident]["native_sha256"])
        for method in METHODS
        if method != HIT
        for ident in pooled
    ]
    roof, refs = references(pooled)
    scores, effects = paired_scores(rows, refs, proof, groups)
    summary, effects_summary = summarize(scores, effects, refs, groups)
    support = [
        dict(
            id=k,
            **{a: b for a, b in r.items() if isinstance(b, int)},
            **{f"{m}_calls": r["calls"][m] for m in METHODS},
            **{f"{m}_observations": r["observations"][m] for m in METHODS},
        )
        for k, r in sorted(proof.items())
    ]
    for name, data in (
        ("support.csv", support),
        ("scores.csv", scores),
        ("effects.csv", effects),
        ("summary.csv", summary),
        ("effects-summary.csv", effects_summary),
        ("capture-era-v5.csv", original_rows(refs, parents[STOCK])),
        ("resources.csv", resources(all_candidates, holdout)),
    ):
        csv_file(REPORT / name, data)
    figures(rows, groups, roof)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--plot", type=local_output)
    args = parser.parse_args()
    publish(args.work)
    if args.plot:
        screening_figures.generate(args.plot, evidence=REPORT)
