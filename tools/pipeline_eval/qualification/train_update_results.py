"""Join sealed fixed-owner predictions to same-input joint and original v5 decisions."""

from collections import Counter

from ..__main__ import read_predictions, save_json, write
from ..scoring import ARMS, ROLES, distribution
from ..variants import train_update
from . import native_joint_full_results as original
from . import train_update_trial as trial
from .native_joint_results import geodata
from .prefix_figures import csv_file

phase = trial.phase
DIAGNOSTIC = {"DS26-0197", "DS26-0223", "DS29-0316"}


def matched(row, control):
    for field in (
        "id",
        "cohort",
        "recording",
        "tile",
        "input_sha256",
        "native_sha256",
        "catalog_sha256",
    ):
        if row[field] != control[field]:
            raise ValueError(f"different {field} in matched replays")
    both_ran = all(entry["result"]["status"] in {"ok", "withheld"} for entry in (row, control))
    digest = row.get("observation_sha256")
    if both_ran and (not digest or digest != control.get("observation_sha256")):
        raise ValueError("matched receivers did not consume identical anonymous Graph tracks")


def groups(rows):
    output = []
    for cohort in ("roof", "omitted"):
        for dataset in ("all", "DS26", "DS29"):
            for arm in ARMS:
                selected = [
                    r
                    for r in rows
                    if r["cohort"] == cohort
                    and r["arm"] == arm
                    and dataset in ("all", r["dataset"])
                ]
                part = dict(
                    cohort=cohort,
                    dataset=dataset,
                    arm=arm,
                    attempts=len(selected),
                    decisions=Counter(r["status"] for r in selected),
                    reason=Counter(r["reason"] for r in selected if r["reason"]),
                )
                for name in (
                    "error_km",
                    "stock_error_km",
                    "forced_error_km",
                    "conditional_rms_hz",
                    "held_score",
                    "worker_cpu_s",
                    "worker_wall_s",
                    "peak_rss_kib",
                    "stock_worker_cpu_s",
                    "stock_worker_wall_s",
                    "pooled_shift_km",
                    "training_exact_shift_km",
                ):
                    part[name] = distribution(r[name] for r in selected)
                part["new_publications"] = sum(
                    r["error_km"] is not None and r["stock_error_km"] is None for r in selected
                )
                part["lost_publications"] = sum(
                    r["error_km"] is None and r["stock_error_km"] is not None for r in selected
                )
                if cohort == "roof":
                    part["original"] = {
                        role: dict(
                            published_error=distribution(r[f"{role}_error_km"] for r in selected),
                            at_most_105pct=sum(
                                r["error_km"] is not None
                                and r["error_km"] <= 1.05 * r[f"{role}_error_km"]
                                for r in selected
                            ),
                            at_most_110pct=sum(
                                r["error_km"] is not None
                                and r["error_km"] <= 1.10 * r[f"{role}_error_km"]
                                for r in selected
                            ),
                        )
                        for role in ROLES
                    }
                output.append(part)
    return output


def diagnostic_split(rows):
    by_scope = {}
    for label, is_diagnostic in (("previously_inspected", True), ("other_roof", False)):
        subset = [r for r in rows if r["cohort"] == "roof" and r["diagnostic"] == is_diagnostic]
        by_scope[label] = [
            g for g in groups(subset) if g["cohort"] == "roof" and g["dataset"] == "all"
        ]
    return by_scope


