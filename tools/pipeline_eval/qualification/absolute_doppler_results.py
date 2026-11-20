"""Score sealed absolute-Doppler attempts and create standard position charts."""

import argparse
import gzip
import json
from pathlib import Path

from ..__main__ import save_json
from ..scoring import ARMS, ROLES, distance_km
from . import absolute_doppler_trial as trial
from .armijo_finish_results import pack
from .native_joint_full_results import original_scores, roi_margin
from .prefix_figures import csv_file

OUT = trial.OUT
MATCH = ("native_sha256", "catalog_sha256", "input_sha256", "original_request_sha256")
PREDICTIONS = "positions.jsonl.gz"


def read_predictions():
    with gzip.open(OUT / PREDICTIONS, "rt") as stream:
        return [json.loads(line) for line in stream]


def calibration_support(arms):
    for k in ("selected_norads", "train_aliases", "held_points", "c_identifiable"):
        if arms["c0"].get(k) != arms["fitted_c"].get(k):
            raise ValueError(f"calibration comparison has different {k}")
    if arms["c0"].get("c_identifiable") is False:
        for k in ("rf_rms_hz", "held_rms_hz", "forced_latlon", "latlon"):
            if arms["c0"].get(k) != arms["fitted_c"].get(k):
                raise ValueError(f"unidentifiable calibration altered {k}")


def authority(work, plan):
    original = trial.prior.archive.base.secant_full.REPORT
    trial.verify(original, trial.read(original / "receipt.json")["files"])
    source = trial.prior.archive.REPORT
    trial.verify(source, trial.read(source / "omitted-figure-lock.json")["files"])
    labels = work / "private/labels.json"
    if trial.digest(labels.read_bytes()) != plan["private_labels_sha256"]:
        raise ValueError("simulated truth differs from pre-inference commitment")
    seed = (work / "private/seed.bin").read_bytes()
    if trial.digest(seed) != plan["seed_sha256"]:
        raise ValueError("simulated seed differs from pre-inference commitment")
    save_json(OUT / "synthetic-truth.json", dict(seed_hex=seed.hex(), captures=trial.read(labels)))
    refs = {
        row["id"]: row
        for panel in ("ds26-common127", "roof16")
        for row in trial.prior.archive.base.phase.corpus.references(panel)
    }
    return (
        refs,
        trial.read(original / "original-v5-inputs.json"),
        {row["id"]: row for row in trial.read(source / "omitted-queries.json")["queries"]},
        trial.read(labels),
    )


def score(work):
    lock = trial.read(OUT / "prediction-lock.json")
    trial.verify(OUT, lock["files"])
    plan = trial.read(OUT / "blind-plan.json")
    refs, original, omitted, synthetic = authority(work, plan)
    rows = read_predictions()
    records = {(r["id"], r["method"]): r for r in rows}
    if len(rows) != len(records) or set(records) != {
        (q["id"], method) for q in plan["cases"] for method in trial.METHODS
    }:
        raise ValueError("predictions omit or repeat a planned attempt")
    scores, panels = [], {}
    for q in plan["cases"]:
        ident, case, cohort = (q[k] for k in ("id", "recording", "cohort"))
        a = records[ident, trial.METHODS[0]]
        control = {}
        synthetic_case = cohort.startswith("simulated-")
        reference = synthetic[case]["latlon"] if synthetic_case else refs[case]["truth"]
        active = {e["norad"] for e in synthetic[case]["emitters"]} if synthetic_case else None
        panel = "simulated" if synthetic_case else cohort
        if cohort in ("diagnostic", "reserve"):
            control = original_scores(ident, refs[case], original[case], reference)
        if cohort == "omitted":
            check = omitted[ident]
            if reference != check["truth"] or any(
                a["original_request_sha256" if k == "input_sha256" else k] != v
                for k, v in check["bindings"].items()
            ):
                raise ValueError("wrong offer differs from the original digest-bound query")
        if cohort != "null" and (roi_margin(reference, q["tile"]) >= 0) != (
            cohort in ("diagnostic", "reserve", "simulated-present")
        ):
            raise ValueError("offer does not have its prespecified relation to truth")
        panels.setdefault(panel, []).append(
            dict(
                id=ident,
                recording=case,
                truth=reference,
                condition=cohort,
                bindings={k: a[k] for k in MATCH},
            )
        )
        for method in trial.METHODS:
            r = records[ident, method]
            if any(r[k] != a[k] for k in MATCH) or any(r[k] != v for k, v in q.items()):
                raise ValueError("paired prediction differs from the planned native input")
            data = r["result"]
            calibration_support(data["arms"])
            distances = [
                distance_km(p, reference) for p in data["metrics"].get("evaluated_points", [])
            ]
            for arm in ARMS:
                v = data["arms"][arm]
                scores.append(
                    dict(
                        id=ident,
                        recording=case,
                        cohort=cohort,
                        method=method,
                        arm=arm,
                        status=data["status"],
                        reason=data["reason"],
                        forced_error_km=distance_km(v.get("forced_latlon"), reference),
                        error_km=distance_km(v.get("latlon"), reference),
                        nearest_evaluated_km=min(distances, default=None),
                        nearest_coarse_km=min(
                            distances[: data["metrics"].get("coarse_sites", 0)], default=None
                        ),
                        tile_error_km=distance_km(q["tile"]["center"], reference),
                        conditional_rf_rms_hz=v.get("rf_rms_hz"),
                        held_rf_rms_hz=v.get("held_rms_hz"),
                        held_points=v.get("held_points"),
                        held_orbits=v.get("held_good_orbits"),
                        held_lead=v.get("held_geographic_lead"),
                        c_hz_per_ghz=v.get("c_hz_per_ghz"),
                        synthetic_active_families_recovered=(
                            len(active & set(v.get("selected_norads", [])))
                            if active is not None
                            else None
                        ),
                        selected_arcs=data["metrics"].get("selected_arcs"),
                        world_sites=data["metrics"].get("world_sites"),
                        wall_s=r.get("native_elapsed_s"),
                        worker_s=r.get("worker_s"),
                        cpu_s=r.get("cpu_s"),
                        rss_kib=r.get("peak_rss_kib"),
                        reused_offer_only=r["reused_offer_only"],
                        **{
                            role + "_error_km": control[role][arm][0] if role in control else None
                            for role in ROLES
                        },
                        **{
                            role + "_rf_rms_hz": control[role][arm][1] if role in control else None
                            for role in ROLES
                        },
                    )
                )
    for pair in (
        [r for r in rows if r["recording"] == case and r["method"] == method]
        for case in synthetic
        for method in trial.METHODS
    ):
        first, replay = pair
        if first["input_sha256"] != replay["input_sha256"] or first["result"] != replay["result"]:
            raise ValueError("scoring-only synthetic offer changed inference")
    save_json(OUT / "scores.json", dict(rows=scores, source=lock["files"][PREDICTIONS]))
    csv_file(OUT / "scores.csv", scores)
    cards(panels, lock["files"])
    return scores


