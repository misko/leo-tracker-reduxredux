"""Release sealed position predictions against the Prague and simulation surveys."""

import argparse
import gzip
from collections import defaultdict
from math import cos, radians
from pathlib import Path

from .. import figure_books, whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..scoring import ARMS, distance_km, distribution
from ..variants.compact_tile_interior import margin
from . import prague_transfer_results
from . import session_geometry_simulation as simulation
from . import session_geometry_trial as trial
from .full_v5_check import _sha
from .prefix_figures import csv_file

LABELS = {
    "fixed": "Fixed phase, intercept",
    "clock": "Fixed phase, affine clock",
    "phase": "Profiled phase, intercept",
    "phase-clock": "Profiled phase, affine clock",
    "center": "Offer centre",
    "median": "Median of capture fits",
    "shuffle": "Training CFO shuffle",
    "rotated": "Rotated training orbit",
}
FREQUENCIES = ("whole_curvature_rms_hz", "tail_forecast_rms_hz", "native_tail_rms_hz")
STAGE = "session-geometry-held-frequency"


def rectangles(offers):
    for name, tile in offers.items():
        lat, lon = tile["center"]
        height = tile["width_km"] / (2 * 111.0)
        width = tile["width_km"] / (2 * 111.32 * cos(radians(lat)))
        yield name, (lat - height, lat + height, lon - width, lon + width)


def signed_margins(truth, offers):
    bounds = list(rectangles(offers))
    for i, (name, (south, north, west, east)) in enumerate(bounds):
        for other, (low, high, left, right) in bounds[:i]:
            if max(south, low) <= min(north, high) and max(west, left) <= min(east, right):
                raise ValueError(f"the sealed search offers touch or overlap: {other} and {name}")
    signed = {name: margin(truth[:2], tile) for name, tile in offers.items()}
    if not all(value > 0 if name == "containing" else value < 0 for name, value in signed.items()):
        raise ValueError("survey membership contradicts sealed offer names")
    return signed


def geography(out, predictions, truths):
    chart_names = []
    for site, survey in truths.items():
        folder = out / site
        data, queries, lock = "positions.jsonl.gz", "queries.json", "figure-lock.json"
        roster = [r for r in predictions if r["site"] == site]
        unique = {row["id"]: row for row in roster}
        write(folder / data, gzip.compress(b"\n".join(map(encoded, roster)) + b"\n", mtime=0))
        save_json(
            folder / queries,
            dict(
                queries=[
                    dict(
                        id=case,
                        recording=row["recording"],
                        condition=row["offer"],
                        truth=survey[:2],
                        bindings={key: row[key] for key in ("tile", "input_sha256")},
                    )
                    for case, row in unique.items()
                ]
            ),
        )
        save_json(
            folder / lock,
            dict(cases=list(unique), files={p: _sha(folder / p) for p in (data, queries)}),
        )
        charts = []
        condition_labels = {k: k.replace("-", " ").title() for k in trial.model.REGIONS_KM}
        experiment = {
            "ablation": ("phase-clock", "fixed", "phase", "clock"),
            "pooling": ("phase-clock", "median", "center"),
            "controls": ("phase-clock", "rotated", "center", "shuffle"),
        }
        caption = (
            "One Prague rooftop and two visits. One coordinate per train/holdout direction. "
            "Author-selected peaks and unaudited ECEF availability."
            if site == "prague"
            else "One simulated Montevideo site and two generated visits. Fixed WGS84 survey."
        )
        for comparison, methods in experiment.items():
            key = f"session-geometry-{site}-{comparison}"
            chart_names.append(key)
            charts.append(
                dict(
                    id=key,
                    method=key,
                    scope="transfer",
                    title=f"{site.title()} static position · {comparison}",
                    caption=caption,
                    cases="sealed",
                    seal=lock,
                    queries=queries,
                    condition_labels=condition_labels,
                    series=[
                        dict(
                            key=series,
                            file=data,
                            value=method,
                            label=LABELS[method],
                            **(
                                {"forced_label": f"Forced {LABELS[method].lower()}"}
                                if method != "center"
                                else {}
                            ),
                        )
                        for series, method in zip(
                            ("candidate", "stock", "one", "four")[: len(methods)],
                            methods,
                            strict=True,
                        )
                    ],
                )
            )
        save_json(folder / "figures.json", dict(version=2, charts=charts))
    figure_books.generate(
        out / "charts", ARMS, panel="screening", evidence=out, methods=chart_names
    )