def figures(output, predictions, lock, parent_lock):
    specs = []
    file = "joint-control.jsonl.gz"
    write(output / file, (trial.panel.REPORT / original.PREDICTIONS).read_bytes())
    if phase.digest(output / file) != parent_lock["files"][original.PREDICTIONS]:
        raise ValueError("joint control bytes differ from their prediction lock")
    for cohort, title in (
        ("roof", "Fixed training assignments on all 135 roof recordings"),
        ("omitted", "Fixed training assignments with the correct region omitted"),
    ):
        omitted = cohort == "omitted"
        cases = [ident for ident, row in predictions.items() if row["cohort"] == cohort]
        selector = dict(where=dict(cohort=cohort))
        chart = dict(
            id=f"native_train_update-{cohort}",
            method=train_update.METHOD,
            cases=cases,
            scope="transfer" if omitted else "roof",
            title=title,
            seal=f"{cohort}-figure-lock.json",
            caption=(
                "Both receivers rebuild tracks from identical native GLRT samples under a "
                "512 MiB address-space cap. The candidate fixes training assignments and "
                "adds the held tracks supported by those predictions."
            ),
            series=[
                dict(
                    key="candidate" if omitted else "one",
                    label="Predict then update",
                    file="positions.jsonl.gz",
                    value=train_update.METHOD,
                    **selector,
                ),
                dict(
                    key="stock",
                    label="Joint fit with pooled reassignment",
                    file=file,
                    value=trial.base.METHOD,
                    match=["input_sha256"],
                    **selector,
                ),
            ],
        )
        files = dict(lock["files"], **{file: phase.digest(output / file)})
        if omitted:
            chart["queries"] = "omitted-queries.json"
            name = chart["queries"]
            parent_figure = phase._read(trial.panel.REPORT / "omitted-figure-lock.json")
            trial.base.secant_full._verify_files(trial.panel.REPORT, parent_figure["files"])
            write(output / name, (trial.panel.REPORT / name).read_bytes())
            files[name] = phase.digest(output / name)
        save_json(output / chart["seal"], dict(cases=cases, files=files))
        specs.append(chart)
    save_json(output / "figures.json", dict(version=1, charts=specs))


def score(output):
    lock = phase._read(output / "prediction-lock.json")
    parent_lock = phase._read(trial.panel.REPORT / "prediction-lock.json")
    trial.base.secant_full._verify_files(output, lock["files"])
    trial.base.secant_full._verify_files(trial.panel.REPORT, parent_lock["files"])
    if lock["cases"] != parent_lock["cases"]:
        raise ValueError("candidate did not retain the entire reference roster")
    refs = {
        r["id"]: r for panel in ("ds26-common127", "roof16") for r in phase.corpus.references(panel)
    }
    source = trial.base.secant_full.REPORT
    trial.base.secant_full._verify_files(source, phase._read(source / "receipt.json")["files"])
    bindings = phase._read(source / "original-v5-inputs.json")
    predictions = read_predictions(output / "positions.jsonl.gz")
    controls = read_predictions(trial.panel.REPORT / original.PREDICTIONS)
    rows = []
    for ident in lock["cases"]:
        row, control = predictions[ident], controls[ident]
        matched(row, control)
        ref = refs[row["recording"]]
        truth, roof = ref["truth"], row["cohort"] == "roof"
        if (original.roi_margin(truth, row["tile"]) >= 0) != roof:
            raise ValueError("offered tile differs from its frozen condition")
        v5 = original.original_scores(ident, ref, bindings[ident], truth) if roof else {}
        for arm in ARMS:
            score_row = dict(
                id=ident,
                arm=arm,
                recording=row["recording"],
                dataset=ref["group"],
                cohort=row["cohort"],
                diagnostic=ident in DIAGNOSTIC,
                **geodata(row, arm, truth),
            )
            for key, value in geodata(control, arm, truth).items():
                score_row["stock_" + key] = value
            for key in (
                "pooled_shift_km",
                "training_exact_shift_km",
                "association_passes",
                "training_rows",
                "updated_held_rows",
            ):
                score_row[key] = row["result"]["metrics"].get(key)
            for role in ROLES:
                score_row[f"{role}_error_km"] = v5[role][arm][0] if roof else None
            rows.append(score_row)
    csv_file(output / "scores.csv", rows)
    save_json(
        output / "summary.json",
        dict(
            groups=groups(rows),
            diagnostic_split=diagnostic_split(rows),
            calibration=original.ablation(rows),
        ),
    )
    figures(output, predictions, lock, parent_lock)


if __name__ == "__main__":
    score(trial.REPORT)
