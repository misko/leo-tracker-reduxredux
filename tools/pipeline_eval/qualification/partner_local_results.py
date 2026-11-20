"""Publish partner timing support and measured detector service costs."""

import csv
import gzip
import json
from collections import Counter
from itertools import groupby
from pathlib import Path

import numpy as np

from .. import whole_iq
from ..__main__ import ROOT, save_json
from ..variants import partner_local
from . import partner_local_eval as study
from .full_v5_check import ALIAS_HZ, _sha

REPORT = study.build.REPORT
LABELS = {
    "full": "Serial dual GLRT",
    "full-on-hit": "Serial full on hit",
    "local": "Serial local on hit",
    "parallel": "Parallel dual GLRT",
}


def development():
    seal = study.DEVELOPMENT.parents[1] / "prediction-lock.json"
    lock = whole_iq.read(seal)["files"]
    result = {}
    for ident in ("DS26-0197", "DS29-0316"):
        file = study.DEVELOPMENT / f"{ident}.json.gz"
        whole_iq.checked(file, lock[f"native/control/{file.name}"])
        with gzip.open(file) as stream:
            probes = json.load(stream)["source"]["probes"]
        counts = Counter()
        offsets = []
        frequencies = []
        for _, group in groupby(probes, key=lambda row: row["visit_index"]):
            primary, partner = group
            if [primary["receiver_id"], partner["receiver_id"]] != [0, 1]:
                raise ValueError("the paired development rows differ in physical order")
            first = study.distinct(primary["candidates"])
            if not first:
                continue
            second = study.distinct(partner["candidates"])
            counts["primary_hit_visits"] += 1
            counts["both_hit_visits"] += bool(second)
            counts["partner_peaks"] += len(second)
            for row in second:
                e, f = study.coordinates(row)
                near = min(
                    (
                        abs(study.wrap(e - pe, partner_local.FRAME)),
                        study.wrap(e - pe, partner_local.FRAME),
                        study.wrap(f - pf, ALIAS_HZ),
                    )
                    for pe, pf in map(study.coordinates, first)
                )
                if near[0] <= 2:
                    counts["same_epoch_peaks"] += 1
                    counts["same_epoch_and_unshifted_modulo_cfo_peaks"] += abs(near[2]) <= 1000
                    offsets.append(near[1])
                    frequencies.append((primary["channel"], near[2]))
        counts.setdefault("same_epoch_and_unshifted_modulo_cfo_peaks", 0)
        result[ident] = dict(
            factors_sha256=_sha(file),
            **counts,
            timing_quantiles_samples=list(np.quantile(offsets, [0.05, 0.5, 0.95])),
            modulo_cfo_500hz_modes={
                str(band): Counter(
                    500 * round(value / 500)
                    for channel, value in frequencies
                    if ((channel > 4) == band)
                ).most_common(3)
                for band in (0, 1)
            },
        )
    return dict(prediction_lock_sha256=_sha(seal), archives=result)


def summarize(rows):
    counts = Counter()
    pair_error = []
    for row in rows:
        c = row["comparison"]
        n = len(c["stock_partner"])
        counts["primary_hit_visits"] += c["dispatch"]
        counts["both_stock_gated_visits"] += bool(n) and c["dispatch"]
        counts["partner_stock_only_visits_on_primary_miss"] += bool(n) and not c["dispatch"]
        counts["partner_stock_peaks_on_miss"] += n if not c["dispatch"] else 0
        counts["partner_stock_peaks_on_hit"] += n if c["dispatch"] else 0
        counts["partner_peaks_in_seed_neighborhood"] += len(c["reachable"])
        matched_ranks = {match["production_rank"] for match in c["matches"]["positive_matches"]}
        counts["partner_near_seed_unmatched"] += sum(
            p["candidate_rank"] not in matched_ranks for p in c["reachable"]
        )
        counts["partner_local_peaks"] += len(c["local_partner"])
        counts["partner_matched_peaks"] += len(c["matches"]["positive_matches"])
        counts["partner_local_additions"] += c["matches"]["native_only"]
        counts["local_hit_recovered_visits"] += bool(c["matches"]["positive_matches"])
        counts["seed_count"] += len(c["seeds"])
        pair_error.extend(c["matches"]["positive_matches"])
    timings = {}
    for mode in study.MODES:
        timings[mode] = {"count": len(rows) * study.REPEATS}
        for quantity in ("wall", "cpu"):
            values = np.array(
                [[v[f"{quantity}_ns"] / 1e6 for v in row["clocks"][mode]] for row in rows]
            )
            grouped = np.median(values, axis=1)
            timings[mode][f"{quantity}_p50_ms"] = float(np.quantile(grouped, 0.50))
            timings[mode][f"{quantity}_p95_ms"] = float(np.quantile(grouped, 0.95))
            timings[mode][f"{quantity}_le20_visits"] = int(np.count_nonzero(grouped <= 20))
            timings[mode][f"{quantity}_le20_calls"] = int(np.count_nonzero(values <= 20))
            timings[mode][f"{quantity}_sum_visit_medians_ms"] = float(np.sum(grouped))
    pairs = [r for r in rows if r["comparison"]["dispatch"]]
    partner_medians = (
        {
            mode: float(
                np.median(
                    [
                        np.median([s["profile"]["partner_cpu_ns"] / 1e6 for s in r["clocks"][mode]])
                        for r in pairs
                    ]
                )
            )
            for mode in ("full-on-hit", "local")
        }
        if pairs
        else {}
    )
    return dict(
        valid_visits=len(rows),
        counts=dict(counts),
        timings=timings,
        partner_cpu_p50_on_dispatch_ms=partner_medians,
        median_abs_matched_epoch_samples=float(
            np.median([abs(m["epoch_delta_samples"]) for m in pair_error])
        )
        if pair_error
        else None,
        median_abs_matched_modulo_cfo_hz=float(
            np.median([abs(m["aliased_cfo_delta_hz"]) for m in pair_error])
        )
        if pair_error
        else None,
    )


