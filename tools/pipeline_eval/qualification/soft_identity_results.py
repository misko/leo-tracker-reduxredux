"""Score the matched native soft-mixture challenge and prepare standard plots."""

import argparse
from collections import Counter
from pathlib import Path

from ..__main__ import read_predictions, save_json
from ..scoring import ARMS, ROLES, distribution, thresholds, validate_result
from ..variants import soft_identity
from . import native_joint_full_results as shared
from . import soft_identity_trial as trial

phase = trial.base.phase
COMPARISON = "exact-control-positions.jsonl.gz"
OUTCOMES = "paired-positions.jsonl.gz"


def paired(predictions, plan):
    archive_path = trial.base.panel.REPORT / "prediction-lock.json"
    if phase.digest(archive_path) != plan["native_joint_lock_sha256"]:
        raise ValueError("the independently sealed joint control lock changed")
    receipt = phase._read(archive_path)
    trial.base.base.secant_full._verify_files(archive_path.parent, receipt["files"])
    archive = read_predictions(archive_path.parent / shared.PREDICTIONS)
    matched = {}
    for ident, row in predictions.items():
        if "control_result" not in row:
            control = row["result"]
        else:
            control = row["control_result"]
            validate_result(control)
            if ident in archive:
                old = archive[ident]
                fields = ("input_sha256", "native_sha256", "catalog_sha256",
                          "observation_sha256", "tile", "counts")
                if any(row[k] != old[k] for k in fields):
                    raise ValueError(f"{ident} rebuilt a different Graph than the exact control")
                if any(control[k] != old["result"][k] for k in ("status", "reason", "arms")):
                    raise ValueError(f"{ident} does not reproduce the independent exact control")
        meta = {k: v for k, v in row.items() if k not in ("result", "control_result")}
        matched[ident] = dict(meta, method=trial.CONTROL, result=control)
    return matched


def classify(predictions, plan):
    memberships = {i: c for c, ids in plan["challenge"].items() for i in ids}
    return {
        ident: dict(row, study_cohort=memberships.get(ident, row["cohort"]))
        for ident, row in predictions.items()
    }


def scores(candidate, control, plan):
    rows, queries = shared.matched_score_rows(candidate, plan, solver_stage="compared_backends")
    truth = {
        r["id"]: r["truth"] for panel in ("ds26-common127", "roof16")
        for r in phase.corpus.references(panel)
    }
    for row in rows:
        current, old = candidate[row["id"]], control[row["id"]]
        point = truth[row["recording"]]
        current_held = current["result"]["metrics"].get("held_by_arm", {}).get(row["arm"], {})
        stock = shared.geodata(old, row["arm"], point)
        row.update(
            study_cohort=current["study_cohort"],
            control_status=stock["status"], control_error_km=stock["error_km"],
            control_fit_rms_hz=stock["conditional_rms_hz"],
            held_rf_rms_hz=current_held.get("rf_rms_hz"),
            held_curved_orbits=current_held.get("held_orbits"),
            soft_backend_wall_s=current.get("soft_backend", {}).get("wall_s"),
            control_backend_wall_s=current.get("control_backend", {}).get("wall_s"),
            optimizer_evals=current["result"]["metrics"].get("optimizer", {}).get(
                row["arm"], {}
            ).get("evaluations"),
        )
    return rows, queries


def groups(rows, *, full):
    subsets = {r["study_cohort"] for r in rows}
    output = []
    for cohort in sorted(subsets | ({"all_roof"} if full else set())):
        for arm in ARMS:
            group = [r for r in rows if r["arm"] == arm and (
                r["cohort"] == "roof" if cohort == "all_roof" else r["study_cohort"] == cohort
            )]
            published = [
                (r["error_km"], r["control_error_km"]) for r in group
                if r["error_km"] is not None and r["control_error_km"] is not None
            ]
            output.append(dict(
                cohort=cohort, arm=arm, scheduled=len(group),
                soft_status=dict(Counter(r["status"] for r in group)),
                soft_withheld_reasons=dict(Counter(
                    r["reason"] for r in group if r["status"] == "withheld"
                )),
                control_status=dict(Counter(r["control_status"] for r in group)),
                held_gate_satisfied=sum(
                    r["held_score"] is not None and r["held_score"] >= 0.28
                    and r["held_curved_orbits"] is not None and r["held_curved_orbits"] >= 2
                    for r in group
                ),
                published_errors_above_radius=sum(
                    r["error_km"] is not None and r["radius_km"] is not None
                    and r["error_km"] > r["radius_km"] for r in group
                ),
                soft_within_km=thresholds([r["error_km"] for r in group]),
                control_within_km=thresholds([r["control_error_km"] for r in group]),
                paired_accuracy=phase._pair_summary(published),
                measures={k: distribution(r[k] for r in group) for k in (
                    "error_km", "control_error_km", "conditional_rms_hz", "control_fit_rms_hz",
                    "held_score", "held_rf_rms_hz", "held_curved_orbits",
                    "soft_backend_wall_s", "control_backend_wall_s", "optimizer_evals",
                    "worker_wall_s", "peak_rss_kib",
                )},
                originals={role: distribution(r[f"{role}_error_km"] for r in group)
                           for role in ROLES},
            ))
    return output


