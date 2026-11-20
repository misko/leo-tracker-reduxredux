"""Score locked cross-satellite phase diagnostics and render matched position views."""

import gzip
import json
from pathlib import Path

import numpy as np

from ..__main__ import save_json
from ..scoring import ARMS, arm_outcome, distance_km
from . import array_closure_trial as trial
from .armijo_finish_results import pack
from .native_joint_full_results import roi_margin
from .prefix_figures import csv_file

OUT, prior = trial.OUT, trial.prior
PLOT = "array-closure-evidence.png"
METRICS = (
    "observed_pairs",
    "modeled_pairs",
    "observed_stencils",
    "modeled_train",
    "modeled_held",
    "candidate_pairs",
    "held_supported_pairs",
    "training_cost",
    "held_cost",
    "held_region_lead",
    "held_rate_rms_hz_s",
    "held_phase_rms_rad",
    "held_phase_time_sham_rad",
    "held_phase_identity_sham_rad",
    "held_phase_bias_removed_rms_rad",
    "held_radius_km",
    "held_pair_bias_free_radius_km",
)
OBSERVED = METRICS[:6]


def data():
    lock = prior.read(OUT / "prediction-lock.json")
    for p, sha in lock["files"].items():
        if prior.digest((OUT / p).read_bytes()) != sha:
            raise ValueError("changed prediction closure")
    plan = prior.read(OUT / "blind-plan.json")
    with gzip.open(OUT / trial.ARCHIVE, "rt") as stream:
        rows = {(r["id"], r["method"]): r for r in map(json.loads, stream)}
    for q in plan["cases"]:
        methods = [(short, rows[q["id"], long]) for short, long in trial.names(q["author_id"])]
        by_scope = {}
        for short, r in methods:
            if any(r[k] != v for k, v in q.items()):
                raise ValueError("changed offer or measurement input")
            if r["result"]["status"] in ("failed", "timed_out"):
                raise ValueError(f"worker did not complete for {q['id']}: {r['result']['reason']}")
            observed = [r["result"]["metrics"].get(k) for k in OBSERVED]
            scope = short.rsplit("_", 1)[0]
            group = by_scope.setdefault(scope, observed)
            if group != observed:
                raise ValueError("matched fits used different measurements or candidates")
            original = q["id"].replace("-near-missing", "-containing")
            source = rows[original, r["method"]]
            if any(source[k] != r[k] for k in trial.MATCH):
                raise ValueError("omitted query changed observed support")
    if len(rows) != 6 * lock["calls"]:
        raise ValueError("missing method results for a scheduled fit")
    return rows, lock, plan


