"""Release the survey after prediction and render the Prague diagnostic."""

import argparse
import gzip
from collections import Counter, defaultdict
from pathlib import Path
from zipfile import ZipFile

from .. import figure_books, whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..scoring import ARMS, distance_km, distribution, validate_result
from ..variants.compact_tile_interior import margin
from . import prague_transfer_trial as trial
from .full_v5_check import _sha
from .prefix_figures import csv_file

CONDITIONS = {"city": "Containing", "east-edge": "Near missing", "east-far": "Far missing"}
SERIES = {
    "curve": ("candidate", "Tied Doppler", "#0072b2"),
    "time-shuffle": ("stock", "Time shuffle", "#d55e00"),
    "center": ("one", "Offer centre", "#666666"),
}
FORCED_LABELS = {"curve": "Forced fit", "time-shuffle": "Forced shuffle"}
STAGE = "prague-held-doppler"
CAPTION = (
    "One CTU roof. Survey-aided track extraction and tied ECEF of unknown availability. "
    "A single RF makes fitted c unidentifiable."
)


def survey(source, plan):
    trial.source_receipts(source, ("outputs.zip",))
    with ZipFile(source / "outputs.zip") as archive:
        releases = [
            (data["truth"].tolist(), digest)
            for row in plan["captures"]
            for data, digest in [trial.read_mat(archive, row["member"])]
        ]
    if [digest for _, digest in releases] != [row["sha256"] for row in plan["captures"]]:
        raise ValueError("deposited recording member changed after the prediction")
    verified = {tuple(value) for value, _ in releases}
    if len(verified) != 1:
        raise ValueError("survey differs across author exports")
    return list(verified.pop())


def display_row(row):
    original = row["result"]
    if row["method"] == "center":
        arms = {key: dict(latlon=value["latlon"]) for key, value in original["arms"].items()}
    else:
        arms = dict(
            c0=original["arms"]["c0"],
            fitted_c=dict(
                status="unavailable",
                latlon=None,
                forced_latlon=None,
                reason="one_nominal_rf_is_in_track_intercept_span",
            ),
        )
    result = dict(original, arms=arms)
    validate_result(result)
    return dict(row, result=result)


def comparison(out, rows, queries, day):
    folder = out / day
    points_file, query_file, lock_file = "positions.jsonl.gz", "queries.json", "figure-lock.json"
    rows = [display_row(row) for row in rows]
    write(folder / points_file, gzip.compress(b"\n".join(map(encoded, rows)) + b"\n", mtime=0))
    save_json(folder / query_file, dict(queries=queries))
    save_json(
        folder / lock_file,
        dict(
            cases=[r["id"] for r in queries],
            files={name: _sha(folder / name) for name in (points_file, query_file)},
        ),
    )
    name = f"prague-{day}"
    save_json(
        folder / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id=name,
                    method=name,
                    scope="transfer",
                    cases="sealed",
                    seal=lock_file,
                    queries=query_file,
                    condition_labels=CONDITIONS,
                    title=f"Prague author-assisted Doppler · {day}",
                    caption=CAPTION,
                    series=[
                        dict(
                            key=key,
                            file=points_file,
                            value=method,
                            label=label,
                            **(
                                {"forced_label": FORCED_LABELS[method]}
                                if method in FORCED_LABELS
                                else {}
                            ),
                        )
                        for method, (key, label, _) in SERIES.items()
                    ],
                )
            ],
        ),
    )
    return name