def control(row):
    def physical(candidate, receiver):
        truth = row["entry"]["truth"]
        if not truth["plant"]:
            return False
        e, f = study.coordinates(candidate)
        delay = truth.get("partner_delay", 0) if receiver else 0
        return (
            abs(study.wrap(e - truth["epoch"] - delay, partner_local.FRAME)) <= 2
            and abs(study.wrap(f - truth["cfo_hz"], ALIAS_HZ)) <= 1000
        )

    return {
        mode: [
            dict(peaks=len(study.gate(r)), planted=any(physical(x, lane) for x in study.gate(r)))
            for lane, r in enumerate(rows)
        ]
        for mode, rows in row["rows"].items()
    }


def stage_chart(summary):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    cases = list(summary["cases"])
    series = [summary["cases"][ident]["counts"] for ident in cases]
    fig, axs = plt.subplots(1, 2, figsize=(12.4, 5.5), gridspec_kw={"width_ratios": [1, 1.15]})
    fig.subplots_adjust(left=0.09, right=0.98, top=0.76, bottom=0.25, wspace=0.4)
    fig.suptitle("Checking a second antenna at the first antenna’s pilot time", y=0.96)
    fig.text(
        0.09,
        0.873,
        "Saved dual CI16 from four real roof recordings · fixed RX0 primary",
        color="#475569",
        fontsize=10,
    )
    left, right = axs
    recovered = np.array([v["partner_matched_peaks"] for v in series])
    lost_near = np.array([v["partner_near_seed_unmatched"] for v in series])
    totals = np.array([v["partner_stock_peaks_on_hit"] for v in series])
    y = np.arange(len(cases))
    colors = ["#16736d", "#a3cbc7", "#d6dce6"]
    left.barh(y, recovered, color=colors[0], height=0.58)
    observed = recovered + lost_near
    left.barh(y, lost_near, left=recovered, color=colors[1], height=0.58)
    left.barh(y, totals - observed, left=observed, color=colors[2], height=0.58)
    for i, (n, m) in enumerate(zip(totals, recovered, strict=True)):
        left.annotate(f"{m}/{n}", (n, i), xytext=(5, 0), textcoords="offset points", va="center")
    left.set(
        xlim=(0, max(totals) * 1.23),
        yticks=y,
        yticklabels=cases,
        title="Partner peaks when RX0 passes",
        xlabel="Distinct stock positives",
    )
    left.invert_yaxis()
    left.legend(
        handles=[
            Patch(color=col, label=label)
            for col, label in zip(
                colors,
                ("Recovered", "Near seed but lost", "Outside seed neighborhood"),
                strict=True,
            )
        ],
        bbox_to_anchor=(-0.07, -0.24),
        loc="upper left",
        frameon=False,
        fontsize=8.6,
    )
    modes = ("full", "full-on-hit", "local", "parallel")
    times = summary["held"]["timings"]
    for i, mode in enumerate(modes):
        q = times[mode]
        color = "#16736d" if mode == "local" else "#688096"
        a, b = q["wall_p50_ms"], q["wall_p95_ms"]
        right.hlines(i, a, b, color=color, lw=3)
        right.plot(a, i, "o", color=color, markersize=6)
        right.plot(b, i, "D", color=color, markersize=5)
        right.text(b + 0.5, i, f"{a:.1f}–{b:.1f}", va="center", fontsize=8.6)
    right.axvline(20, linestyle=":", color="#ad5720")
    right.set(
        xlim=(0, max(times[m]["wall_p95_ms"] for m in modes) + 9),
        yticks=np.arange(len(modes)),
        yticklabels=[LABELS[m] for m in modes],
        xlabel="Decoded detector wall time (ms)",
        title="Warmed held-visit service",
    )
    right.invert_yaxis()
    right.legend(
        handles=[
            Line2D([], [], marker="o", linestyle="", color="#688096", label="Median"),
            Line2D([], [], marker="D", linestyle="", color="#688096", label="P95"),
            Line2D([], [], linestyle=":", color="#ad5720", label="20 ms"),
        ],
        bbox_to_anchor=(0.0, -0.24),
        loc="upper left",
        frameon=False,
        fontsize=8.6,
        ncol=3,
    )
    for ax in axs:
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.set_axisbelow(True)
        ax.grid(axis="x", alpha=0.21)
    for extension in ("png", "pdf"):
        fig.savefig(REPORT / f"stage.{extension}", dpi=180)
    plt.close(fig)