def score():
    predictions, lock, plan = data()
    source = prior.authority.STUDY / "field_private/truth.json"
    truth = {
        r["id"]: r
        for r in json.loads(
            prior.authority._read(
                source,
                plan["scoring_truth_sha256"],
            )
        )["cases"]
    }
    table, diagnostics, queries, charts = [], [], {}, []
    for q in plan["cases"]:
        ident, mode, assisted = q["id"], q["mode"], q["author_id"]
        point = truth[q["original_case_id"]]["latlon"]
        margin = roi_margin(point, q["tile"])
        if (margin >= 0) != (mode == "containing"):
            raise ValueError("the checked survey and offered region disagree")
        endpoint = q["tile"]["center"]
        recording = ident.removesuffix("-" + mode)
        chart_row = q | dict(
            recording=recording,
            cohort=mode,
            method="array_closure_centre",
            result=dict(
                status="ok",
                boundary="Offered square centre",
                reason=None,
                metrics={},
                arms={a: dict(latlon=endpoint, forced_latlon=None) for a in ARMS},
            ),
        )
        charts.append(chart_row)
        queries.setdefault((mode, assisted), []).append(
            dict(
                id=ident,
                recording=recording,
                truth=point,
                condition="repeat" if q["repeat"] else "first",
                bindings={k: q[k] for k in (*trial.MATCH, "input_sha256")},
            )
        )
        for short, method in trial.names(assisted):
            scope, technique = short.rsplit("_", 1)
            record = predictions[ident, method]
            result = record["result"]
            m = result["metrics"]
            chart_value = result
            if result["status"] == "withheld" and not m["position_attempted"]:
                chart_value = result | {"metrics": m | {"terminal_position_decision": True}}
            charts.append(record | dict(recording=recording, cohort=mode, result=chart_value))
            for arm, value in result["arms"].items():
                status, reason = arm_outcome(result, value)
                c0 = arm == "c0"
                row = dict(
                    id=ident,
                    site=q["site"],
                    repeat=q["repeat"],
                    mode=mode,
                    scope=scope,
                    author_id=assisted,
                    method=technique,
                    arm=arm,
                    status=status,
                    reason=reason,
                    truth_margin_km=margin,
                    center_error_km=distance_km(point, endpoint),
                    forced_error_km=distance_km(point, value["forced_latlon"]),
                    published_error_km=distance_km(point, value["latlon"]),
                    worker_cpu_s=record.get("cpu_s") if c0 else None,
                    worker_wall_s=record.get("worker_wall_s") if c0 else None,
                    elapsed_s=record.get("elapsed_s") if c0 else None,
                    rss_kib=record.get("rss_kib") if c0 else None,
                    **{k: m.get(k) if c0 else None for k in METRICS},
                )
                table.append(row)
            for r in m.get("pairs", []):
                diagnostics.append(
                    dict(
                        id=ident,
                        scope=scope,
                        author_id=assisted,
                        method=technique,
                        **{
                            k: r.get(k)
                            for k in (
                                "arcs",
                                "orbit_pair",
                                "train_gap",
                                "held_gap",
                                "train_stencils",
                                "held_stencils",
                                "held_rate_rms_hz_s",
                                "held_phase_rms_rad",
                                "held_phase_time_sham_rad",
                                "held_phase_identity_sham_rad",
                                "held_phase_bias_removed_rms_rad",
                                "candidate_pairs",
                            )
                        },
                    )
                )
    csv_file(OUT / "scores.csv", table)
    csv_file(OUT / "pair-diagnostics.csv", diagnostics)
    save_json(OUT / "scores.json", dict(rows=table))
    plot(table)
    save_json(
        OUT / "stage-figure.json",
        dict(
            version=1,
            id="array-closure-held-evidence",
            title="Cross-satellite phase support and conditioning",
            sample="First recordings at eight StarLoc sites with containing offers.",
            boundary="Exact simultaneous phase and bracketed hardware-only phase correction.",
            note="The offset sensitivity removes a free phase constant for each satellite pair.",
            seal="score-lock.json",
            image=PLOT,
            csv="scores.csv",
        ),
    )
    files = lock["files"] | {
        p: prior.digest((OUT / p).read_bytes())
        for p in (
            "prediction-lock.json",
            "scores.csv",
            "scores.json",
            "pair-diagnostics.csv",
            "stage-figure.json",
            PLOT,
        )
    }
    comparison = "chart-positions.jsonl.gz"
    files[comparison] = pack(OUT, comparison, charts)
    save_json(
        OUT / "score-lock.json",
        dict(files=files, scorer_sha256=prior.digest(Path(__file__).read_bytes())),
    )
    write_cards(
        queries,
        files | {"score-lock.json": prior.digest((OUT / "score-lock.json").read_bytes())},
        comparison,
    )


