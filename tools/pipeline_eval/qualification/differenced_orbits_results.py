"""Score the locked staggered-RF predictions and their matched controls."""

import gzip
import json
from pathlib import Path

import numpy as np

from ..__main__ import save_json
from ..scoring import ARMS, ROLES, arm_outcome, distance_km
from . import differenced_orbits_trial as trial
from .absolute_doppler_results import MATCH
from .armijo_finish_results import pack
from .native_joint_full_results import original_scores, roi_margin
from .prefix_figures import csv_file
from .trackless_likelihood_results import authorities

OUT, METHOD = trial.OUT, trial.model.METHOD
CENTER = "differenced_orbits_tile_center"
POSITIONS = "chart-positions.jsonl.gz"
PLOT = "staggered-support.png"
METRICS = (
    "native_zero_offset_visits",
    "exact_distinct_rf_path_windows",
    "train_groups",
    "train_blocks",
    "held_groups",
    "potential_copy_triples_rejected",
    "regional_orbits",
    "trial_triples",
    "retained_triples",
    "sites",
    "held_qualified_triples",
    "train_cost_hz_s",
    "held_rms_hz_s",
    "held_permuted_rms_hz_s",
    "held_lead_hz_s",
    "held_radius_km",
    "held_rf_proportional_free_radius_km",
    "max_calibration_design_hz_s_per_unit",
    "max_cubic_clock_moment_difference_s2",
)


def locked_predictions():
    seal = json.loads((OUT / "prediction-lock.json").read_bytes())
    files = seal["files"]
    for name, digest in files.items():
        if trial.digest((OUT / name).read_bytes()) != digest:
            raise ValueError(f"changed prediction file {name}")
    with gzip.open(OUT / trial.PREDICTIONS, "rt") as stream:
        rows = list(map(json.loads, stream))
    cases = json.loads((OUT / "blind-plan.json").read_bytes())["cases"]
    if (
        [r["id"] for r in rows] != seal["cases"]
        or len(cases) != len(rows)
        or any(any(r.get(k) != v for k, v in q.items()) for r, q in zip(rows, cases, strict=True))
    ):
        raise ValueError("changed prediction roster")
    same_schedule = METRICS[:6]
    original = {r["recording"]: r for r in rows if not r["id"].endswith(("omitted", "time-sham"))}
    for row in rows:
        paired = original[row["recording"]]
        a, b = (r["result"]["metrics"] for r in (row, paired))
        if any(a.get(k) != b.get(k) for k in same_schedule):
            raise ValueError("a control changed the measured support")
        if {
            (g["block"], tuple(map(tuple, g["lanes"]))): g["witnesses"] for g in a.get("groups", [])
        } != {
            (g["block"], tuple(map(tuple, g["lanes"]))): g["witnesses"] for g in b.get("groups", [])
        }:
            raise ValueError("a control changed native CFO, timing or stencil weights")
    return rows, files


def conditional_geometry(m):
    held = [g for g in m.get("groups", []) if "held_rms" in g]
    rows = {}
    for metric, label in [
        ("held_jacobian", "conditional_weak_hz_s_km"),
        ("rf_free_jacobian", "conditional_rf_free_weak_hz_s_km"),
    ]:
        singular, _ = trial.model.geometry(held, metric, m.get("held_rms_hz_s"))
        rows[label] = singular[1] if len(singular) >= 2 else None
    s = m.get("centre_conditional_singular_hz_s_km", [])
    rows["centre_conditional_weak_hz_s_km"] = s[1] if len(s) >= 2 else None
    return rows


