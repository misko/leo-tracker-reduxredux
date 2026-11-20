"""Score and plot the sealed signed-range comparisons and calibration audit."""

import argparse
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from .. import corpus, figure_books, whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS, distance_km, distribution, validate_result
from ..variants import code_carrier as model
from ..variants import compact_tile_interior
from ..variants.multi_session import design
from . import code_carrier_trial as trial
from .full_v5_check import _sha
from .prefix_figures import csv_file

LABELS = dict(
    carrier="Carrier only",
    joint="Joint shared",
    joint_free="Joint free",
    code_shuffle="Epoch shuffle",
    carrier_shuffle="CFO shuffle",
    center="Tile center",
)
CONDITIONS = dict(containing="Containing", near_missing="Near missing", far_missing="Far missing")
COMPARISONS = (
    (
        "joint",
        "Code plus carrier on the same native endpoints",
        (
            ("candidate", "joint"),
            ("stock", "carrier"),
            ("one", "joint_free"),
            ("four", "center"),
        ),
    ),
    (
        "shuffle",
        "Code and carrier with matched timing shuffles",
        (
            ("candidate", "joint"),
            ("stock", "code_shuffle"),
            ("one", "carrier_shuffle"),
        ),
    ),
)
SUPPORT = "code-carrier-support"


def sealed(report):
    lock = whole_iq.read(report / trial.LOCK)
    for name, digest in lock["files"].items():
        whole_iq.checked(report / name, digest)
    plan = whole_iq.read(report / trial.PLAN)
    path = report / trial.PREDICTIONS
    rows = list(map(json.loads, gzip.decompress(path.read_bytes()).splitlines()))
    if [row["id"] for row in rows] != lock["cases"]:
        raise ValueError("the signed-range worker output differs from its sealed roster")
    for case, row in zip(plan["cases"], rows, strict=True):
        if any(row[key] != value for key, value in case.items()):
            raise ValueError("signed-range worker changed blind inputs")
        if row["status"] == "ok":
            for record in row["outcomes"]:
                validate_result(record["result"])
    return plan, rows


def outcomes(row):
    if row["status"] == "ok":
        return row["outcomes"]
    _, offers = design(row["center"])
    result = dict(
        status=row["status"],
        reason=row["reason"],
        boundary=model.BOUNDARY,
        arms={arm: dict(latlon=None) for arm in ARMS},
        metrics=dict(position_attempted=False),
    )
    return [
        dict(
            offer=offer, tile=dict(center=value["center"], width_km=25), method=mode, result=result
        )
        for offer, value in offers.items()
        for mode in model.MODES
    ]


def scored(row, record, truth, reference):
    result = record["result"]
    endpoint = result["arms"]["c0"]
    metrics = result["metrics"]
    matched = metrics.get("matched_carrier_only", {})
    cal = row.get("calibration", {})
    baseline = reference.get("reference", {}).get("baseline", {})
    singular = metrics.get("fisher_singular_km_inv", (None, None))
    carrier_singular = matched.get("fisher_singular_km_inv", (None, None))
    fields = (
        "code_rms",
        "carrier_rms",
        "closure_rms",
        "code_clock_only_rms",
        "code_reflected_rms",
        "code_shuffled_rms",
        "carrier_shuffled_rms",
        "fisher_rank",
        "qualified_held_orbits",
        "held_site_lead",
        "selected_cell_km",
    )
    return dict(
        id=row["id"],
        group=row["group"],
        offer=record["offer"],
        mode=record["method"],
        status=result["status"],
        reason=result["reason"],
        published_error_km=distance_km(endpoint.get("latlon"), truth),
        forced_error_km=distance_km(endpoint.get("forced_latlon"), truth),
        truth_tile_margin_km=compact_tile_interior.margin(truth, record["tile"]),
        baseline_c0_km=baseline.get("c0", {}).get("error_km"),
        baseline_fitted_c_km=baseline.get("fitted_c", {}).get("error_km"),
        arcs=len(row.get("arcs", [])),
        donor_orbits=row.get("donor_orbits"),
        train_intervals=row.get("train_intervals"),
        held_intervals=row.get("held_intervals"),
        train_loss=metrics.get("loss", {}).get("train"),
        held_loss=metrics.get("loss", {}).get("held"),
        fisher_min_km_inv=singular[0],
        fisher_max_km_inv=singular[1],
        carrier_fisher_min_km_inv=carrier_singular[0],
        carrier_fisher_max_km_inv=carrier_singular[1],
        calibration_rank=cal.get("rank"),
        calibration_rank_with_c=cal.get("rank_with_c"),
        c_projected_norm=cal.get("residual_norm"),
        cpu_s=row.get("cpu_s"),
        wall_s=row["direct_wall_s"],
        rss_mib=row["peak_rss_kib"] / 1024 if "peak_rss_kib" in row else None,
        **{field: metrics.get(field) for field in fields},
    )


