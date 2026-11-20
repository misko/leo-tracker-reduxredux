"""Score turning-point feasibility and render honest stage-only positions."""

import argparse
import gzip
import json
from pathlib import Path

from ..__main__ import save_json
from ..scoring import ARMS, ROLES
from . import doppler_turns_trial as trial
from .absolute_doppler_results import MATCH
from .armijo_finish_results import pack
from .native_joint_full_results import original_scores, roi_margin
from .prefix_figures import csv_file

OUT, world = trial.OUT, trial.world
METRICS = (
    "arc_count",
    "total_arc_seconds",
    "descending_arcs",
    "candidate_windows",
    "held_windows",
    "held_arcs",
)


def score(work):
    lock = world.read(OUT / "prediction-lock.json")
    world.verify(OUT, lock["files"])
    plan = world.read(OUT / "blind-plan.json")
    private = work / "private/labels.json"
    seed = (work / "private/seed.bin").read_bytes()
    if (world.digest(private.read_bytes()), world.digest(seed)) != (
        plan["private_labels_sha256"],
        plan["seed_sha256"],
    ):
        raise ValueError("simulation truth differs from the commitment")
    synthetic = world.read(private)
    save_json(OUT / "synthetic-truth.json", dict(seed_hex=seed.hex(), captures=synthetic))
    ref_dir = world.prior.archive.base.secant_full.REPORT
    transfer = world.prior.archive.REPORT
    world.verify(ref_dir, world.read(ref_dir / "receipt.json")["files"])
    world.verify(transfer, world.read(transfer / "omitted-figure-lock.json")["files"])
    originals = world.read(ref_dir / "original-v5-inputs.json")
    omitted = {q["id"]: q for q in world.read(transfer / "omitted-queries.json")["queries"]}
    refs = {
        r["id"]: r
        for panel in ("ds26-common127", "roof16")
        for r in world.prior.archive.base.phase.corpus.references(panel)
    }
    with gzip.open(OUT / trial.PREDICTIONS, "rt") as stream:
        rows = list(map(json.loads, stream))
    records = {r["id"]: r for r in rows}
    if len(records) != len(rows) or set(records) != set(lock["cases"]):
        raise ValueError("stage receipt differs from the frozen offer roster")
    scores, panels, empirical = [], {}, {}
    for q in plan["cases"]:
        key, case, cohort = (q[k] for k in ("id", "recording", "cohort"))
        row = records[key]
        if any(row.get(k) != v for k, v in q.items()):
            raise ValueError("measured input differs from the plan")
        sim = cohort.startswith("simulated-")
        panel = "simulated" if sim else cohort
        truth = synthetic[case]["latlon"] if sim else refs[case]["truth"]
        control = (
            original_scores(case, refs[case], originals[case], truth)
            if panel == "diagnostic"
            else {}
        )
        if cohort == "omitted":
            check = omitted[key]
            if check["truth"] != truth or any(
                row["original_request_sha256" if k == "input_sha256" else k] != v
                for k, v in check["bindings"].items()
            ):
                raise ValueError("omitted query differs from the authenticated archive")
        if (roi_margin(truth, q["tile"]) >= 0) != (cohort in ("diagnostic", "simulated-present")):
            raise ValueError("offer does not have its prospectively committed geographic relation")
        data = row["result"]
        if data["arms"]["c0"] != data["arms"]["fitted_c"]:
            raise ValueError("a constant per-lane calibration changed the stage decision")
        m = data["metrics"]
        record = dict(
            id=key,
            recording=case,
            cohort=cohort,
            status=data["status"],
            attempts=1,
            unique_held_turns=len(m["events"]) if "events" in m else None,
            wall_s=row["native_elapsed_s"],
            cpu_s=row.get("cpu_s"),
            peak_rss_kib=row.get("peak_rss_kib"),
            **{k: m.get(k) for k in METRICS},
            **m.get("modeled", {}),
            **{
                role + "_" + arm + "_error_km": control[role][arm][0] if role in control else None
                for role in ROLES
                for arm in ARMS
            },
        )
        if sim:
            independent = {k: m.get(k) for k in (*METRICS, "events", "arc_inventory")}
            if case in empirical and independent != empirical[case]:
                raise ValueError(
                    "an offered location altered the measured anonymous turn inventory"
                )
            empirical[case] = independent
        panels.setdefault(panel, []).append(
            dict(
                id=key,
                recording=case,
                truth=truth,
                condition=cohort,
                bindings={k: row[k] for k in MATCH},
            )
        )
        scores.append(record)
    roof = [r for r in scores if r["cohort"] == "diagnostic"]
    ready = len(roof) == 2 and all(
        (r["unique_held_turns"] or 0) >= 3 and r.get("visible_two_sided_turn_windows", 0) > 0
        for r in roof
    )
    save_json(OUT / "scores.json", dict(rows=scores, support_gate_passed=ready))
    csv_file(OUT / "scores.csv", scores)
    figures(rows, panels, lock["files"])
    incidence(scores)
    return ready


