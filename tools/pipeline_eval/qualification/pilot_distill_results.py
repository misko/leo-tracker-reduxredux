"""Score the sealed pilot replay and write its standard receiver figures."""

import argparse
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json
from ..scoring import ARMS, ROLES, distance_km, distribution
from . import pilot_distill_trial as trial
from . import screening_figures, staggered_benchmark
from .fresh_replay_results import sealed
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack, records
from .prefix_figures import csv_file

REPORT = trial.REPORT
LABELS = {
    "stock": "Ordinary stock gate",
    "learned": "Distilled gate",
    "strength": "Strongest margin, same count",
    "oracle": "Attainable teacher-family oracle",
}
COLORS = dict(stock="#a65a12", learned="#087568", strength="#3e798c", oracle="#664a87")
GROUPS = {"narrow": trial.HELD, "wide": trial.SUPPLEMENT}
MEASURED_STAGES = ("native_preparation", "initial", "conservative", "family", "signed", "cavity")


def references(report, cases):
    authority, recent = staggered_benchmark.fresh_references()
    spec, extended = staggered_benchmark.export_references(report, "wide", cases, authority, recent)
    for row in recent:
        if row["id"] not in extended:
            continue
        for arm in ARMS:
            fit = extended[row["id"]]["reference"][row["method"]][arm]
            fit.update(row["result"]["arms"][arm])
    _, frozen = held_references(None, [ident for ident in cases if ident not in extended])
    return {row["id"]: row for row in frozen} | extended, spec


def compare(rows, refs):
    positions, controls = [], []
    for row in rows:
        ident = row["id"]
        result = row["result"]
        ref = refs[ident]
        for arm, fit in result["arms"].items():
            error = distance_km(ref["truth"], fit["latlon"])
            baseline = ref["reference"]["baseline"][arm]["error_km"]
            comparable = baseline is not None and error is not None
            positions.append(
                dict(
                    id=ident,
                    method=row["condition"],
                    detector_range=row["detector_range"],
                    calibration=arm,
                    status=result["status"],
                    reason=result.get("reason"),
                    error_km=error,
                    original_v5_error_km=baseline,
                    pct_above_v5=100 * (error / baseline - 1) if comparable and baseline else None,
                    within_5pct=comparable and error <= 1.05 * baseline,
                    within_10pct=comparable and error <= 1.10 * baseline,
                    rf_rms_hz=fit.get("rf_rms_hz"),
                    frequency_score=result["metrics"].get(f"{arm}_frequency_score"),
                )
            )
        if row["condition"] == "stock":
            for role in ROLES:
                for arm in ARMS:
                    endpoint = ref["reference"][role][arm]
                    controls.append(
                        dict(
                            id=ident,
                            role=role,
                            calibration=arm,
                            status=endpoint["status"],
                            error_km=endpoint["error_km"],
                            rf_rms_hz=endpoint.get("rf_rms_hz"),
                            historical_wall_s=endpoint.get("wall_s"),
                        )
                    )
    return positions, controls


def rf_agreement(plan, amendment):
    rows = []
    for ids in GROUPS.values():
        for ident in ids:
            stage = plan[ident]
            counts = stage["counts"]
            definite = counts["shareable"]
            negatives = counts["teacher_negative"]
            positive = counts["probes"] - negatives
            for method in trial.METHODS:
                attainable = amendment.get(ident, {}).get("eligible", definite)
                census = stage["agreements"].get(method) or {
                    "admitted": attainable,
                    "correct_family": attainable,
                    "admitted/shareable": attainable,
                }
                correct = census["correct_family"]
                false = census.get("admitted/teacher_negative", 0)
                rows.append(
                    dict(
                        id=ident,
                        detector_range=stage["binding"]["detector_range"],
                        method=method,
                        probes=counts["probes"],
                        fast_candidates=counts["fast_candidates"],
                        duplicate_fast_members=counts["duplicate_fast_members"],
                        teacher_positive=positive,
                        teacher_negative=negatives,
                        shareable=definite,
                        solver_eligible_shareable=attainable,
                        ambiguous=counts.get("ambiguous", 0),
                        no_roster_match=counts.get("no_roster_match", 0),
                        no_winner_member_match=counts.get("no_winner_member_match", 0),
                        admitted=census["admitted"],
                        admitted_on_shareable=census.get("admitted/shareable", 0),
                        admitted_on_teacher_negative=false,
                        correct_family=correct,
                        shareable_recall=correct / definite,
                        all_teacher_positive_family_recall=correct / positive,
                        teacher_negative_admission_rate=false / negatives,
                    )
                )
    return rows