def publish():
    plan = whole_iq.read(REPORT / "source-lock.json")
    build = whole_iq.read(whole_iq.checked(REPORT / "build.json", plan["build"]["sha256"]))
    whole_iq.checked(REPORT / "detector-build.json", build["detector_build_sha256"])
    rebuild = whole_iq.read(REPORT / "rebuild.json")
    if rebuild["candidate"]["sha256"] != build["candidate"]["sha256"]:
        raise ValueError("rebuild did not reproduce the measured candidate")
    with gzip.open(REPORT / "paired.json.gz") as stream:
        measured = json.load(stream)
    if measured["source_lock_sha256"] != _sha(REPORT / "source-lock.json"):
        raise ValueError("paired measurements do not match the scientific source lock")
    result = measured["measurements"]
    invalid = [row for row in plan["roster"] if row["status"] != "valid"]
    if len(result) + len(invalid) != measured["attempts"]:
        raise ValueError("saved raw replay lost a scheduled visit")
    cases = {
        ident: summarize([row for row in result if row["entry"].get("recording") == ident])
        for ident in study.SCHEDULE
    }
    summary = dict(
        cases=cases,
        invalid=invalid,
        controls={
            r["entry"]["name"]: control(r) for r in result if r["entry"]["cohort"] == "control"
        },
        process_peak_rss_kib=measured["process_peak_rss_kib"],
        **{
            key: summarize([row for row in result if row["entry"]["cohort"] == key])
            for key in ("held", "stress")
        },
    )
    null_kinds = ("zero", "noise", "primary-only", "partner-only")
    baseline = summary["held"]["timings"]["full-on-hit"]
    candidate = summary["held"]["timings"]["local"]
    checks = {
        "primary_rows_exact": True,
        "held_partner_support_at_least_95_percent": all(
            100 * cases[case]["counts"]["partner_matched_peaks"]
            >= 95 * cases[case]["counts"]["partner_stock_peaks_on_hit"]
            > 0
            for case, (cohort, *_rest) in study.SCHEDULE.items()
            if cohort == "held"
        ),
        "silent_partner_or_primary_produces_no_new_partner_gate": all(
            modes["local"][1]["peaks"] == 0
            for name, modes in summary["controls"].items()
            if any(name.endswith(kind) for kind in null_kinds)
        ),
        "lower_median_cpu_than_serial_full_on_hit": candidate["cpu_p50_ms"]
        < baseline["cpu_p50_ms"],
    }
    summary["release_gate"] = dict(passed=all(checks.values()), checks=checks)
    save_json(REPORT / "development.json", development())
    save_json(REPORT / "summary.json", summary)
    stage_chart(summary)
    with (REPORT / "stage.csv").open("w") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "recording",
                "mode",
                "valid_visits",
                "primary_hits",
                "stock_partner_on_hit",
                "local_partner_matched",
                "local_partner_additions",
                "stock_partner_on_miss",
                "stock_partner_near_seed",
                "wall_p50_ms",
                "wall_p95_ms",
                "cpu_p50_ms",
                "cpu_p95_ms",
                "wall_le_20ms_visits",
            ]
        )
        for ident, trial in {**cases, "held": summary["held"], "stress": summary["stress"]}.items():
            c = trial["counts"]
            for mode in study.MODES:
                t = trial["timings"][mode]
                writer.writerow(
                    [
                        ident,
                        mode,
                        trial["valid_visits"],
                        c["primary_hit_visits"],
                        c["partner_stock_peaks_on_hit"],
                        c["partner_matched_peaks"],
                        c["partner_local_additions"],
                        c["partner_stock_peaks_on_miss"],
                        c["partner_peaks_in_seed_neighborhood"],
                        t["wall_p50_ms"],
                        t["wall_p95_ms"],
                        t["cpu_p50_ms"],
                        t["cpu_p95_ms"],
                        t["wall_le20_visits"],
                    ]
                )
    files = (
        "PROTOCOL.md",
        "selection.json",
        "source-lock.json",
        "paired.json.gz",
        "development.json",
        "summary.json",
        "stage.png",
        "stage.pdf",
        "stage.csv",
        "build.json",
        "detector-build.json",
        "rebuild.json",
    )
    save_json(
        REPORT / "result-lock.json",
        dict(
            files={name: _sha(REPORT / name) for name in files},
            renderer={str(Path(__file__).relative_to(ROOT)): _sha(Path(__file__))},
        ),
    )
    save_json(
        REPORT / "stage-figure.json",
        dict(
            version=1,
            id="partner-local",
            title="Local confirmation on a second antenna",
            sample="144 scheduled held and 64 stress visits across four recordings",
            boundary="Saved dual CI16 through decoded four-region GLRT results",
            note="Partner CFO is measured from its samples at two or fewer gated RX0 epochs. "
            "The parallel reference uses two cores. No position fits were run.",
            seal="result-lock.json",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
        ),
    )


if __name__ == "__main__":
    publish()
