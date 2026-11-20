"""Score the sealed native clock/offset models and format standard figures."""

import argparse
from collections import Counter
from pathlib import Path

from ..__main__ import read_predictions, save_json
from ..scoring import ARMS, ROLES, distribution, thresholds, validate_result
from ..variants import clock_offset as model
from . import clock_offset_trial as trial
from . import native_joint_full_results as shared

phase = trial.base.phase
ALL = "all-model-positions.jsonl.gz"
METHODS = tuple(model.MODES)
FULL_ROOF_OVERLAY = "native_clock_offset-full-all-roof"
MODEL_ROOF_IDS = tuple(f"{method}-full-roof" for method in METHODS)
METRICS = (
    "error_km", "conditional_rms_hz", "fit_conditional_rf_rms_hz", "raw_held_rf_rms_hz",
    "conditional_held_rf_rms_hz", "held_deviance_per_point", "final_fit_wall_s",
)


def _models(containers, ids):
    result = {method: {} for method in METHODS}
    for ident, row in containers.items():
        if row["result"]["status"] in ("ok", "withheld"):
            held, owner = [], []
            variants = row["models"]
            if set(variants) != set(METHODS):
                raise ValueError("all four models must consume the same native request")
            for info in variants.values():
                validate_result(info)
                metrics = info["metrics"]
                owner.append(tuple(
                    metrics[k]["sha256"] if metrics[k] else None
                    for k in ("training_ownership", "held_prefix_ownership", "final_ownership")
                ))
                held.append(tuple(
                    metrics["conditional_held_by_arm"].get(arm, {}).get("held_points")
                    for arm in ARMS
                ))
            if len(set(owner)) != 1 or len(set(held)) != 1 or held[0][0] != held[0][1]:
                raise ValueError(f"{ident} changed native model or c-ablation support")
        else:
            variants = dict.fromkeys(METHODS, row["result"])
        cohort = next((k for k, values in ids.items() if ident in values), row["cohort"])
        for name, info in variants.items():
            public = {key: value for key, value in row.items() if key not in ("models", "result")}
            result[name][ident] = dict(
                public, result=info, method=name, study_cohort=cohort,
            )
    return result


def rows_by_method(models, plan):
    rows, queries = [], []
    for method, predictions in models.items():
        group, offers = shared.matched_score_rows(
            predictions, plan, solver_stage="nuisance_backend",
        )
        if not queries:
            queries = offers
        for row in group:
            entry = predictions[row["id"]]
            metrics, arm = entry["result"]["metrics"], row["arm"]
            predictive = metrics.get("conditional_held_by_arm", {}).get(arm, {})
            fitted = metrics.get("final_model", {}).get(arm, {})
            row.update(
                method=method, study_cohort=entry["study_cohort"],
                fit_conditional_rf_rms_hz=fitted.get("fit_conditional_rf_rms_hz"),
                final_fit_wall_s=metrics.get("final_fit_wall_s"),
                held_points=predictive.get("held_points"),
                **{k: predictive.get(k) for k in (
                    "raw_held_rf_rms_hz", "conditional_held_rf_rms_hz",
                    "held_deviance_per_point",
                )},
            )
        rows.extend(group)
    return rows, queries


def _groups(rows):
    groups = sorted({r["study_cohort"] for r in rows})
    return [*groups, "all_roof"] if "roof" in groups else groups


def _in_group(row, cohort):
    return row["cohort"] == "roof" if cohort == "all_roof" else row["study_cohort"] == cohort


def summarize(rows):
    summaries = []
    for cohort in _groups(rows):
        for method in METHODS:
            selected = [r for r in rows if _in_group(r, cohort) and r["method"] == method]
            for arm in ARMS:
                group = [r for r in selected if r["arm"] == arm]
                summaries.append(dict(
                    cohort=cohort, method=method, arm=arm,
                    statuses=dict(Counter(r["status"] for r in group)),
                    within_km=thresholds([r["error_km"] for r in group]),
                    metrics={k: distribution(r[k] for r in group) for k in METRICS},
                    original={role: distribution(r[f"{role}_error_km"] for r in group)
                              for role in ROLES},
                ))
    return summaries


