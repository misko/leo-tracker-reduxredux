"""Score sealed inverse proposals beside the original matched-input global search."""

import gzip
import json

import numpy as np

from ..__main__ import save_json
from ..scoring import ARMS, arm_outcome, distance_km
from . import anonymous_geometry_results as old_score
from . import orbit_proposals_trial as trial
from .absolute_doppler_results import MATCH
from .armijo_finish_results import pack
from .prefix_figures import csv_file

OUT, MODEL, world = trial.OUT, trial.model, trial.world
BASE = "orbit_proposals_uniform_control"
COMPARISON = "chart-positions.jsonl.gz"
PLOT = "orbit-proposal-support.png"
METRICS = (
    "training_loss",
    "held_loss",
    "held_lead",
    "held_blocks",
    "held_distinct_orbits",
    "held_slope_rms_hz_s",
    "held_curvature_rms_hz_s2",
    "conditional_held_shape_cfo_rms_hz",
    "train_profiles",
    "held_profiles",
    "inverse_points",
    "inverse_arcs",
    "proposal_blocks",
    "site_proposals",
    "world_sites",
    "training_comparisons",
    "held_comparisons",
)


def score():
    receipt = world.read(OUT / "prediction-lock.json")
    world.verify(OUT, receipt["files"])
    old_lock, queries, prior = trial.authority()
    survey_path = trial.old.OUT / "survey-diagnostic.json"
    survey = world.read(survey_path)
    if survey["prediction_lock_sha256"] != world.digest(old_lock.read_bytes()):
        raise ValueError("privileged survey differs from the frozen worldwide comparison")
    survey_scores = {
        r["id"]: r["at_survey"] for r in survey["rows"] if r["method"] == trial.old.METHODS[0]
    }
    refs, _, omitted, _, _ = old_score.clock.original.authorities()
    with gzip.open(OUT / "positions.jsonl.gz", "rt") as source:
        records = list(map(json.loads, source))
    indexed = {r["id"]: r for r in records}
    if len(indexed) != len(records) or set(indexed) != set(receipt["cases"]):
        raise ValueError("predictions differ from the sealed roster")
    geometry = MODEL.forward.earth_mesh(MODEL.forward.COARSE).tolist()
    series, panels, scores = [], {}, []
    for q in queries:
        ident, recording, condition = (q[k] for k in ("id", "recording", "cohort"))
        new, old = indexed[ident], prior[ident] | {"method": BASE}
        match = {key: new[key] for key in MATCH}
        if any(r.get(k) != v for r in (new, old) for k, v in (q | match).items()):
            raise ValueError("the proposal experiment changed its comparator's native request")
        truth = refs[recording]["truth"]
        if old_score.inside(truth, q["tile"]) != (condition != "omitted"):
            raise ValueError("the held recording differs from the evaluator offer condition")
        if condition == "omitted":
            bound = omitted[ident]
            if truth != bound["truth"] or any(
                new["original_request_sha256" if k == "input_sha256" else k] != v
                for k, v in bound["bindings"].items()
            ):
                raise ValueError("omitted offer differs from its recorded authority")
        panels.setdefault(condition, []).append(
            dict(id=ident, recording=recording, condition=condition, truth=truth, bindings=match)
        )
        series.extend((new, old))
        for r in (new, old):
            outcome = r["result"]
            for arm in ARMS:
                ep = outcome["arms"][arm]
                status, reason = arm_outcome(outcome, ep)
                info = outcome["metrics"] if arm == "c0" else {}
                diag = survey_scores.get(ident, {}) if arm == "c0" else {}
                initial = (
                    geometry if r["method"] == BASE and info else info.get("initial_points", [])
                )
                scores.append(
                    dict(
                        id=ident,
                        recording=recording,
                        condition=condition,
                        arm=arm,
                        method=r["method"],
                        status=status,
                        reason=reason,
                        error_km=distance_km(ep["latlon"], truth),
                        forced_error_km=distance_km(ep["forced_latlon"], truth),
                        forced_inside_scored_offer=old_score.inside(ep["forced_latlon"], q["tile"]),
                        published_inside_scored_offer=old_score.inside(ep["latlon"], q["tile"]),
                        initial_nearest_km=min(
                            (distance_km(p, truth) for p in initial), default=None
                        ),
                        privileged_survey_train_loss=diag.get("train_loss"),
                        privileged_survey_held_loss=diag.get("held_loss"),
                        privileged_survey_ring_lead=diag.get("held_survey_ring_lead"),
                        wall_s=r.get("native_elapsed_s"),
                        cpu_s=r.get("cpu_s"),
                        rss_kib=r.get("peak_rss_kib"),
                        **{key: info.get(key) for key in METRICS},
                    )
                )
    csv_file(OUT / "scores.csv", scores)
    save_json(OUT / "scores.json", dict(rows=scores))
    plot(scores)
    files = receipt["files"] | {
        f: world.digest((OUT / f).read_bytes())
        for f in (
            "prediction-lock.json",
            "scores.json",
            "scores.csv",
            PLOT,
        )
    }
    files[COMPARISON] = pack(OUT, COMPARISON, series)
    ancestors = {
        str(p.relative_to(trial.ROOT)): world.digest(p.read_bytes())
        for p in (old_lock, survey_path, trial.old.OUT / "score-lock.json")
    }
    save_json(
        OUT / "score-lock.json", dict(cases=receipt["cases"], files=files, compared=ancestors)
    )
    files["score-lock.json"] = world.digest((OUT / "score-lock.json").read_bytes())
    cards(panels, files)


