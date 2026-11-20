"""Score and expose signed-mean blind positions through the standard atlas."""

import gzip
import json
from collections import Counter

from ..__main__ import read_predictions, save_json
from ..scoring import ARMS, distribution
from . import phase_forecast_trial as trial
from .native_joint_full_results import roi_margin
from .native_joint_results import geodata
from .prefix_figures import csv_file

METHOD = trial.law.METHOD
CONTROL = trial.BASE.METHOD
MATCH = ("input_sha256", "native_sha256", "catalog_sha256", "observation_sha256")


def main():
    output = trial.OUTPUT
    lock = trial.read(output / "prediction-lock.json")
    trial.BASE.secant_full._verify_files(output, lock["files"])
    plan = trial.read(output / "native-plan.json")
    if trial.proxy_binding(plan) != lock["catalogue_lock_sha256"]:
        raise ValueError("catalogue validation differs from the pre-native seal")
    candidate = read_predictions(output / "positions.jsonl.gz")
    stock = read_predictions(output / "control-positions.jsonl.gz")
    if tuple(candidate) != tuple(lock["cases"]) or candidate.keys() != stock.keys():
        raise ValueError("blind positions differ from the sealed schedule")
    with gzip.open(output / "phase-means.jsonl.gz", "rt") as stream:
        traces = {row["id"]: row for row in map(json.loads, stream)}
    refs = {
        row["id"]: row
        for panel in ("ds26-common127", "roof16")
        for row in trial.BASE.phase.corpus.references(panel)
    }
    roof = trial.read(trial.panel.REPORT / "omitted-figure-lock.json")
    trial.BASE.secant_full._verify_files(trial.panel.REPORT, roof["files"])
    original_queries = {
        q["id"]: q for q in trial.read(trial.panel.REPORT / "omitted-queries.json")["queries"]
    }
    rows, queries = [], []
    for case, record in candidate.items():
        reference = stock[case]
        if (
            any(
                record.get(k) != reference[k]
                for k in MATCH
                if k != "observation_sha256" or k in record
            )
            or reference["tile"] != record["tile"]
        ):
            raise ValueError(
                "native signed and stock requested different factors, catalogue or tile"
            )
        truth = refs[record["recording"]]["truth"]
        margin = roi_margin(truth, record["tile"])
        cohort = record["study_cohort"]
        if cohort == "omitted":
            q = original_queries[case]
            if (
                margin >= 0
                or q["truth"] != truth
                or any(record[k] != v for k, v in q["bindings"].items())
            ):
                raise ValueError("signed evaluation failed its original omitted bindings")
            queries.append(q)
        elif margin < 0:
            raise ValueError("supplied tile lacks the archived GNSS site")
        for arm in ARMS:
            for outcome in (record, reference):
                rows.append(
                    dict(
                        id=case,
                        cohort=cohort,
                        method=outcome["method"],
                        arm=arm,
                        roi_margin_km=margin,
                        **geodata(outcome, arm, truth),
                    )
                )
    summaries = []
    for cohort, method, arm in sorted({(r["cohort"], r["method"], r["arm"]) for r in rows}):
        group = [r for r in rows if (r["cohort"], r["method"], r["arm"]) == (cohort, method, arm)]
        summaries.append(
            dict(
                cohort=cohort,
                method=method,
                arm=arm,
                n=len(group),
                status=dict(Counter(r["status"] for r in group)),
                **{
                    k: distribution(r[k] for r in group)
                    for k in (
                        "error_km",
                        "forced_error_km",
                        "conditional_rms_hz",
                        "worker_cpu_s",
                        "worker_wall_s",
                    )
                },
            )
        )
    targets = {}
    for i, number in (("DS26-0197", 67348), ("DS26-0223", 67315)):
        trace = traces.get(i, {})
        center = trace.get("phase_mean_s", {}).get(str(number))
        by_arm = {}
        for arm, kept in trace.get("kept_by_arm", {}).items():
            matching = [r for r in kept if r["norad"] == number]
            by_arm[arm] = dict(
                tracks=len(matching),
                points=sum(r["points"] for r in matching),
                total_phase_s=[r["relative_phase_s"] + center for r in matching]
                if center is not None
                else [],
            )
        targets[i] = dict(norad=number, prior_mean_s=center, assigned=by_arm)
    csv_file(output / "scores.csv", rows)
    save_json(output / "scores.json", dict(groups=summaries, cases=rows, target_phases=targets))
    save_json(output / "omitted-queries.json", dict(queries=queries))
    chart_files = dict(
        lock["files"],
        **{
            name: trial.proxy.digest((output / name).read_bytes())
            for name in ("catalogue-lock.json", "omitted-queries.json", "scores.json")
        },
    )
    specs = []
    for cohort in ("diagnostic", "confirmation", "omitted"):
        cases = [r["id"] for r in candidate.values() if r["study_cohort"] == cohort]
        transfer = cohort == "omitted"
        file = f"{cohort}-figure-lock.json"
        successful = all(candidate[i].get("observation_sha256") is not None for i in cases)
        spec = dict(
            id=METHOD + "-" + cohort,
            method=METHOD,
            scope="transfer" if transfer else "roof",
            title={
                "diagnostic": "Signed phase prior on diagnosed recordings",
                "confirmation": "Signed phase prior on four reserve recordings",
                "omitted": "Signed phase prior with the true region omitted",
            }[cohort],
            caption="Causal prior-to-current TEME timing forecast. Both fits use the same native "
            "Graph and offer. Points use the fresh receiver and archived nominal fits.",
            seal=file,
            cases=cases,
            provenance=["native-plan.json", "catalogue-lock.json"],
            series=[
                dict(
                    key="candidate" if transfer else "one",
                    file="positions.jsonl.gz",
                    value=METHOD,
                    label="Signed phase prior · publication",
                    forced_label="Signed phase prior · forced",
                    where=dict(study_cohort=cohort),
                ),
                dict(
                    key="stock",
                    file="control-positions.jsonl.gz",
                    value=CONTROL,
                    label="Nominal native joint · publication",
                    where=dict(study_cohort=cohort),
                    match=list(MATCH if successful else MATCH[:-1]),
                ),
            ],
        )
        if transfer:
            spec["queries"] = "omitted-queries.json"
            spec["series"][1]["forced_label"] = "Nominal native joint · forced"
        save_json(output / file, dict(cases=cases, files=chart_files))
        specs.append(spec)
    save_json(output / "figures.json", dict(version=1, charts=specs))


if __name__ == "__main__":
    main()
