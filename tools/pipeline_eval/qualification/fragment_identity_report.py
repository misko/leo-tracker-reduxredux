"""Export sealed fragment fits, native point checks, and a measured figure."""

import csv
import gzip
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from ..__main__ import save_json
from .fragment_identity_inputs import CASE, OUT
from .fragment_identity_search import ARMS, ENVELOPE, LEVELS, Support, rms, verify
from .full_v5_check import _sha
from .input_factor_bridge import read
from .range_epoch_model import FOLD_HZ, wrap

REGIMES = ("causal", "later")


def read_gzip(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def table(path, rows, compressed=False):
    keys = list(dict.fromkeys(k for row in rows for k in row))
    opener = gzip.open if compressed else open
    with opener(path, "wt", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def ranked(run, arm, level):
    return sorted(
        (
            r
            for r in run["candidate_fits"]
            if r["arm"] == arm and r["level"] == level and r["fit"] is not None
        ),
        key=lambda r: (r["fit"]["held_loss"], r["norad"]),
    )


def bridge(selection):
    out = []
    wide = {p["id"]: p for p in selection["wide_context"]}
    period = round(selection["proof"]["actual_sample_rate"] / 750)
    for row in selection["selected_parents"]:
        if row["condition"] in ("matched_graph", "matched_untracked") or row["id"] not in wide:
            continue
        old = row["context"]["winner"]
        original_epoch = old["integer_epoch_sample"] + old["fractional_epoch_offset_samples"]
        matched = []
        for p in wide[row["id"]]["candidates"]:
            delta_epoch = wrap(
                p["integer_epoch_sample"] + p["fractional_epoch_offset_samples"] - original_epoch,
                period,
            )
            delta_hz = wrap(
                p["fractional_tracking_cfo_hz"] - old["fractional_tracking_cfo_hz"],
                FOLD_HZ,
            )
            if abs(delta_epoch) <= 2 and abs(delta_hz) <= 1000:
                matched.append(dict(p, epoch_delta_samples=delta_epoch, folded_delta_hz=delta_hz))
        out.append(
            dict(
                id=row["id"],
                visit=row["context"]["visit"],
                time_s=row["time_s"],
                disposition=row["condition"],
                wide_graph=wide[row["id"]]["graph"],
                parent_peak=old,
                wide_winner=wide[row["id"]]["winner"],
                reciprocal_neighborhood=matched,
            )
        )
    return sorted(out, key=lambda row: row["time_s"])


def plot_prediction(support, run, index, arm, level, prior_fit=None):
    fit = index["fit"] if prior_fit is None else prior_fit
    row = next(
        r
        for r in run["curve_predictions"]
        if r["norad"] == index["norad"] and r["arm"] == arm and r["level"] == level
    )
    physical = np.asarray(row["phase_curves"][fit["phase_index"]])
    radio = np.asarray(run["radio"][arm]["L1" if level == "L1" else "L2"])
    if level == "L0":
        radio[:] = 0
    adjusted = physical + radio + fit["rate_hz_per_100s"] * support.q
    corrected = (
        adjusted
        + np.array([fit["alias"][support.names.index(p)] for p in support.pieces]) * FOLD_HZ
    )
    return physical, corrected, support.y - corrected


def summarize(selection, runs, support):
    original = selection["chosen"]["owner"]
    output, swaps, cross_rows = [], [], []
    for arm in ARMS:
        for level in LEVELS:
            for regime, run in runs.items():
                table_rows = ranked(run, arm, level)
                original_row = next(r for r in table_rows if r["norad"] == original)
                raw = table_rows[:5]
                result = dict(
                    arm=arm,
                    level=level,
                    regime=regime,
                    eligible_at_level=len(table_rows),
                    original_rank=table_rows.index(original_row) + 1,
                    finalists=raw,
                    original=original_row,
                )
                if level == "L3":
                    for fold in (0, 1):
                        rows = sorted(
                            table_rows, key=lambda r: r["fit"]["folds"][fold]["held_whitened_loss"]
                        )
                        cross_rows.append(
                            dict(
                                arm=arm,
                                regime=regime,
                                fold=fold,
                                original_rank=rows.index(original_row) + 1,
                                trained_graph=rows[0]["fit"]["folds"][fold]["trained_graph"],
                                top=[
                                    dict(norad=r["norad"], **r["fit"]["folds"][fold])
                                    for r in rows[:5]
                                ],
                            )
                        )
                output.append(result)
            before = next(r for r in ranked(runs["causal"], arm, level) if r["norad"] == original)
            later = next(r for r in ranked(runs["later"], arm, level) if r["norad"] == original)
            _, _, fixed = plot_prediction(support, runs["later"], later, arm, level, before["fit"])
            swaps.append(
                dict(
                    arm=arm,
                    level=level,
                    norad=original,
                    causal_joint_rms_hz=before["fit"]["full_rms_hz"],
                    later_frozen_causal_rms_hz=rms(fixed),
                    later_refitted_joint_rms_hz=later["fit"]["full_rms_hz"],
                    causal_phase_s=before["fit"]["phase_s"],
                    later_refitted_phase_s=later["fit"]["phase_s"],
                )
            )
    return output, swaps, cross_rows


def render(selection, runs, comparison, support, prediction_rows):
    fig, ax = plt.subplots(3, 2, figsize=(14, 12), layout="constrained")
    fig.suptitle(
        "DS29-0082 · RX1 CH1 · two wide Graph pieces and the published capture-era owner",
        fontsize=16,
        fontweight="bold",
        color="#172b36",
    )
    a, b, c, d, e, f = ax.flat
    cohort = {row["id"] for row in selection["target"]}
    chosen = selection["chosen"]["component"]
    settings = (
        ("capture_context", "Capture-era owned component", "#355e8a", selection["capture_context"]),
        ("wide_context", "Selected wide Graph pieces", "#008878", selection["wide_context"]),
    )
    for field, label, color, rows in settings:
        for category, sub, marker, fill in (
            (
                label,
                [
                    r
                    for r in rows
                    if r["winner"]
                    and (r["graph"] == chosen if field.startswith("capture") else r["id"] in cohort)
                ],
                "o",
                color,
            ),
            (
                "Other tracked",
                [
                    r
                    for r in rows
                    if r["winner"]
                    and r["graph"]
                    and (
                        r["graph"] != chosen
                        if field.startswith("capture")
                        else r["id"] not in cohort
                    )
                ],
                ".",
                "#949ca0",
            ),
            ("Untracked", [r for r in rows if r["winner"] and not r["graph"]], "x", "#B3B8BA"),
        ):
            legend = category if field.startswith("capture") or category == label else None
            a.scatter(
                [r["time_s"] for r in sub],
                [wrap(r["winner"]["fractional_tracking_cfo_hz"], FOLD_HZ) / 1000 for r in sub],
                label=legend,
                color=fill,
                s=22 if category == label else 12,
                marker=marker,
                alpha=0.7,
            )
        measured = [r for r in rows if r["winner"]]
        f.scatter(
            [r["time_s"] for r in measured],
            [r["winner"]["fractional_margin"] for r in measured],
            s=14,
            label="Capture-era winners" if field.startswith("capture") else "Wide winners",
            color=color,
            alpha=0.75,
        )
    recoverable = [row for row in bridge(selection) if row["reciprocal_neighborhood"]]
    if recoverable:
        alternatives = [
            max(row["reciprocal_neighborhood"], key=lambda peak: peak["fractional_margin"])
            for row in recoverable
        ]
        a.scatter(
            [row["time_s"] for row in recoverable],
            [wrap(p["fractional_tracking_cfo_hz"], FOLD_HZ) / 1000 for p in alternatives],
            s=65,
            linewidth=1.4,
            color="#b66039",
            marker="+",
            label="Matched wide nonwinner",
            zorder=4,
        )
        f.scatter(
            [row["time_s"] for row in recoverable],
            [p["fractional_margin"] for p in alternatives],
            s=64,
            color="#b66039",
            marker="+",
            label="Matched wide nonwinner",
            zorder=4,
        )
    a.set(title="Native folded CFO context", ylabel="Folded CFO (kHz)")
    a.legend(fontsize=8, loc="best", frameon=False)
    f.axhline(0.025, color="#8b4e31", linestyle=":", lw=1, label="Original fractional margin gate")
    f.set(title="Detector score by native opportunity", ylabel="Fractional exact − control")
    f.legend(fontsize=8, frameon=False)
    b.scatter(
        support.t, support.y / 1000, s=18, color="#182e39", label="Wide Graph lifted observations"
    )
    for bank, arm, color in (("causal", "c0", "#126a5e"), ("later", "fitted_c", "#a76233")):
        row = next(
            r for r in comparison if (r["arm"], r["regime"], r["level"]) == (arm, bank, "L3")
        )
        model = row["finalists"][0]
        physical, adjusted, residual = plot_prediction(support, runs[bank], model, arm, "L3")
        for j, group in enumerate(support.folds):
            tag = f"{bank} {arm.replace('_', ' ')} · {model['norad']}"
            b.plot(
                support.t[group], adjusted[group] / 1000, color=color, label=tag if j == 0 else None
            )
            branch = model["fit"]["alias"][j] * FOLD_HZ
            b.plot(
                support.t[group],
                (physical[group] + branch) / 1000,
                color=color,
                alpha=0.68,
                linestyle=":",
                label=f"{bank} orbital only" if j == 0 else None,
            )
            c.plot(
                support.t[group],
                residual[group],
                color=color,
                marker="o",
                markersize=3,
                label=tag if j == 0 else None,
            )
        for point, p, adj, error in zip(
            selection["target"], physical, adjusted, residual, strict=True
        ):
            prediction_rows.append(
                dict(
                    recording=CASE,
                    point=point["id"],
                    regime=bank,
                    arm=arm,
                    level="L3",
                    norad=model["norad"],
                    time_s=point["time_s"],
                    graph=point["graph"],
                    physical_hz=p,
                    corrected_hz=adj,
                    residual_hz=error,
                    role="joint fit",
                )
            )
    b.set(title="Lifted physical and radio-adjusted curves", ylabel="CFO (kHz)")
    b.legend(fontsize=8, frameon=False)
    c.axhspan(-ENVELOPE, ENVELOPE, color="#d9e8e4", alpha=0.55)
    c.axhline(0, color="#93a4a0", lw=1)
    c.set(title="Descriptive joint-fit residuals", ylabel="Residual (Hz)")
    c.legend(fontsize=8, frameon=False)
    finalists = sorted(
        {
            r["norad"]
            for row in comparison
            if row["level"] == "L3" and row["arm"] == "c0"
            for r in row["finalists"][:3]
        }
    )
    colors = []
    for norad in finalists:
        values = []
        for bank in REGIMES:
            for level in LEVELS:
                fit = next(
                    (
                        r["fit"]
                        for r in runs[bank]["candidate_fits"]
                        if (r["norad"], r["arm"], r["level"]) == (norad, "c0", level)
                    ),
                    None,
                )
                values.append(np.log10(1 + fit["held_loss"]) if fit else np.nan)
        colors.append(values)
    chart = d.imshow(colors, cmap="YlGnBu_r", aspect="auto")
    d.set_xticks(range(10), [r + "\n" + lev for r in ("C", "Later") for lev in LEVELS], fontsize=8)
    d.set_yticks(range(len(finalists)), finalists)
    d.set(title="Whole-piece predictive score · c = 0", ylabel="NORAD")
    fig.colorbar(chart, ax=d, label="log₁₀(1 + normalized held loss)", shrink=0.72)
    for fold in runs["causal"]["polynomial"]:
        vector = fold["alternatives"]
        short = fold["graph"].split("-RF")[0].split("-")[-1]
        e.plot(
            [r["degree"] for r in vector],
            [r["held_rms_hz"] for r in vector],
            "o-",
            label=f"Train {short}, hold other piece",
        )
    e.set_yscale("log")
    e.set(
        title="Empirical polynomial gap forecast",
        xlabel="Polynomial degree",
        ylabel="Held RMS (Hz)",
        xticks=range(5),
    )
    e.legend(fontsize=8, frameon=False)
    lo, hi = max(support.t[support.folds[1]]), min(support.t[support.folds[0]])
    for panel in (a, b, c, f):
        panel.axvspan(lo, hi, color="#f4e4cd", alpha=0.28, zorder=-1)
        panel.set_xlabel("Scan time (s)")
    for panel in (a, b, c, e, f):
        panel.spines[["top", "right"]].set_visible(False)
        panel.grid(axis="y", color="#e2e6e7", linewidth=0.65)
    fig.savefig(OUT / "fragment-identity.png", dpi=160)
    fig.savefig(OUT / "fragment-identity.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def main():
    verify(
        "selection-lock.json",
        "ledger-lock.json",
        "causal-search-lock.json",
        "later-search-lock.json",
    )
    selection = read(OUT / "selection.json")
    runs = {k: read_gzip(OUT / f"{k}-search.json.gz") for k in REGIMES}
    support = Support(selection["target"])
    comparisons, swaps, crosses = summarize(selection, runs, support)
    summary = OUT / "comparison.json"
    save_json(
        summary,
        dict(
            cases=[CASE],
            comparisons=comparisons,
            paired_frozen_swaps=swaps,
            cross_piece_leaders=crosses,
            bridge=bridge(selection),
        ),
    )
    fits = []
    for regime, run in runs.items():
        for row in run["candidate_fits"]:
            item = row["fit"]
            fits.append(
                dict(
                    regime=regime,
                    norad=row["norad"],
                    arm=row["arm"],
                    level=row["level"],
                    status="complete" if item else "not_visible_at_allowed_phase",
                    **({k: v for k, v in item.items() if k != "folds"} if item else {}),
                    cross_folds=json.dumps(item["folds"], separators=(",", ":")) if item else "",
                )
            )
    table(OUT / "candidate-fits.csv.gz", fits, compressed=True)
    elements = []
    book = read_gzip(OUT / "orbital-ledgers.json.gz")
    for regime, rows in book.items():
        invalid = set(runs[regime]["rejected"])
        for norad, value in rows.items():
            elements.append(
                dict(
                    regime=regime,
                    norad=norad,
                    paired=norad in book["later" if regime == "causal" else "causal"],
                    availability="causal" if regime == "causal" else "post-scan diagnostic",
                    status="visibility_or_propagation_excluded"
                    if norad in invalid
                    else "evaluated",
                    **{k: v for k, v in value.items() if k != "lines"},
                )
            )
    table(OUT / "tle-inventory.csv.gz", elements, compressed=True)
    data = []
    parents = {r["id"]: r for r in selection["selected_parents"]}
    for name in ("capture_context", "wide_context"):
        for row in selection[name]:
            p = row["winner"]
            owner = parents.get(row["id"])
            data.append(
                dict(
                    recording=CASE,
                    point=row["id"],
                    source=name,
                    native_visit=row["visit"],
                    time_s=row["time_s"],
                    raw_receiver=row["raw_receiver"],
                    channel=row["channel"],
                    rf_hz=row["rf_hz"],
                    edge=row["edge"],
                    sample_counter=row["counter"],
                    graph=row["graph"],
                    lifted_hz=row["graph_cfo_hz"],
                    winner_hz=p["fractional_tracking_cfo_hz"] if p else None,
                    winner_rank=p["candidate_rank"] if p else None,
                    winner_epoch=p["integer_epoch_sample"] + p["fractional_epoch_offset_samples"]
                    if p
                    else None,
                    margin=p["fractional_margin"] if p else None,
                    disposition=owner["condition"] if owner else None,
                    published_original=owner["owner"] if owner else row.get("published_owner"),
                    archived_residual_c0_hz=owner["parent"]["archived_residual_hz"]["c0"]
                    if owner
                    else None,
                    archived_residual_fitted_hz=owner["parent"]["archived_residual_hz"]["fitted_c"]
                    if owner
                    else None,
                )
            )
    render(selection, runs, comparisons, support, data)
    table(OUT / "fragment-identity.csv", data)
    seals = (
        "selection-lock.json",
        "ledger-lock.json",
        "causal-search-lock.json",
        "later-search-lock.json",
    )
    names = (
        *seals,
        "fragment-identity.png",
        "fragment-identity.pdf",
        "fragment-identity.csv",
        "comparison.json",
        "candidate-fits.csv.gz",
        "tle-inventory.csv.gz",
    )
    save_json(
        OUT / "chart-lock.json",
        dict(
            cases=[CASE],
            files={name: _sha(OUT / name) for name in names},
            renderer_sha256=_sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    main()
