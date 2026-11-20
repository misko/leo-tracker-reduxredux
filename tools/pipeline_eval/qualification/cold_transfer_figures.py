"""Render one checked physical and synthetic transfer page per cold receiver."""

import argparse
import gzip
import io
import json
from collections import Counter
from hashlib import sha256
from os.path import relpath
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch
from matplotlib.ticker import FixedLocator, FuncFormatter, PercentFormatter

from .. import corpus
from ..__main__ import encoded, read_predictions, save_json, write
from ..position_figure import save_png
from ..scoring import ARMS, distance_km, distribution, validate_result
from . import cold_missing, cold_scenes
from .prefix_figures import csv_file

REPORT = cold_missing.REPORT
DEFAULT_OUT = corpus.REPO / "reports/2026_11_19_position_atlas/cold-transfer"
TITLES = {
    "point_votes": "Carrier and frame-timing votes",
    "rate_triplets": "Frequency rate triplets",
    "folded_doppler": "Folded Doppler trajectories",
}
COHORTS = {
    "correct": ("Physical · Correct tile", "Three DS29 captures, same roof"),
    "omitted": ("Physical · Correct region omitted", "The same captures, one wrong tile each"),
    "synthetic": ("Simulated · Global search", "Four planted sites, no search tile"),
}
SHUFFLE = "shuffle"
LOCATIONS = ("Europe", "Australia", "Mexico", "Southern Africa")
ARM_LABELS = {"c0": "Zero calibration", "fitted_c": "Fitted calibration"}
COLORS = {"c0": "#087b89", "fitted_c": "#a65b28"}
AXTEXT = "#28414a"
ERROR_LIMIT = 22000


def _read(path):
    return json.loads(path.read_bytes())


def _digest(path):
    return sha256(path.read_bytes()).hexdigest()


def _record(evidence, path, expected=None):
    digest = _digest(path)
    if expected is not None and digest != expected:
        raise ValueError(f"saved evidence differs from its commitment: {path}")
    evidence[str(path.relative_to(corpus.REPO))] = digest


def _position_row(method, record, case, label, cohort, truth, source, arm):
    outcome = record["result"]
    output = outcome.get("arms", {}).get(arm, {})
    fix, forced = output.get("latlon"), output.get("forced_latlon")
    published = fix is not None
    status = "published" if published else outcome["status"]
    if status == "ok":
        status = "withheld"
    return dict(
        method=method,
        arm=arm,
        cohort=cohort,
        id=case,
        label=label,
        status=status,
        reason=outcome.get("reason"),
        published=published,
        false_publication=published and cohort in ("omitted", SHUFFLE),
        forced=forced is not None,
        error_km=distance_km(fix, truth),
        forced_error_km=distance_km(forced, truth),
        source=str(source.relative_to(corpus.REPO)),
    )


def _frozen_bindings(refs):
    ids, files = corpus._selection("transfer124")
    inputs = corpus._index(corpus._read_frozen("inputs.jsonl", files))
    conditions = {case: row["condition"] for case, row in refs.items()}
    bindings = []
    for case, expected in cold_missing.CASES.items():
        native = inputs[case]
        query, tile = cold_missing.select_query(
            native, (inputs[key] for key in ids), conditions, expected
        )
        public = {field: query[field] for field in ("id", "observation", "catalog", "regions")}
        bindings.append(
            dict(
                id=case,
                query_id=expected,
                query_sha256=sha256(encoded(public) + b"\n").hexdigest(),
                native_sha256=native["native"]["sha256"],
                observation_sha256=query["observation"],
                catalog_sha256=query["catalog"],
                catalog_timestamp_ns=query["catalog_timestamp_ns"],
                supplied_tile=tile,
                supplied_offer_index=0,
            )
        )
    return bindings


