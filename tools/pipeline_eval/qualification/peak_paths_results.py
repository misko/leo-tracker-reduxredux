"""Score sealed peak-path and graphless controls on the exact original offers."""

import gzip
import json
from collections import Counter

from ..__main__ import read_predictions, save_json
from ..scoring import ARMS, ROLES, distribution
from . import peak_paths_trial as trial
from .native_joint_full_results import original_scores, roi_margin
from .native_joint_results import geodata
from .prefix_figures import csv_file

OUTPUT = trial.OUTPUT
MATCH = ("native_sha256", "catalog_sha256", "input_sha256", "original_request_sha256")


def main():
    lock = trial.read(OUTPUT / "prediction-lock.json")
    trial.archive.base.secant_full._verify_files(OUTPUT, lock["files"])
    original = trial.read(OUTPUT / "first-pass/prediction-lock.json")
    trial.archive.base.secant_full._verify_files(OUTPUT / "first-pass", original["files"])
    plan = trial.read(OUTPUT / "elapsed-plan.json")
    first_pass_digest = trial.digest((OUTPUT / "first-pass/prediction-lock.json").read_bytes())
    if plan["first_pass_sha256"] != first_pass_digest:
        raise ValueError("first-pass source files differ from the elapsed experiment seal")
    methods = {
        "peak_paths": read_predictions(OUTPUT / "positions.jsonl.gz"),
        "folded_doppler": read_predictions(OUTPUT / "folded-positions.jsonl.gz"),
    }
    init = read_predictions(OUTPUT / "first-pass/positions.jsonl.gz")
    shuffled = read_predictions(OUTPUT / "shuffle-position.jsonl.gz")[trial.SHUFFLE]
    if (
        lock["cases"] != [r["id"] for r in plan["frames"]]
        or init.keys() != methods["peak_paths"].keys()
        or init.keys() != methods["folded_doppler"].keys()
    ):
        raise ValueError("scheduled peak and folded scopes differ")
    with gzip.open(OUTPUT / "path-traces.jsonl.gz", "rt") as stream:
        trace = {row["id"]: row["selected_paths"] for row in map(json.loads, stream)}
    for case, paths in trace.items():
        keys = [(p["lane"][0], k) for p in paths for k in p["visit_ids"]]
        if len(set(keys)) != len(keys):
            raise ValueError(f"{case} duplicates native support over orbital paths")
        paired = shuffled if case == trial.SHUFFLE else methods["peak_paths"][case]
        if len(keys) != paired["result"]["metrics"]["selected_points"]:
            raise ValueError("selected peak audit differs from the original inference")
    base = trial.archive.base
    refs = {
        r["id"]: r
        for panel in ("ds26-common127", "roof16")
        for r in base.phase.corpus.references(panel)
    }
    owner_root = base.secant_full.REPORT
    owner_seal = trial.read(owner_root / "receipt.json")
    base.secant_full._verify_files(owner_root, owner_seal["files"])
    originals = trial.read(owner_root / "original-v5-inputs.json")
    queries_file = trial.archive.REPORT / "omitted-queries.json"
    omitted_lock = trial.read(trial.archive.REPORT / "omitted-figure-lock.json")
    base.secant_full._verify_files(queries_file.parent, omitted_lock["files"])
    known_wrong = {r["id"]: r for r in trial.read(queries_file)["queries"]}
    scores, queries = [], []
    for case, a in methods["peak_paths"].items():
        b = methods["folded_doppler"][case]
        if a["tile"] != b["tile"] or any(a[k] != b[k] or a[k] != init[case][k] for k in MATCH):
            raise ValueError("candidate and control have different native handoffs")
        ref = refs[a["recording"]]
        truth, cohort = ref["truth"], a["cohort"]
        if cohort == "omitted":
            q = known_wrong[case]
            if (
                roi_margin(truth, a["tile"]) >= 0
                or q["truth"] != truth
                or any(a.get(k) != v for k, v in q["bindings"].items() if k != "input_sha256")
                or q["bindings"]["input_sha256"] != a["original_request_sha256"]
            ):
                raise ValueError("the omitted region does not match the archived wrong request")
            queries.append(dict(q, bindings={k: a[k] for k in MATCH}))
            original_rf = {}
        else:
            if roi_margin(truth, a["tile"]) < 0:
                raise ValueError("a matched tile excludes the released scoring reference")
            original_rf = original_scores(case, ref, originals[case], truth)
        for arm in ARMS:
            for candidate in (a, b):
                value = geodata(
                    dict(
                        candidate,
                        worker_wall_s=candidate["native_elapsed_s"],
                        worker={"cpu_s": candidate.get("cpu_s")},
                        resident_peak_kib=candidate.get("peak_rss_kib"),
                    ),
                    arm,
                    truth,
                )
                measure = candidate["result"]["arms"][arm]
                scores.append(
                    dict(
                        id=case,
                        cohort=cohort,
                        method=candidate["method"],
                        arm=arm,
                        held_rf_rms_hz=measure.get("held_rms_hz"),
                        held_points=measure.get("held_points"),
                        **value,
                        **{
                            f"{k}_error_km": original_rf[k][arm][0] if k in original_rf else None
                            for k in ROLES
                        },
                        **{
                            f"{k}_rf_rms_hz": original_rf[k][arm][1] if k in original_rf else None
                            for k in ROLES
                        },
                    )
                )
    summary = []
    for cohort, method, arm in sorted({(r["cohort"], r["method"], r["arm"]) for r in scores}):
        rows = [r for r in scores if (r["cohort"], r["method"], r["arm"]) == (cohort, method, arm)]
        summary.append(
            dict(
                cohort=cohort,
                method=method,
                arm=arm,
                count=len(rows),
                status=dict(Counter(r["status"] for r in rows)),
                **{
                    k: distribution(r[k] for r in rows)
                    for k in (
                        "error_km",
                        "forced_error_km",
                        "conditional_rms_hz",
                        "held_rf_rms_hz",
                        "worker_wall_s",
                        "worker_cpu_s",
                        "peak_rss_kib",
                    )
                },
            )
        )
    save_json(OUTPUT / "scores.json", dict(summary=summary, rows=scores, shuffle=shuffled))
    csv_file(OUTPUT / "scores.csv", scores)
    save_json(OUTPUT / "omitted-queries.json", dict(queries=queries))
    provenance = ("blind-plan.json", "elapsed-plan.json", "prediction-lock.json")
    files = dict(
        lock["files"],
        **{
            name: trial.digest((OUTPUT / name).read_bytes())
            for name in (
                "omitted-queries.json",
                "scores.json",
                *provenance,
            )
        },
    )
    figures = []
    for cohort in ("diagnostic", "confirmation", "omitted"):
        ids = [k for k, r in methods["peak_paths"].items() if r["cohort"] == cohort]
        outside = cohort == "omitted"
        filename = cohort + "-figure-lock.json"
        series = [
            dict(
                key="candidate" if outside else "one",
                file="positions.jsonl.gz",
                value="peak_paths",
                label="Temporal paths · published",
                forced_label="Temporal paths · forced",
                where=dict(cohort=cohort),
            ),
            dict(
                key="stock",
                file="folded-positions.jsonl.gz",
                value="folded_doppler",
                label="Folded Doppler · published",
                where=dict(cohort=cohort),
                match=list(MATCH),
            ),
        ]
        if outside:
            series[-1]["forced_label"] = "Folded Doppler · forced"
        card = dict(
            id="peak_paths-" + cohort,
            method="peak_paths",
            cases=ids,
            title={
                "diagnostic": "Ordered GLRT peak paths on diagnosed captures",
                "confirmation": "Ordered GLRT peak paths on reserve captures",
                "omitted": "Ordered GLRT peak paths on omitted offers",
            }[cohort],
            caption="Complete recorded GLRT candidates and one causal TLE with one tile. "
            "The folded comparator has one shared calibration estimate.",
            scope="transfer" if outside else "roof",
            seal=filename,
            provenance=list(provenance),
            series=series,
        )
        if outside:
            card["queries"] = "omitted-queries.json"
        save_json(OUTPUT / filename, dict(cases=ids, files=files))
        figures.append(card)
    save_json(OUTPUT / "figures.json", dict(version=1, charts=figures))


if __name__ == "__main__":
    main()
