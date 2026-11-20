"""Post-seal triplet evidence and charts on exact containing and omitted offers."""

import gzip
import json

from ..__main__ import save_json
from ..scoring import ARMS, ROLES, distance_km
from . import trackless_likelihood_results as previous
from . import tracklet_triplets_trial as trial
from .absolute_doppler_results import MATCH
from .armijo_finish_results import pack
from .native_joint_full_results import roi_margin
from .prefix_figures import csv_file

OUT, world = trial.OUT, trial.world
CENTER = "triplet_tile_center"
FIELDS = (
    "triplets",
    "held_triplets",
    "held_blocks",
    "candidate_triples",
    "sites",
    "modeled_orbits",
    "exact_orbit_triplet_predictions",
    "slope_kernel_hz_s",
    "curvature_kernel_hz_s",
    "held_location_lead",
    "held_reversed_lead",
    "held_log_score",
    "held_center_log_score",
    "held_effective_competing_orbits",
    "held_slope_rms_hz_s",
    "held_curvature_rms_hz_s",
)


def score():
    lock = world.read(OUT / "prediction-lock.json")
    world.verify(OUT, lock["files"])
    q = world.read(OUT / "blind-plan.json")["cases"]
    refs, original, omitted, wave, installed = previous.authorities()
    previous_lock = world.read(previous.OUT / "score-lock.json")
    world.verify(previous.OUT, previous_lock["files"])
    prior = {
        r["id"]: r
        for r in world.read(previous.OUT / "scores.json")["rows"]
        if r["method"] == "trackless_likelihood" and r["arm"] == "c0"
    }
    with gzip.open(OUT / trial.PREDICTIONS, "rt") as stream:
        rows = list(map(json.loads, stream))
    with gzip.open(previous.OUT / trial.PREDICTIONS, "rt") as stream:
        prior_bindings = {
            r["id"]: r for r in map(json.loads, stream) if r["method"] == "trackless_likelihood"
        }
    records = {(r["id"], r["method"]): r for r in rows}
    if len(rows) != len(records) or set(records) != {
        (p["id"], mode) for p in q for mode in trial.model.METHODS
    }:
        raise ValueError("triplet outputs do not cover the sealed roster")
    scores, panels, centres = [], {}, []
    for p in q:
        key = p["id"]
        primary = records[key, trial.model.METHODS[0]]
        truth, panel, condition, roof, waveform = previous.compare_original(
            primary, wave, omitted, refs, original, installed
        )
        if (roi_margin(truth, p["tile"]) >= 0) != (condition == "containing"):
            raise ValueError("truth and offered region disagree with the frozen condition")
        bind = {k: primary[k] for k in MATCH}
        if any(prior_bindings[key][k] != value for k, value in bind.items()):
            raise ValueError("prior two-snapshot comparison used a different input")
        panels.setdefault(panel, []).append(
            dict(
                id=key,
                recording=p["recording"],
                condition=condition,
                truth=truth,
                bindings=bind,
            )
        )
        center = p["tile"]["center"]
        centres.append(
            dict(
                primary,
                method=CENTER,
                result=dict(
                    status="ok",
                    reason=None,
                    boundary="Unconditional supplied tile centre",
                    metrics={},
                    arms={a: dict(latlon=center, forced_latlon=None) for a in ARMS},
                ),
            )
        )
        for method in trial.model.METHODS:
            row = records[key, method]
            if any(row.get(k) != v for k, v in (p | bind).items()):
                raise ValueError("matched controls received different native inputs")
            result = row["result"]
            arms = result["arms"]
            if arms["c0"] != arms["fitted_c"]:
                raise ValueError("constant per-lane calibration must cancel")
            m = result["metrics"]
            slope = m.get("contrast_25km_slope_hz_s") or [None] * 3
            bend = m.get("contrast_25km_curvature_hz_s") or [None] * 3
            for arm, endpoint in arms.items():
                comp = waveform.get(arm, {})
                scores.append(
                    dict(
                        id=key,
                        recording=p["recording"],
                        condition=condition,
                        panel=panel,
                        method=method,
                        arm=arm,
                        status=result["status"],
                        reason=result["reason"],
                        position_attempted=m.get("position_attempted", False),
                        error_km=distance_km(endpoint["latlon"], truth),
                        forced_error_km=distance_km(endpoint["forced_latlon"], truth),
                        tile_error_km=distance_km(center, truth),
                        installed_error_km=comp.get("position_error_km"),
                        installed_rf_rms_hz=comp.get("rf_rms_hz"),
                        earlier_two_snapshot_forced_km=prior[key]["forced_error_km"],
                        earlier_two_snapshot_spatial_lead=prior[key]["held_location_lead"],
                        earlier_two_snapshot_competing_orbits=prior[key][
                            "held_effective_competing_orbits"
                        ],
                        slope_25km_median_hz_s=slope[1],
                        slope_25km_p90_hz_s=slope[2],
                        curvature_25km_median_hz_s=bend[1],
                        curvature_25km_p90_hz_s=bend[2],
                        wall_s=row["native_elapsed_s"],
                        cpu_s=row.get("cpu_s"),
                        peak_rss_kib=row.get("peak_rss_kib"),
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
    save_json(OUT / "scores.json", dict(rows=scores))
    csv_file(OUT / "scores.csv", scores)
    plot(scores)
    bind = lock["files"] | {
        name: world.digest((OUT / name).read_bytes())
        for name in (
            "scores.json",
            "scores.csv",
            "prediction-lock.json",
            "triplet-support.png",
        )
    }
    save_json(OUT / "score-lock.json", dict(cases=lock["cases"], files=bind))
    figures(panels, rows + centres, bind)


def plot(rows):
    import matplotlib.pyplot as plt

    selected = [
        r
        for r in rows
        if r["arm"] == "c0" and r["method"] == trial.model.METHODS[0] and r["position_attempted"]
    ]
    single = {
        r["id"]: r for r in rows if r["arm"] == "c0" and r["method"] == trial.model.METHODS[1]
    }
    yy = list(range(len(selected)))
    names = [
        r["id"] if r["panel"] != "waveform" else "Waveform " + r["condition"] for r in selected
    ]
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.5), layout="constrained")
    a, b, c = axes
    a.scatter(
        [r["curvature_25km_median_hz_s"] for r in selected],
        yy,
        marker="o",
        label="Median 25 km curvature change",
    )
    a.scatter(
        [r["curvature_kernel_hz_s"] for r in selected],
        yy,
        marker="x",
        label="Curvature kernel width",
    )
    b.scatter(
        [single[r["id"]]["held_effective_competing_orbits"] for r in selected],
        yy,
        marker="x",
        label="Slope only",
    )
    b.scatter(
        [r["held_effective_competing_orbits"] for r in selected],
        yy,
        marker="o",
        label="Shared orbit + curvature",
    )
    c.axvline(0, linewidth=0.8, color="grey")
    c.scatter(
        [r["held_location_lead"] for r in selected], yy, marker="o", label="Joint vs separated site"
    )
    c.scatter(
        [r["held_reversed_lead"] for r in selected],
        yy,
        marker="x",
        label="Joint vs reversed curvature",
    )
    for i, ax in enumerate(axes):
        ax.set(yticks=yy, yticklabels=names if i == 0 else [""] * len(names))
        ax.invert_yaxis()
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), frameon=False)
    a.set(title="Modeled curvature information", xlabel="Difference in rates (Hz/s at 11.5 GHz)")
    b.set(title="Held orbit alternatives", xlabel="Effective competing trajectories")
    c.set(title="Held score advantages", xlabel="Mean log-likelihood difference")
    fig.savefig(OUT / "triplet-support.png", dpi=160)
    plt.close(fig)


