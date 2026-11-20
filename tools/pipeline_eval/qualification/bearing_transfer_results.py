"""Score held StarLoc phase, matched Doppler and true containing or near-missing offers."""

import gzip
import json
from pathlib import Path

import numpy as np

from ..__main__ import save_json
from ..scoring import arm_outcome, distance_km
from . import bearing_transfer_trial as trial
from .armijo_finish_results import pack
from .native_joint_full_results import roi_margin
from .prefix_figures import csv_file

OUT = trial.OUT
PLOT = "measured-phase-support.png"
METRICS = (
    "modeled_arcs",
    "train_pairs",
    "held_pairs",
    "total_nominees",
    "held_rate_rms_hz_s",
    "held_phase_rms_rad",
    "held_phase_time_sham_rad",
    "held_phase_reflection_rad",
    "held_conditional_radius_km",
    "held_spatial_lead",
    "train_yaw_deg",
)
BIND = ("native_sha256", "catalogue_sha256", "input_sha256", "measured_pairs_sha256")
PRIMARY, CONTROL = trial.model.METHODS


def checked():
    lock = trial.read(OUT / "prediction-lock.json")
    for name, digest in lock["files"].items():
        if trial.digest((OUT / name).read_bytes()) != digest:
            raise ValueError(f"prediction lock differs for {name}")
    with gzip.open(OUT / trial.ARTIFACT, "rt") as stream:
        imported = list(map(json.loads, stream))
    rows = {(r["id"], r["method"]): r for r in imported}
    plan = trial.read(OUT / "blind-plan.json")
    if len(rows) != len(imported) or len(rows) != 2 * lock["calls"]:
        raise ValueError("unexpected measured capture roster")
    for entry in plan["cases"]:
        suffix = "_author_id" if entry["author_id"] else ""
        a, b = (rows[entry["id"], model + suffix] for model in trial.model.METHODS)
        if any(any(r.get(k) != v for k, v in entry.items()) for r in (a, b)):
            raise ValueError("the two methods used a different measured packet")
        if any(
            a["result"]["metrics"].get(k) != b["result"]["metrics"].get(k)
            for k in ("modeled_arcs", "train_pairs", "held_pairs", "total_nominees")
        ):
            raise ValueError("Doppler and phases did not use the same opportunities")
        if entry["mode"] == "near-missing":
            matching = entry["id"].replace("-near-missing", "-containing")
            r = rows[matching, PRIMARY + suffix]
            if r["measured_pairs_sha256"] != entry["measured_pairs_sha256"]:
                raise ValueError("offered region changed the observed phase or Doppler")
    if any(r["result"]["status"] in ("failed", "timed_out") for r in rows.values()):
        raise ValueError("physical-site worker failed, consult the sealed trace")
    return rows, lock, plan


def score():
    rows, lock, plan = checked()
    source = trial.authority.STUDY / "field_private/truth.json"
    truth = {
        r["id"]: r
        for r in json.loads(
            trial.authority._read(
                source,
                plan["scoring_truth_sha256"],
            )
        )["cases"]
    }
    scored, assignments, queries = [], [], {}
    for (ident, method), r in rows.items():
        point = truth[r["original_case_id"]]["latlon"]
        boxed = roi_margin(point, r["tile"])
        if (boxed >= 0) != (r["mode"] == "containing"):
            raise ValueError("actual region support differs from the matched offer condition")
        suffix = "_author_id" if r["author_id"] else ""
        if method == PRIMARY + suffix:
            qq = queries.setdefault((r["mode"], suffix), [])
            qq.append(
                dict(
                    id=ident,
                    recording=ident.split(f"-{r['mode']}")[0],
                    truth=point,
                    condition="repeat" if r["repeat"] else "first",
                    bindings={k: r[k] for k in BIND},
                )
            )
        result = r["result"]
        m = result["metrics"]
        labels = {
            x["arc"]: x["orbit"]
            for x in rows[ident, PRIMARY + "_author_id"]["result"]["metrics"].get("arcs", [])
        }
        for arc in m.get("arcs", []):
            assignments.append(
                dict(
                    id=ident,
                    method=method,
                    arc=arc["arc"],
                    proposed_norad=arc["orbit"],
                    paired_author_norad=labels.get(arc["arc"]),
                    confirmed=arc["confirmed"],
                    prefix_margin=arc["prefix_margin"],
                    held_margin=arc["held_margin"],
                    held_alternative=arc["held_alternative"],
                    held_phase_rms_rad=arc.get("held_phase_rms_rad"),
                    held_rate_rms_hz_s=arc.get("held_rate_rms_hz_s"),
                )
            )
        agreements = [
            x["orbit"] == labels[x["arc"]] for x in m.get("arcs", []) if x["arc"] in labels
        ]
        for arm, endpoint in result["arms"].items():
            available = arm == "c0"
            status, reason = arm_outcome(result, endpoint)
            scored.append(
                dict(
                    id=ident,
                    method=method,
                    site=r["site"],
                    repeat=r["repeat"],
                    mode=r["mode"],
                    arm=arm,
                    status=status,
                    reason=reason,
                    signed_truth_margin_km=boxed,
                    tile_error_km=distance_km(point, r["tile"]["center"]),
                    forced_error_km=distance_km(point, endpoint["forced_latlon"]),
                    published_error_km=distance_km(point, endpoint["latlon"]),
                    author_id=r["author_id"],
                    phase_and_doppler=method.startswith(PRIMARY),
                    independent_held_orbits=len(m.get("held_independent_norads", []))
                    if available and not r["author_id"]
                    else None,
                    comparable_author_orbits=len(agreements)
                    if available and not r["author_id"]
                    else None,
                    author_orbit_agreements=sum(agreements)
                    if available and not r["author_id"]
                    else None,
                    worker_wall_s=r["worker_wall_s"] if available else None,
                    worker_cpu_s=r["cpu_s"] if available else None,
                    elapsed_s=r["elapsed_s"] if available else None,
                    rss_kib=r["rss_kib"] if available else None,
                    **{k: m.get(k) if available else None for k in METRICS},
                )
            )
    save_json(OUT / "scores.json", dict(rows=scored))
    csv_file(OUT / "scores.csv", scored)
    csv_file(OUT / "orbit-comparisons.csv", assignments)
    plot(scored)
    stage_spec = dict(
        version=1,
        id="bearing-transfer-data-and-null-support",
        title="Held differential phase in measured StarLoc captures",
        sample="First measured capture at each of eight physical sites.",
        boundary="Raw channel phase changes and training-only yaw.",
        note="The shuffled and reflected controls preserve observed frequencies and times.",
        seal="score-lock.json",
        image=PLOT,
        csv="scores.csv",
    )
    save_json(OUT / "stage-figure.json", stage_spec)
    artifacts = (
        "scores.csv",
        "scores.json",
        "orbit-comparisons.csv",
        PLOT,
        "stage-figure.json",
        "prediction-lock.json",
    )
    files = lock["files"] | {p: trial.digest((OUT / p).read_bytes()) for p in artifacts}
    save_json(
        OUT / "score-lock.json",
        dict(
            files=files,
            score_source_sha256=trial.digest(Path(__file__).read_bytes()),
        ),
    )
    cards(
        rows,
        queries,
        files | {"score-lock.json": trial.digest((OUT / "score-lock.json").read_bytes())},
    )