def resource_rows(results):
    bound = sealed(trial.BAND, "prediction-lock.json")
    raw = whole_iq.read(trial.BAND / "resources.json")
    if "resources.json" not in bound["files"]:
        raise ValueError("raw measurements need their earlier authority")
    return [
        dict(
            id=row["id"],
            method=row["condition"],
            detector_range=row["detector_range"],
            status=row["result"]["status"],
            cpu=row["cpu"],
            historical_raw_wall_s=raw.get(row["id"], {}).get("narrow", {}).get("raw_s"),
            policy_wall_s=row.get("policy", {}).get("wall_s"),
            policy_cpu_s=row.get("policy", {}).get("cpu_s"),
            position_wall_s=row.get("position", {}).get("wall_s"),
            position_cpu_s=row.get("position", {}).get("cpu_s"),
            service_wall_s=row["service_wall_s"],
            peak_bytes=row.get("resources", {}).get("memory.peak"),
            swap_bytes=row.get("resources", {}).get("memory.swap.current"),
            admitted_probes=row.get("admitted_probes"),
            observations=row["result"]["metrics"].get("observations"),
            tracks=row["result"]["metrics"].get("tracks"),
            native_projections=row["result"]["metrics"].get("compact_projections"),
            **{
                f"{stage}_wall_s": row["result"]["metrics"].get("stage_s", {}).get(stage)
                for stage in MEASURED_STAGES
            },
        )
        for row in results
    ]


def calibration_rows(positions):
    lookup = {(r["id"], r["method"], r["calibration"]): r for r in positions}
    changes = []
    for row in positions:
        if row["calibration"] != "c0":
            continue
        fitted = lookup[row["id"], row["method"], "fitted_c"]
        changes.append(
            dict(
                id=row["id"],
                method=row["method"],
                detector_range=row["detector_range"],
                **{
                    f"fitted_minus_c0_{field}": fitted[field] - row[field]
                    if fitted[field] is not None and row[field] is not None
                    else None
                    for field in ("error_km", "rf_rms_hz", "frequency_score")
                },
            )
        )
    return changes


def summary(positions, resources, agreement):
    cohorts = {}
    for cohort, cases in GROUPS.items():
        findings = cohorts[cohort] = {}
        for method in trial.METHODS:
            work = [r for r in resources if r["id"] in cases and r["method"] == method]
            teacher = [r for r in agreement if r["id"] in cases and r["method"] == method]
            result = findings[method] = {
                "work": {
                    key: distribution([r[key] for r in work])
                    for key in (
                        "position_cpu_s",
                        "position_wall_s",
                        "policy_cpu_s",
                        "service_wall_s",
                    )
                },
                "teacher_agreement": {
                    key: sum(r[key] for r in teacher)
                    for key in (
                        "admitted",
                        "correct_family",
                        "teacher_positive",
                        "shareable",
                        "admitted_on_teacher_negative",
                        "teacher_negative",
                    )
                },
            }
            for arm in ARMS:
                group = [
                    r
                    for r in positions
                    if r["id"] in cases and r["method"] == method and r["calibration"] == arm
                ]
                result[arm] = dict(
                    attempted=len(cases),
                    published=sum(r["status"] == "ok" for r in group),
                    within_5pct=sum(r["within_5pct"] for r in group),
                    within_10pct=sum(r["within_10pct"] for r in group),
                    error_km=distribution([r["error_km"] for r in group]),
                    rf_rms_hz=distribution([r["rf_rms_hz"] for r in group]),
                )
    return cohorts


def figures(report, rows, extended):
    charts = []
    for cohort, ids in GROUPS.items():
        series = f"{cohort}-positions.jsonl.gz"
        pack(report / series, [r for r in rows if r["id"] in ids])
        provenance = (
            "scores.csv",
            "v5-controls.csv",
            "prediction-lock.json",
            "oracle-amendment-lock.json",
            "teacher-agreement.csv",
        )
        extras = extended if cohort == "wide" else {}
        seal = f"{cohort}-figure-lock.json"
        save_json(
            report / seal,
            dict(
                cases=ids,
                files={p: _sha(report / p) for p in (series, *provenance, *extras.values())},
            ),
        )
        chart = dict(
            id=f"pilot-distillation-{cohort}",
            method="pilot_distill_learned",
            scope="roof",
            title=f"Distilled pilot admission on the held {cohort} detector roster",
            caption=(
                "The compact fits use whole stored fast factors. The linear gate uses fast "
                "signal features. The oracle requires retrospective teacher labels. "
                "All recordings are from one roof."
            ),
            cases=ids,
            seal=seal,
            provenance=list(provenance),
            series=[
                dict(
                    key=key,
                    file=series,
                    label=LABELS[arm],
                    value=f"pilot_distill_{arm}",
                    native_field="paired_capture_sha256",
                    match=[
                        "paired_ordinary_sha256",
                        "original_request_sha256",
                        "catalog_sha256",
                        "tile",
                    ],
                )
                for key, arm in (
                    ("one", "learned"),
                    ("stock", "stock"),
                    ("one_native_factors", "strength"),
                    ("all_visits", "oracle"),
                )
            ],
        )
        if extras:
            chart["roof_references"] = extras
        charts.append(chart)
    save_json(report / "figures.json", dict(version=2, charts=charts))
    screening_figures.generate(report / "charts", evidence=report)