def stage(out, rows):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    containing = [row for row in rows if row["offer"] == "containing"]
    csv, png, pdf = (f"{STAGE}.{extension}" for extension in ("csv", "png", "pdf"))
    csv_file(out / csv, containing)
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), sharex=True, layout="constrained")
    for j, site in enumerate(("prague", "simulation")):
        series = axes[:, j]
        group = [r for r in containing if r["site"] == site]
        for i, metric in enumerate(FREQUENCIES[:2]):
            ax = series[i]
            for offset, visit in zip(
                (-0.12, 0.12), sorted({r["held_visit"] for r in group}), strict=True
            ):
                medians = [
                    distribution(
                        r[metric]
                        for r in group
                        if r["method"] == method and r["held_visit"] == visit
                    )["p50"]
                    for method in LABELS
                ]
                ax.scatter([p + offset for p in range(len(LABELS))], medians, label=visit)
            ax.set_yscale("log")
            ax.set_ylabel(
                ("Whole-capture curvature RMS" if i == 0 else "Prefix-conditioned tail RMS")
                + " (Hz)"
            )
            ax.grid(alpha=0.25, axis="y", which="both")
            ax.set_xticks(range(len(LABELS)), LABELS.values(), rotation=45, ha="right")
        series[0].set_title(site.title())
        series[0].legend(frameon=False)
    title = "Independent frequency scores in the containing offer"
    fig.suptitle(title)
    fig.savefig(out / png, dpi=160)
    fig.savefig(out / pdf, metadata={"CreationDate": None})
    plt.close(fig)
    descriptor, seal = "stage-figure.json", "stage-figure-lock.json"
    save_json(
        out / descriptor,
        dict(
            version=1,
            id=STAGE,
            title=title,
            sample="11 captures at one CTU roof and 10 at one simulated site",
            boundary="Whole-visit fit → per-capture held frequency residual",
            note=(
                "The nominal-phase curvature score fits zero held-capture parameters. Tail RMS "
                "uses the same clock and orbital phase profiling on the early 40% for every "
                "position. Dots are visit medians."
            ),
            seal=seal,
            csv=csv,
            image=png,
            pdf=pdf,
        ),
    )
    save_json(
        out / seal,
        dict(
            files={
                p: _sha(out / p)
                for p in (
                    trial.LOCK,
                    "frequency-scores.csv",
                    descriptor,
                    csv,
                    png,
                    pdf,
                )
            }
        ),
    )


def release(source, out):
    lock = whole_iq.read(out / trial.LOCK)
    for filename, digest in lock["files"].items():
        whole_iq.checked(out / filename, digest)
    for filename, digest in lock["source_files"].items():
        whole_iq.checked(ROOT / filename, digest)
    score_plan = dict(
        prediction_lock_sha256=_sha(out / trial.LOCK),
        scorer_sha256=_sha(Path(__file__)),
        frequency=list(FREQUENCIES),
        geographic="Haversine km, forced and published separately, one point per direction",
        positive_simulation_max_error_km=1.0,
    )
    plan_path = out / "score-plan-lock.json"
    if plan_path.exists() and whole_iq.read(plan_path) != score_plan:
        raise ValueError("score plan differs from pre-survey seal")
    save_json(plan_path, score_plan)
    plan = whole_iq.read(out / trial.PLAN)
    truth = dict(
        prague=prague_transfer_results.survey(source, {"captures": plan["ctu_members"]}),
        simulation=simulation.truth(),
    )
    margins = {site: signed_margins(value, plan["offers"][site]) for site, value in truth.items()}
    save_json(
        out / "survey-release.json",
        dict(
            prediction_lock_sha256=_sha(out / trial.LOCK),
            physical_prague_sites=1,
            wgs84=truth,
            signed_offer_margins_km=margins,
        ),
    )
    predictions = whole_iq.read(out / trial.PREDICTIONS)
    geographic, frequency, individual = [], [], []
    for row in predictions:
        site, offer, method = (row[key] for key in ("site", "offer", "method"))
        keys = dict(site=site, offer=offer, method=method, held_visit=row["recording"])
        result = row["result"]
        arm = result["arms"]["c0"]
        geographic.append(
            dict(
                **keys,
                status=result["status"],
                reason=result["reason"],
                forced_error_km=distance_km(arm["forced_latlon"], truth[site][:2]),
                published_error_km=distance_km(arm["latlon"], truth[site][:2]),
                fitted_c_status=result["arms"]["fitted_c"]["status"],
                train_objective_rms_hz=row["train_objective_rms_hz"],
                **result["metrics"],
            )
        )
        frequency.extend(dict(**keys, **held) for held in row["held_frequency"])
    for row in whole_iq.read(out / trial.INDIVIDUAL):
        individual.append(
            dict(row, forced_error_km=distance_km(row["point"], truth[row["site"]][:2]))
        )
    positive = [
        row
        for row in geographic
        if row["site"] == "simulation"
        and row["offer"] == "containing"
        and row["method"] == "phase-clock"
    ]
    save_json(
        out / "positive-simulation.json",
        dict(
            passed=len(positive) == 2
            and all(
                row["forced_error_km"] <= score_plan["positive_simulation_max_error_km"]
                for row in positive
            ),
            visit_outcomes=positive,
        ),
    )
    for filename, rows in (
        ("geographic-scores.csv", geographic),
        ("frequency-scores.csv", frequency),
        ("per-capture-scores.csv", individual),
    ):
        csv_file(out / filename, rows)
    summaries = defaultdict(list)
    for row in frequency:
        summaries[row["site"], row["offer"], row["method"], row["held_visit"]].append(row)
    save_json(
        out / "frequency-summary.json",
        [
            dict(
                site=site,
                offer=offer,
                method=method,
                held_visit=visit,
                **{key: distribution(r[key] for r in rows) for key in FREQUENCIES},
            )
            for (site, offer, method, visit), rows in summaries.items()
        ],
    )
    geography(out, predictions, truth)
    stage(out, frequency)
    save_json(
        out / "score-lock.json",
        dict(
            files={
                p: _sha(out / p)
                for p in (
                    trial.LOCK,
                    "score-plan-lock.json",
                    "survey-release.json",
                    "positive-simulation.json",
                    "geographic-scores.csv",
                    "per-capture-scores.csv",
                    "frequency-scores.csv",
                    "frequency-summary.json",
                    "charts/manifest.json",
                    "stage-figure-lock.json",
                )
            },
            scorer_sha256=_sha(Path(__file__)),
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=local_output)
    parser.add_argument("--out", type=local_output, default=trial.OUT)
    args = parser.parse_args()
    release(args.source, args.out)


if __name__ == "__main__":
    main()