def compare(rows):
    indexed = {(r["id"], r["method"], r["arm"]): r for r in rows}
    reports = []
    pairs = [(a, b) for a in METHODS[:2] for b in METHODS[2:]]
    for candidate, control in [*pairs, (METHODS[1], METHODS[0])]:
        for cohort in _groups(rows):
            for arm in ARMS:
                current = [r for r in rows if _in_group(r, cohort)
                           and r["method"] == candidate and r["arm"] == arm]
                paired = [(r, indexed[r["id"], control, arm]) for r in current]
                deltas = {
                    k: [a[k] - b[k] for a, b in paired if a[k] is not None and b[k] is not None]
                    for k in METRICS
                }
                reports.append(dict(
                    cohort=cohort, candidate=candidate, control=control, arm=arm,
                    paired_deltas={k: distribution(v) for k, v in deltas.items()},
                    lower={k: sum(x < 0 for x in v) for k, v in deltas.items()},
                ))
    return reports


def promote(rows, pair_results):
    verdict = {}
    for method in METHODS[:2]:
        evidence = [
            r["paired_deltas"] for r in pair_results
            if r["candidate"] == method and r["cohort"] == "reserve" and r["control"] in METHODS[2:]
        ]
        verdict[method] = len(evidence) == 4 and all(
            r["error_km"]["n"] >= 4 and r["error_km"]["p50"] <= 0
            and r["held_deviance_per_point"]["n"] == 6 and r["held_deviance_per_point"]["p50"] < 0
            for r in evidence
        ) and all(
            r["status"] != "ok" for r in rows if r["study_cohort"] == "omitted"
            and r["method"] == method
        )
    return verdict


def calibration(rows):
    zero = {(r["id"], r["method"]): r for r in rows if r["arm"] == "c0"}
    return {
        method: {
            k: distribution(
                r[k] - zero[r["id"], method][k] for r in rows
                if r["cohort"] == "roof" and r["method"] == method and r["arm"] == "fitted_c"
                and r[k] is not None and zero[r["id"], method][k] is not None
            ) for k in METRICS[:-1]
        } for method in METHODS
    }


def with_model_roofs(specs):
    """Add one sealed roof chart per model while keeping the matched overlay."""
    overlays = [spec for spec in specs if spec["id"] == FULL_ROOF_OVERLAY]
    if len(overlays) != 1:
        raise ValueError("expected the single sealed full-roof clock/offset overlay")
    (overlay,) = overlays
    curves = {curve["value"]: curve for curve in overlay["series"]}
    if set(curves) != set(METHODS):
        raise ValueError("the full-roof overlay does not cover all four clock/offset models")
    result = [spec for spec in specs if spec["id"] not in MODEL_ROOF_IDS]
    for method, chart_id in zip(METHODS, MODEL_ROOF_IDS, strict=True):
        primary = dict(curves[method], key="one")
        primary.pop("match", None)
        result.append(dict(
            overlay, id=chart_id, method=method, cases="roof135",
            title=f'{primary["label"]} on 135 matched roof recordings',
            caption="Complete native factors and the causal catalogue. The four original v5 "
            "controls use the same 135 recordings. Forced positions are diagnostic.",
            series=[primary],
        ))
    return result


def publish_model_roofs(output):
    manifest = output / "figures.json"
    current = phase._read(manifest)
    save_json(manifest, dict(current, charts=with_model_roofs(current["charts"])))


