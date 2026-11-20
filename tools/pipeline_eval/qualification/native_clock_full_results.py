"""Seal the native oscillator replay and compare matched receiver boundaries."""

import argparse
from collections import Counter
from pathlib import Path

from ..__main__ import encoded, read_predictions, save_json
from ..scoring import ARMS, distance_km, distribution, thresholds
from . import native_clock_full as trial
from . import native_joint_full_results as shared
from .robust_em_trials import load as load_prepared

phase = trial.phase
PREDICTIONS = shared.PREDICTIONS
JOINT = "joint-positions.jsonl.gz"
PAIR_FIELDS = ("input_sha256", "native_sha256", "catalog_sha256", "tile")
METRICS = ("error_km", "forced_error_km", "conditional_rms_hz", "held_score", "held_orbits")


def verified_pairs(candidate, stock):
    if set(candidate) != set(stock):
        raise ValueError("the native joint and clock rosters differ")
    for ident, row in candidate.items():
        control = stock[ident]
        if any(row[k] != control[k] for k in (*PAIR_FIELDS, "cohort", "recording")):
            raise ValueError(f"{ident} native joint and clock had different requests")
        if row["result"]["status"] in ("ok", "withheld"):
            if not row["result"]["metrics"].get("fixed_assignment_clock"):
                raise ValueError(f"{ident} did not run the frozen clock fit")
            if row["observation_sha256"] != control.get("observation_sha256"):
                raise ValueError(f"{ident} native joint and clock rebuilt different Graphs")


def compare(rows, candidate, stock, truth):
    for row in rows:
        arm, ident = row["arm"], row["id"]
        control = stock[ident]
        clock = candidate[ident]["result"]["metrics"]
        data = shared.geodata(control, arm, truth[row["recording"]])
        row.update(
            joint_status=data["status"],
            joint_reason=data["reason"],
            exact_graph=bool(candidate[ident].get("observation_sha256")),
            clock_held_rf_rms_hz=clock.get("held_by_arm", {}).get(arm, {}).get("held_rf_rms_hz"),
            **{f"joint_{key}": data[key] for key in METRICS},
        )


def comparisons(rows):
    output = []
    for cohort in ("roof", "omitted"):
        for dataset in ("all", "DS26", "DS29"):
            for arm in ARMS:
                group = [
                    r
                    for r in rows
                    if r["cohort"] == cohort
                    and r["arm"] == arm
                    and dataset in ("all", r["dataset"])
                ]
                if not group:
                    continue
                matched = [r for r in group if r["exact_graph"]]
                pairs = [
                    (r["error_km"], r["joint_error_km"])
                    for r in matched
                    if r["error_km"] is not None and r["joint_error_km"] is not None
                ]
                controls = dict(
                    statuses=dict(Counter(r["joint_status"] for r in group)),
                    within_km=thresholds([r["joint_error_km"] for r in group]),
                    worker_boundary="Historical native joint replay with verified Graph bindings",
                    **{key: distribution(r[f"joint_{key}"] for r in group) for key in METRICS},
                )
                output.append(
                    dict(
                        cohort=cohort,
                        dataset=dataset,
                        arm=arm,
                        scheduled=len(group),
                        exact_graph=len(matched),
                        joint=controls,
                        publication_pairs=dict(
                            Counter(f"clock_{r['status']}_joint_{r['joint_status']}" for r in group)
                        ),
                        paired_accuracy=phase._pair_summary(pairs),
                        held_rf_rms_hz_clock=distribution(r["clock_held_rf_rms_hz"] for r in group),
                        clock_minus_joint={
                            key: distribution(
                                r[key] - r[f"joint_{key}"]
                                for r in matched
                                if r[key] is not None and r[f"joint_{key}"] is not None
                            )
                            for key in METRICS
                        },
                    )
                )
    return output


