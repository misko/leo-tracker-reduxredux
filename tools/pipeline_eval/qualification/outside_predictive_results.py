"""Score frozen held predictions and render their paired publication outcomes."""

import argparse
import json
from collections import Counter
from pathlib import Path

from ..__main__ import read_predictions, save_json, write
from ..scoring import ARMS, distance_km, distribution, thresholds
from . import native_joint_full_results as shared
from . import outside_predictive_trial as trial

phase = trial.phase
CANDIDATE, STOCK = trial.METHOD, trial.base.clock.METHOD
CONDITIONS = {
    "centered": "Centered",
    "original": "Original containing",
    "near-inside": "Near inside",
    "near-outside": "Near omission",
    "far-outside": "15 km omitted",
    "six-outside": "6 km omitted",
}


def verify(records, queries):
    old = trial.base.exterior.prior_cases()[1]
    observations = {}
    for ident, row in records.items():
        expected = trial.base.clock.bindings(queries[ident]) | {"method": CANDIDATE}
        if any(row[k] != value for k, value in expected.items()):
            raise ValueError("prediction used different native factors or tile")
        if row["result"]["status"] not in ("ok", "withheld"):
            continue
        fold = row["fold_receipts"]
        if len(fold) != 2 or any(
            fold[i]["train_peaks"] != fold[1 - i]["held_raw_peaks"] for i in (0, 1)
        ):
            raise ValueError("the captured time blocks are not reciprocal")
        digests = [row["observation_sha256"], *(r["train_graph_sha256"] for r in fold)]
        if observations.setdefault(row["recording"], digests) != digests:
            raise ValueError("changing the offer changed the Graphs for the same capture")
        if row["cohort"] == "archived-roof":
            prior = old[ident]
            if row["observation_sha256"] != prior["observation_sha256"] or any(
                row["initial"].get(k) != prior["result"].get(k)
                for k in ("status", "arms", "reason")
            ):
                raise ValueError("ordinary first fit differs from its exact sealed archive")


def score_rows(records, labels):
    rows = []
    for ident, row in records.items():
        label = labels[ident]
        initial, result = row.get("initial", row["result"]), row["result"]
        decisions = row.get("folds", [{}, {}])
        timings = row.get("fold_receipts", [])
        for arm in ARMS:
            first, final = initial["arms"][arm], result["arms"][arm]
            data = dict(
                id=ident,
                arm=arm,
                cohort=row["cohort"],
                recording=row["recording"],
                source=label["source_label"],
                condition=label["condition"],
                truth_margin_km=label["margin_km"],
                initial_status=initial["status"],
                status=result["status"],
                reason=result.get("reason"),
                decision=row.get("outside_decision"),
                initial_error_km=distance_km(first.get("latlon"), label["truth"]),
                final_error_km=distance_km(final.get("latlon"), label["truth"]),
                initial_forced_error_km=distance_km(first.get("forced_latlon"), label["truth"]),
                ordinary_rms_hz=first.get("rf_rms_hz"),
                worker_wall_s=row.get("worker_wall_s"),
                worker_cpu_s=(row.get("worker") or {}).get("cpu_s"),
                peak_rss_kib=row.get("resident_peak_kib"),
                vm_peak_kib=(row.get("proc_memory_kib") or {}).get("VmPeak"),
                independent_wall_s=sum(
                    t[k]["wall_s"] for t in timings for k in ("training_time", "held_time")
                )
                if timings
                else None,
                independent_cpu_s=sum(
                    t[k]["cpu_s"] for t in timings for k in ("training_time", "held_time")
                )
                if timings
                else None,
            )
            for i, fold in enumerate(decisions):
                estimate = fold.get(arm, {})
                fit = timings[i]["train_arms"][arm].get("forced_latlon") if timings else None
                data.update(
                    {
                        f"fold{i}_{key}": value
                        for key, value in dict(
                            training_signed_tile_margin_km=shared.roi_margin(fit, row["tile"]),
                            training_forced_error_km=distance_km(fit, label["truth"]),
                            decision_status=estimate.get("status"),
                            held_orbits=estimate.get("held_orbits"),
                            held_units=estimate.get("held_units"),
                            held_peaks=estimate.get("held_peaks"),
                            exterior_gain=estimate.get("exterior_gain"),
                            interior_rf_hz=estimate.get("regions", {})
                            .get("inside", {})
                            .get("descriptive_best_held_rms_hz"),
                            exterior_rf_hz=estimate.get("regions", {})
                            .get("outside", {})
                            .get("descriptive_best_held_rms_hz"),
                        ).items()
                    }
                )
            rows.append(data)
    return rows