def figures(panels, records, frozen):
    cards = []
    for name, queries in panels.items():
        transfer = name != "containing"
        cases = [q["id"] for q in queries]
        positions, seal = f"{name}-positions.jsonl.gz", f"{name}-figure-lock.json"
        files = frozen | {positions: pack(OUT, positions, [r for r in records if r["id"] in cases])}
        titles = {
            "containing": "Joint Doppler triplets on real containing offers",
            "omitted": "Joint Doppler triplets on real omitted offers",
            "waveform": "Joint Doppler triplets on the emitted Qin waveform",
        }
        card = dict(
            id=f"{trial.model.METHODS[0]}-{name}",
            method=trial.model.METHODS[0],
            scope="transfer" if transfer else "roof",
            cases=cases,
            title=titles[name],
            caption="Same three snapshots for joint, common-slope and reversed-curvature fits.",
            seal=seal,
            provenance=["blind-plan.json", "prediction-lock.json", "scores.json"],
            series=[],
        )
        keys = (
            ("candidate", "stock", "one", "four")
            if transfer
            else ("one", "stock", "one_native_factors", "all_visits")
        )
        for key, method, label in zip(
            keys,
            (*trial.model.METHODS, CENTER),
            (
                "Joint slope and curvature",
                "Common slope only",
                "Reversed curvature",
                "Tile centre prior",
            ),
            strict=True,
        ):
            line = dict(key=key, value=method, label=label, file=positions)
            if method != trial.model.METHODS[0]:
                line["match"] = list(MATCH)
            if method != CENTER and (transfer or method == trial.model.METHODS[0]):
                line["forced_label"] = label + " · forced"
            card["series"].append(line)
        if transfer:
            query = f"{name}-queries.json"
            save_json(OUT / query, dict(queries=queries))
            files[query] = world.digest((OUT / query).read_bytes())
            card["queries"] = query
        save_json(OUT / seal, dict(cases=cases, files=files))
        cards.append(card)
    save_json(OUT / "figures.json", dict(version=1, charts=cards))


if __name__ == "__main__":
    score()