def prepared_overlap(plan, predictions, cache):
    for filename, checksum in plan["prepared_locks"].items():
        if phase.digest(trial.PREPARED / filename) != checksum:
            raise ValueError("prepared clock locks changed after the native run was frozen")
    input_lock = phase._read(trial.PREPARED / "input-lock.json")["inputs"]
    by_offer = {(r["recording"], encoded(r["tile"])): r for r in predictions.values()}
    comparisons = []
    for cohort in trial.COHORTS:
        folder = trial.PREPARED / cohort
        lock = phase._read(folder / "prediction-lock.json")
        if lock["root_lock_sha256"] != plan["prepared_locks"]["prediction-lock.json"]:
            raise ValueError("prepared subset differs from the frozen root lock")
        trial.base.secant_full._verify_files(folder, lock["files"])
        records = read_predictions(folder / "joint_clock_model.jsonl.gz")
        if set(records) != set(lock["cases"]):
            raise ValueError("the prepared cohort differs from its frozen roster")
        for ident, prior in records.items():
            key = prior["recording"], encoded(prior["tile"])
            current = by_offer.get(key)
            row = dict(id=ident, cohort=cohort, matched_offer=bool(current))
            if current:
                mode = "wrong-region" if cohort == "wrong_offer" else "matched-tile"
                packet, origins = load_prepared(prior["recording"], mode, cache)
                if (
                    prior["input_sha256"] != phase.corpus._sha(encoded(packet))
                    or prior["input_sha256"] != input_lock[ident]["input_sha256"]
                    or any(prior[k] != value for k, value in origins.items())
                    or current["native_sha256"] != prior["native_sha256"]
                    or current["catalog_sha256"] != prior["catalog_sha256"]
                    or packet["offer"] != current["tile"]
                ):
                    raise ValueError(f"{ident} prepared clock input differs from its exact seal")
                # Prepared storage adds a newline. The streaming worker hashes canonical JSON.
                graph = phase.corpus._sha(encoded(packet["observation"]))
                exact = graph == current.get("observation_sha256")
                old, new = prior["result"], current["result"]
                row.update(
                    native_query_id=current["id"],
                    exact_graph=exact,
                    native_graph=current.get("observation_sha256"),
                    prepared_canonical_graph=graph,
                    native_input_sha256=current["input_sha256"],
                    prepared_input_sha256=prior["input_sha256"],
                    prepared_status=old["status"],
                    native_status=new["status"],
                    exact_decision_and_arms=all(
                        old.get(k) == new.get(k) for k in ("status", "reason", "arms")
                    ),
                    arms={
                        arm: dict(
                            forced_endpoint_delta_km=distance_km(
                                new["arms"][arm].get("forced_latlon"),
                                old["arms"][arm].get("forced_latlon"),
                            ),
                            native_objective=new["arms"][arm].get("frequency_score"),
                            prepared_objective=old["arms"][arm].get("frequency_score"),
                        )
                        for arm in ARMS
                    },
                )
            comparisons.append(row)
    return comparisons


def figures(output, predictions, queries, lock, stock_sha):
    specs = []
    for cohort in ("roof", "omitted"):
        omitted = cohort == "omitted"
        cases = [i for i, r in predictions.items() if r["cohort"] == cohort]
        files = lock["files"] | {JOINT: stock_sha}
        spec = dict(
            id=f"native_clock_full-{cohort}",
            method=trial.METHOD,
            scope="transfer" if omitted else "roof",
            title="Native smooth oscillator with omitted tiles"
            if omitted
            else "Native smooth oscillator on 135 roof recordings",
            caption="Complete archived native factors and matched native joint orbit controls.",
            cases=cases,
            seal=f"{cohort}-figure-lock.json",
            series=[
                dict(
                    key="candidate" if omitted else "one",
                    label="Native smooth oscillator",
                    file=PREDICTIONS,
                    value=trial.METHOD,
                    where=dict(cohort=cohort),
                ),
                dict(
                    key="stock",
                    label="Archived native joint orbit fit",
                    file=JOINT,
                    value=shared.METHOD,
                    where=dict(cohort=cohort),
                    match=list(PAIR_FIELDS),
                ),
            ],
        )
        if all(predictions[ident].get("observation_sha256") for ident in cases):
            spec["series"][1]["match"].append("observation_sha256")
        if omitted:
            spec["queries"] = "omitted-queries.json"
            save_json(output / spec["queries"], dict(queries=queries))
            files[spec["queries"]] = phase.digest(output / spec["queries"])
        save_json(output / spec["seal"], dict(cases=cases, files=files))
        specs.append(spec)
    save_json(output / "figures.json", dict(version=1, charts=specs))


def score(output, cache):
    lock = phase._read(output / "prediction-lock.json")
    trial.base.secant_full._verify_files(output, lock["files"])
    plan = phase._read(output / "plan.json")
    reference = trial.panel.REPORT / "prediction-lock.json"
    if phase.digest(reference) != plan["native_joint_lock_sha256"]:
        raise ValueError("the native joint control lock changed")
    trial.base.secant_full._verify_files(reference.parent, phase._read(reference)["files"])
    candidate = read_predictions(output / PREDICTIONS)
    stock = read_predictions(reference.parent / PREDICTIONS)
    if set(candidate) != set(lock["cases"]):
        raise ValueError("unexpected oscillator prediction roster")
    verified_pairs(candidate, stock)
    rows, queries = shared.matched_score_rows(candidate, plan, solver_stage="clock_backend")
    truth = {
        r["id"]: r["truth"]
        for panel in ("ds26-common127", "roof16")
        for r in phase.corpus.references(panel)
    }
    compare(rows, candidate, stock, truth)
    overlap = prepared_overlap(plan, candidate, cache)
    shared.csv_file(output / "scores.csv", rows)
    save_json(output / "prepared-overlap.json", dict(queries=overlap))
    save_json(
        output / "summary.json",
        dict(
            replay=lock["run"],
            groups=shared.summarize(rows),
            native_joint_comparison=comparisons(rows),
            c_ablation=shared.ablation(rows),
        ),
    )
    stock_sha = shared.pack(output, JOINT, stock.values())
    figures(output, candidate, queries, lock, stock_sha)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--work", type=Path, default=trial.WORK)
    cli.add_argument("--bundle", type=Path, default=trial.base.BUNDLE)
    cli.add_argument("--output", type=Path, default=trial.REPORT)
    args = cli.parse_args()
    shared.seal(
        args.work,
        args.bundle,
        args.output,
        prepare=trial.prepare,
        method=trial.METHOD,
        fail=trial.failed,
    )
    score(args.output, args.work / "prepared-cache")


if __name__ == "__main__":
    main()