def _physical(evidence):
    folder = REPORT / "wrong-tiles"
    saved = folder / "scores.json"
    _record(evidence, saved)
    receipts = _read(saved)["receipts"]
    refs = {r["id"]: r for r in corpus.references("transfer124")}
    bindings = _frozen_bindings(refs)
    rows = []
    for method, (directory, release) in cold_missing.METHODS.items():
        lock_path = folder / f"{method}-lock.json"
        lock = _read(lock_path)
        _record(evidence, lock_path)
        plan_path = folder / f"{method}-plan.json"
        _record(evidence, plan_path, lock["plan_sha256"])
        if _read(plan_path)["bindings"] != bindings or any(
            receipts[method][key] != value for key, value in lock.items()
        ):
            raise ValueError("omitted tile evidence differs from the frozen paired plan")
        correct_path = REPORT / directory / "matched-tile.jsonl.gz"
        omitted_path = folder / f"{method}.jsonl.gz"
        _record(evidence, correct_path, receipts[method]["correct_sha256"])
        _record(evidence, omitted_path, lock["prediction_sha256"])
        if (correct_lock_path := correct_path.with_name("prediction-lock.json")).is_file():
            _record(evidence, correct_lock_path)
            _record(evidence, correct_path, _read(correct_lock_path)["files"][correct_path.name])
        correct = read_predictions(correct_path)
        omitted = read_predictions(omitted_path)
        if omitted.keys() != set(cold_missing.CASES):
            raise ValueError("omitted predictions must cover the exact paired recording roster")
        for binding in bindings:
            case, query = binding["id"], binding["query_id"]
            label = refs[query]
            if label["condition"] != "missing" or label["recording"] != case:
                raise ValueError("omitted offer and physical position reference differ")
            _check_physical_pair(correct[case], omitted[case], binding, method, release)
            for arm in ARMS:
                rows.append(
                    _position_row(
                        method,
                        correct[case],
                        case,
                        case,
                        "correct",
                        label["truth"],
                        correct_path,
                        arm,
                    )
                )
                rows.append(
                    _position_row(
                        method,
                        omitted[case],
                        case,
                        case,
                        "omitted",
                        label["truth"],
                        omitted_path,
                        arm,
                    )
                )
    return rows


def _check_physical_pair(correct, omitted, binding, method, release):
    for row, policy in ((correct, "matched-tile"), (omitted, "omitted-tile")):
        if (
            row["mode"] != policy
            or row["method"] != method
            or row["implementation_sha256"] != release
            or any(row[key] != binding[key] for key in ("id", "native_sha256", "catalog_sha256"))
        ):
            raise ValueError("physical comparison contains unmatched recording or solver inputs")
    if any(omitted[key] != value for key, value in binding.items()):
        raise ValueError("omitted prediction used a tile outside the paired plan")


def _synthetic(evidence):
    folder = REPORT / "scenes"
    prediction_lock = folder / "prediction-lock.json"
    lock = _read(prediction_lock)
    _record(evidence, prediction_lock)
    input_lock = folder / "input-lock.json"
    _record(evidence, input_lock, lock["input_lock_sha256"])
    inputs = _read(input_lock)
    source_lock = folder / "source-lock.json"
    _record(evidence, source_lock, inputs["source_lock_sha256"])
    releases = _read(source_lock)["sources"]
    if any(
        releases[f"tools/pipeline_eval/variants/{name}"] != digest
        for name, digest in cold_scenes.RELEASES.items()
    ):
        raise ValueError("synthetic evidence used a different solver release")
    _record(evidence, folder / "manifest.json", inputs["manifest_sha256"])
    if lock["mode"] != "global" or lock["methods"] != list(TITLES):
        raise ValueError("expected the corrected common three-method synthetic global seal")
    source = folder / "predictions.jsonl.gz"
    _record(evidence, source, lock["predictions_sha256"])
    scored = folder / "scores.json"
    _record(evidence, scored)
    labels = _read(scored)["generated_truth"]
    if sha256(encoded(labels) + b"\n").hexdigest() != inputs["truth_sha256"]:
        raise ValueError("synthetic truth differs from its input commitment")
    roster = [*lock["cases"]]
    if (
        len(roster) != 5
        or set(roster) != labels.keys()
        or [labels[case]["case_index"] for case in roster[:4]] != list(range(4))
        or any(labels[case]["latlon"] is None for case in roster[:4])
        or labels[roster[-1]]["latlon"] is not None
    ):
        raise ValueError("expected four matched planted sites and one shuffle without a position")
    with gzip.open(source, "rt") as stream:
        predictions = list(map(json.loads, stream))
    indexed = {(r["method"], r["id"]): r for r in predictions}
    if len(predictions) != 15 or indexed.keys() != {(m, c) for m in TITLES for c in roster}:
        raise ValueError("synthetic methods must predict all five cases once")
    rows = []
    for method in TITLES:
        for index, case in enumerate(roster):
            result = indexed[method, case]
            validate_result(result["result"])
            cohort = "synthetic" if index < 4 else SHUFFLE
            label = LOCATIONS[index] if index < 4 else "Shuffled candidates"
            for arm in ARMS:
                rows.append(
                    _position_row(
                        method, result, case, label, cohort, labels[case]["latlon"], source, arm
                    )
                )
    return rows