def figures(output, groups, queries, lock, sealed, *, full):
    labels = ("Clock + offset, OU", "Clock + offset, diagonal", "Clock only, OU", "Offset only, OU")
    specs = []
    for group, cases in groups.items():
        omitted = group == "omitted"
        keys = ("candidate", "stock", "one", "four") if omitted else (
            "one", "stock", "one_native_factors", "all_visits"
        )
        where = dict(cohort="roof") if group == "all_roof" else dict(study_cohort=group)
        series = [
            dict(key=key, label=label, file=ALL, value=name, where=where)
            for key, label, name in zip(keys, labels, METHODS, strict=True)
        ]
        fields = ["input_sha256", "native_sha256", "catalog_sha256"]
        for item in series[1:]:
            item["match"] = fields
        receipt = {ALL: sealed}
        chart_id = "all-roof" if group == "all_roof" else group
        title = "135 roof" if group == "all_roof" else group
        spec = dict(
            id=f"native_clock_offset-{'full-' if full else ''}{chart_id}", method=model.METHOD,
            cases=cases, scope="transfer" if omitted else "roof",
            title=f"Joint receiver clock and component offsets on {title} offers",
            caption="Four exact final fits share the anonymous native owners, aliases and "
            "first-fit gate. Forced coordinates are diagnostic.",
            seal=f"{group}-figure-lock.json",
            source_lock=dict(file="plan.json", digest_key="plan_sha256"), series=series,
        )
        if omitted:
            qname = "omitted-queries.json"
            save_json(output / qname, dict(queries=queries))
            receipt[qname] = phase.digest(output / qname)
            spec["queries"] = qname
            for item, label in zip(series, labels, strict=True):
                item["forced_label"] = f"{label} forced diagnostic"
        save_json(output / spec["seal"], dict(
            cases=cases, files=receipt, plan_sha256=lock["files"]["plan.json"],
        ))
        specs.append(spec)
    save_json(output / "figures.json", dict(
        version=1, charts=with_model_roofs(specs) if full else specs,
    ))


def score(work, bundle, output, *, full=False):
    shared.seal(
        work, bundle, output, prepare=lambda path: trial.prepare(path, full=full),
        method=model.METHOD, fail=trial.base.failed,
    )
    lock = phase._read(output / "prediction-lock.json")
    plan = phase._read(output / "plan.json")
    selected = read_predictions(output / shared.PREDICTIONS)
    models = _models(selected, plan["challenge"])
    rows, queries = rows_by_method(models, plan)
    pairs = compare(rows)
    verdict = promote(rows, pairs)
    groups = {
        g: [i for i, row in models[model.METHOD].items() if row["study_cohort"] == g]
        for g in sorted({r["study_cohort"] for r in rows}) if g != "roof"
    }
    if full:
        groups = dict(
            all_roof=[i for i, row in models[model.METHOD].items() if row["cohort"] == "roof"],
            omitted=groups["omitted"],
        )
        previous = plan["challenge"]["first"] + plan["challenge"]["reserve"]
        if any(i not in selected for i in previous):
            raise ValueError("complete native roster lost a challenge case")
    data = [row for records in models.values() for row in records.values()]
    digest = shared.pack(output, ALL, data)
    shared.csv_file(output / "scores.csv", rows)
    save_json(output / "summary.json", dict(
        replay=lock["run"], groups=summarize(rows), comparisons=pairs,
        c_ablation=calibration(rows), promotion=verdict, chart_archive_sha256=digest,
    ))
    figures(output, groups, queries, lock, digest, full=full)


if __name__ == "__main__":
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--work", type=Path, default=trial.WORK)
    args.add_argument("--bundle", type=Path, default=trial.base.base.BUNDLE)
    args.add_argument("--output", type=Path, default=trial.REPORT)
    args.add_argument("--full", action="store_true")
    args.add_argument("--figures-only", action="store_true")
    opts = args.parse_args()
    if opts.figures_only:
        publish_model_roofs(opts.output)
    else:
        score(opts.work, opts.bundle, opts.output, full=opts.full)