def stages(report, work, agreement):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    figure, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True, layout="constrained")
    ids = trial.HELD + trial.SUPPLEMENT
    for axis, data, ylabel, field in zip(
        axes,
        (work, agreement),
        ("Measured compact position CPU", "Capture-era winner families recovered"),
        ("position_cpu_s", "shareable_recall"),
        strict=True,
    ):
        indexed = {(r["id"], r["method"]): r for r in data}
        for j, method in enumerate(trial.METHODS):
            y = [i + 0.18 * (j - 1.5) for i in range(len(ids))]
            values = [indexed[ident, method][field] for ident in ids]
            if field == "shareable_recall":
                values = [100 * v for v in values]
            axis.barh(
                y,
                [v if v is not None else 0 for v in values],
                height=0.16,
                color=COLORS[method],
                label=LABELS[method],
            )
            for ident, level, value in zip(ids, y, values, strict=True):
                if value is None:
                    state = indexed[ident, method]["status"].replace("_", " ").capitalize()
                    axis.text(0, level, state, va="center", fontsize=8, color=COLORS[method])
        axis.set_title(ylabel)
        axis.set_xlabel(
            "Position CPU seconds"
            if field == "position_cpu_s"
            else "Shareable families recovered (%)"
        )
        axis.set_yticks(range(len(ids)), labels=ids)
        axis.axhline(len(trial.HELD) - 0.5, color="#aeb7c1", lw=0.8)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0].invert_yaxis()
    axes[-1].set_xlim(0, 103)
    axes[0].legend(ncols=2, loc="upper left", bbox_to_anchor=(0.0, -0.13), frameon=False)
    for suffix in ("png", "pdf"):
        figure.savefig(report / f"pilot-distillation-stages.{suffix}", dpi=160)
    plt.close(figure)
    files = (
        "resources.csv",
        "teacher-agreement.csv",
        "pilot-distillation-stages.png",
        "pilot-distillation-stages.pdf",
        "prediction-lock.json",
        "oracle-amendment-lock.json",
    )
    save_json(report / "stage-lock.json", dict(files={p: _sha(report / p) for p in files}))
    save_json(
        report / "stage-figure.json",
        dict(
            version=1,
            id="pilot-distillation-stages",
            title="Pilot gate coverage and compact position CPU",
            boundary="Stored fast GLRT through compact position",
            sample="Four held narrow recordings and two held wide recordings from the same roof",
            note="The divider marks the detector-range change. The CSV includes gate overhead.",
            image="pilot-distillation-stages.png",
            pdf="pilot-distillation-stages.pdf",
            csv="resources.csv",
            seal="stage-lock.json",
        ),
    )


def score(report=REPORT):
    if (report / "score-lock.json").exists():
        raise FileExistsError("pilot publication already has a score lock")
    lock = sealed(report, "prediction-lock.json")
    amendment_lock = sealed(report, "oracle-amendment-lock.json")
    plan = whole_iq.read(report / "replay-plan.json")
    amendment = whole_iq.read(report / "oracle-amendment-plan.json")
    changes = records(report / "oracle-amendment.jsonl.gz")
    if (
        amendment["original_plan_sha256"] != _sha(report / "replay-plan.json")
        or set(amendment_lock["cases"]) != set(amendment["cases"])
        or {r["id"] for r in changes if r["condition"] == "oracle"} != set(amendment["cases"])
    ):
        raise ValueError("the oracle amendment does not match the original plan")
    corrected = {(r["id"], r["condition"]): r for r in changes}
    rows = records(report / "positions.jsonl.gz")
    keys = {(r["id"], r["condition"]) for r in rows}
    if len(rows) != len(keys) or keys != {(i, a) for i in lock["cases"] for a in trial.METHODS}:
        raise ValueError("scoring requires a terminal result for every scheduled compact fit")
    rows = [corrected.get((r["id"], r["condition"]), r) for r in rows]
    refs, extended = references(report, lock["cases"])
    positions, original = compare(rows, refs)
    work = resource_rows(rows)
    agreement = rf_agreement(plan["cases"], amendment["cases"])
    csv_file(report / "scores.csv", positions)
    csv_file(report / "v5-controls.csv", original)
    csv_file(report / "resources.csv", work)
    csv_file(report / "teacher-agreement.csv", agreement)
    csv_file(report / "calibration.csv", calibration_rows(positions))
    save_json(report / "summary.json", summary(positions, work, agreement))
    figures(report, rows, extended)
    stages(report, work, agreement)
    source = Path(__file__).resolve()
    names = (
        "summary.json",
        "scores.csv",
        "v5-controls.csv",
        "resources.csv",
        "teacher-agreement.csv",
        "calibration.csv",
        "figures.json",
        "stage-figure.json",
        "stage-lock.json",
        "prediction-lock.json",
        "oracle-amendment-lock.json",
    )
    save_json(
        report / "score-lock.json",
        dict(files={name: _sha(report / name) for name in names}, publisher_sha256=_sha(source)),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=local_output, default=REPORT)
    score(parser.parse_args().report)