def promotion(rows, summary):
    prospective = [g["paired_accuracy"] for g in summary if g["cohort"] == "reserve"]
    return (
        len(prospective) == 2 and all(
            g["pairs"] >= 5 and g["error_difference_km"]["p50"] <= 0 for g in prospective
        )
        and all(r["status"] != "ok" for r in rows if r["cohort"] == "omitted")
    )


def render_specs(output, candidate, queries, lock, digest, *, full):
    chart_groups = ("all_roof", "omitted") if full else ("diagnostic", "reserve", "omitted")
    specs = []
    for cohort in chart_groups:
        omitted = cohort == "omitted"
        where = dict(cohort="roof") if cohort == "all_roof" else dict(study_cohort=cohort)
        cases = [i for i, row in candidate.items() if all(row[k] == v for k, v in where.items())]
        suffix = "full-" if full else ""
        slug = "all-roof" if cohort == "all_roof" else cohort
        subject = {
            "diagnostic": "two diagnostics", "reserve": "eight reserved roof recordings",
            "all_roof": "135 roof recordings", "omitted": "omitted offers",
        }[cohort]
        files = {OUTCOMES: digest}
        item = dict(
            id=f"native_soft_identity-{suffix}{slug}", method=soft_identity.METHOD,
            scope="transfer" if omitted else "roof", cases=cases,
            title=f"Soft orbit identity on {subject}",
            caption="Both receivers read the same complete archived native Graph. "
            "The soft receiver estimates shared state only on training tracks and "
            "scores held tracks before publishing. Forced coordinates are diagnostic.",
            seal=f"{cohort}-figure-lock.json",
            source_lock=dict(file="plan.json", digest_key="plan_sha256"),
            series=[
                dict(key="candidate" if omitted else "one", label="Soft orbit mixture",
                     file=OUTCOMES, value=soft_identity.METHOD, where=where),
                dict(key="stock", label="Exact joint receiver", file=OUTCOMES, value=trial.CONTROL,
                     where=where, match=["input_sha256", "native_sha256", "catalog_sha256"]),
            ],
        )
        if all(candidate[i].get("observation_sha256") for i in cases):
            item["series"][1]["match"].append("observation_sha256")
        if omitted:
            name = "omitted-queries.json"
            save_json(output / name, dict(queries=queries))
            files[name] = phase.digest(output / name)
            item["queries"] = name
            for curve in item["series"]:
                curve["forced_label"] = f'{curve["label"]} forced diagnostic'
        save_json(output / item["seal"], dict(
            cases=cases, files=files, plan_sha256=lock["files"]["plan.json"],
        ))
        specs.append(item)
    save_json(output / "figures.json", dict(version=1, charts=specs))


def score(work, bundle, output, *, full=False):
    shared.seal(
        work, bundle, output, prepare=lambda path: trial.prepare(path, full=full),
        method=soft_identity.METHOD, fail=trial.base.failed,
    )
    lock = phase._read(output / "prediction-lock.json")
    plan = phase._read(output / "plan.json")
    candidate = classify(read_predictions(output / shared.PREDICTIONS), plan)
    control = paired(candidate, plan)
    rows, queries = scores(candidate, control, plan)
    summary = groups(rows, full=full)
    zero = {r["id"]: r["held_rf_rms_hz"] for r in rows if r["arm"] == "c0"}
    rf_c = distribution(
        r["held_rf_rms_hz"] - zero[r["id"]] for r in rows
        if r["cohort"] == "roof" and r["arm"] == "fitted_c"
        and r["held_rf_rms_hz"] is not None and zero[r["id"]] is not None
    )
    shared.csv_file(output / "scores.csv", rows)
    digest = shared.pack(output, OUTCOMES, [*candidate.values(), *control.values()])
    shared.pack(output, COMPARISON, control.values())
    save_json(output / "summary.json", dict(
        replay=lock["run"], comparisons=summary, c_ablation=shared.ablation(rows),
        held_rf_c_ablation=rf_c, promotes=promotion(rows, summary), paired_positions_sha256=digest,
    ))
    render_specs(output, candidate, queries, lock, digest, full=full)


if __name__ == "__main__":
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--work", type=Path, default=trial.WORK)
    args.add_argument("--bundle", type=Path, default=trial.base.base.BUNDLE)
    args.add_argument("--output", type=Path, default=trial.REPORT)
    args.add_argument("--full", action="store_true")
    settings = args.parse_args()
    score(settings.work, settings.bundle, settings.output, full=settings.full)