def cards(panels, frozen):
    provenance = ["blind-plan.json", "prediction-lock.json", "scores.json", "synthetic-truth.json"]
    sources = {name: trial.digest((OUT / name).read_bytes()) for name in provenance} | frozen
    descriptions = [
        (
            "diagnostic",
            "Absolute Doppler from anonymous GLRT on diagnostic recordings",
            "The new methods search worldwide. V5 receives the containing offer.",
        ),
        (
            "reserve",
            "Absolute Doppler on four preselected held roof recordings",
            "Both methods search worldwide and retain forced positions.",
        ),
        (
            "omitted",
            "Site-free absolute Doppler with real omitted offers",
            "The two authentic offers are used for scoring only. No omitted-offer v5 comparison.",
        ),
        (
            "simulated",
            "Absolute Doppler at new simulated locations",
            "Two independent simulated sites. Each uses the same predictions for both offers.",
        ),
        (
            "null",
            "Absolute Doppler with the causal orbits shifted by 120 seconds",
            "DS26-0122 RF observations with displaced orbital prediction times.",
        ),
    ]
    cards = []
    for name, title, caption in descriptions:
        transfer = name not in ("diagnostic", "reserve")
        cases = [q["id"] for q in panels[name]]
        seal = name + "-figure-lock.json"
        card = dict(
            id=f"{trial.model.METHOD}-{name}",
            method=trial.model.METHOD,
            scope="transfer" if transfer else "roof",
            cases=cases,
            title=title,
            caption=caption,
            seal=seal,
            provenance=provenance,
            series=[],
        )
        for key, method, label in zip(
            ("candidate" if transfer else "one", "stock"),
            trial.METHODS,
            ("Shared clock level", "Free arc intercept"),
            strict=True,
        ):
            line = dict(
                key=key,
                value=method,
                label=label + " · publication",
                file=PREDICTIONS,
                where={"cohort": (name if name != "simulated" else "simulated-present")},
            )
            if name == "simulated":
                # Include both scored conditions by their shared dedicated JSONL below.
                line.pop("where")
                line["file"] = "simulated-positions.jsonl.gz"
            if transfer or method == trial.model.METHOD:
                line["forced_label"] = label + " · forced"
            if key == "stock":
                line["match"] = list(MATCH)
            card["series"].append(line)
        files = sources.copy()
        if name == "simulated":
            name_file = "simulated-positions.jsonl.gz"
            records = read_predictions()
            files[name_file] = pack(OUT, name_file, [r for r in records if r["id"] in cases])
        if transfer:
            query = name + "-queries.json"
            save_json(OUT / query, dict(queries=panels[name]))
            files[query] = trial.digest((OUT / query).read_bytes())
            card["queries"] = query
        save_json(OUT / seal, dict(cases=cases, files=files))
        cards.append(card)
    save_json(OUT / "figures.json", dict(version=1, charts=cards))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    args = parser.parse_args()
    score(args.work)


if __name__ == "__main__":
    main()