def aggregate(rows):
    out = []
    for cohort in ("fresh-synthetic", "archived-roof"):
        for arm in ARMS:
            all_rows = [r for r in rows if r["cohort"] == cohort and r["arm"] == arm]
            for label, selected in (
                ("all", all_rows),
                ("containing", [r for r in all_rows if r["truth_margin_km"] > 0]),
                ("omitted", [r for r in all_rows if r["truth_margin_km"] < 0]),
                *((c, [r for r in all_rows if r["condition"] == c]) for c in CONDITIONS),
            ):
                if not selected:
                    continue
                errors = [r["final_error_km"] for r in selected]
                out.append(
                    dict(
                        cohort=cohort,
                        arm=arm,
                        condition=label,
                        scheduled=len(selected),
                        captures=len({r["recording"] for r in selected}),
                        initial_decisions=dict(Counter(r["initial_status"] for r in selected)),
                        publication_decisions=dict(Counter(r["status"] for r in selected)),
                        held_classifications=dict(Counter(r["decision"] for r in selected)),
                        geographic_error_km=distribution(errors),
                        within_km=thresholds(errors),
                        **{
                            key: distribution(r[key] for r in selected)
                            for key in (
                                "ordinary_rms_hz",
                                "worker_wall_s",
                                "worker_cpu_s",
                                "peak_rss_kib",
                                "vm_peak_kib",
                                "independent_wall_s",
                                "independent_cpu_s",
                                "fold0_exterior_gain",
                                "fold1_exterior_gain",
                                "fold0_held_units",
                                "fold1_held_units",
                                "fold0_held_orbits",
                                "fold1_held_orbits",
                                "fold0_interior_rf_hz",
                                "fold1_interior_rf_hz",
                                "fold0_exterior_rf_hz",
                                "fold1_exterior_rf_hz",
                            )
                        },
                    )
                )
    return out


def manifests(output, records, labels, lock):
    for cohort in ("fresh-synthetic", "archived-roof"):
        group = [r for r in records.values() if r["cohort"] == cohort]
        folder = output / cohort
        files, queries = {}, []
        for row in group:
            label = labels[row["id"]]
            queries.append(
                dict(
                    id=row["id"],
                    condition=label["condition"],
                    recording=label["source_label"],
                    truth=label["truth"],
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
        plot = [
            dict(
                r,
                result=dict(
                    r["result"],
                    arms={a: dict(q, forced_latlon=None) for a, q in r["result"]["arms"].items()},
                ),
            )
            for r in group
        ]
        stock = [dict(r, method=STOCK, result=r.get("initial", r["result"])) for r in group]
        for method, rows in ((CANDIDATE, plot), (STOCK, stock)):
            name = f"{method}.jsonl.gz"
            files[name] = shared.pack(folder, name, rows)
        cases = [r["id"] for r in group]
        save_json(
            folder / "figure-lock.json",
            dict(
                cases=cases,
                files=files,
                main_prediction_sha256=lock["files"][f"{CANDIDATE}.jsonl.gz"],
            ),
        )
        seen = {r["condition"] for r in queries}
        spec = dict(
            id=f"native_outside_predictive-{cohort}",
            method=CANDIDATE,
            scope="transfer",
            title="Held Doppler at two new synthetic sites"
            if cohort == "fresh-synthetic"
            else "Held Doppler on measured roof offers",
            caption="Complementary held blocks with fixed calibration and matched held peaks.",
            cases=cases,
            seal="figure-lock.json",
            queries="figure-queries.json",
            condition_labels={k: v for k, v in CONDITIONS.items() if k in seen},
            series=[
                dict(
                    key="candidate",
                    label="Held exterior evidence",
                    file=f"{CANDIDATE}.jsonl.gz",
                    value=CANDIDATE,
                ),
                dict(
                    key="stock",
                    label="Native smooth",
                    forced_label="Smooth · forced",
                    file=f"{STOCK}.jsonl.gz",
                    value=STOCK,
                    match=["input_sha256", "tile"],
                ),
            ],
        )
        write(
            folder / "figures.json",
            json.dumps(dict(version=1, charts=[spec]), indent=2).encode() + b"\n",
        )


def score(output, work):
    lock = phase._read(output / "prediction-lock.json")
    trial.base.clock.base.secant_full._verify_files(output, lock["files"])
    plan = phase._read(output / "roster.json")
    oracle = work / "evaluator.json"
    if phase.digest(oracle) != plan["evaluator_sha256"]:
        raise ValueError("the blinded labels changed")
    write(output / "evaluator.json", oracle.read_bytes())
    labels = phase._read(oracle)["labels"]
    queries = {r["id"]: r for r in plan["cases"]}
    records = read_predictions(output / f"{CANDIDATE}.jsonl.gz")
    if not set(records) == set(queries) == set(labels) == set(lock["cases"]):
        raise ValueError("incomplete signed-region query pedigree")
    verify(records, queries)
    rows = score_rows(records, labels)
    shared.csv_file(output / "scores.csv", rows)
    save_json(output / "summary.json", dict(groups=aggregate(rows), elapsed_s=lock["elapsed_s"]))
    manifests(output, records, labels, lock)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output", type=Path, default=trial.REPORT)
    cli.add_argument("--work", type=Path, default=trial.WORK)
    args = cli.parse_args()
    score(args.output, args.work)


if __name__ == "__main__":
    main()
