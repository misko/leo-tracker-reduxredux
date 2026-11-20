"""Score live local influence and the independent held exterior comparator."""

import argparse
import json
from collections import Counter
from pathlib import Path

from ..__main__ import read_predictions, save_json, write
from ..scoring import ARMS, distribution, thresholds
from . import exterior_evidence_results as exterior
from . import orbit_influence_trial as trial

phase = trial.phase
METHODS = (trial.METHOD, trial.clock.METHOD, trial.exterior.METHOD)
edge = exterior.edge


def labels(plan, scope):
    exterior_plan = trial.exterior.REPORT / "plan.json"
    if phase.digest(exterior_plan) != plan["exterior_plan_sha256"]:
        raise ValueError("parent exterior plan differs from trial seal")
    if scope == "diagnostic-stress":
        return exterior.labels(None, None, phase._read(exterior_plan), scope)
    path = trial.exterior.REPORT / scope / "evaluator.json"
    if phase.digest(path) != phase._read(exterior_plan)["reserve_evaluator_sha256"]:
        raise ValueError("reserve labels differ from their sealed source")
    return {r["id"]: r for r in phase._read(path)["labels"]}


def case_rows(series, cases, true):
    rows = []
    for method, predictions in series.items():
        for ident, row in predictions.items():
            label = true[ident]
            stock = series[trial.clock.METHOD][ident]
            if (
                any(
                    row.get(k) != stock.get(k)
                    for k in (
                        "input_sha256",
                        "native_sha256",
                        "catalog_sha256",
                        "tile",
                        "observation_sha256",
                    )
                )
                or stock["input_sha256"] != label["input_sha256"]
                or stock["tile"] != label["tile"]
            ):
                raise ValueError("scored control does not match the exact live native offer")
            influence = row.get("orbit_influence", {})
            for arm in ARMS:
                diag = influence.get(arm, {})
                receipt = diag.get("timing", {})
                widths = diag.get("nominal_projection_halfwidths_km", [None, None])
                rows.append(
                    dict(
                        id=ident,
                        method=method,
                        arm=arm,
                        recording=row["recording"],
                        source_cohort=row["cohort"],
                        source=row.get("source"),
                        condition=label["condition"],
                        true_margin_km=label["true_margin_km"],
                        exact_check=ident in cases,
                        influence_orbits=diag.get("orbits"),
                        influence_admitted=diag.get("admitted"),
                        influence_unavailable=diag.get("unavailable"),
                        ordinary_margin_km=diag.get("ordinary_margin_km"),
                        ellipse_margin_km=diag.get("ellipse_margin_km"),
                        deletion_margin_km=diag.get("deletion_margin_km"),
                        ellipse_east_km=widths[0],
                        ellipse_north_km=widths[1],
                        max_deletion_shift_km=diag.get("max_deletion_shift_km"),
                        influence_cpu_s=receipt.get("cpu_s"),
                        influence_wall_s=receipt.get("wall_s"),
                        exterior_state=(row.get("exterior") or {}).get("state"),
                        **edge.shared.geodata(row, arm, label["truth"]),
                    )
                )
    return rows


def summarize(rows):
    result = []
    for method in METHODS:
        for arm in ARMS:
            group = [r for r in rows if r["method"] == method and r["arm"] == arm]
            conditions = []
            for condition in edge.CONDITIONS:
                chosen = [r for r in group if r["condition"] == condition]
                conditions.append(
                    dict(
                        condition=condition,
                        scheduled=len(chosen),
                        statuses=dict(Counter(r["status"] for r in chosen)),
                        withheld_reasons=dict(Counter(r["reason"] for r in chosen if r["reason"])),
                        error_km=distribution(r["error_km"] for r in chosen),
                        forced_error_km=distribution(r["forced_error_km"] for r in chosen),
                        conditional_rms_hz=distribution(r["conditional_rms_hz"] for r in chosen),
                        within_km=thresholds([r["error_km"] for r in chosen]),
                    )
                )
            output = dict(method=method, arm=arm, conditions=conditions)
            for name, contained in (("present", True), ("omitted", False)):
                subset = [r for r in group if (r["true_margin_km"] > 0) == contained]
                output[name] = dict(
                    scheduled=len(subset),
                    statuses=dict(Counter(r["status"] for r in subset)),
                    affected_recordings=len(
                        {r["recording"] for r in subset if r["status"] == "ok"}
                    ),
                )
            result.append(output)
    return result


def measurements(rows, candidate):
    paired = {}
    for row in rows:
        if row["method"] == trial.METHOD and row["influence_cpu_s"] is not None:
            paired.setdefault(row["id"], []).append(row)
    data = [r for r in candidate.values() if r.get("source") == "fresh_live_influence"]
    routine = [
        r
        for r in data
        if not any("exact_diagnostic" in d for d in r.get("orbit_influence", {}).values())
    ]
    return dict(
        measured_influence=len(paired),
        fresh_statuses=dict(Counter(r["result"]["status"] for r in data)),
        cpu_overhead_s=distribution(
            sum(r["influence_cpu_s"] for r in case) for case in paired.values()
        ),
        wall_overhead_s=distribution(
            sum(r["influence_wall_s"] for r in case) for case in paired.values()
        ),
        routine_supervisor_wall_s=distribution(r["worker_wall_s"] for r in routine),
        routine_rss_kib=distribution(r.get("resident_peak_kib") for r in routine),
        routine_vm_peak_kib=distribution(
            r.get("proc_memory_kib", {}).get("VmPeak") for r in routine
        ),
    )