def write_cards(queries, files, archive):
    cards = []
    for (mode, assisted), rows in queries.items():
        suffix = "_author_id" if assisted else ""
        endpoint = "author-id" if assisted else "anonymous"
        root = endpoint + "-" + mode
        query = root + "-queries.json"
        seal = root + "-figure-lock.json"
        save_json(OUT / query, dict(queries=rows))
        files_here = files | {query: prior.digest((OUT / query).read_bytes())}
        ids = [r["id"] for r in rows]
        save_json(OUT / seal, dict(files=files_here, cases=ids))
        for scope, scope_title in (("coincident", "Exact"), ("wire_stable", "Wire-stable")):
            candidates = []
            for k, label, method in (
                ("candidate", "Phase closure", scope + "_closure"),
                ("stock", "Temporal phase", scope + "_temporal"),
                ("one", "Doppler rate", scope + "_doppler"),
                ("four", "Tile centre", "centre"),
            ):
                name = "array_closure_" + method + ("" if method == "centre" else suffix)
                where = {"cohort": mode, "author_id": assisted}
                series = dict(key=k, value=name, file=archive, where=where, label=label)
                if k != "candidate":
                    series["match"] = [*trial.MATCH, "input_sha256"]
                candidates.append(series)
            cards.append(
                dict(
                    id="array-closure-" + scope + "-" + root,
                    method="array_closure_" + scope + "_closure" + suffix,
                    scope="transfer",
                    title=f"{scope_title} phase closure, {endpoint}, {mode} tiles",
                    caption="The three fits share recorded endpoints and causal orbit options.",
                    cases=ids,
                    queries=query,
                    seal=seal,
                    series=candidates,
                    provenance=["prediction-lock.json", "score-lock.json"],
                    condition_labels={"first": "First captures", "repeat": "Repeat captures"},
                )
            )
    save_json(OUT / "figures.json", dict(version=2, charts=cards))


def plot(table):
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    records = [
        r
        for r in table
        if r["arm"] == "c0"
        and r["method"] == "closure"
        and r["mode"] == "containing"
        and not r["repeat"]
        and not r["author_id"]
    ]
    sites = sorted({r["site"] for r in records})
    y = np.arange(len(sites))
    scopes = ("coincident", "wire_stable")
    fig, (a, b, c) = plt.subplots(1, 3, figsize=(13.4, 4.6), layout="constrained")
    for i, scope in enumerate(scopes):
        lookup = {r["site"]: r for r in records if r["scope"] == scope}
        shift = (-1 if i == 0 else 1) * 0.1
        a.scatter(
            [lookup[s]["modeled_held"] for s in sites],
            y + shift,
            label=("Exact" if i == 0 else "Wire-stable"),
            marker=("o" if i == 0 else "x"),
        )
        b.scatter(
            [lookup[s]["held_phase_rms_rad"] for s in sites],
            y + shift,
            label=("Exact" if i == 0 else "Wire-stable"),
            marker=("o" if i == 0 else "x"),
        )
        if i == 0:
            continue
        b.scatter(
            [lookup[s]["held_phase_time_sham_rad"] for s in sites],
            y,
            label="Held time shuffle",
            marker="+",
            color="0.5",
        )
        c.scatter(
            [lookup[s]["held_radius_km"] for s in sites], y - 0.1, marker="o", label="Shared phase"
        )
        c.scatter(
            [lookup[s]["held_pair_bias_free_radius_km"] for s in sites],
            y + 0.1,
            marker="x",
            label="Free pair bias",
        )
    a.xaxis.set_major_locator(MaxNLocator(integer=True))
    labels = ("Held four-endpoint stencils", "Held phase RMS (rad)", "Wire-stable local scale (km)")
    c.set_xscale("log")
    c.set_xticks([5, 10, 20, 40, 80], labels=["5", "10", "20", "40", "80"])
    c.tick_params(axis="x", which="minor", labelbottom=False)
    c.axvline(5, color="0.5", linestyle=":", linewidth=1)
    for ax, label in zip((a, b, c), labels, strict=True):
        if ax != a:
            ax.tick_params(labelleft=False)
        ax.set(yticks=y, yticklabels=[s.split("-")[-1] for s in sites], xlabel=label)
        ax.invert_yaxis()
        ax.legend(frameon=False, fontsize=8)
    a.set_ylabel("Physical site")
    fig.savefig(OUT / PLOT, dpi=155)
    plt.close(fig)


if __name__ == "__main__":
    score()