def figures(rows, panels, frozen):
    provenance = ["blind-plan.json", "prediction-lock.json", "scores.json", "synthetic-truth.json"]
    common = frozen | {name: world.digest((OUT / name).read_bytes()) for name in provenance}
    names = {
        "diagnostic": "Doppler turn stage on real containing recordings",
        "omitted": "Doppler turn stage with real omitted offers",
        "simulated": "Doppler turn stage at new simulated sites",
    }
    cards = []
    for panel, title in names.items():
        transfer = panel != "diagnostic"
        cases = [r["id"] for r in panels[panel]]
        positions, seal = f"{panel}-positions.jsonl.gz", f"{panel}-figure-lock.json"
        files = common | {positions: pack(OUT, positions, [r for r in rows if r["id"] in cases])}
        card = dict(
            id=f"{trial.model.METHOD}-{panel}",
            method=trial.model.METHOD,
            scope="transfer" if transfer else "roof",
            title=title,
            caption="Held samples test for observable slope reversals. Position is unmeasured.",
            cases=cases,
            seal=seal,
            provenance=provenance,
            series=[
                dict(
                    key="candidate" if transfer else "one",
                    value=trial.model.METHOD,
                    label="Doppler turn stage",
                    file=positions,
                )
            ],
        )
        if transfer:
            query = panel + "-queries.json"
            save_json(OUT / query, dict(queries=panels[panel]))
            files[query] = world.digest((OUT / query).read_bytes())
            card["queries"] = query
        save_json(OUT / seal, dict(cases=cases, files=files))
        cards.append(card)
    save_json(OUT / "figures.json", dict(version=1, charts=cards))


def incidence(scores):
    import matplotlib.pyplot as plt

    measured = [r for r in scores if r.get("arc_count") is not None]
    if not measured:
        return
    index = list(range(len(measured)))
    labels = [
        r["id"]
        if r["cohort"] in ("diagnostic", "omitted")
        else f"Sim {r['recording'][:4]} {r['cohort'].split('-')[1]}"
        for r in measured
    ]
    fig, (left, right) = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    descending = [r["descending_arcs"] for r in measured]
    left.barh(index, descending, label="Negative overall slope", color="#3e7085")
    left.barh(
        index,
        [r["arc_count"] - n for r, n in zip(measured, descending, strict=True)],
        left=descending,
        label="Other overall slope",
        color="#b4c8cc",
    )
    left.scatter(
        [r["held_arcs"] for r in measured],
        index,
        color="#b53e18",
        marker="D",
        label="Arc with a two-fit measured turn",
        zorder=4,
        clip_on=False,
    )
    right.barh(
        index,
        [r["visible_orbit_sites"] for r in measured],
        color="#3e7085",
        label="Above-horizon orbit–site pairs",
    )
    right.scatter(
        [r["raw_visible_zero_crossings"] for r in measured],
        index,
        color="#b53e18",
        marker="D",
        label="Modeled slope reversals",
        zorder=4,
        clip_on=False,
    )
    for ax in (left, right):
        ax.set(yticks=index, yticklabels=labels)
        ax.invert_yaxis()
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), frameon=False)
    left.set(title="Measured on anonymous GLRT arcs", xlabel="Arc count")
    right.set(title="Causal TLE at five generic offered sites", xlabel="Orbit–site count")
    right.set_xscale("symlog", linthresh=1)
    fig.savefig(OUT / "turn-support.png", dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    print("Observability support gate passed:", score(parser.parse_args().work))


if __name__ == "__main__":
    main()