def checks(series, ids, true):
    rows = []
    for ident in ids:
        if ident not in series:
            continue
        recorded = series[ident].get("orbit_influence", {})
        for arm in ARMS:
            approx = recorded.get(arm, {})
            nonlinear = approx.get("exact_diagnostic")
            if nonlinear is None:
                rows.append(dict(id=ident, arm=arm, status="unavailable"))
                continue
            rows.append(
                dict(
                    id=ident,
                    arm=arm,
                    status="measured",
                    condition=true[ident]["condition"],
                    recording=true[ident]["recording"],
                    shift_error_km=distribution(nonlinear["shift_error_km"].values()),
                    approximate_admitted=approx["admitted"],
                    exact_admitted=nonlinear["admitted"],
                    approximate_covariance_km2=approx["deletion_covariance_km2"],
                    exact_covariance_km2=nonlinear["deletion_covariance_km2"],
                    approximate_widths_km=approx["nominal_projection_halfwidths_km"],
                    exact_widths_km=nonlinear["nominal_projection_halfwidths_km"],
                    nonlinear_wall_s=nonlinear["timing"]["wall_s"],
                )
            )
    return rows


def figures(folder, scope, series, labels, lock):
    files = lock["files"].copy()
    queries = []
    specs = []
    for ident in lock["cases"]:
        row, truth = series[trial.METHOD][ident], labels[ident]
        queries.append(
            dict(
                id=ident,
                condition=truth["condition"],
                recording=row["recording"],
                truth=truth["truth"],
                bindings={
                    k: row[k]
                    for k in (
                        "input_sha256",
                        "native_sha256",
                        "catalog_sha256",
                    )
                },
            )
        )
    save_json(folder / "figure-queries.json", dict(queries=queries))
    files["figure-queries.json"] = phase.digest(folder / "figure-queries.json")
    keys = ("candidate", "stock", "one")
    names = ("Orbit influence gate", "Native smooth", "Held exterior gate")
    for key, method, name in zip(keys, METHODS, names, strict=True):
        table = []
        for row in series[method].values():
            result = row["result"]
            if method != trial.clock.METHOD or result["status"] == "missing":
                result = dict(
                    result,
                    arms={
                        arm: dict(value, forced_latlon=None)
                        for arm, value in result["arms"].items()
                    },
                )
            table.append(dict(row, result=result))
        filename = f"plot-{method}.jsonl.gz"
        files[filename] = edge.shared.pack(folder, filename, table)
        specs.append(
            dict(
                key=key,
                label=name,
                value=method,
                file=filename,
                match=["input_sha256", "tile", "observation_sha256"],
            )
        )
    save_json(folder / "figure-lock.json", dict(cases=lock["cases"], files=files))
    specs[1]["forced_label"] = "Smooth · forced"
    chart = dict(
        id=f"native_smooth_orbit_influence-{scope}",
        method=trial.METHOD,
        scope="transfer",
        title="Whole-orbit uncertainty on archival roof offers"
        if scope == "diagnostic-stress"
        else "Whole-orbit uncertainty on six reserve captures",
        caption="Matched native Graphs. Five reserve exterior evaluations are unmeasured."
        if scope == "reserve"
        else "Matched native Graphs with the earlier independent exterior rule.",
        cases=lock["cases"],
        seal="figure-lock.json",
        queries="figure-queries.json",
        condition_labels=edge.LABELS
        if scope == "diagnostic-stress"
        else edge.LABELS
        | {
            "near-inside": "1.5 km inside",
            "near-outside": "1.5 km outside",
        },
        series=specs,
    )
    write(
        folder / "figures.json",
        json.dumps(dict(version=1, charts=[chart]), indent=2).encode() + b"\n",
    )


def score(output):
    plan_path = output / "plan.json"
    plan = phase._read(plan_path)
    for scope in trial.COHORTS:
        folder = output / scope
        lock = phase._read(folder / "prediction-lock.json")
        trial.clock.base.secant_full._verify_files(folder, lock["files"])
        if phase.digest(plan_path) != lock["plan_sha256"]:
            raise ValueError("the locked plan changed after prediction")
        true = labels(plan, scope)
        series = {method: read_predictions(folder / f"{method}.jsonl.gz") for method in METHODS}
        if set(true) != set(lock["cases"]) or any(r.keys() != true.keys() for r in series.values()):
            raise ValueError("an offered case is missing from the scored methods")
        rows = case_rows(series, plan["exact_checks"], true)
        edge.shared.csv_file(folder / "scores.csv", rows)
        save_json(
            folder / "summary.json",
            dict(
                groups=summarize(rows),
                resources=measurements(rows, series[trial.METHOD]),
                exact_checks=checks(series[trial.METHOD], plan["exact_checks"], true),
                batch_wall_s=lock["batch_wall_s"],
                worker_statuses=lock["statuses"],
            ),
        )
        figures(folder, scope, series, true, lock)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output", type=Path, default=trial.REPORT)
    score(cli.parse_args().output)


if __name__ == "__main__":
    main()
