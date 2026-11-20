"""Validate, seal and score the complete-factor joint position replay."""

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path

from ..__main__ import encoded, read_predictions, save_json
from ..scoring import ARMS, ROLES, distance_km, distribution, thresholds
from . import native_joint_trial as trial
from .armijo_finish_results import pack
from .prefix_figures import csv_file

phase = trial.phase
METHOD = trial.METHOD
STOCK = trial.native.native_lean.METHOD
CANDIDATE_FILE = "positions.jsonl.gz"
STOCK_FILE = "stock-positions.jsonl.gz"


def same_worker_inputs(candidate, stock):
    return all(
        candidate[k] == stock[k]
        for k in ("native_sha256", "catalog_sha256", "input_sha256", "tile")
    )


def seal(work, bundle, output):
    plan = phase._read(work / "plan.json")
    if plan["sources"] != trial.sources(bundle):
        raise ValueError("frozen worker sources changed")
    if plan["cases"] != [query for query, _ in trial.jobs(phase.frozen_inputs())]:
        raise ValueError("prediction request differs from the prospective plan")
    native_lock = phase._read(trial.NATIVE / "prediction-lock.json")
    wrong_lock = phase._read(trial.NATIVE / "wrong-figure-lock.json")
    for lock in (native_lock, wrong_lock):
        trial.secant_full._verify_files(trial.NATIVE, lock["files"])
    stock = read_predictions(trial.NATIVE / "positions.jsonl.gz")
    with gzip.open(trial.NATIVE / "wrong-positions.jsonl.gz", "rt") as stream:
        (wrong,) = [r for r in map(json.loads, stream) if r["method"] == STOCK]
    stock[wrong["id"]] = wrong
    candidates, controls = [], []
    for query in plan["cases"]:
        ident, cohort, packet = query["id"], query["cohort"], query["packet"]
        row = phase._read(work / f"{ident}.json")
        if row["input_sha256"] != phase.corpus._sha(encoded(packet)) or row["id"] != ident:
            raise ValueError(f"{ident} candidate factors or tile changed")
        prior = stock.get(ident)
        if prior is not None:
            graph = row.get("observation_sha256")
            if row["result"]["status"] in ("ok", "withheld") and not graph:
                raise ValueError(f"{ident} returned a receiver decision without its Graph hash")
            if not same_worker_inputs(row, prior) or (
                graph is not None and graph != prior.get("observation_sha256")
            ):
                raise ValueError(
                    f"{ident} does not match the exact archived native stream and Graph"
                )
            controls.append(dict(prior, cohort=cohort, source="archived_raw_lean"))
        candidates.append(row)
    save_json(output / "plan.json", plan)
    save_json(output / "source-lock.json", plan["sources"])
    files = {
        CANDIDATE_FILE: pack(output, CANDIDATE_FILE, candidates),
        STOCK_FILE: pack(output, STOCK_FILE, controls),
    }
    files.update({name: phase.digest(output / name) for name in ("plan.json", "source-lock.json")})
    save_json(
        output / "prediction-lock.json",
        dict(
            cases=[r["id"] for r in candidates],
            files=files,
            run=phase._read(work / "run-receipt.json"),
            parent_native_sha256=phase.digest(trial.NATIVE / "prediction-lock.json"),
            original_controls_receipt_sha256=phase.digest(
                trial.secant_full.REPORT / "receipt.json"
            ),
        ),
    )


def _chart_specs(output, plan, lock):
    charts = []
    candidates = read_predictions(output / CANDIDATE_FILE)
    for cohort in ("primary", "confirmation", "wrong_offer"):
        cases = [item["id"] for item in plan["cases"] if item["cohort"] == cohort]
        files = dict(lock["files"])
        wrong = cohort == "wrong_offer"
        label = {
            "primary": "Native GLRT and joint orbit positioning",
            "confirmation": "Joint orbits on three new native inputs",
            "wrong_offer": "Joint orbits with the correct tile omitted",
        }[cohort]
        chart = dict(
            id=f"{METHOD}-{cohort.replace('_', '-')}",
            method=METHOD,
            title=label,
            caption="Complete stored GLRT factors through the streaming receiver and joint solver.",
            scope="transfer" if wrong else "roof",
            cases=cases,
            seal=f"{cohort}-figure-lock.json",
            series=[
                dict(
                    key="candidate" if wrong else "one",
                    label="Streaming GLRT with joint orbit fit",
                    file=CANDIDATE_FILE,
                    value=METHOD,
                    where=dict(cohort=cohort),
                )
            ],
        )
        if cohort != "confirmation":
            chart["series"].append(
                dict(
                    key="stock",
                    label="Archived native-lean exact robust fit",
                    file=STOCK_FILE,
                    value=STOCK,
                    where=dict(cohort=cohort),
                    match=["input_sha256"]
                    + (
                        ["observation_sha256"]
                        if all(candidates[ident].get("observation_sha256") for ident in cases)
                        else []
                    ),
                )
            )
        if wrong:
            name = "wrong-queries.json"
            queries = phase._read(trial.NATIVE / name)
            for query in queries["queries"]:
                if not candidates[query["id"]].get("observation_sha256"):
                    query["bindings"].pop("observation_sha256", None)
            save_json(output / name, queries)
            files[name] = phase.digest(output / name)
            chart["queries"] = name
        save_json(output / chart["seal"], dict(cases=cases, files=files))
        charts.append(chart)
    return dict(version=1, charts=charts)


