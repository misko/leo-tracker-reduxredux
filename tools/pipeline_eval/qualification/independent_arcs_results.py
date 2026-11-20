"""Score sealed native arcs separately from the original roof roles and held RF."""

import gzip
import json
from collections import Counter

from ..__main__ import read_predictions, save_json
from ..scoring import ROLES, distribution
from . import independent_arcs_trial as trial
from .native_joint_full_results import original_scores, roi_margin
from .native_joint_results import geodata
from .prefix_figures import csv_file

MATCH = tuple(k for k in trial.MATCH if k != "tile")
OUT = trial.OUTPUT


def read_arms(row, truth):
    for arm, detail in row["result"]["arms"].items():
        yield (
            arm,
            geodata(
                dict(
                    row,
                    worker_wall_s=row["native_elapsed_s"],
                    resident_peak_kib=row.get("peak_rss_kib"),
                    worker={"cpu_s": row.get("cpu_s")},
                ),
                arm,
                truth,
            )
            | dict(
                held_points=detail.get("held_points"),
                held_rf_rms_hz=detail.get("held_rms_hz"),
                leave_orbit_max_shift_km=detail.get("leave_orbit_max_shift_km"),
                selected_orbits=row["result"]["metrics"].get("selected_orbits"),
            ),
        )


def main():
    archive = trial.prior.archive
    read = trial.prior.read
    verify = archive.base.secant_full._verify_files
    lock = read(OUT / "prediction-lock.json")
    verify(OUT, lock["files"])
    planned = read(OUT / "blind-plan.json")
    candidate = read_predictions(OUT / "positions.jsonl.gz")
    negative = read_predictions(OUT / "misaligned-position.jsonl.gz")[trial.NULL]
    with gzip.open(OUT / "control-positions.jsonl.gz", "rt") as stream:
        controls = {(r["id"], r["method"]): r for r in map(json.loads, stream)}
    if set(candidate) | {trial.NULL} != set(lock["cases"]) or len(controls) != 2 * len(candidate):
        raise ValueError("sealed denominator has unexpected attempts")
    if any(
        candidate[q["id"]].get(k) != v
        for q in planned["cases"]
        if q["id"] != trial.NULL
        for k, v in q.items()
    ):
        raise ValueError("sealed predictions diverge from prospective query bindings")
    refs = {
        r["id"]: r
        for panel in ("ds26-common127", "roof16")
        for r in archive.base.phase.corpus.references(panel)
    }
    original = archive.base.secant_full.REPORT
    verify(original, read(original / "receipt.json")["files"])
    roof = read(original / "original-v5-inputs.json")
    verify(archive.REPORT, read(archive.REPORT / "omitted-figure-lock.json")["files"])
    source_queries = {q["id"]: q for q in read(archive.REPORT / "omitted-queries.json")["queries"]}
    scores, queries = [], []
    for key, row in candidate.items():
        ref = refs[row["recording"]]
        truth, cohort = ref["truth"], row["cohort"]
        wrong = cohort == "omitted"
        if wrong:
            q = source_queries[key]
            if (
                roi_margin(truth, row["tile"]) >= 0
                or truth != q["truth"]
                or any(
                    row["original_request_sha256" if k == "input_sha256" else k] != v
                    for k, v in q["bindings"].items()
                )
            ):
                raise ValueError(f"{key} does not use the sealed omitted offer")
            queries.append(dict(q, bindings={k: row[k] for k in MATCH}))
            original_arms = {}
        else:
            if roi_margin(truth, row["tile"]) < 0:
                raise ValueError(f"{key} matched offer does not contain the released site")
            original_arms = original_scores(key, ref, roof[key], truth)
        for m in trial.METHODS:
            fit = row if m == trial.solver.METHOD else controls[key, m]
            if any(fit[k] != row[k] for k in trial.MATCH):
                raise ValueError(f"{key} and {m} do not use identical inputs")
            for arm, value in read_arms(fit, truth):
                roles = {}
                for role in ROLES:
                    error, rms = original_arms[role][arm] if role in original_arms else (None, None)
                    roles.update({f"{role}_error_km": error, f"{role}_rf_rms_hz": rms})
                scores.append(dict(id=key, cohort=cohort, method=m, arm=arm, **value, **roles))
    totals = []
    groups = sorted({(r["cohort"], r["method"], r["arm"]) for r in scores})
    for cohort, method, arm in groups:
        own = [r for r in scores if (r["cohort"], r["method"], r["arm"]) == (cohort, method, arm)]
        totals.append(
            dict(
                cohort=cohort,
                method=method,
                arm=arm,
                total=len(own),
                status=dict(Counter(r["status"] for r in own)),
                **{
                    k: distribution(r[k] for r in own)
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
    files = lock["files"] | {
        n: trial.prior.digest((OUT / n).read_bytes()) for n in (*provenance, "omitted-queries.json")
    }
    charts = []
    for cohort, title in (
        ("diagnostic", "Independent GLRT arcs on diagnosed captures"),
        ("confirmation", "Independent GLRT arcs on archive reserves"),
        ("omitted", "Independent GLRT arcs with the correct tile omitted"),
    ):
        outside = cohort == "omitted"
        cases = [key for key, row in candidate.items() if row["cohort"] == cohort]
        series = []
        for key, method, label, name in zip(
            (
                "candidate" if outside else "one",
                "one" if outside else "one_native_factors",
                "stock",
            ),
            trial.METHODS,
            ("Independent arcs", "Paired peaks", "Elapsed-time paths"),
            ("positions.jsonl.gz", "control-positions.jsonl.gz", "control-positions.jsonl.gz"),
            strict=True,
        ):
            curve = dict(
                key=key,
                label=f"{label} · publication",
                file=name,
                value=method,
                where=dict(cohort=cohort),
            )
            if outside or method == trial.solver.METHOD:
                curve["forced_label"] = f"{label} · forced"
            if method != trial.solver.METHOD:
                curve["match"] = list(MATCH)
            series.append(curve)
        seal = cohort + "-figure-lock.json"
        card = dict(
            id=f"independent_arcs-{cohort}",
            method=trial.solver.METHOD,
            title=title,
            caption="Full anonymous native GLRT and one causal TLE on the same 25 km offer. "
            "Pair evidence keeps unmatched receiver visits and checks identities on held time.",
            cases=cases,
            series=series,
            seal=seal,
            provenance=list(provenance),
            scope="transfer" if outside else "roof",
        )
        if outside:
            card["queries"] = "omitted-queries.json"
        save_json(OUT / seal, dict(cases=cases, files=files))
        charts.append(card)
    save_json(OUT / "figures.json", dict(version=1, charts=charts))


if __name__ == "__main__":
    main()
