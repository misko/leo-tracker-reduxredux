"""Score the matched shared and independent multi-pass oscillator trial."""

import gzip
import json

from ..__main__ import save_json
from ..scoring import ARMS, ROLES, distance_km
from . import joint_pass_trial as trial
from . import trackless_likelihood_results as original
from .absolute_doppler_results import MATCH
from .armijo_finish_results import pack
from .native_joint_full_results import roi_margin
from .prefix_figures import csv_file

OUT, world = trial.OUT, trial.world
CENTER = "joint_pass_tile_center"
FIELDS = (
    "selected_arcs",
    "train_arcs",
    "eligible_held_arcs",
    "clock_paths_with_train_support",
    "regional_causal_orbits",
    "candidate_shapes",
    "train_rms_hz",
    "held_rms_hz",
    "held_families",
    "held_site_lead",
    "profiled_radius_km",
    "retained_clock_direction",
    "position_attempted",
    "rival_sites",
)


def score():
    lock = world.read(OUT / "prediction-lock.json")
    world.verify(OUT, lock["files"])
    plan = world.read(OUT / "blind-plan.json")
    archive = trial.regional.OUT
    world.verify(archive, world.read(archive / "simulated-figure-lock.json")["files"])
    sim = {r["id"]: r for r in world.read(archive / "simulated-queries.json")["queries"]}
    refs, old, omitted, wave, installed = original.authorities()
    with gzip.open(OUT / trial.PREDICTIONS, "rt") as stream:
        rows = list(map(json.loads, stream))
    indexed = {(r["id"], r["method"]): r for r in rows}
    if len(indexed) != len(rows) or set(indexed) != {
        (q["id"], mode) for q in plan["cases"] for mode in trial.model.METHODS
    }:
        raise ValueError("joint-pass records differ from the predeclared roster")
    scores, centre_rows, panels = [], [], {}
    for q in plan["cases"]:
        ident = q["id"]
        first = indexed[ident, trial.model.METHODS[0]]
        if ident in sim:
            signed = sim[ident]
            if any(
                first[k] != digest
                for k, digest in signed["bindings"].items()
                if k != "input_sha256"
            ):
                raise ValueError("factor-simulation provenance differs from established receipts")
            truth = signed["truth"]
            panel, condition = (
                "simulation",
                "containing" if q["cohort"].endswith("present") else "omitted",
            )
            roof, historical = {}, {}
        else:
            truth, panel, condition, roof, historical = original.compare_original(
                first, wave, omitted, refs, old, installed
            )
        if (roi_margin(truth, q["tile"]) >= 0) != (condition == "containing"):
            raise ValueError(
                "offer does not have its frozen relation to the independently scored site"
            )
        bind = {field: first[field] for field in MATCH}
        panels.setdefault(panel, []).append(
            dict(
                id=ident,
                recording=q["recording"],
                condition=condition,
                truth=truth,
                bindings=bind,
            )
        )
        center = q["tile"]["center"]
        centre_rows.append(
            dict(
                first,
                method=CENTER,
                result=dict(
                    status="ok",
                    reason=None,
                    boundary="Supplied centre prior",
                    metrics={},
                    arms={a: dict(latlon=center, forced_latlon=None) for a in ARMS},
                ),
            )
        )
        for method in trial.model.METHODS:
            row = indexed[ident, method]
            if any(row.get(k) != val for k, val in (bind | q).items()):
                raise ValueError("drift control used a different raw input or offer")
            result = row["result"]
            if result["arms"]["c0"] != result["arms"]["fitted_c"]:
                raise ValueError("the per-arc intercept must absorb constant RF calibration")
            m = result["metrics"]
            for arm, endpoint in result["arms"].items():
                inst = historical.get(arm, {})
                scores.append(
                    dict(
                        id=ident,
                        method=method,
                        panel=panel,
                        condition=condition,
                        recording=q["recording"],
                        arm=arm,
                        status=result["status"],
                        reason=result["reason"],
                        error_km=distance_km(endpoint["latlon"], truth),
                        forced_error_km=distance_km(endpoint["forced_latlon"], truth),
                        centre_error_km=distance_km(center, truth),
                        installed_error_km=inst.get("position_error_km"),
                        installed_rf_rms_hz=inst.get("rf_rms_hz"),
                        cpu_s=row.get("cpu_s"),
                        wall_s=row["native_elapsed_s"],
                        peak_rss_kib=row.get("peak_rss_kib"),
                        maximum_absolute_drift_hz_s=max(
                            map(abs, m.get("estimated_drift_hz_s", [])), default=None
                        ),
                        **{k: m.get(k) for k in FIELDS},
                        **{
                            role + "_error_km": roof[role][arm][0] if role in roof else None
                            for role in ROLES
                        },
                        **{
                            role + "_cfo_rms_hz": roof[role][arm][1] if role in roof else None
                            for role in ROLES
                        },
                    )
                )
    csv_file(OUT / "scores.csv", scores)
    save_json(OUT / "scores.json", dict(rows=scores))
    plot(scores)
    files = lock["files"] | {
        name: world.digest((OUT / name).read_bytes())
        for name in ("scores.csv", "scores.json", "prediction-lock.json", "joint-pass-support.png")
    }
    save_json(OUT / "score-lock.json", dict(cases=lock["cases"], files=files))
    figures(panels, rows + centre_rows, files)