def cards(rows, panels, files):
    chart_rows = [
        r | {"recording": r["id"].split(f"-{r['mode']}")[0], "cohort": r["mode"]}
        for r in rows.values()
    ]
    comparison = "chart-positions.jsonl.gz"
    files[comparison] = pack(OUT, comparison, chart_rows)
    charts = []
    for (mode, suffix), queries in panels.items():
        slug = ("author-id" if suffix else "anonymous") + "-" + mode
        filename = f"{slug}-queries.json"
        seal = f"{slug}-figure-lock.json"
        save_json(OUT / filename, dict(queries=queries))
        chart_files = files | {filename: trial.digest((OUT / filename).read_bytes())}
        ids = [r["id"] for r in queries]
        save_json(OUT / seal, dict(files=chart_files, cases=ids))
        charts.append(
            dict(
                id="bearing-transfer-" + slug,
                method=PRIMARY,
                scope="transfer",
                title=("Author-ID aided" if suffix else "Anonymous") + f" StarLoc, {mode} offers",
                caption="Three-channel phase and Doppler on eight sites and three repeat captures.",
                cases=ids,
                queries=filename,
                condition_labels={
                    "first": "First captures at eight sites",
                    "repeat": "Repeat captures",
                },
                seal=seal,
                provenance=["prediction-lock.json", "score-lock.json"],
                series=[
                    dict(
                        key="candidate",
                        file=comparison,
                        value=PRIMARY + suffix,
                        where={"cohort": mode},
                        label="Phase and Doppler",
                        forced_label="Phase and Doppler · forced",
                    ),
                    dict(
                        key="stock",
                        file=comparison,
                        value=CONTROL + suffix,
                        where={"cohort": mode},
                        label="Doppler only",
                        forced_label="Doppler only · forced",
                        match=list(BIND),
                    ),
                ],
            )
        )
    save_json(OUT / "figures.json", dict(version=2, charts=charts))


def plot(scores):
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    rows = [
        r
        for r in scores
        if r["arm"] == "c0"
        and not r["repeat"]
        and r["mode"] == "containing"
        and r["method"] == PRIMARY
    ]
    rows.sort(key=lambda r: r["site"])
    y = np.arange(len(rows))
    fig, (a, b, c) = plt.subplots(1, 3, figsize=(13.2, 4.4), layout="constrained")
    for field, label, marker in (
        ("train_pairs", "Training", "o"),
        ("held_pairs", "Held", "x"),
    ):
        a.scatter([r[field] for r in rows], y, label=label, marker=marker)
    a.xaxis.set_major_locator(MaxNLocator(integer=True))
    a.legend(frameon=False)
    a.set(
        yticks=y,
        yticklabels=[r["site"].split("-")[-1] for r in rows],
        ylabel="Physical site",
        xlabel="Admitted phase and Doppler pairs",
    )
    for field, name, marker in (
        ("held_phase_rms_rad", "Observed", "o"),
        ("held_phase_time_sham_rad", "Time shuffle", "x"),
        ("held_phase_reflection_rad", "Reflected baseline", "+"),
    ):
        b.scatter([r[field] for r in rows], y, label=name, marker=marker)
    b.set(yticks=y, yticklabels=[], xlabel="Held phase vector RMS (rad)")
    b.legend(frameon=False)
    for method, label, symbol in (
        (PRIMARY, "Anonymous", "o"),
        (PRIMARY + "_author_id", "Author IDs supplied", "d"),
    ):
        values = {
            r["site"]: r["held_conditional_radius_km"]
            for r in scores
            if r["arm"] == "c0"
            and r["method"] == method
            and not r["repeat"]
            and r["mode"] == "containing"
        }
        c.scatter([values[r["site"]] for r in rows], y, label=label, marker=symbol)
    c.axvline(5, linewidth=1, color="0.5", linestyle=":")
    c.set(yticks=y, yticklabels=[], xscale="log", xlabel="Weakest-axis conditional scale (km)")
    c.legend(frameon=False)
    for ax in (a, b, c):
        ax.invert_yaxis()
    fig.savefig(OUT / PLOT, dpi=155)
    plt.close(fig)


if __name__ == "__main__":
    score()
