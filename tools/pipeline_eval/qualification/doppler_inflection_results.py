"""Score sealed inflection timing, geometry bounds and conditional position evidence."""

import argparse
import gzip
import json
from pathlib import Path

import numpy as np

from ..__main__ import save_json
from ..scoring import ARMS, ROLES, distance_km
from . import doppler_inflection_trial as trial
from .absolute_doppler_results import MATCH
from .armijo_finish_results import pack
from .native_joint_full_results import original_scores, roi_margin
from .prefix_figures import csv_file

OUT, world = trial.OUT, trial.world
FIELDS = (
    "arc_count",
    "usable_arc_count",
    "candidate_windows",
    "held_arcs",
    "centre_modeled_events",
    "known_identity_events",
    "position_attempted",
    "held_log_lead",
    "held_identified_events",
)
ARTIFACTS = (
    "inflection-support.png",
    "inflection-support.pdf",
    "scores.csv",
    "scores.json",
    "prediction-lock.json",
    "blind-plan.json",
    "synthetic-truth.json",
)
CENTER = "inflection_tile_center"


def authority(work, plan):
    private = work / "private/labels.json"
    seed = (work / "private/seed.bin").read_bytes()
    if (world.digest(private.read_bytes()), world.digest(seed)) != (
        plan["private_labels_sha256"],
        plan["seed_sha256"],
    ):
        raise ValueError("simulation labels differ from their commitment")
    synthetic = world.read(private)
    save_json(OUT / "synthetic-truth.json", dict(seed_hex=seed.hex(), captures=synthetic))
    ref_dir = world.prior.archive.base.secant_full.REPORT
    transfer = world.prior.archive.REPORT
    world.verify(ref_dir, world.read(ref_dir / "receipt.json")["files"])
    world.verify(transfer, world.read(transfer / "omitted-figure-lock.json")["files"])
    return (
        {
            r["id"]: r
            for panel in ("ds26-common127", "roof16")
            for r in world.prior.archive.base.phase.corpus.references(panel)
        },
        world.read(ref_dir / "original-v5-inputs.json"),
        {q["id"]: q for q in world.read(transfer / "omitted-queries.json")["queries"]},
        synthetic,
    )


def score(work):
    lock = world.read(OUT / "prediction-lock.json")
    world.verify(OUT, lock["files"])
    plan = world.read(OUT / "blind-plan.json")
    refs, original, omitted, synthetic = authority(work, plan)
    with gzip.open(OUT / trial.PREDICTIONS, "rt") as stream:
        rows = list(map(json.loads, stream))
    rows_by_id = {r["id"]: r for r in rows}
    if len(rows) != len(rows_by_id) or set(rows_by_id) != set(lock["cases"]):
        raise ValueError("inflection results do not cover the fixed roster")
    counts, panels, same_arc_data = [], {}, {}
    for q in plan["cases"]:
        key, case, cohort = (q[k] for k in ("id", "recording", "cohort"))
        row = rows_by_id[key]
        if any(row[k] != value for k, value in q.items()):
            raise ValueError("worker used a different bound input")
        sim = cohort.startswith("simulated-")
        pane = "simulated" if sim else cohort
        truth = synthetic[case]["latlon"] if sim else refs[case]["truth"]
        if cohort == "omitted":
            check = omitted[key]
            if check["truth"] != truth or any(
                row["original_request_sha256" if k == "input_sha256" else k] != value
                for k, value in check["bindings"].items()
            ):
                raise ValueError("omitted offer differs from frozen archive")
        if (roi_margin(truth, q["tile"]) >= 0) != (cohort in ("diagnostic", "simulated-present")):
            raise ValueError("tile does not have its predeclared containment")
        result = row["result"]
        arm = result["arms"]["c0"]
        if arm != result["arms"]["fitted_c"]:
            raise ValueError("free affine curvature fit cannot depend on calibration c")
        m = result["metrics"]
        if sim:
            unconditional = {k: m.get(k) for k in ("events", "arc_inventory", "injections")}
            if case in same_arc_data and unconditional != same_arc_data[case]:
                raise ValueError("site offer changed the measured timing support")
            same_arc_data[case] = unconditional
        inject = m.get("injections", [])
        controls = (
            original_scores(case, refs[case], original[case], truth) if pane == "diagnostic" else {}
        )
        counts.append(
            dict(
                id=key,
                cohort=cohort,
                recording=case,
                status=result["status"],
                reason=result["reason"],
                **{k: m.get(k) for k in FIELDS},
                distinct_measured_events=len(m["events"]) if "events" in m else None,
                event_sigma_median_s=float(np.median([r["sigma_s"] for r in m["events"]]))
                if m.get("events")
                else None,
                **{
                    f"contrast_25km_p{k}_s": v
                    for k, v in zip((10, 50, 90, 100), m.get("contrast_25km_s", []), strict=False)
                },
                **{
                    f"ideal_worst_axis_{k}_km": v
                    for k, v in m.get("ideal_worst_axis_km", {}).items()
                },
                **{
                    f"inject_{int(j)}_{kind}": sum(
                        r["jerk_hz_s3"] == j
                        and (
                            kind == "attempted"
                            or r["fit_abs_error_s"] is not None
                            and r["fit_abs_error_s"] <= 1.25
                        )
                        for r in inject
                    )
                    for j in (2, 12)
                    for kind in ("attempted", "detected")
                },
                forced_error_km=distance_km(arm["forced_latlon"], truth),
                position_error_km=distance_km(arm["latlon"], truth),
                tile_error_km=distance_km(q["tile"]["center"], truth),
                cpu_s=row.get("cpu_s"),
                wall_s=row["native_elapsed_s"],
                peak_rss_kib=row.get("peak_rss_kib"),
                **{
                    role + "_" + arm + "_error_km": controls[role][arm][0]
                    if role in controls
                    else None
                    for role in ROLES
                    for arm in ARMS
                },
            )
        )
        panels.setdefault(pane, []).append(
            dict(
                id=key,
                recording=case,
                condition=cohort,
                truth=truth,
                bindings={k: row[k] for k in MATCH},
            )
        )
    attempted = [r["id"] for r in counts if r["position_attempted"]]
    save_json(OUT / "scores.json", dict(rows=counts, tested_positions=attempted))
    csv_file(OUT / "scores.csv", counts)
    plot(counts)
    files = {name: world.digest((OUT / name).read_bytes()) for name in ARTIFACTS}
    save_json(OUT / "stage-lock.json", dict(cases=list(lock["cases"]), files=files))
    if attempted:
        figures(rows, panels, attempted, lock["files"] | files)
    return counts


