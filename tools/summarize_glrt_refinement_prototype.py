#!/usr/bin/env python3
"""Audit and summarize the frozen local/joint GLRT experiment."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np
from evaluate_scan_glrt_rms import rms, write_json
from prototype_glrt_local_joint import PROFILES
from replay_scan_glrt_search import alias_difference
from review_scan_sample_rates import timing_difference


def identity(row):
    return row["candidate_id"], row["case"], row["amount"]


def inventory(plan):
    expected = set()
    for scan in plan["selection"]:
        versions = [(scan["sample_rate_hz"], "native")]
        if scan["sample_rate_hz"] == 5000000:
            versions.append((2500000, "filtered"))
        for p in scan["selected_probes"]:
            cases = (
                [("baseline", 0.0)]
                + [("delay_ns", d) for d in p["delays_ns"]]
                + [("shift_hz", f) for f in p["shifts_hz"]]
            )
            for fs, version in versions:
                for kind, amount in cases:
                    for profile in PROFILES:
                        expected.add(
                            (
                                scan["session_id"],
                                p["candidate_id"],
                                fs,
                                version,
                                kind,
                                amount,
                                profile,
                            )
                        )
    return expected


def details_for(rows):
    baseline = {
        (r["candidate_id"], r["fs"], r["version"], r["profile"]): r
        for r in rows
        if r["case"] == "baseline"
    }
    details = []
    for r in rows:
        if r["case"] == "baseline":
            continue
        base = baseline[r["candidate_id"], r["fs"], r["version"], r["profile"]]
        a, b = r["target"], base["target"]
        d = {
            k: r[k]
            for k in ["session_id", "candidate_id", "fs", "version", "profile", "case", "amount"]
        }
        d["recovered"] = a is not None and b is not None
        if d["recovered"]:
            d["timing_error_ns"] = timing_difference(a["epoch_s"], b["epoch_s"]) * 1e9 - (
                r["amount"] if r["case"] == "delay_ns" else 0
            )
            d["raw_cfo_error_hz"] = (
                a["cfo_hz"] - b["cfo_hz"] - (r["amount"] if r["case"] == "shift_hz" else 0)
            )
            d["cfo_error_hz"] = alias_difference(d["raw_cfo_error_hz"])
            d["alias_changed"] = abs(d["raw_cfo_error_hz"] - d["cfo_error_hz"]) > 1
            d["rank_changed"] = a["rank"] != b["rank"]
        details.append(d)
    return details


def metrics(group, common):
    recovered = [r for r in group if r["recovered"]]
    paired = [r for r in recovered if identity(r) in common]
    result = {
        "attempted": len(group),
        "recovered": len(recovered),
        "common": len(paired),
        "alias_changes": sum(r["alias_changed"] for r in recovered),
        "rank_changes": sum(r["rank_changed"] for r in recovered),
    }
    for key in ["timing_error_ns", "cfo_error_hz", "raw_cfo_error_hz"]:
        values = [r[key] for r in paired]
        all_values = [r[key] for r in recovered]
        result[key + "_rms"] = rms(values) if values else None
        result[key + "_p95"] = float(np.quantile(np.abs(values), 0.95)) if values else None
        result[key + "_max"] = max(map(abs, values)) if values else None
        result[key + "_all_recovered_rms"] = rms(all_values) if all_values else None
    return result


def summarize(output):
    plan = json.loads((output / "plan.json").read_text())
    docs = [json.loads(p.read_text()) for p in sorted((output / "raw").glob("*.json"))]
    rows = [{**r, "session_id": d["session_id"]} for d in docs for r in d["rows"]]
    actual = [
        (
            r["session_id"],
            r["candidate_id"],
            r["fs"],
            r["version"],
            r["case"],
            r["amount"],
            r["profile"],
        )
        for r in rows
    ]
    expected = inventory(plan)
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError(
            f"incomplete/duplicate frozen inventory: {len(actual)} vs {len(expected)} rows"
        )
    details = details_for(rows)
    groups = [(2500000, "native"), (5000000, "native"), (2500000, "filtered")]
    summary, per_scan = [], []
    for fs, version in groups:
        for kind in ["delay_ns", "shift_hz"]:
            subset = [
                r for r in details if (r["fs"], r["version"], r["case"]) == (fs, version, kind)
            ]
            common = set.intersection(
                *[
                    {identity(r) for r in subset if r["profile"] == p and r["recovered"]}
                    for p in PROFILES
                ]
            )
            for profile in PROFILES:
                group = [r for r in subset if r["profile"] == profile]
                summary.append(
                    {
                        "fs": fs,
                        "version": version,
                        "profile": profile,
                        "case": kind,
                        **metrics(group, common),
                    }
                )
                for session in sorted({r["session_id"] for r in group}):
                    per_scan.append(
                        {
                            "session_id": session,
                            "fs": fs,
                            "version": version,
                            "profile": profile,
                            "case": kind,
                            **metrics([r for r in group if r["session_id"] == session], common),
                        }
                    )
    paired = []
    for kind in ["delay_ns", "shift_hz"]:
        subset = [
            r
            for r in details
            if r["case"] == kind and (r["fs"] == 5000000 or r["version"] == "filtered")
        ]
        common = set.intersection(
            *[
                {
                    identity(r)
                    for r in subset
                    if r["fs"] == fs and r["profile"] == p and r["recovered"]
                }
                for fs in [2500000, 5000000]
                for p in PROFILES
            ]
        )
        for fs in [2500000, 5000000]:
            for profile in PROFILES:
                paired.append(
                    {
                        "fs": fs,
                        "profile": profile,
                        "case": kind,
                        **metrics(
                            [r for r in subset if r["fs"] == fs and r["profile"] == profile], common
                        ),
                    }
                )
    runtime = []
    for fs, version in groups:
        for profile in PROFILES:
            group = [
                r for r in rows if (r["fs"], r["version"], r["profile"]) == (fs, version, profile)
            ]
            runtime.append(
                {
                    "fs": fs,
                    "version": version,
                    "profile": profile,
                    "rows": len(group),
                    "baseline_recovered": sum(
                        r["target"] is not None for r in group if r["case"] == "baseline"
                    ),
                    "median_scoring_ms": float(np.median([r["scoring_s"] for r in group])) * 1000,
                    "median_total_ms": float(
                        np.median([r["scoring_s"] + r["acquisition_s"] for r in group])
                    )
                    * 1000,
                }
            )
    histories = [
        h
        for r in rows
        if r["profile"] == "joint512"
        for c in r["candidates"]
        for h in c.get("diagnostics", {}).get("history", [])
    ]
    if any(h["after_score"] < h["before_score"] - 1e-14 for h in histories):
        raise ValueError("joint exact score decreased")
    document = {
        "summary": summary,
        "paired": paired,
        "per_scan": per_scan,
        "runtime": runtime,
        "details": details,
        "inventory_rows": len(rows),
        "acquisitions": len(rows) // len(PROFILES),
        "joint_passes": len(histories),
        "accepted_cfo_updates": sum(h["cfo_update_accepted"] for h in histories),
        "limits": plan["limits"],
    }
    write_json(output / "summary.json", document)
    for name, data in [
        ("summary", summary),
        ("paired", paired),
        ("per-scan", per_scan),
        ("runtime", runtime),
    ]:
        with (output / f"{name}.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(data[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(data)
    plot(output, summary)
    plot_paired(output, paired)
    print(
        json.dumps(
            {
                k: document[k]
                for k in [
                    "inventory_rows",
                    "acquisitions",
                    "joint_passes",
                    "accepted_cfo_updates",
                ]
            },
            indent=2,
        )
    )


def plot_paired(output, paired):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.8))
    panels = [
        ("shift_hz", "cfo_error_hz_rms", "CFO-shift recovery RMS (Hz)", 63),
        ("delay_ns", "timing_error_ns_rms", "Delay recovery RMS (ns)", 59),
        ("delay_ns", "cfo_error_hz_rms", "CFO response to pure delay RMS (Hz)", 59),
    ]
    for ax, (kind, key, title, count) in zip(axes, panels, strict=True):
        for fs, delta, label, color in [
            (2500000, -0.18, "Filtered 2.5 MS/s", "#398b59"),
            (5000000, 0.18, "Native 5 MS/s", "#d66c20"),
        ]:
            values = [
                next(
                    r[key]
                    for r in paired
                    if (r["fs"], r["profile"], r["case"]) == (fs, profile, kind)
                )
                for profile in PROFILES
            ]
            bars = ax.bar(np.arange(4) + delta, values, width=0.35, label=label, color=color)
            ax.bar_label(bars, fmt="%.2f", fontsize=8, padding=3)
        ax.set_title(f"{title}\nSame {count} cases across all settings", fontsize=10)
        ax.set_xticks(range(4), ["512", "8192", "Local", "Joint"])
        ax.set_ylim(0, ax.get_ylim()[1] * 1.16)
        ax.grid(axis="y", alpha=0.2)
        ax.set_axisbelow(True)
    axes[0].legend(fontsize=8)
    fig.suptitle("Paired comparison on the same physical observations", fontweight="bold")
    fig.text(
        0.5,
        0.015,
        "Three 5 MS/s recordings and their filtered copies. "
        "Bandwidth changes too; relative shift consistency, not absolute accuracy.",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.045, 1, 0.94))
    fig.savefig(output / "paired-comparison.png", dpi=170)
    plt.close(fig)


def plot(output, summary):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(15, 5.3))
    specifications = [
        ("shift_hz", "cfo_error_hz_rms", "CFO-shift RMS within alias (Hz)"),
        ("delay_ns", "timing_error_ns_rms", "Delay recovery RMS (ns)"),
        ("delay_ns", "cfo_error_hz_rms", "Delay-induced CFO RMS within alias (Hz)"),
    ]
    colors = ["#2479b6", "#d66c20", "#398b59"]
    for ax, (kind, key, title) in zip(axes, specifications, strict=True):
        for i, (fs, version, label) in enumerate(
            [
                (2500000, "native", "Native 2.5 MS/s"),
                (5000000, "native", "Native 5 MS/s"),
                (2500000, "filtered", "Filtered 2.5 MS/s"),
            ]
        ):
            group = [
                next(
                    r
                    for r in summary
                    if (r["fs"], r["version"], r["case"], r["profile"]) == (fs, version, kind, p)
                )
                for p in PROFILES
            ]
            values = [r[key] for r in group]
            x = np.arange(4) + (i - 1) * 0.25
            bars = ax.bar(x, values, width=0.24, label=label, color=colors[i])
            ax.bar_label(bars, fmt="%.2f", fontsize=7, padding=3, rotation=90)
        ax.set_xticks(range(4), ["512", "8192", "512 + local", "512 + joint"], rotation=20)
        ax.set_title(title, fontsize=10)
        ax.set_yscale("log")
        ax.grid(axis="y", alpha=0.2)
        ax.set_axisbelow(True)
        ax.margins(y=0.35)
    axes[0].legend(fontsize=8, loc="upper right")
    fig.suptitle(
        "Historical IQ: identical recovered cases across all four profiles within each cohort",
        fontsize=12,
    )
    fig.text(
        0.5,
        0.01,
        "Log scales; relative consistency. Native cohorts are unpaired. Native 2.5 has "
        "227 kHz alias jumps in every profile: see raw errors in the report.",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.94))
    fig.savefig(output / "comparison.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    summarize(parser.parse_args().output)
