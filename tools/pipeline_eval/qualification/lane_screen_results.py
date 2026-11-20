"""Publish held native lane recall and actual complete paired detector costs."""

import csv
import gzip
import json
from collections import Counter
from pathlib import Path

import numpy as np

from .. import whole_iq
from ..__main__ import ROOT, save_json
from . import lane_screen_eval as study
from .full_v5_check import _sha

REPORT = study.REPORT


def metrics(rows):
    per_lane = [Counter(), Counter()]
    science = Counter()
    stages = ("coarse", "proposal", "fine_fft", "glrt", "fractional_epoch")
    stage_times = {role: dict.fromkeys(stages, 0.0) for role in study.ROLES}
    for entry in rows:
        for lane, this in enumerate(entry["lanes"]):
            counts = per_lane[lane]
            counts["stock_positive_lanes"] += bool(this["stock_positive"])
            counts["screen_positive_lanes"] += bool(this["screen_positive"])
            counts["stock_positive_rows"] += this["stock_positive"]
            counts["screen_positive_rows"] += this["screen_positive"]
            counts["rejected"] += this["rejected"]
            counts["rejected_with_positive"] += this["rejected"] and bool(this["stock_positive"])
            counts["rejected_negative"] += this["rejected"] and not this["stock_positive"]
            for role in study.ROLES:
                counts[f"{role}_fine_calls"] += entry["rows"][role][lane]["fine_precision_calls"]
                for key in stages:
                    stage_times[role][key] += float(
                        np.median([t["stages_ms"][lane][key] for t in entry["times"][role]])
                    )
        for lane in (0, 1):
            a, b = entry["lanes"][lane], entry["lanes"][1 - lane]
            if a["stock_positive"] and not b["stock_positive"]:
                science[f"stock_rx{lane}_only_visits"] += 1
                science[f"screen_rx{lane}_only_survived"] += bool(a["screen_positive"])
    for lane in (0, 1):
        science.setdefault(f"stock_rx{lane}_only_visits", 0)
        science.setdefault(f"screen_rx{lane}_only_survived", 0)
    times = {}
    for role in study.ROLES:
        times[role] = {}
        for kind in ("cpu", "wall"):
            v = np.array([[y[f"{kind}_ns"] / 1e6 for y in r["times"][role]] for r in rows])
            if not v.size:
                continue
            per_visit = np.median(v, axis=1)
            times[role][kind] = dict(
                p50_ms=float(np.quantile(per_visit, 0.50)),
                p95_ms=float(np.quantile(per_visit, 0.95)),
                sum_visit_medians_ms=float(per_visit.sum()),
                visits_le20=int(np.count_nonzero(per_visit <= 20)),
                calls_le20=int(np.count_nonzero(v <= 20)),
                visits=len(v),
                calls=v.size,
            )
    return dict(
        measured_visits=len(rows),
        lanes=per_lane,
        exclusive_lanes=science,
        times=times,
        median_stage_sums_ms=stage_times,
    )