def score():
    rows, files = locked_predictions()
    refs, originals, *_ = authorities()
    scores, chart, queried, identities = [], [], {}, []
    for row in rows:
        ident, recording, panel = (row[k] for k in ("id", "recording", "cohort"))
        truth = refs[recording]["truth"]
        margin = roi_margin(truth, row["tile"])
        if (margin >= 0) != (panel != "omitted"):
            raise ValueError("measured site and offered region differ from expected containment")
        matches = {k: row[k] for k in MATCH}
        queried.setdefault(panel, []).append(
            dict(id=ident, recording=recording, truth=truth, condition=panel, bindings=matches)
        )
        point = row["tile"]["center"]
        centre = dict(
            status="ok",
            reason=None,
            boundary="Unconditional offered tile centre",
            metrics={},
            arms={a: dict(latlon=point, forced_latlon=None) for a in ARMS},
        )
        chart.extend([row, row | dict(method=CENTER, result=centre)])
        result = row["result"]
        metrics = result["metrics"]
        v5 = (
            original_scores(recording, refs[recording], originals[recording], truth)
            if panel == "known"
            else {}
        )
        geo = conditional_geometry(metrics)
        for arm in ARMS:
            end = result["arms"][arm]
            status, reason = arm_outcome(result, end)
            evaluate = arm == "c0"
            scores.append(
                dict(
                    id=ident,
                    recording=recording,
                    panel=panel,
                    arm=arm,
                    status=status,
                    reason=reason,
                    truth_in_offered_square=margin >= 0,
                    truth_signed_roi_margin_km=margin,
                    centre_error_km=distance_km(point, truth),
                    forced_error_km=distance_km(end["forced_latlon"], truth),
                    published_error_km=distance_km(end["latlon"], truth),
                    independent_held_orbits=len(metrics.get("held_independent_norads", []))
                    if evaluate
                    else None,
                    worker_cpu_s=row.get("cpu_s") if evaluate else None,
                    worker_wall_s=row.get("worker_s") if evaluate else None,
                    elapsed_s=row.get("native_elapsed_s") if evaluate else None,
                    peak_rss_kib=row.get("peak_rss_kib") if evaluate else None,
                    **{k: metrics.get(k) if evaluate else None for k in METRICS},
                    **{k: v if evaluate else None for k, v in geo.items()},
                    **{
                        f"{role}_{key}": v5[role][arm][i] if role in v5 else None
                        for role in ROLES
                        for i, key in enumerate(("error_km", "conditional_rms_hz"))
                    },
                )
            )
        groups = metrics.get("groups", [])
        for g in groups:
            held = g.get("held_rms")
            fields = (
                "winning_norads",
                "training_runner_up",
                "held_runner_up",
                "train_rms",
                "train_gap",
                "held_rms",
                "held_gap",
                "sham_rms",
                "visible_orbits",
                "candidate_triples",
            )
            identities.append(
                dict(
                    id=ident,
                    first_second=g["block"] * 40,
                    receiver=g["lanes"][0][0],
                    channels=[r[1] for r in g["lanes"]],
                    check="missing held continuation" if held is None else "contested",
                    **{k: g.get(k) for k in fields},
                )
            )
    save_json(OUT / "scores.json", dict(rows=scores))
    csv_file(OUT / "scores.csv", scores)
    csv_file(OUT / "identities.csv", identities)
    plot(scores, rows)
    save_json(
        OUT / "stage-figure.json",
        dict(
            version=1,
            id="differenced-orbits-support",
            title="Staggered RF lanes and held Doppler contrast",
            sample="Six roof recordings, matched displaced offers and a 79 s orbit-time sham.",
            boundary="Contemporaneous slope differences on three distinct carriers of one RF path.",
            note="Forced coordinates and low residuals can occur with contested orbit triplets.",
            seal="score-lock.json",
            image=PLOT,
            csv="scores.csv",
        ),
    )
    files |= {
        p: trial.digest((OUT / p).read_bytes())
        for p in (
            "prediction-lock.json",
            "stage-figure.json",
            "scores.csv",
            "scores.json",
            "identities.csv",
            PLOT,
        )
    }
    files[POSITIONS] = pack(OUT, POSITIONS, chart)
    save_json(
        OUT / "score-lock.json",
        dict(
            files=files,
            cases=[r["id"] for r in rows],
            scorer_sha256=trial.digest(Path(__file__).read_bytes()),
        ),
    )
    cards(
        queried, files | {"score-lock.json": trial.digest((OUT / "score-lock.json").read_bytes())}
    )