def evidence_rows():
    evidence = {}
    for name in ("provenance.json", "inputs.jsonl", "panels.json", "targets.jsonl"):
        _record(evidence, corpus.FROZEN / name)
    rows = [*_physical(evidence), *_synthetic(evidence)]
    expected = {"correct": 3, "omitted": 3, "synthetic": 4, SHUFFLE: 1}
    actual = Counter((r["method"], r["arm"], r["cohort"]) for r in rows)
    if actual != Counter(
        {
            (method, arm, group): count
            for method in TITLES
            for arm in ARMS
            for group, count in expected.items()
        }
    ) or len({(r["method"], r["arm"], r["cohort"], r["id"]) for r in rows}) != len(rows):
        raise ValueError("chart evidence contains missing or repeated attempts")
    return rows, evidence


def _summary(rows):
    summaries = []
    for method in TITLES:
        for cohort in (*COHORTS, SHUFFLE):
            for arm in ARMS:
                sample = [
                    r for r in rows if (r["method"], r["cohort"], r["arm"]) == (method, cohort, arm)
                ]
                states = Counter(r["status"] for r in sample)
                errors = [r["error_km"] for r in sample]
                summaries.append(
                    dict(
                        method=method,
                        cohort=cohort,
                        arm=arm,
                        attempts=len(sample),
                        published=states["published"],
                        withheld=states["withheld"],
                        other_outcomes=sum(
                            n
                            for state, n in states.items()
                            if state not in ("published", "withheld")
                        ),
                        status_counts=dict(states),
                        false_publications=sum(r["false_publication"] for r in sample),
                        within_5_km=sum(e is not None and e <= 5 for e in errors)
                        if cohort != SHUFFLE
                        else None,
                        forced=sum(r["forced"] for r in sample),
                        error_km=distribution(errors),
                        forced_error_km=distribution(r["forced_error_km"] for r in sample),
                    )
                )
    return summaries


