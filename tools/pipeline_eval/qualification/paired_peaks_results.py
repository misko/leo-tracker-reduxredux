"""Score and stage actual native paired-peak positions for the shared atlas."""

import gzip
import json
from collections import Counter

from ..__main__ import read_predictions, save_json
from ..scoring import ARMS, ROLES, distribution
from . import paired_peaks_trial as trial
from .native_joint_full_results import original_scores, roi_margin
from .native_joint_results import geodata
from .prefix_figures import csv_file

OUT = trial.OUTPUT
MATCH = ("input_sha256", "original_request_sha256", "native_sha256", "catalog_sha256")
METHODS = ("paired_peaks", "peak_paths", "folded_doppler")


def main():
    lock = trial.prior.read(OUT / "prediction-lock.json")
    archive = trial.prior.archive
    archive.base.secant_full._verify_files(OUT, lock["files"])
    candidate = read_predictions(OUT / "positions.jsonl.gz")
    negative = read_predictions(OUT / "misaligned-position.jsonl.gz")[trial.NULL]
    with gzip.open(OUT / "control-positions.jsonl.gz", "rt") as stream:
        controls = {(r["id"], r["method"]): r for r in map(json.loads, stream)}
    with gzip.open(OUT / "selected-paths.jsonl.gz", "rt") as stream:
        paths = {r["id"]: r["paths"] for r in map(json.loads, stream)}
    for label, curves in paths.items():
        row = negative if label == trial.NULL else candidate[label]
        visits = [key for entry in curves for key in entry["visit_ids"]]
        if len(set(visits)) != len(visits) or len(visits) != row["result"]["metrics"].get(
            "selected_points", 0
        ):
            raise ValueError("fused receiver visits were duplicated or missing")
    refs = {
        r["id"]: r
        for panel in ("ds26-common127", "roof16")
        for r in archive.base.phase.corpus.references(panel)
    }
    root = archive.base.secant_full.REPORT
    receipt = trial.prior.read(root / "receipt.json")
    archive.base.secant_full._verify_files(root, receipt["files"])
    roof = trial.prior.read(root / "original-v5-inputs.json")
    queries_lock = trial.prior.read(archive.REPORT / "omitted-figure-lock.json")
    archive.base.secant_full._verify_files(archive.REPORT, queries_lock["files"])
    source_queries = {
        q["id"]: q for q in trial.prior.read(archive.REPORT / "omitted-queries.json")["queries"]
    }
    scores, queries = [], []
    for case, row in candidate.items():
        ref = refs[row["recording"]]
        truth, cohort = ref["truth"], row["cohort"]
        if cohort == "omitted":
            q = source_queries[case]
            if (
                roi_margin(truth, row["tile"]) >= 0
                or truth != q["truth"]
                or any(
                    row["original_request_sha256"] != v if k == "input_sha256" else row.get(k) != v
                    for k, v in q["bindings"].items()
                )
            ):
                raise ValueError("omitted tile differs from its authenticated request")
            queries.append(dict(q, bindings={k: row[k] for k in MATCH}))
            roles = {}
        else:
            if roi_margin(truth, row["tile"]) < 0:
                raise ValueError("matched offer does not contain the released site")
            roles = original_scores(case, ref, roof[case], truth)
        for method in METHODS:
            fit = row if method == "paired_peaks" else controls[case, method]
            if fit["tile"] != row["tile"] or any(row[k] != fit[k] for k in MATCH):
                raise ValueError(
                    "comparison has different native factors, offer or orbit catalogue"
                )
            for arm in ARMS:
                value = geodata(
                    dict(
                        fit,
                        worker_wall_s=fit["native_elapsed_s"],
                        resident_peak_kib=fit.get("peak_rss_kib"),
                        worker={"cpu_s": fit.get("cpu_s")},
                    ),
                    arm,
                    truth,
                )
                detail = fit["result"]["arms"][arm]
                scores.append(
                    dict(
                        id=case,
                        cohort=cohort,
                        method=method,
                        arm=arm,
                        **value,
                        held_points=detail.get("held_points"),
                        held_rf_rms_hz=detail.get("held_rms_hz"),
                        **{
                            role + "_error_km": roles[role][arm][0] if role in roles else None
                            for role in ROLES
                        },
                        **{
                            role + "_rf_rms_hz": roles[role][arm][1] if role in roles else None
                            for role in ROLES
                        },
                    )
                )
    totals = []
    for cohort, method, arm in sorted({(r["cohort"], r["method"], r["arm"]) for r in scores}):
        group = [r for r in scores if (r["cohort"], r["method"], r["arm"]) == (cohort, method, arm)]
        totals.append(
            dict(
                cohort=cohort,
                method=method,
                arm=arm,
                total=len(group),
                status=dict(Counter(r["status"] for r in group)),
                **{
                    k: distribution(r[k] for r in group)
                    for k in (
                        "error_km",
                        "forced_error_km",
                        "conditional_rms_hz",
                        "held_rf_rms_hz",
                        "worker_cpu_s",
                        "worker_wall_s",
                        "peak_rss_kib",
                    )
                },
            )
        )
    csv_file(OUT / "scores.csv", scores)
    save_json(OUT / "scores.json", dict(groups=totals, rows=scores, misaligned=negative))
    save_json(OUT / "omitted-queries.json", dict(queries=queries))
    provenance = ("blind-plan.json", "prediction-lock.json", "scores.json")
    files = dict(
        lock["files"],
        **{
            k: trial.prior.digest((OUT / k).read_bytes())
            for k in (*provenance, "omitted-queries.json")
        },
    )
    cards = []
    for cohort in ("diagnostic", "confirmation", "omitted"):
        keys = [case for case, row in candidate.items() if row["cohort"] == cohort]
        outside = cohort == "omitted"
        seal = cohort + "-figure-lock.json"
        names = (
            (
                "candidate" if outside else "one",
                "Paired GLRT peaks",
                "paired_peaks",
                "positions.jsonl.gz",
            ),
            ("stock", "Elapsed-time paths", "peak_paths", "control-positions.jsonl.gz"),
            (
                "one" if outside else "one_native_factors",
                "Folded Doppler",
                "folded_doppler",
                "control-positions.jsonl.gz",
            ),
        )
        series = []
        for key, label, method, path in names:
            s = dict(
                key=key,
                label=label + " · publication",
                file=path,
                value=method,
                where=dict(cohort=cohort),
            )
            if outside or method == "paired_peaks":
                s["forced_label"] = label + " · forced"
            if method != "paired_peaks":
                s["match"] = list(MATCH)
            series.append(s)
        card = dict(
            id="paired_peaks-" + cohort,
            method="paired_peaks",
            cases=keys,
            seal=seal,
            title={
                "diagnostic": "Paired GLRT peaks on diagnosed captures",
                "confirmation": "Paired GLRT peaks on reserves",
                "omitted": "Paired GLRT peaks on omitted offers",
            }[cohort],
            caption="Synchronized same-RF GLRT factors and one causal catalogue. "
            "All three receivers use the same original offered tile.",
            scope="transfer" if outside else "roof",
            series=series,
            provenance=list(provenance),
        )
        if outside:
            card["queries"] = "omitted-queries.json"
        save_json(OUT / seal, dict(cases=keys, files=files))
        cards.append(card)
    save_json(OUT / "figures.json", dict(version=1, charts=cards))


if __name__ == "__main__":
    main()