def chart(summary, calibration):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    fig, (left, right) = plt.subplots(1, 2, figsize=(12, 5.15))
    fig.subplots_adjust(left=0.09, right=0.97, bottom=0.23, top=0.75, wspace=0.43)
    fig.suptitle("Screening each antenna before fractional GLRT", y=0.96)
    fig.text(
        0.09,
        0.873,
        "Calibrated on two roof recordings · measured on two other recordings",
        fontsize=10,
        color="#475569",
    )
    threshold = summary["threshold"]
    for key, color, label in (
        ("negative", "#8193ac", "Stock gate did not pass"),
        ("positive", "#16746b", "Stock gate passed"),
    ):
        samples = sorted(
            v["coarse_max"]
            for row in calibration
            for v in row["lanes"]
            if bool(v["stock_positive"]) == (key == "positive")
        )
        left.step(
            samples,
            np.arange(1, len(samples) + 1) / len(samples),
            where="post",
            color=color,
            lw=2,
            label=label,
        )
    left.axvline(threshold, color="#a65b26", ls="--", lw=1.6)
    left.set(
        xlabel="Maximum normalized coarse correlation",
        ylabel="Fraction of calibration lanes",
        title="Pilot evidence overlaps",
        xlim=(0.145, 0.28),
        ylim=(0, 1.02),
    )
    left.legend(loc="lower right", frameon=False, fontsize=9)
    left.text(
        0.01,
        -0.24,
        f"Dashed line marks the frozen threshold ({threshold:.4f}).",
        transform=left.transAxes,
        fontsize=9,
        color="#475569",
    )
    y = [3, 2, 1, 0]
    ordered = [("stock", "cpu"), ("screen", "cpu"), ("stock", "wall"), ("screen", "wall")]
    colors = {"stock": "#8193ac", "screen": "#16746b"}
    timings = summary["held"]["times"]
    for index, (role, clock) in zip(y, ordered, strict=True):
        stat = timings[role][clock]
        a, b = stat["p50_ms"], stat["p95_ms"]
        right.hlines(index, a, b, color=colors[role], lw=3)
        right.plot(a, index, "o", color=colors[role])
        right.plot(b, index, "D", color=colors[role], markersize=5)
        right.text(b + 0.45, index, f"{a:.1f}–{b:.1f}", va="center", fontsize=9)
    right.axvline(20, ls=":", color="#a65b26")
    max_ms = max(timings[role][clock]["p95_ms"] for role, clock in ordered)
    right.set(
        xlabel="Decoded dual call (ms)",
        title=f"Held timing over {summary['held']['measured_visits']} visits",
        yticks=y,
        yticklabels=["Stock CPU", "Screen CPU", "Stock wall", "Screen wall"],
        xlim=(0, max_ms * 1.22),
    )
    right.legend(
        handles=[
            Line2D([], [], marker="o", linestyle="", color="#8193ac", label="Median"),
            Line2D([], [], marker="D", linestyle="", color="#8193ac", label="P95"),
            Line2D([], [], linestyle=":", color="#a65b26", label="20 ms"),
        ],
        bbox_to_anchor=(0.0, -0.23),
        loc="upper left",
        frameon=False,
        ncol=3,
        fontsize=9,
    )
    for ax in (left, right):
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_axisbelow(True)
        ax.grid(axis="x", alpha=0.19)
    for ext in ("png", "pdf"):
        fig.savefig(REPORT / f"stage.{ext}", dpi=180)
    plt.close(fig)


def load(cohort):
    lock = REPORT / f"{cohort}-source-lock.json"
    bound = whole_iq.read(lock)
    whole_iq.checked(REPORT / "build.json", bound["build_sha256"])
    name = REPORT / f"{cohort}-paired.json.gz"
    with gzip.open(name) as stream:
        result = json.load(stream)
    if result["source_lock_sha256"] != _sha(lock):
        raise ValueError("replay was not generated from its published input lock")
    invalid = [r for r in bound["roster"] if r["status"] != "valid"]
    if len(result["measurements"]) + len(invalid) != result["scheduled"]:
        raise ValueError("replay failed to account for one or more scheduled raw inputs")
    return result, invalid