def _style_error_axis(ax, cohort, limit):
    ax.set_xscale("symlog", linthresh=0.05)
    ax.set_xlim(0, limit)
    ticks = [0, 0.1, 1, 5, 50, 500] if limit == 1000 else [0, 0.1, 1, 5, 50, 500, 5000, 20000]
    ax.xaxis.set_major_locator(FixedLocator(ticks))
    ax.xaxis.set_major_formatter(
        FuncFormatter(lambda value, _: f"{value / 1000:g}k" if value >= 1000 else f"{value:g}")
    )
    ax.set_facecolor("#faf7ef" if cohort == "synthetic" else "#f4f8f9")
    ax.axvline(5, color="#9aabb2", linestyle=":", linewidth=1)
    ax.spines[["right", "top"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#b7c7cb")
    ax.tick_params(colors=AXTEXT, labelsize=8, length=3)
    ax.set_axisbelow(True)
    ax.grid(color="#e0e9eb", linewidth=0.8)


def _coverage(ax, rows, stats, cohort, limit):
    _style_error_axis(ax, cohort, limit)
    title, subtitle = COHORTS[cohort]
    ax.text(0, 1.24, title, transform=ax.transAxes, fontsize=12, color=AXTEXT, weight="bold")
    ax.text(0, 1.10, subtitle, transform=ax.transAxes, fontsize=8.5, color=AXTEXT)
    ax.set_ylim(-0.06, 1.06)
    ax.set_yticks([0, 1 / 3, 2 / 3, 1] if cohort != "synthetic" else [0, 0.25, 0.5, 0.75, 1])
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    ax.tick_params(axis="x", labelbottom=False)
    for index, arm in enumerate(ARMS):
        errors = sorted(
            r["error_km"] for r in rows if r["arm"] == arm and r["error_km"] is not None
        )
        subtotal = stats[arm]
        n = subtotal["attempts"]
        ax.step(
            [0, *errors, limit],
            [0, *(np.arange(1, len(errors) + 1) / n), len(errors) / n],
            where="post",
            color=COLORS[arm],
            linewidth=1.6,
            linestyle="-" if index == 0 else "--",
        )
        pubs = "false fixes" if cohort == "omitted" else "published"
        text = f"{subtotal['published']}/{n} {pubs} · {subtotal['withheld']}/{n} withheld"
        if subtotal["other_outcomes"]:
            text += f" · {subtotal['other_outcomes']}/{n} other"
        ax.text(
            0.98,
            0.92 - index * 0.15,
            text,
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=8.3,
            color=COLORS[arm],
        )


def _dot_plot(ax, rows, cohort, limit):
    _style_error_axis(ax, cohort, limit)
    locations = list(dict.fromkeys(r["label"] for r in rows))
    ax.set_yticks(range(len(locations)), locations)
    ax.set_ylim(len(locations) - 0.52, -0.50)
    ax.set_xlabel("Horizontal error (km)", fontsize=9, color=AXTEXT)
    ax.text(1.013, 1.025, "Fix?", transform=ax.transAxes, fontsize=8, color=AXTEXT)
    for row in rows:
        arm = row["arm"]
        y = locations.index(row["label"]) + (-0.16 if arm == "c0" else 0.16)
        color = COLORS[arm]
        if row["forced_error_km"] is not None:
            ax.scatter(
                row["forced_error_km"],
                y,
                s=44,
                facecolors="none",
                edgecolors=color,
                linewidths=1.1,
                zorder=3,
            )
        if row["error_km"] is not None:
            ax.scatter(row["error_km"], y, s=18, color=color, zorder=4)
        state = {"published": "●", "withheld": "×"}.get(row["status"], "–")
        ax.text(
            1.021,
            y,
            state,
            transform=ax.get_yaxis_transform(),
            va="center",
            color=color,
            fontsize=10,
            clip_on=False,
        )


def _page(method, rows, summaries):
    fig, axes = plt.subplots(2, 3, figsize=(14.6, 8.25), gridspec_kw={"height_ratios": (1, 1.35)})
    fig.subplots_adjust(left=0.11, right=0.955, top=0.742, bottom=0.21, hspace=0.62, wspace=0.48)
    fig.text(0.053, 0.951, TITLES[method], fontsize=24, weight="bold", color="#132b35")
    fig.text(
        0.054,
        0.914,
        "Paired physical tiles and independent synthetic cold start",
        fontsize=11,
        color=AXTEXT,
    )
    handles = [
        Line2D(
            [],
            [],
            color=COLORS[arm],
            linewidth=2,
            label=ARM_LABELS[arm],
            linestyle="-" if arm == "c0" else "--",
        )
        for arm in ARMS
    ]
    handles.extend(
        [
            Line2D([], [], color=AXTEXT, ls="none", marker="o", label="Published fix", ms=5),
            Line2D(
                [],
                [],
                color=AXTEXT,
                ls="none",
                marker="o",
                mfc="none",
                label="Forced estimate",
                ms=6,
            ),
            Line2D([], [], color=AXTEXT, ls="none", marker="x", label="Withheld", ms=6),
        ]
    )
    fig.legend(
        handles=handles,
        ncol=5,
        loc="upper left",
        bbox_to_anchor=(0.046, 0.887),
        frameon=False,
        fontsize=10,
    )
    physical_limit = 1000
    if any(
        r["cohort"] in ("correct", "omitted")
        and max(r["error_km"] or 0, r["forced_error_km"] or 0) > physical_limit
        for r in rows
    ):
        physical_limit = ERROR_LIMIT
    for column, cohort in enumerate(COHORTS):
        selected = [r for r in rows if r["method"] == method and r["cohort"] == cohort]
        stats = {r["arm"]: r for r in summaries if r["method"] == method and r["cohort"] == cohort}
        limit = ERROR_LIMIT if cohort == "synthetic" else physical_limit
        _coverage(axes[0, column], selected, stats, cohort, limit)
        _dot_plot(axes[1, column], selected, cohort, limit)
    axes[0, 0].set_ylabel("Published at or below error", fontsize=10, color=AXTEXT)
    fig.add_artist(
        FancyBboxPatch(
            (0.047, 0.075),
            0.908,
            0.078,
            boxstyle="round,pad=0.006",
            transform=fig.transFigure,
            facecolor="#f3f6f7",
            edgecolor="#dce6e8",
            linewidth=0.7,
        )
    )
    fig.text(0.054, 0.127, "Shuffled synthetic control", fontsize=11, color=AXTEXT, weight="bold")
    fig.text(0.054, 0.098, "No reference position", fontsize=8.7, color=AXTEXT)
    for index, arm in enumerate(ARMS):
        row = next(
            r for r in summaries if (r["method"], r["cohort"], r["arm"]) == (method, SHUFFLE, arm)
        )
        at = 0.30 + index * 0.32
        fig.text(at, 0.127, ARM_LABELS[arm], fontsize=9, weight="bold", color=COLORS[arm])
        n = row["attempts"]
        fig.text(
            at,
            0.098,
            f"{row['false_publications']}/{n} false fixes · {row['withheld']}/{n} withheld"
            f" · {row['forced']}/{n} forced",
            fontsize=8.7,
            color=AXTEXT,
        )
    fig.text(
        0.054,
        0.039,
        "Coverage uses all attempts. The dotted line marks 5 km. "
        "Simulated errors use a wider horizontal scale.",
        fontsize=8.7,
        color=AXTEXT,
    )
    return fig


def generate(out):
    rows, sources = evidence_rows()
    summaries = _summary(rows)
    out = Path(out)
    pdf = io.BytesIO()
    with PdfPages(
        pdf, metadata=dict(Title="Cold-start receiver transfer", CreationDate=None)
    ) as book:
        for method in TITLES:
            fig = _page(method, rows, summaries)
            try:
                save_png(fig, out / f"{method}.png")
                book.savefig(fig)
            finally:
                plt.close(fig)
    write(out / "modifications.pdf", pdf.getvalue())
    csv_file(out / "per-case.csv", rows)
    save_json(out / "coverage.json", dict(groups=summaries, sources=sources))
    index = [
        "# Cold-start receiver transfer",
        "",
        "Each page compares the correct tile and one omitted-region tile on the",
        "same three physical DS29 captures from one roof. The separate synthetic",
        "panel tests four new planted sites with a global search. The shuffled",
        "control has no geographic reference and appears in its own count row.",
        "",
        "Both calibration arms use the same attempt roster in each panel. Curves",
        "show the fraction of attempts that published at or below each error.",
        "Open circles mark forced positions and crosses mark withholding. The",
        "omitted-region count treats every publication as a false fix. These",
        "pages compare the three cold receivers' existing measurements.",
        "",
        "[Figure book](modifications.pdf) · [Per-case data](per-case.csv) ·",
        "[Coverage and source digests](coverage.json)",
        "",
        *(f"- [{title}]({method}.png)" for method, title in TITLES.items()),
        "",
        "The source studies document the matched physical tile challenge and the",
        "corrected synthetic input. The earlier timing-invalid draw is excluded.",
        f"[Physical challenge](<{relpath(REPORT / 'wrong-tiles/README.md', out)}>) ·",
        f"[Synthetic controls](<{relpath(REPORT / 'scenes/README.md', out)}>)",
        "",
    ]
    destination = out / "README.md"
    write(destination, "\n".join(index).encode())
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    generate(parser.parse_args().out)


if __name__ == "__main__":
    main()