def stage(out, rows):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    title = "Held Doppler fit in the containing Prague offer"
    fields = ("recording", "session", "method", "tracks", "held_rms_hz")
    chart = [{key: row[key] for key in fields} for row in rows if row["offer"] == "city"]
    names = [f"{STAGE}.{ext}" for ext in ("csv", "png", "pdf")]
    csv_file(out / names[0], chart)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.1), sharey=True, layout="constrained")
    for ax, day in zip(axes, sorted({r["session"] for r in chart}), strict=True):
        for method, (_, label, color) in SERIES.items():
            r = [r for r in chart if r["session"] == day and r["method"] == method]
            ax.plot(
                [item["recording"][9:13] for item in r],
                [item["held_rms_hz"] / 1000 for item in r],
                "o-",
                color=color,
                label=label,
                linewidth=1.6,
            )
        ax.set_title(day)
        ax.set_yscale("log")
        ax.set_xlabel("Capture order (filename UTC HHMM)")
        ax.grid(alpha=0.2, which="both", axis="y")
    axes[0].set_ylabel("Held Doppler RMS (kHz)")
    axes[0].legend(loc="center left", frameon=False)
    fig.suptitle(title)
    fig.supxlabel(CAPTION, fontsize=9, color="#394b56")
    fig.savefig(out / names[1], dpi=160)
    fig.savefig(out / names[2], metadata={"CreationDate": None})
    plt.close(fig)
    descriptor, seal = "stage-figure.json", "stage-figure-lock.json"
    save_json(
        out / descriptor,
        dict(
            version=1,
            id=STAGE,
            title=title,
            sample="11 recordings from two visits to one CTU roof",
            boundary="Published Doppler tracks with author-tied ECEF → held frequency residual",
            note=CAPTION + " Intercepts use the first 60% per track. The last 40% measure the RMS.",
            seal=seal,
            csv=names[0],
            image=names[1],
            pdf=names[2],
        ),
    )
    save_json(
        out / seal,
        dict(
            files={
                name: _sha(out / name)
                for name in (
                    trial.LOCK,
                    "scores.csv",
                    descriptor,
                    *names,
                )
            }
        ),
    )


def release(source, out):
    lock = whole_iq.read(out / trial.LOCK)
    for name, digest in lock["files"].items():
        whole_iq.checked(out / name, digest)
    for name, digest in lock["source_files"].items():
        whole_iq.checked(ROOT / name, digest)
    plan = whole_iq.read(out / trial.PLAN)
    truth = survey(source, plan)
    truth_margins = {key: margin(truth[:2], tile) for key, tile in plan["offers"].items()}
    if not (truth_margins["city"] > 0 > truth_margins["east-edge"] > truth_margins["east-far"]):
        raise ValueError("recorded survey does not match the declared offer conditions")
    save_json(
        out / "survey-release.json",
        dict(
            physical_sites=1,
            author_truth_wgs84=truth,
            selected_recordings=len(plan["captures"]),
            prediction_lock_sha256=_sha(out / trial.LOCK),
            signed_margins_km=truth_margins,
        ),
    )
    predictions = whole_iq.read(out / trial.PREDICTIONS)
    capture_ids = {r["id"]: r["start_utc"][:10] for r in plan["captures"]}
    by_session, queries, groups = defaultdict(list), defaultdict(dict), defaultdict(list)
    scores = []
    for row in predictions:
        day, offer, method = capture_ids[row["recording"]], row["offer"], row["method"]
        arm = row["result"]["arms"]["c0"]
        score = dict(
            recording=row["recording"],
            session=day,
            offer=offer,
            method=method,
            status=row["result"]["status"],
            reason=row["result"]["reason"],
            tracks=row["tracks"],
            published_error_km=distance_km(truth[:2], arm["latlon"]),
            forced_error_km=distance_km(truth[:2], arm["forced_latlon"]),
            **row["result"]["metrics"],
            cpu_s=row["cpu_s"],
            wall_s=row["wall_s"],
        )
        scores.append(score)
        groups[day, offer, method].append(score)
        by_session[day].append(row)
        queries[day][row["id"]] = dict(
            id=row["id"],
            condition=offer,
            recording=row["recording"],
            truth=truth[:2],
            bindings={key: row[key] for key in ("tile", "input_sha256")},
        )
    csv_file(out / "scores.csv", scores)
    save_json(
        out / "summary.json",
        [
            dict(
                session=day,
                offer=offer,
                method=method,
                attempted=len(values),
                statuses=dict(Counter(row["status"] for row in values)),
                reasons=dict(Counter(row["reason"] for row in values if row["reason"] is not None)),
                **{
                    key: distribution(row[key] for row in values)
                    for key in (
                        "published_error_km",
                        "forced_error_km",
                        "held_rms_hz",
                        "train_rms_hz",
                        "cpu_s",
                        "wall_s",
                    )
                },
            )
            for (day, offer, method), values in groups.items()
        ],
    )
    names = [
        comparison(out, rows, list(queries[day].values()), day) for day, rows in by_session.items()
    ]
    figure_books.generate(out / "charts", ARMS, panel="screening", evidence=out, methods=names)
    stage(out, scores)
    receipts = (
        trial.LOCK,
        "scores.csv",
        "summary.json",
        "survey-release.json",
        "charts/manifest.json",
        "stage-figure-lock.json",
    )
    save_json(
        out / "score-lock.json",
        dict(
            files={name: _sha(out / name) for name in receipts},
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
