"""Check every paired attempt and publish standard position charts and timing totals."""

import argparse
from pathlib import Path
from statistics import median

from ..__main__ import local_output, save_json
from ..scoring import ARMS
from . import cached_association as trial
from . import screening_figures as figures
from .native_lean_eval import _write_predictions

read = trial.trial.phase._read
digest = trial.trial.phase.digest


def timing(rows):
    complete = [
        p for p in rows if p["candidate_cpu_s"] is not None and p["control_cpu_s"] is not None
    ]
    candidate_cpu = sum(p["candidate_cpu_s"] for p in complete)
    stock_cpu = sum(p["control_cpu_s"] for p in complete)
    stage = "match_and_preparation_cpu_s"
    candidate_match = sum(p["candidate_association"][stage] for p in complete)
    stock_match = sum(p["control_association"][stage] for p in complete)
    prep = sum(p["candidate_association"]["gram_preparation_cpu_s"] for p in complete)
    return dict(
        pairs=len(complete),
        scheduled_pairs=len(rows),
        worker_cpu_s=[stock_cpu, candidate_cpu],
        match_cpu_s=[stock_match, candidate_match],
        gram_preparation_cpu_s=prep,
        worker_pooled_savings=1 - candidate_cpu / stock_cpu if stock_cpu else None,
        worker_median_pair_savings=median(
            1 - p["candidate_cpu_s"] / p["control_cpu_s"] for p in complete
        )
        if complete
        else None,
        match_pooled_savings=1 - candidate_match / stock_match if stock_match else None,
        direct_fallbacks=sum(p["candidate_association"]["direct_fallbacks"] for p in complete),
        match_calls=sum(p["candidate_association"]["calls"] for p in complete),
        max_cache_array_bytes=max(
            (p["candidate_association"]["cache_array_bytes"] for p in complete), default=None
        ),
    )


def publish(work, report):
    report = local_output(report)
    lock = read(report / "prediction-lock.json")
    trial.trial.secant_full._verify_files(report, lock["files"])
    plan = read(report / "plan.json")
    if read(work / "plan.json") != plan:
        raise ValueError("raw attempts differ from the bound measurement plan")
    data = read(report / "measurements.json")["pairs"]
    roster = (*trial.MATCHED, *trial.OMITTED)
    archives = trial.archived()
    attempts = []
    for ident in roster:
        for index in range(plan["repeat"]):
            candidate, stock = (
                read(work / f"{ident}-{index}-{method}.json")
                for method in (trial.METHOD, trial.STOCK)
            )
            if trial.measure(candidate, stock, archives[ident]) != data[ident][index]:
                raise ValueError(f"{ident} attempt {index} differs from the timing receipt")
            attempts.extend(dict(row, repetition=index + 1) for row in (candidate, stock))
    _write_predictions(report / "paired-attempts.jsonl.gz", attempts)
    rows = [p for ident in roster for p in data[ident]]
    evidence = dict(
        exact_ownership_pairs=sum(p["same_owners"] for p in rows),
        exact_Graph_pairs=sum(p["same_graph"] for p in rows),
        exact_decision_pairs=sum(p["same_decision"] for p in rows),
        timings=timing(rows),
        roof_timings=timing([p for p in rows if p["id"] in trial.MATCHED]),
        omitted_timings=timing([p for p in rows if p["id"] in trial.OMITTED]),
    )
    for name in (
        "endpoint_shift_m",
        "archived_endpoint_shift_m",
        "rms_delta_hz",
        "objective_delta",
    ):
        values = [
            abs(p["arms"][arm][name])
            for p in rows
            for arm in ARMS
            if p["arms"][arm][name] is not None
        ]
        evidence[f"max_absolute_{name}"] = max(values, default=None)
    save_json(report / "summary.json", evidence)
    refs, _ = figures.shared._frozen_roof()
    first = {a["id"]: a for a in attempts if a["method"] == trial.METHOD and a["repetition"] == 1}
    queries = [
        dict(
            id=ident,
            condition="omitted",
            recording=first[ident]["recording"],
            truth=refs[first[ident]["recording"]]["truth"],
            bindings={
                field: first[ident][field]
                for field in trial.FINGERPRINTS
                if first[ident].get(field) is not None
            },
        )
        for ident in trial.OMITTED
    ]
    save_json(report / "omitted-queries.json", dict(queries=queries))
    names = ("paired-attempts.jsonl.gz", "summary.json", "prediction-lock.json")
    files = lock["files"] | {name: digest(report / name) for name in names}
    charts = []
    for group, cases in (("roof", trial.MATCHED), ("omitted", trial.OMITTED)):
        roof = group == "roof"
        seal = f"{group}-figure-lock.json"
        bindings = dict(files)
        spec = dict(
            id=f"{trial.METHOD}-{group}",
            method=trial.METHOD,
            scope="roof" if roof else "transfer",
            title="Cached joint association on eight roof recordings"
            if roof
            else "Cached joint association with the correct tile omitted",
            caption="Fresh paired native Graph runs with identical observations and causal orbits.",
            cases=cases,
            seal=seal,
            provenance=["summary.json", "source-lock.json", "plan.json"],
            series=[
                dict(
                    key="one" if roof else "candidate",
                    label="Cached joint association",
                    file=trial.FILES[0],
                    value=trial.METHOD,
                    where=dict(cohort=group),
                ),
                dict(
                    key="stock",
                    label="Original joint association",
                    file=trial.FILES[1],
                    value=trial.STOCK,
                    where=dict(cohort=group),
                    match=["native_sha256", "catalog_sha256", "input_sha256", "observation_sha256"],
                ),
            ],
        )
        if not roof:
            spec.update(
                queries="omitted-queries.json",
                condition_labels=dict(omitted="Correct tile omitted"),
            )
            bindings[spec["queries"]] = digest(report / spec["queries"])
        save_json(report / seal, dict(cases=cases, files=bindings))
        figures._chart(report, spec)
        charts.append(spec)
    save_json(report / "figures.json", dict(version=1, charts=charts))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--report", default=trial.REPORT, type=Path)
    args = parser.parse_args()
    publish(args.work, args.report)


if __name__ == "__main__":
    main()