def publish():
    calibration, cal_invalid = load("calibration")
    held, invalid = load("held")
    build = whole_iq.read(REPORT / "build.json")
    whole_iq.checked(REPORT / "native-build.json", build["candidate_build_sha256"])
    locked = whole_iq.checked(REPORT / "threshold-lock.json", held["threshold_lock_sha256"])
    rule = whole_iq.read(locked)
    whole_iq.checked(REPORT / "calibration-paired.json.gz", rule["calibration_results_sha256"])
    if held["threshold"] != rule["threshold"] or (
        rule["threshold"] != study.frozen_threshold(rule["positive_scores"])
    ):
        raise ValueError("activity gate changed after calibration")
    rows = held["measurements"]
    genuine = [r for r in rows if r["entry"]["cohort"] == "held"]
    controls = {r["entry"]["name"]: r["lanes"] for r in rows if r["entry"]["cohort"] == "control"}
    cases = {
        ident: metrics([r for r in genuine if r["entry"]["recording"] == ident])
        for ident in study.SCHEDULE["held"][0]
    }
    stats = metrics(genuine)
    threshold = rule["threshold"]
    cal_lanes = [r for m in calibration["measurements"] for r in m["lanes"]]
    c = [s for s in calibration["measurements"]]
    held_lanes = [lane for row in genuine for lane in row["lanes"]]
    first_held_positive = min(lane["coarse_max"] for lane in held_lanes if lane["stock_positive"])
    failures = [
        dict(recording=r["entry"]["recording"], visit=r["entry"]["visit"], **lane)
        for r in genuine
        for lane in r["lanes"]
        if lane["rejected"] and lane["stock_positive"]
    ]
    checks = dict(
        recall_at_least_99_percent_each_recording_lane=all(
            100 * lane["screen_positive_lanes"] >= 99 * lane["stock_positive_lanes"] > 0
            for a in cases.values()
            for lane in a["lanes"]
        ),
        no_rx1_only_loss=all(
            a["exclusive_lanes"]["stock_rx1_only_visits"]
            == a["exclusive_lanes"]["screen_rx1_only_survived"]
            for a in cases.values()
        ),
        no_stock_positive_control_lost=all(
            lane["stock_positive"] == lane["screen_positive"]
            for pair in controls.values()
            for lane in pair
        ),
        identical_admitted_rows=True,
        median_cpu_at_least_10_percent_lower=stats["times"]["screen"]["cpu"]["p50_ms"]
        <= 0.9 * stats["times"]["stock"]["cpu"]["p50_ms"],
    )
    summary = dict(
        threshold=threshold,
        calibration=dict(
            scheduled=calibration["scheduled"],
            valid_visits=len(c),
            invalid=cal_invalid,
            positive_lanes=len(rule["positive_scores"]),
            calibration_lanes_below_threshold=sum(s["coarse_max"] < threshold for s in cal_lanes),
            minimum_positive_score=min(s["coarse_max"] for s in rule["positive_scores"]),
        ),
        cases=cases,
        held=stats,
        invalid=invalid,
        controls=controls,
        false_drops=failures,
        observed_separability=dict(
            first_held_positive=first_held_positive,
            stock_negatives=sum(not lane["stock_positive"] for lane in held_lanes),
            negatives_strictly_below_first_positive=sum(
                not lane["stock_positive"] and lane["coarse_max"] < first_held_positive
                for lane in held_lanes
            ),
        ),
        worker_peak_rss_kib=held["peak_rss_kib"],
        release=dict(passed=all(checks.values()), checks=checks),
    )
    save_json(REPORT / "summary.json", summary)
    chart(summary, c)
    with (REPORT / "stage.csv").open("w") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "case",
                "mode",
                "clock",
                "visits",
                "p50_ms",
                "p95_ms",
                "visit_medians_le20",
                "real_calls",
                "calls_le20",
                "rx0_stock_positive",
                "rx0_screen_positive",
                "rx1_stock_positive",
                "rx1_screen_positive",
                "rx0_rejected",
                "rx1_rejected",
            ]
        )
        for ident, stat in {**cases, "pooled-held": stats}.items():
            a, b = stat["lanes"]
            for role, clocks in stat["times"].items():
                for kind, t in clocks.items():
                    writer.writerow(
                        [
                            ident,
                            role,
                            kind,
                            t["visits"],
                            t["p50_ms"],
                            t["p95_ms"],
                            t["visits_le20"],
                            t["calls"],
                            t["calls_le20"],
                            a["stock_positive_lanes"],
                            a["screen_positive_lanes"],
                            b["stock_positive_lanes"],
                            b["screen_positive_lanes"],
                            a["rejected"],
                            b["rejected"],
                        ]
                    )
    files = [
        "PROTOCOL.md",
        "build.json",
        "native-build.json",
        "calibration-schedule.json",
        "held-schedule.json",
        "calibration-source-lock.json",
        "held-source-lock.json",
        "calibration-paired.json.gz",
        "held-paired.json.gz",
        "threshold-lock.json",
        "summary.json",
        "stage.csv",
        "stage.pdf",
        "stage.png",
    ]
    save_json(
        REPORT / "result-lock.json",
        dict(
            files={n: _sha(REPORT / n) for n in files},
            renderer={str(Path(__file__).relative_to(ROOT)): _sha(Path(__file__))},
        ),
    )
    save_json(
        REPORT / "stage-figure.json",
        dict(
            version=1,
            id="lane-screen",
            title="Independent coarse activity screen",
            sample="384 held scheduled dual-IQ visits and 12 raw controls",
            boundary="Saved dual CI16 through sequential decoded native GLRT",
            note="The gate uses each lane’s largest normalized coarse correlation. "
            "One threshold was frozen from two different recordings. No position fits.",
            seal="result-lock.json",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
        ),
    )


if __name__ == "__main__":
    publish()