def plot(scores):
    import matplotlib.pyplot as plt

    a, b = trial.model.METHODS
    rows = [r for r in scores if r["arm"] == "c0" and r["method"] == a and r["position_attempted"]]
    controls = {r["id"]: r for r in scores if r["arm"] == "c0" and r["method"] == b}
    index = list(range(len(rows)))
    labels = [
        r["id"]
        if r["panel"] in ("containing", "omitted")
        else r["panel"].title() + " " + r["condition"]
        for r in rows
    ]
    fig, axes = plt.subplots(1, 3, figsize=(14.5, 5.5), layout="constrained")
    specs = [
        ("profiled_radius_km", "Clock-profiled conditioning", "Worst-axis position σ (km)", 12.5),
        ("held_rms_hz", "Held Doppler prediction", "Conditional shape RMS (Hz)", 700),
        ("held_site_lead", "Held score over separated rival", "Mean cost advantage", 0.15),
    ]
    for i, (ax, (field, title, unit, threshold)) in enumerate(zip(axes, specs, strict=True)):
        ax.scatter(
            [r[field] for r in rows], index, marker="D", color="#236f86", label="Shared path drift"
        )
        ax.scatter(
            [controls[r["id"]][field] for r in rows],
            index,
            marker="x",
            color="#962959",
            label="Independent arc drift",
        )
        ax.axvline(threshold, color="#83939a", linestyle="--", label="Publication threshold")
        ax.set(
            title=title,
            xlabel=unit,
            yticks=index,
            yticklabels=labels if i == 0 else [""] * len(index),
        )
        ax.invert_yaxis()
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), frameon=False)
    fig.savefig(OUT / "joint-pass-support.png", dpi=160)
    plt.close(fig)


def figures(panels, rows, files):
    cards = []
    for name, queries in panels.items():
        transfer = name != "containing"
        ids = [r["id"] for r in queries]
        archive, seal = f"{name}-positions.jsonl.gz", f"{name}-figure-lock.json"
        bound = files | {archive: pack(OUT, archive, [r for r in rows if r["id"] in ids])}
        entry = dict(
            id=f"{trial.model.METHODS[0]}-{name}",
            method=trial.model.METHODS[0],
            scope="transfer" if transfer else "roof",
            cases=ids,
            title=f"Joint pass Doppler on {name} offers",
            caption="Matched arcs and orbits with shared or independent oscillator drift.",
            provenance=["prediction-lock.json", "blind-plan.json", "scores.csv"],
            series=[],
            seal=seal,
        )
        keys = (
            ("candidate", "stock", "four") if transfer else ("one", "stock", "one_native_factors")
        )
        for key, mode, label in zip(
            keys,
            (*trial.model.METHODS, CENTER),
            ("Shared drift", "Independent arc drift", "Tile centre"),
            strict=True,
        ):
            series = dict(key=key, value=mode, label=label, file=archive)
            if mode != trial.model.METHODS[0]:
                series["match"] = list(MATCH)
            if mode != CENTER and (transfer or mode == trial.model.METHODS[0]):
                forced = "Shared drift" if mode == trial.model.METHODS[0] else label
                series["forced_label"] = forced + " · forced"
            entry["series"].append(series)
        if transfer:
            name_file = f"{name}-queries.json"
            save_json(OUT / name_file, dict(queries=queries))
            bound[name_file] = world.digest((OUT / name_file).read_bytes())
            entry["queries"] = name_file
        save_json(OUT / seal, dict(cases=ids, files=bound))
        cards.append(entry)
    save_json(OUT / "figures.json", dict(version=2, charts=cards))


if __name__ == "__main__":
    score()