def position_figures(folder, positions, queries, key):
    folder.mkdir(parents=True, exist_ok=True)
    files = ("positions.jsonl.gz", "queries.json")
    write(
        folder / files[0], gzip.compress(b"".join(encoded(p) + b"\n" for p in positions), mtime=0)
    )
    save_json(folder / files[1], dict(queries=queries))
    save_json(
        folder / "figure-lock.json",
        dict(cases=[r["id"] for r in queries], files={n: _sha(folder / n) for n in files}),
    )
    cards = []
    for suffix, title, comparisons in COMPARISONS:
        name = f"code-carrier-{key}-{suffix}"
        subject = (
            "Four measured recordings at one roof"
            if key == "roof"
            else "One blinded generated site"
        )
        cards.append(
            dict(
                id=name,
                method=name,
                scope="transfer",
                cases="sealed",
                seal="figure-lock.json",
                queries=files[1],
                condition_labels=CONDITIONS,
                title=title,
                caption=(
                    subject + ". The fitted RF coefficient is absorbed by the local "
                    "carrier offset. Numeric positions use the c0 gauge."
                ),
                series=[
                    dict(
                        key=s,
                        file=files[0],
                        value=m,
                        label=LABELS[m],
                        forced_label=f"{LABELS[m]} fit",
                    )
                    for s, m in comparisons
                ],
            )
        )
    save_json(folder / "figures.json", dict(version=2, charts=cards))
    return [card["id"] for card in cards]


def support(report, scores):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fields = (
        "id",
        "group",
        "held_intervals",
        "arcs",
        "code_rms",
        "carrier_rms",
        "closure_rms",
        "code_clock_only_rms",
        "code_reflected_rms",
        "code_shuffled_rms",
        "carrier_shuffled_rms",
        "fisher_min_km_inv",
        "carrier_fisher_min_km_inv",
    )
    points = [
        {key: r[key] for key in fields}
        for r in scores
        if r["offer"] == "containing" and r["mode"] == "joint"
    ]
    csv_file(report / f"{SUPPORT}.csv", points)
    fig, axes = plt.subplots(1, 3, figsize=(12.6, 4.3), layout="constrained")
    x = np.arange(len(points))
    labels = [p["id"] if p["group"] != "simulation" else "Simulated" for p in points]
    for ax, series, title, unit in (
        (
            axes[0],
            (
                ("code_rms", "Physical"),
                ("code_clock_only_rms", "Clock only"),
                ("code_reflected_rms", "Reflected"),
                ("code_shuffled_rms", "Epoch shuffle"),
            ),
            "Held pilot arrival difference",
            "RMS, ADC samples",
        ),
        (
            axes[1],
            (("carrier_rms", "Physical"), ("carrier_shuffled_rms", "CFO shuffle")),
            "Held integrated CFO",
            "RMS, ADC samples",
        ),
        (
            axes[2],
            (("fisher_min_km_inv", "Joint"), ("carrier_fisher_min_km_inv", "Carrier only")),
            "Weakest profiled direction",
            "Conditional singular value, km⁻¹",
        ),
    ):
        for offset, (key, label) in zip(np.linspace(-0.20, 0.20, len(series)), series, strict=True):
            y = [np.nan if p[key] is None else max(p[key], 1e-9) for p in points]
            ax.scatter(x + offset, y, label=label, s=22)
        ax.set(xticks=x, title=title, ylabel=unit, yscale="log")
        ax.set_xticklabels(labels, rotation=18)
        ax.axvline(len(points) - 1.5, color="#9ca3af", linestyle="--", linewidth=0.9)
        ax.grid(axis="y", alpha=0.2)
        ax.legend(fontsize=8)
    fig.suptitle("Matched held code and carrier evidence at the joint containing fit")
    fig.savefig(report / f"{SUPPORT}.png", dpi=170)
    fig.savefig(report / f"{SUPPORT}.pdf")
    plt.close(fig)
    save_json(
        report / "stage-figure.json",
        dict(
            version=1,
            id=SUPPORT,
            title="Held signed code and carrier geometry",
            sample="4 roof recordings · 1 separately labeled generated site",
            boundary="Native GLRT → held range change and conditional spatial information",
            note=(
                "Endpoints match within each recording. Training sets position and nuisance terms. "
                "The Fisher panel conditions on frozen anonymous orbit hypotheses."
            ),
            seal="score-lock.json",
            image=f"{SUPPORT}.png",
            pdf=f"{SUPPORT}.pdf",
            csv=f"{SUPPORT}.csv",
        ),
    )