def plot(rows):
    import matplotlib.pyplot as plt

    rows = [r for r in rows if r["arc_count"] is not None]
    x = list(range(len(rows)))
    labels = [
        r["id"]
        if not r["cohort"].startswith("simulated")
        else f"Sim {r['recording'][:4]} {r['cohort'].split('-')[1]}"
        for r in rows
    ]
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), layout="constrained")
    ax = axes[0]
    ax.barh(x, [r["usable_arc_count"] for r in rows], color="#aac4c9", label="Arcs spanning ≥20 s")
    ax.scatter(
        [r["distinct_measured_events"] for r in rows],
        x,
        color="#922859",
        marker="D",
        zorder=5,
        clip_on=False,
        label="Held events",
    )
    ax.set(title="Anonymous native arcs", xlabel="Count", yticks=x, yticklabels=labels)
    ax = axes[1]
    ax.barh(x, [r["contrast_25km_p90_s"] for r in rows], color="#43869a", label="90th percentile")
    ax.scatter(
        [r["contrast_25km_p50_s"] for r in rows], x, color="#212d4b", zorder=4, label="Median"
    )
    ax.set(title="Known-orbit 25 km timing contrast", xlabel="Seconds")
    ax = axes[2]
    for k, color in (("0.3", "#236f86"), ("3.0", "#676185"), ("8.0", "#922859")):
        ax.plot(
            [r[f"ideal_worst_axis_{k}_km"] for r in rows], x, "o", color=color, label=f"{k} s RMS"
        )
    ax.set(title="Optimistic known-orbit geometry", xlabel="Worst-axis position σ (km)")
    for i, ax in enumerate(axes):
        ax.set_ylim(len(x) - 0.5, -0.5)
        if i:
            ax.set_yticks(x, [""] * len(x))
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), frameon=False)
    fig.savefig(OUT / "inflection-support.png", dpi=150)
    fig.savefig(OUT / "inflection-support.pdf")
    plt.close(fig)


def figures(rows, panels, attempted, frozen):
    descriptors = []
    provenance = ["blind-plan.json", "prediction-lock.json", "scores.json"]
    for name, queries in panels.items():
        if not any(q["id"] in attempted for q in queries):
            continue
        transfer = name != "diagnostic"
        cases = [q["id"] for q in queries]
        positions, seal = f"{name}-positions.jsonl.gz", f"{name}-figure-lock.json"
        current = [r for r in rows if r["id"] in cases]
        center = [
            dict(
                r,
                method=CENTER,
                result=dict(
                    status="ok",
                    reason=None,
                    boundary="Unconditional supplied tile centre",
                    metrics={},
                    arms={a: dict(latlon=r["tile"]["center"], forced_latlon=None) for a in ARMS},
                ),
            )
            for r in current
        ]
        files = frozen | {positions: pack(OUT, positions, current + center)}
        card = dict(
            id=f"{trial.model.METHOD}-{name}",
            method=trial.model.METHOD,
            scope="transfer" if transfer else "roof",
            cases=cases,
            title=f"Doppler inflection positioning on {name} offers",
            caption="Sites ranked by training event times and checked on separate held events.",
            provenance=provenance,
            seal=seal,
            series=[
                dict(
                    key="candidate" if transfer else "one",
                    file=positions,
                    value=trial.model.METHOD,
                    label="Steepest-descent time · published",
                    forced_label="Steepest-descent time · forced",
                ),
                dict(
                    key="four" if transfer else "one_native_factors",
                    file=positions,
                    value=CENTER,
                    label="Tile centre prior",
                    match=list(MATCH),
                ),
            ],
        )
        if transfer:
            name_file = f"{name}-queries.json"
            save_json(OUT / name_file, dict(queries=queries))
            files[name_file] = world.digest((OUT / name_file).read_bytes())
            card["queries"] = name_file
        save_json(OUT / seal, dict(cases=cases, files=files))
        descriptors.append(card)
    save_json(OUT / "figures.json", dict(version=1, charts=descriptors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    score(parser.parse_args().work)


if __name__ == "__main__":
    main()
