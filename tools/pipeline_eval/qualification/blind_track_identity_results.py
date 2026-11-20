"""Score sealed anonymous identity trials and build standard atlas cards."""

import gzip
import json

from ..__main__ import save_json
from ..scoring import ARMS, ROLES, distance_km
from . import blind_track_identity_trial as trial
from .armijo_finish_results import pack
from .native_joint_full_results import original_scores, roi_margin
from .prefix_figures import csv_file

OUT = trial.OUT
MATCH = tuple(k for k in trial.MATCH if k != "tile") + ("original_request_sha256",)


def get_rows(name):
    with gzip.open(OUT / name, "rt") as data:
        return list(map(json.loads, data))


def score():
    lock = trial.read(OUT / "prediction-lock.json")
    verify = trial.prior.archive.base.secant_full._verify_files
    verify(OUT, lock["files"])
    archived = trial.prior.archive.REPORT
    original = trial.prior.archive.base.secant_full.REPORT
    verify(original, trial.read(original / "receipt.json")["files"])
    verify(archived, trial.read(archived / "omitted-figure-lock.json")["files"])
    known = {q["id"]: q for q in trial.read(archived / "omitted-queries.json")["queries"]}
    site_lock = trial.read(trial.SITE_REPORT / "input-lock.json")
    plan = trial.read(OUT / "blind-plan.json")
    if (
        plan["simulated_lock_sha256"]
        != trial.digest((trial.SITE_REPORT / "input-lock.json").read_bytes())
        or trial.digest((trial.SITE_REPORT / "labels.json").read_bytes())
        != site_lock["files"]["private/labels.json"]
    ):
        raise ValueError("synthetic truth differs from the earlier measurement commitment")
    labels = trial.read(trial.SITE_REPORT / "labels.json")
    official = {
        r["id"]: r
        for panel in ("ds26-common127", "roof16")
        for r in trial.prior.archive.base.phase.corpus.references(panel)
    }
    controls = trial.read(original / "original-v5-inputs.json")
    predictions = {(r["id"], r["method"]): r for r in get_rows("positions.jsonl.gz")}
    (negative,) = get_rows("shuffle-position.jsonl.gz")
    result, transfers = [], dict(omitted=[], simulated=[])
    for q in plan["cases"]:
        case, cohort = q["id"], q["cohort"]
        if case == trial.NULL:
            if negative["id"] != case or not negative["shuffle"]:
                raise ValueError("wrong held control")
            continue
        base = predictions[case, trial.model.METHOD]
        if any(base[k] != v for k, v in q.items()):
            raise ValueError("prediction differs from its prospective binding")
        fits = {}
        if cohort.startswith("simulated-"):
            label = labels[case]
            if label["capture_id"] != q["recording"] or "simulated-" + label["condition"] != cohort:
                raise ValueError("simulated offer scope changed")
            truth = label["latlon"]
            transfers["simulated"].append(
                dict(
                    id=case,
                    recording=q["recording"],
                    truth=truth,
                    condition=label["condition"],
                    bindings={k: base[k] for k in MATCH},
                    eligible=True,
                )
            )
        else:
            ref = official[q["recording"]]
            truth = ref["truth"]
            if cohort == "omitted":
                old = known[case]
                if old["truth"] != truth or any(
                    base["original_request_sha256" if k == "input_sha256" else k] != v
                    for k, v in old["bindings"].items()
                ):
                    raise ValueError(
                        "real wrong tile differs from the authenticated archived request"
                    )
                transfers["omitted"].append(dict(old, bindings={k: base[k] for k in MATCH}))
            else:
                fits = original_scores(case, ref, controls[case], truth)
        included = roi_margin(truth, q["tile"]) >= 0
        if included != (cohort in ("diagnostic", "reserve", "simulated-present")):
            raise ValueError("tile reason disagrees with the released location")
        tile_error = distance_km(q["tile"]["center"], truth)
        for method in trial.METHODS[:2] if cohort.startswith("simulated-") else trial.METHODS:
            r = predictions[case, method]
            if any(r[k] != base[k] for k in (*MATCH, "tile")):
                raise ValueError(f"{case}/{method} control used different samples")
            metrics = r["result"]["metrics"]
            for arm in ARMS:
                endpoint = r["result"]["arms"][arm]
                result.append(
                    dict(
                        id=case,
                        cohort=cohort,
                        method=method,
                        arm=arm,
                        tile_error_km=tile_error,
                        used_matching_tile=included,
                        status=r["result"]["status"],
                        reason=r["result"]["reason"],
                        error_km=distance_km(endpoint.get("latlon"), truth),
                        forced_error_km=distance_km(endpoint.get("forced_latlon"), truth),
                        c_hz_per_ghz=endpoint.get("c_hz_per_ghz"),
                        conditional_rms_hz=endpoint.get("rf_rms_hz"),
                        held_rms_hz=endpoint.get("held_rms_hz"),
                        held_points=endpoint.get("held_points"),
                        held_orbits=endpoint.get("held_orbits"),
                        selected_arcs=metrics.get("selected_arcs", metrics.get("selected_paths")),
                        wall_s=r["native_elapsed_s"],
                        cpu_s=r.get("cpu_s"),
                        rss_kib=r.get("peak_rss_kib"),
                        **{
                            role + "_error_km": fits[role][arm][0] if role in fits else None
                            for role in ROLES
                        },
                        **{
                            role + "_rf_rms_hz": fits[role][arm][1] if role in fits else None
                            for role in ROLES
                        },
                    )
                )
    csv_file(OUT / "scores.csv", result)
    save_json(OUT / "scores.json", dict(rows=result, shuffle=negative))
    for label, items in transfers.items():
        save_json(OUT / f"{label}-queries.json", dict(queries=items))
    provenance = ("blind-plan.json", "prediction-lock.json", "scores.json")
    files = lock["files"] | {
        name: trial.digest((OUT / name).read_bytes())
        for name in (*provenance, "omitted-queries.json", "simulated-queries.json")
    }
    charts = []
    panels = (
        ("diagnostic", "Cross-track orbit identities on two diagnostics"),
        ("reserve", "Cross-track orbit identities on archive reserves"),
        ("omitted", "Cross-track orbit identities with the true tile omitted"),
        ("simulated", "Cross-track orbit identities at two simulated sites"),
    )
    for label, title in panels:
        sim = label == "simulated"
        omitted = label == "omitted"
        outside = sim or omitted
        cases = [
            q["id"]
            for q in plan["cases"]
            if q["cohort"] == label or (sim and q["cohort"].startswith("simulated-"))
        ]
        figure_seal = label + "-figure-lock.json"
        series = []
        for key, method, name in zip(
            ("candidate", "stock", "one") if outside else ("one", "stock", "one_native_factors"),
            trial.METHODS,
            ("Cross-track clock", "Local arc clock", "Independent arcs"),
            strict=True,
        ):
            if sim and method == trial.METHODS[2]:
                continue
            where = {} if sim else {"cohort": label}
            item = dict(
                key=key,
                label=name + " · publication",
                file="positions.jsonl.gz",
                value=method,
                where=where,
            )
            if outside or method == trial.model.METHOD:
                item["forced_label"] = name + " · forced"
            if method != trial.model.METHOD:
                item["match"] = list(MATCH)
            if sim:
                item["file"] = "simulated-positions.jsonl.gz"
            series.append(item)
        caption = "Complete native GLRT peaks and causal TLE with one 25 km offer. "
        if sim:
            caption = (
                "Simulated native GLRT with archived measured CFO disturbances. "
                "Each site has its original containing and near-missing offer."
            )
            files["simulated-positions.jsonl.gz"] = pack(
                OUT,
                "simulated-positions.jsonl.gz",
                [r for r in predictions.values() if r["cohort"].startswith("simulated-")],
            )
        card = dict(
            id=f"{trial.model.METHOD}-{label}",
            method=trial.model.METHOD,
            scope="transfer" if outside else "roof",
            title=title,
            caption=caption,
            cases=cases,
            seal=figure_seal,
            provenance=list(provenance),
            series=series,
        )
        if outside:
            card["queries"] = label + "-queries.json"
        if sim:
            card["condition_labels"] = {
                "present": "Containing offer",
                "missing-near": "Near missed offer",
            }
        save_json(OUT / figure_seal, dict(cases=cases, files=files))
        charts.append(card)
    save_json(OUT / "figures.json", dict(version=1, charts=charts))
    return result


if __name__ == "__main__":
    score()
