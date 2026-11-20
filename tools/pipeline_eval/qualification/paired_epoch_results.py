"""Summarize sealed stage-only paired epoch measurements."""

import gzip
import json
from collections import Counter
from statistics import mean

from ..__main__ import save_json
from . import paired_epoch_eval as trial
from .full_v5_check import _wrapped
from .prefix_figures import csv_file

OUT = trial.REPORT


def ranks(comparison):
    return {r["production_rank"] for r in comparison["positive_matches"]}


def missed_epoch_support(raw, summary):
    if summary["union_matched"] == summary["captured_positives"]:
        return []
    native = trial.load(raw["case"])
    if native.native_sha256 != raw["native_sha256"]:
        raise ValueError("missed candidates refer to another native capture")
    frame = round(native.sample_rate_hz / 750)
    probes = {(p["visit_index"], p["receiver_id"]): p for p in native.probes}
    misses = []
    for win in raw["rows"]:
        if win["status"] != "processed":
            continue
        for rx, match in enumerate(win["comparisons"]["union"]):
            candidates = probes[win["visit"], rx]["candidates"]
            found = ranks(match)
            for point in candidates:
                if not point["passed_fractional_margin_gate"] or point["candidate_rank"] in found:
                    continue
                epoch = point["integer_epoch_sample"] + point["fractional_epoch_offset_samples"]
                distances = {
                    mode: min(
                        (abs(_wrapped(i - epoch, frame)) for i in info["active"][rx]), default=None
                    )
                    for mode, info in win["traces"].items()
                }
                misses.append(
                    dict(
                        case=raw["case"],
                        visit=win["visit"],
                        receiver=rx,
                        archive_rank=point["candidate_rank"],
                        archival_epoch_samples=epoch,
                        archive_cfo_hz=point["fractional_tracking_cfo_hz"],
                        distance_to_own_samples=distances["off"],
                        distance_to_union_samples=distances["union"],
                    )
                )
    return misses


def compare(raw):
    stats, lanes = Counter(), []
    delays, windows = [], []
    for r in raw["rows"]:
        if r["status"] != "processed":
            stats["capture_excluded"] += 1
            lanes.append(dict(case=raw["case"], visit=r["visit"], status=r["status"]))
            continue
        stats["processed"] += 1
        stats["same_non_timing_payloads"] += r["payloads"]["wide"] == r["payloads"]["union"]
        off, union = r["traces"]["off"]["active"], r["traces"]["union"]["active"]
        stats["active_intersection_epochs"] += len(set(off[0]) & set(off[1]))
        stats["disjoint_own_epoch_sets"] += not set(off[0]) & set(off[1])
        window = {"case": raw["case"], "visit": r["visit"], "status": r["status"]}
        if r["stereo_positive_delta"]:
            delays.append(window | r["stereo_positive_delta"])
        windows.append(r)
        for rx, (base, added) in enumerate(
            zip(r["comparisons"]["wide"], r["comparisons"]["union"], strict=True)
        ):
            original, revised = ranks(base), ranks(added)
            row = dict(
                window,
                receiver=rx,
                segment=r["segment"],
                sequence=r["sequence"],
                iq_sha256=r["iq_sha256"],
                start_counter=r["start_counter"],
                captured_positives=base["production_positive"],
                wide_matched=len(original),
                union_matched=len(revised),
                captured_gained=len(revised - original),
                captured_lost=len(original - revised),
                wide_other_positive=base["native_only"],
                union_other_positive=added["native_only"],
                wide_epochs=len(off[rx]),
                union_epochs=len(union[rx]),
                own_shared_epochs=len(set(off[0]) & set(off[1])),
            )
            stats.update(
                {
                    k: row[k]
                    for k in (
                        "captured_positives",
                        "wide_matched",
                        "union_matched",
                        "captured_gained",
                        "captured_lost",
                        "wide_other_positive",
                        "union_other_positive",
                    )
                }
            )
            lanes.append(row)
    for mode in trial.MODES:
        for metric in ("native_cpu_ms", "wall_s", "cpu_s"):
            stats[f"{mode}_mean_{metric}"] = mean(
                value[metric] for r in windows for value in r["timings"][mode]
            )
    return {"case": raw["case"], **stats}, lanes, delays


