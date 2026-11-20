"""Score sealed offset and no-offset endpoints, with frequency diagnostics kept separate."""

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path
from statistics import median

from ..__main__ import local_output, save_json
from ..scoring import ARMS, distance_km
from . import marginal_offset as trial
from . import screening_figures as f
from .phase_confirmation import _read, digest
from .prefix_figures import csv_file
from .secant_full import _verify_files

LABELS = {
    "diagnostic": "Four diagnostic roof captures",
    "confirmation": "Six salted roof captures",
    "omitted": "Three prior omitted offers",
}


def _rows(path):
    with gzip.open(path, "rt") as stream:
        return {row["id"]: row for row in map(json.loads, stream)}


def score(record, ref, arm):
    result = record["result"]
    point = result["arms"][arm]
    held = result["metrics"].get("held_by_arm", {}).get(arm, {})
    return dict(
        id=record["id"],
        cohort=record["cohort"],
        method=record["method"],
        arm=arm,
        status=result["status"],
        reason=result["reason"],
        error_km=distance_km(point.get("latlon"), ref),
        forced_error_km=distance_km(point.get("forced_latlon"), ref),
        final_raw_rms_hz=point.get("rf_rms_hz"),
        held_raw_rms_hz=held.get("held_raw_rms_hz"),
        held_marginal_loss_per_point=held.get("held_normalized_mean_loss"),
        held_support_orbits=held.get("held_orbits"),
        geometry_radius_km=point.get("radius_km"),
    )


def _summary(rows):
    def numeric(key):
        return [r[key] for r in rows if r[key] is not None]

    return dict(
        attempts=len(rows),
        statuses=dict(Counter(r["status"] for r in rows)),
        published_within_5km=sum(r["error_km"] is not None and r["error_km"] <= 5 for r in rows),
        **{
            f"median_{k}": median(values) if (values := numeric(k)) else None
            for k in (
                "error_km",
                "forced_error_km",
                "final_raw_rms_hz",
                "held_raw_rms_hz",
                "held_marginal_loss_per_point",
                "geometry_radius_km",
            )
        },
    )


def publish(report):
    report = local_output(report)
    lock = _read(report / "prediction-lock.json")
    _verify_files(report, lock["files"])
    plan = _read(report / "plan.json")["cases"]
    if [q["id"] for q in plan] != lock["cases"]:
        raise ValueError("the sealed result differs from the prospective plan")
    candidate, control = (_rows(report / name) for name in trial.FILES)
    if list(candidate) != lock["cases"] or list(control) != lock["cases"]:
        raise ValueError("the two arms do not match the scheduled cases")
    refs, _ = f.shared._frozen_roof()
    prior = trial.full.REPORT
    previous = _read(prior / "omitted-figure-lock.json")
    _verify_files(prior, previous["files"])
    omitted_refs = {r["id"]: r for r in _read(prior / "omitted-queries.json")["queries"]}
    rows = []
    for ident in lock["cases"]:
        a, b = candidate[ident], control[ident]
        if any(a[field] != b[field] for field in (*trial.BINDINGS, "tile", "cpu")):
            raise ValueError(f"{ident} changed native, graph, catalogue, tile or execution CPU")
        first, second = (r["result"]["metrics"]["offset_study"] for r in (a, b))
        if any(first[key] != second[key] for key in trial.OWNERSHIP):
            raise ValueError(f"{ident} changed a frozen owner/alias set")
        if any(r["final_c0_ownership"] != r["final_fitted_c_ownership"] for r in (first, second)):
            raise ValueError(f"{ident} changed frozen owners across the c arms")
        if a["cohort"] == "omitted":
            reference = omitted_refs[ident]
            if any(a[key] != value for key, value in reference["bindings"].items()):
                raise ValueError(f"{ident} differs from the sealed omitted-offer reference")
            truth = reference["truth"]
        else:
            truth = refs[a["recording"]]["truth"]
        rows.extend(score(r, truth, arm) for r in (a, b) for arm in ARMS)
    csv_file(report / "per-recording.csv", rows)
    stats = {
        group: {
            method: {
                arm: _summary(
                    [
                        r
                        for r in rows
                        if r["cohort"] == group and r["method"] == method and r["arm"] == arm
                    ]
                )
                for arm in ARMS
            }
            for method in (trial.variant.METHOD, trial.variant.STOCK)
        }
        for group in LABELS
    }
    save_json(report / "summary.json", dict(graph_and_owner_alias_pairs=len(plan), groups=stats))
    charts = []
    omitted = []
    common = lock["files"] | {
        name: digest(report / name)
        for name in ("prediction-lock.json", "summary.json", "per-recording.csv")
    }
    for group, label in LABELS.items():
        roof = group != "omitted"
        cases = [q["id"] for q in plan if q["cohort"] == group]
        spec = dict(
            id=f"{trial.variant.METHOD}-{group}",
            method=trial.variant.METHOD,
            title=f"Marginal Doppler offset · {label}",
            scope="roof" if roof else "transfer",
            caption="Paired native runs share owners and CFO aliases. "
            "The candidate integrates one constant per Graph track.",
            cases=cases,
            seal=f"{group}-figure-lock.json",
            provenance=["source-lock.json", "plan.json", "summary.json", "per-recording.csv"],
            series=[
                dict(
                    key="one" if roof else "candidate",
                    label="Marginal offset · 1000 Hz",
                    file=trial.FILES[0],
                    value=trial.variant.METHOD,
                    where=dict(cohort=group),
                ),
                dict(
                    key="stock",
                    label="Matched zero-offset fit",
                    file=trial.FILES[1],
                    value=trial.variant.STOCK,
                    where=dict(cohort=group),
                    match=trial.BINDINGS,
                ),
            ],
        )
        files = dict(common)
        if not roof:
            for ident in cases:
                row = candidate[ident]
                omitted.append(
                    dict(
                        id=ident,
                        recording=row["recording"],
                        condition="omitted",
                        truth=omitted_refs[ident]["truth"],
                        bindings={key: row[key] for key in trial.BINDINGS},
                    )
                )
            queries = "omitted-queries.json"
            save_json(report / queries, dict(queries=omitted))
            files[queries] = digest(report / queries)
            spec.update(queries=queries, condition_labels=dict(omitted="Correct tile omitted"))
        save_json(report / spec["seal"], dict(cases=cases, files=files))
        f._chart(report, spec)
        charts.append(spec)
    save_json(report / "figures.json", dict(version=1, charts=charts))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default=trial.REPORT, type=Path)
    publish(parser.parse_args().report)