def execute(work, report):
    plan, rows = sealed(report)
    priv = {
        name: whole_iq.checked(work / "private" / name, digest)
        for name, digest in plan["private_sim"].items()
    }
    sim = whole_iq.read(priv["truth.json"])
    save_json(
        report / "simulation-release.json",
        dict(seed_hex=priv["seed.bin"].read_bytes().hex(), labels=sim),
    )
    ids = {r["id"] for r in rows if r["group"] != "simulation"}
    refs = {
        r["id"]: r
        for p in ("roof16", "ds26-all159")
        for r in corpus.references(p)
        if r["id"] in ids
    }
    score, queries, positions = [], defaultdict(list), defaultdict(list)
    for row in rows:
        key = "simulation" if row["group"] == "simulation" else "roof"
        ref = sim if key == "simulation" else refs[row["id"]]
        seen = set()
        for record in outcomes(row):
            offer = record["offer"]
            ident = f"{row['id']}-{offer}"
            geo = ref["truth"]
            values = scored(row, record, geo, ref)
            if (values["truth_tile_margin_km"] >= 0) != (offer == "containing"):
                raise ValueError("supplied region does not match the sealed condition")
            bindings = dict(
                tile=record["tile"],
                native_sha256=row["native_sha256"],
                catalog_sha256=row["catalog_sha256"],
                input_sha256=row["input_sha256"],
            )
            if offer not in seen:
                seen.add(offer)
                queries[key].append(
                    dict(
                        id=ident, condition=offer, recording=row["id"], truth=geo, bindings=bindings
                    )
                )
            positions[key].append(
                dict(id=ident, method=record["method"], result=record["result"], **bindings)
            )
            score.append(values)
    csv_file(report / "scores.csv", score)
    groups = defaultdict(list)
    for row in score:
        cohort = "simulation" if row["group"] == "simulation" else "roof"
        groups[cohort, row["offer"], row["mode"]].append(row)
    save_json(
        report / "summary.json",
        dict(
            conditions=[
                dict(
                    cohort=c,
                    offer=o,
                    mode=m,
                    attempted=len(rs),
                    statuses=dict(Counter(r["status"] for r in rs)),
                    forced_error_km=distribution(r["forced_error_km"] for r in rs),
                    published_error_km=distribution(r["published_error_km"] for r in rs),
                    code_rms_samples=distribution(r["code_rms"] for r in rs),
                    carrier_rms_samples=distribution(r["carrier_rms"] for r in rs),
                )
                for (c, o, m), rs in groups.items()
            ]
        ),
    )
    chart_ids = [
        name
        for key in ("roof", "simulation")
        for name in position_figures(report / key, positions[key], queries[key], key)
    ]
    figure_books.generate(
        report / "charts", ARMS, panel="screening", evidence=report, methods=chart_ids
    )
    support(report, score)
    included = (
        trial.LOCK,
        "scores.csv",
        "summary.json",
        "simulation-release.json",
        "charts/manifest.json",
        "stage-figure.json",
        *(f"{SUPPORT}.{ext}" for ext in ("png", "pdf", "csv")),
    )
    save_json(
        report / "score-lock.json",
        dict(
            files={name: _sha(report / name) for name in included},
            scorer_sha256=_sha(Path(__file__)),
        ),
    )


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("work", type=local_output)
    cli.add_argument("--report", type=local_output, default=trial.OUT)
    args = cli.parse_args()
    execute(args.work, args.report)


if __name__ == "__main__":
    main()