def cards(queries, base_files):
    charts = []
    titles = {
        "known": "Staggered RF contrasts on two matched roof recordings",
        "fresh": "Staggered RF contrasts on four hash-selected roof recordings",
        "omitted": "Staggered RF contrasts with the receiver outside the offer",
        "time-sham": "Staggered RF contrasts with orbit time advanced by 79 seconds",
    }
    for panel, rows in queries.items():
        direct = panel == "known"
        seal = panel + "-figure-lock.json"
        ids = [q["id"] for q in rows]
        chart = dict(
            id=METHOD + "-" + panel,
            method=METHOD,
            scope="roof" if direct else "transfer",
            title=titles[panel],
            caption="Tile centre and training-only forced estimates in both calibration views.",
            cases=ids,
            seal=seal,
            provenance=["prediction-lock.json", "score-lock.json"],
            series=[
                dict(
                    key="one" if direct else "candidate",
                    value=METHOD,
                    label="Staggered RF contrast",
                    forced_label="Staggered RF contrast · forced",
                    file=POSITIONS,
                    where={"cohort": panel},
                ),
                dict(
                    key="stock",
                    value=CENTER,
                    label="Offered tile centre",
                    file=POSITIONS,
                    where={"cohort": panel},
                    match=list(MATCH),
                ),
            ],
        )
        files = base_files.copy()
        if not direct:
            name = panel + "-queries.json"
            chart.update(queries=name, condition_labels={panel: panel.replace("-", " ").title()})
            save_json(OUT / name, dict(queries=rows))
            files[name] = trial.digest((OUT / name).read_bytes())
        save_json(OUT / seal, dict(cases=ids, files=files))
        charts.append(chart)
    save_json(OUT / "figures.json", dict(version=2, charts=charts))


def plot(scores, predictions):
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    rows = [r for r in scores if r["arm"] == "c0"]
    originals = [r for r in rows if r["panel"] in ("known", "fresh")]
    fig, (a, b, c) = plt.subplots(1, 3, figsize=(14, 4.3), layout="constrained")
    y = list(range(len(originals)))
    for key, marker, label in (
        ("train_groups", "o", "Selected from prefix"),
        ("held_groups", "x", "Same arcs later"),
    ):
        a.scatter([r[key] for r in originals], y, marker=marker, label=label)
    a.set(yticks=y, yticklabels=[r["recording"] for r in originals], xlabel="RF triplets")
    a.xaxis.set_major_locator(MaxNLocator(integer=True))
    a.invert_yaxis()
    a.legend(frameon=False, loc="lower right")
    colors = {"fresh": "#1f7d74", "omitted": "#b75835", "time-sham": "#605387"}
    held = [r for r in rows if r["held_rms_hz_s"] is not None]
    for i, r in enumerate(held):
        b.scatter(r["held_rms_hz_s"], i, marker="D", color=colors[r["panel"]])
    b.axvline(130, linestyle="--", color="0.55", label="Residual gate")
    b.set(
        yticks=list(range(len(held))),
        yticklabels=[f"{r['recording']} {r['panel']}" for r in held],
        xlabel="Held contrast RMS (Hz/s)",
    )
    b.invert_yaxis()
    b.legend(frameon=False, loc="lower right")
    by_id = {r["id"]: r for r in predictions}
    sample = [g for g in by_id["DS26-0136"]["result"]["metrics"]["groups"] if "held_rms" in g][0]
    seconds = (sample["block"] * 5 + np.asarray(sample["slots"]) + 0.5) * 8
    observed = np.asarray(sample["observed_contrasts_hz_s"])
    expected = np.vstack((sample["train_predicted_hz_s"], sample["held_predicted_hz_s"]))
    for i, co in enumerate(("#1f7d74", "#b75835")):
        c.plot(seconds, observed[:, i], "o", color=co, label=f"Observed contrast {i + 1}")
        c.plot(
            seconds, expected[:, i], "--", color=co, label="Orbit prediction" if i == 0 else None
        )
    c.axvline(sample["block"] * 40 + 24, color="0.45", linestyle=":", label="Held windows")
    c.set(
        xlabel="DS26-0136 capture time (s)",
        ylabel="Rate contrast (Hz/s)",
        title="Contested orbit triplet",
    )
    c.legend(frameon=False, fontsize=8)
    fig.savefig(OUT / PLOT, dpi=155)
    plt.close(fig)


if __name__ == "__main__":
    score()