def geodata(record, arm, truth):
    result = record["result"]
    point = result["arms"][arm]
    held = result["metrics"].get("held_by_arm", {}).get(arm, {})
    return dict(
        status=result["status"],
        reason=result.get("reason"),
        error_km=distance_km(point.get("latlon"), truth),
        forced_error_km=distance_km(point.get("forced_latlon"), truth),
        conditional_rms_hz=point.get("rf_rms_hz"),
        original_report_rms_hz=None,
        objective=point.get("frequency_score"),
        held_score=point.get(
            "held_score",
            held.get("held_score", result["metrics"].get("held_score") if arm == "c0" else None),
        ),
        held_orbits=held.get(
            "held_orbits", result["metrics"].get("held_orbits") if arm == "c0" else None
        ),
        fitted_c_hz_per_ghz=point.get("c_hz_per_ghz"),
        worker_wall_s=record["worker_wall_s"],
        worker_cpu_s=(record.get("worker") or {}).get("cpu_s"),
        peak_rss_kib=record.get("resident_peak_kib"),
        vm_peak_kib=(record.get("proc_memory_kib") or {}).get("VmPeak"),
    )


def score(output):
    lock = phase._read(output / "prediction-lock.json")
    trial.secant_full._verify_files(output, lock["files"])
    candidate = read_predictions(output / CANDIDATE_FILE)
    stock = read_predictions(output / STOCK_FILE)
    original_path = trial.secant_full.REPORT / "receipt.json"
    if phase.digest(original_path) != lock["original_controls_receipt_sha256"]:
        raise ValueError("the four original v5 controls changed after the prediction seal")
    original_lock = phase._read(original_path)
    trial.secant_full._verify_files(trial.secant_full.REPORT, original_lock["files"])
    original_bindings = phase._read(trial.secant_full.REPORT / "original-v5-inputs.json")
    refs = {r["id"]: r for r in phase.projector_roof.roster()}
    rows = []
    for ident, pred in candidate.items():
        ref = refs[pred["recording"]]
        for method, selected in ((METHOD, pred), (STOCK, stock.get(ident))):
            if selected is None:
                continue
            for arm in ARMS:
                rows.append(
                    dict(
                        id=ident,
                        method=method,
                        cohort=pred["cohort"],
                        arm=arm,
                        **geodata(selected, arm, ref["truth"]),
                    )
                )
        if pred["cohort"] == "wrong_offer":
            continue
        archive = phase.ARCHIVE if pred["recording"].startswith("DS26-") else phase.DS29
        for role in ROLES:
            execution = archive / f"{ident}-r0" / f"{role}-execution.json"
            if phase.digest(execution) != original_bindings[ident][role]["execution_sha256"]:
                raise ValueError(f"{ident} original control differs from the matched input seal")
            for arm, endpoint in phase._read(execution)["worker"]["arms"].items():
                delta = distance_km(
                    endpoint["endpoint_latlon"], ref["reference"][role][arm]["latlon"]
                )
                if delta is None or delta > 1e-6:
                    raise ValueError(f"{ident} original role geographic control changed")
                row = dict.fromkeys(rows[0])
                row.update(
                    id=ident,
                    method=role,
                    cohort=pred["cohort"],
                    arm=arm,
                    status="ok",
                    error_km=distance_km(endpoint["endpoint_latlon"], ref["truth"]),
                    original_report_rms_hz=endpoint.get("residual_rms_hz"),
                )
                rows.append(row)
    csv_file(output / "scores.csv", rows)
    groups = []
    for cohort, method, arm in sorted({(r["cohort"], r["method"], r["arm"]) for r in rows}):
        subset = [r for r in rows if (r["cohort"], r["method"], r["arm"]) == (cohort, method, arm)]
        errors = [r["error_km"] for r in subset]
        groups.append(
            dict(
                cohort=cohort,
                method=method,
                arm=arm,
                scheduled=len(subset),
                status=dict(Counter(r["status"] for r in subset)),
                within_km=thresholds(errors),
                **{
                    key: distribution(r[key] for r in subset)
                    for key in (
                        "error_km",
                        "forced_error_km",
                        "conditional_rms_hz",
                        "original_report_rms_hz",
                        "objective",
                        "held_score",
                        "worker_wall_s",
                        "worker_cpu_s",
                        "peak_rss_kib",
                        "vm_peak_kib",
                    )
                },
            )
        )
    save_json(output / "summary.json", dict(groups=groups))
    save_json(
        output / "figures.json", _chart_specs(output, phase._read(output / "plan.json"), lock)
    )


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--work", type=Path, required=True)
    cli.add_argument("--bundle", type=Path, default=trial.BUNDLE)
    cli.add_argument("--output", type=Path, default=trial.REPORT)
    args = cli.parse_args()
    seal(args.work, args.bundle, args.output)
    score(args.output)


if __name__ == "__main__":
    main()