def plot(rows):
    import matplotlib.pyplot as plt

    active = [r for r in rows if r["method"] == MODEL.METHOD and r["arm"] == "c0"]
    labels = [
        r["id"].replace("-profile-shuffle", " shuffled").replace("-omitted", " omitted")
        for r in active
    ]
    y = np.arange(len(active))
    fig, axes = plt.subplots(1, 3, figsize=(13.0, 4.8), layout="constrained")
    for method, legend, marker in (
        (MODEL.METHOD, "Inverse proposals", "D"),
        (BASE, "Uniform grid", "x"),
    ):
        selected = [r for r in rows if r["method"] == method and r["arm"] == "c0"]
        for ax, key in zip(axes, ("initial_nearest_km", "held_loss", "held_lead"), strict=True):
            ax.scatter([r[key] for r in selected], y, label=legend, marker=marker)
    axes[0].axvline(25, linestyle="--", color="0.4", label="25 km")
    axes[1].scatter(
        [r["privileged_survey_held_loss"] for r in active],
        y,
        marker="o",
        facecolors="none",
        edgecolors="black",
        label="Given survey",
    )
    axes[2].axvline(0.15, linestyle="--", color="0.4", label="Held lead gate")
    for i, (ax, name) in enumerate(
        zip(
            axes,
            (
                "Nearest initial candidate (km)",
                "Held normalized loss per arc",
                "Lead over held geographic rivals",
            ),
            strict=True,
        )
    ):
        ax.set(yticks=y, yticklabels=labels if not i else [""] * len(y), xlabel=name)
        ax.invert_yaxis()
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.17), frameon=False)
    fig.savefig(OUT / PLOT, dpi=150)
    plt.close(fig)


def cards(panels, files):
    charts = []
    for cohort, rows in panels.items():
        direct = cohort == "containing"
        cases = [r["id"] for r in rows]
        seal = cohort + "-figure-lock.json"
        complement = {
            "containing": "on measured roofs",
            "omitted": "with omitted offers",
            "shuffle": "on shuffled shapes",
        }[cohort]
        chart = dict(
            id=MODEL.METHOD + "-" + cohort,
            method=MODEL.METHOD,
            scope="roof" if direct else "transfer",
            title="Orbit-derived proposals " + complement,
            caption="Worldwide from native peaks and causal orbits. Offers stay in scoring.",
            cases=cases,
            seal=seal,
            provenance=["prediction-lock.json", "score-lock.json"],
            series=[],
        )
        for j, (method, legend) in enumerate(
            ((MODEL.METHOD, "Inverse sites"), (BASE, "Uniform grid"))
        ):
            line = dict(
                key="stock" if j else "one" if direct else "candidate",
                file=COMPARISON,
                where={"cohort": cohort},
                value=method,
                label=legend,
            )
            if not direct or not j:
                line["forced_label"] = legend + " · forced"
            if j:
                line["match"] = list(MATCH)
            chart["series"].append(line)
        lock = files.copy()
        if not direct:
            path = cohort + "-queries.json"
            save_json(OUT / path, dict(queries=rows))
            lock[path] = world.digest((OUT / path).read_bytes())
            chart["queries"] = path
        save_json(OUT / seal, dict(cases=cases, files=lock))
        charts.append(chart)
    save_json(OUT / "figures.json", dict(version=2, charts=charts))


if __name__ == "__main__":
    score()