def render(summary, lanes, delays):
    import matplotlib.pyplot as plt
    import numpy as np

    cases = [r["case"] for r in summary]
    xx = np.arange(len(cases))
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    ax = axes[0, 0]
    for j, (key, label, color) in enumerate(
        (
            ("captured_positives", "Capture-era positives", "#8D97A9"),
            ("wide_matched", "Own-RX epochs", "#396290"),
            ("union_matched", "Epoch union", "#138276"),
        )
    ):
        ax.bar(xx + (j - 1) * 0.23, [r[key] for r in summary], width=0.22, label=label, color=color)
    ax.set_ylabel("Positive detections")
    ax.set_title("Capture-era recall")
    ax.legend(fontsize=8)
    ax = axes[0, 1]
    for j, (mode, label, color) in enumerate(
        (
            ("wide", "Released wide", "#8D97A9"),
            ("off", "Overlay off", "#396290"),
            ("union", "Epoch union", "#138276"),
        )
    ):
        ax.bar(
            xx + (j - 1) * 0.23,
            [r[f"{mode}_mean_native_cpu_ms"] for r in summary],
            width=0.22,
            label=label,
            color=color,
        )
    ax.set_ylabel("Mean native CPU per dual window (ms)")
    ax.set_title("Four rotated repeats")
    ax.legend(fontsize=8)
    ax = axes[1, 0]
    for kind, shift, name, color in (
        ("wide", -0.12, "Own-RX epochs", "#396290"),
        ("union", 0.12, "Epoch union", "#138276"),
    ):
        ax.scatter(
            [cases.index(r["case"]) + shift for r in lanes if r["status"] == "processed"],
            [r[kind + "_epochs"] for r in lanes if r["status"] == "processed"],
            alpha=0.5,
            s=26,
            label=name,
            color=color,
        )
    ax.set_ylabel("Unique evaluated epochs per lane")
    ax.set_title("Exact evaluated epoch membership")
    ax.legend(fontsize=8)
    ax = axes[1, 1]
    ax.axhline(0, color="#888888", linewidth=1)
    ax.scatter(
        [cases.index(r["case"]) for r in delays],
        [r["delta_rx1_minus_rx0_samples"] for r in delays],
        color="#623e86",
        s=30,
    )
    ax.set_ylabel("RX1 − RX0 fractional epoch (samples)")
    ax.set_title("Same-RF/CFO stereo pairs in measured windows")
    for ax in axes.flat:
        ax.set_xticks(xx, cases, rotation=20, ha="right")
        ax.set_xlim(-0.5, len(cases) - 0.5)
        ax.grid(axis="y", alpha=0.22)
    fig.suptitle("Paired epoch proposals on authenticated dual CI16", fontsize=16)
    fig.savefig(OUT / "recall-and-cost.png", dpi=145)
    plt.close(fig)


def main():
    expected = trial.source_lock()
    canary = json.loads((OUT / "canary.json").read_bytes())
    if canary["pins"] != expected:
        raise ValueError("synthetic controls reference another build or protocol")
    summary, lanes, deltas, missed_epochs = [], [], [], []
    for case in trial.CASES:
        raw = json.loads(gzip.decompress((OUT / f"{case}.json.gz").read_bytes()))
        if raw["pins"] != expected or raw["case"] != case:
            raise ValueError("archive measurement cohort differs from the seal")
        review, records, delays = compare(raw)
        summary.append(review)
        lanes.extend(records)
        deltas.extend(delays)
        missed_epochs.extend(missed_epoch_support(raw, review))
    csv_file(OUT / "per-lane.csv", lanes)
    save_json(
        OUT / "summary.json",
        dict(
            cases=summary,
            measured_pair_deltas=deltas,
            missed_epoch_support=missed_epochs,
            processed=sum(r["processed"] for r in summary),
            stage_only=True,
        ),
    )
    render(summary, lanes, deltas)


if __name__ == "__main__":
    main()
