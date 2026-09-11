#!/usr/bin/env python3
"""Report factorial effects without treating fitted trajectories as truth."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from evaluate_scan_glrt_rms import bootstrap_scan_ratio, rms, write_json
from evaluate_scan_glrt_stride import polynomial_prediction
from replay_scan_glrt_search import ALIAS_HZ, alias_difference

BASELINE = "fine500_conditioned100_fft512"


def validate_inventory(plan, docs, profiles):
    expected_scans = {d["session_id"]: d for d in plan["selection"]}
    if len(docs) != len(expected_scans) or {d["session_id"] for d in docs} != set(expected_scans):
        raise ValueError("complete frozen scan inventory required")
    for doc in docs:
        selected = expected_scans[doc["session_id"]]
        expected = {
            (index, shift, profile)
            for index in range(selected["probes"])
            for shift in [0.0] + selected["shifts"].get(str(index), [])
            for profile in profiles
        }
        actual = [(r["index"], r["imposed_shift_hz"], r["profile"]) for r in doc["rows"]]
        if len(actual) != len(expected) or set(actual) != expected:
            raise ValueError("missing or duplicate frozen profile/probe/shift case")


def block_error(rows, fs_scale):
    """Whole original visits share the frozen baseline-time fold assignment."""
    t = np.array([r["target"]["t_s"] for r in rows])
    original_t = np.array([r["original_t_s"] for r in rows])
    y = np.array(
        [
            r["original_branch_hz"]
            + fs_scale * alias_difference(r["target"]["cfo_hz"] - r["original_cfo_hz"])
            for r in rows
        ]
    )
    fold = np.floor((original_t - min(original_t)) / 3).astype(int) % 5
    prediction = np.full(len(t), np.nan)
    for f in np.unique(fold):
        train, test = fold != f, fold == f
        prediction[test] = polynomial_prediction(t[train], y[train], t[test], np.ones(sum(train)))
    return rms(y - prediction)


def shift_error(row, baseline_row, which="target"):
    a, b = row[which], baseline_row[which]
    if a is None or b is None:
        return None
    raw_error = a["cfo_hz"] - b["cfo_hz"] - row["imposed_shift_hz"]
    return {
        "raw_error_hz": raw_error,
        "alias_adjusted_error_hz": alias_difference(raw_error),
        "alias_branch_change": int(np.rint(raw_error / ALIAS_HZ)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads((args.output / "plan.json").read_text())
    docs = [json.loads(p.read_text()) for p in sorted((args.output / "raw").glob("*.json"))]
    profiles = [
        f"fine{fine}_conditioned{conditioned}_fft{grid}"
        for fine in (500, 250)
        for conditioned in (100, 50)
        for grid in (512, 8192)
    ]
    validate_inventory(plan, docs, profiles)
    track_rows, shifts, increment_rows = [], [], []
    for doc in docs:
        original = [r for r in doc["rows"] if r["imposed_shift_hz"] == 0]
        by_profile = {
            name: {r["index"]: r for r in original if r["profile"] == name} for name in profiles
        }
        if any(len(v) != doc["probes"] for v in by_profile.values()):
            raise ValueError("incomplete profile/probe inventory")
        common = sorted(
            set.intersection(
                *({i for i, r in v.items() if r["target"] is not None} for v in by_profile.values())
            )
        )
        for name in profiles:
            group = list(by_profile[name].values())
            matched = [r for r in group if r["target"] is not None]
            metrics = {
                "session_id": doc["session_id"],
                "sample_rate_hz": doc["sample_rate_hz"],
                "profile": name,
                "probes": len(group),
                "target_recovered": len(matched),
                "common_probes": len(common),
                "global_winner_agrees_with_target": sum(
                    r["global_winner"] == r["target"] and r["target"] is not None for r in group
                ),
                "median_runtime_ms": float(
                    np.median([(r["acquisition_s"] + r["scoring_s"]) * 1000 for r in group])
                ),
                "original_cfo_available": sum(
                    any(
                        c["cfo_hz"] is not None and abs(c["cfo_hz"] - r["original_cfo_hz"]) < 1e-5
                        for c in r["candidates"]
                    )
                    for r in group
                ),
                "status": "complete",
            }
            try:
                metrics["common_self_block_rms_hz"] = block_error(
                    [by_profile[name][i] for i in common], 11.2e9 / doc["actual_rf_hz"]
                )
            except ValueError as error:
                metrics.update(status="insufficient_support", reason=str(error))
            track_rows.append(metrics)
        per_profile_errors = {name: {} for name in profiles}
        for row in doc["rows"]:
            if row["imposed_shift_hz"] == 0:
                continue
            base = by_profile[row["profile"]][row["index"]]
            result = shift_error(row, base)
            global_result = shift_error(row, base, "global_winner")
            detail = {
                "session_id": doc["session_id"],
                "index": row["index"],
                "profile": row["profile"],
                "imposed_shift_hz": row["imposed_shift_hz"],
                "target": result,
                "global_winner": global_result,
            }
            shifts.append(detail)
            per_profile_errors[row["profile"]][row["index"], row["imposed_shift_hz"]] = detail
        common_shift_keys = set.intersection(
            *(
                {key for key, r in group.items() if r["target"] is not None}
                for group in per_profile_errors.values()
            )
        )
        for name in profiles:
            group = list(per_profile_errors[name].values())
            ok = [r["target"] for r in group if r["target"] is not None]
            shared = [per_profile_errors[name][k]["target"] for k in common_shift_keys]
            global_ok = [r["global_winner"] for r in group if r["global_winner"] is not None]
            increment_rows.append(
                {
                    "session_id": doc["session_id"],
                    "sample_rate_hz": doc["sample_rate_hz"],
                    "profile": name,
                    "attempted": len(group),
                    "recovered": len(ok),
                    "common_comparisons": len(shared),
                    "alias_branch_changes": sum(r["alias_branch_change"] != 0 for r in ok),
                    "large_nonalias_errors": sum(
                        abs(r["alias_adjusted_error_hz"]) > 500 for r in ok
                    ),
                    "common_increment_rms_hz": rms([r["alias_adjusted_error_hz"] for r in shared])
                    if shared
                    else None,
                    "raw_increment_rms_hz": rms([r["raw_error_hz"] for r in ok]) if ok else None,
                    "global_comparisons": len(global_ok),
                    "global_increment_rms_hz": rms(
                        [r["alias_adjusted_error_hz"] for r in global_ok]
                    )
                    if global_ok
                    else None,
                }
            )
    baseline_tracks = {r["session_id"]: r for r in track_rows if r["profile"] == BASELINE}
    baseline_increments = {r["session_id"]: r for r in increment_rows if r["profile"] == BASELINE}
    summary = []
    for name in profiles:
        tracks = [r for r in track_rows if r["profile"] == name]
        good = [r for r in tracks if r["status"] == "complete"]
        increments = [r for r in increment_rows if r["profile"] == name]
        errors = [r["target"] for r in shifts if r["profile"] == name and r["target"] is not None]
        global_errors = [
            r["global_winner"]
            for r in shifts
            if r["profile"] == name and r["global_winner"] is not None
        ]
        summary.append(
            {
                "profile": name,
                **{
                    key: sum(r[key] for r in tracks)
                    for key in (
                        "probes",
                        "target_recovered",
                        "common_probes",
                        "global_winner_agrees_with_target",
                        "original_cfo_available",
                    )
                },
                "fitted_tracks": len(good),
                "median_self_block_rms_hz": float(
                    np.median([r["common_self_block_rms_hz"] for r in good])
                )
                if good
                else None,
                "paired_block_rms": bootstrap_scan_ratio(
                    [
                        (
                            r["session_id"],
                            r["common_self_block_rms_hz"],
                            baseline_tracks[r["session_id"]]["common_self_block_rms_hz"],
                        )
                        for r in good
                    ]
                ),
                "median_runtime_ms": float(np.median([r["median_runtime_ms"] for r in tracks])),
                **{
                    key: sum(r[key] for r in increments)
                    for key in (
                        "attempted",
                        "recovered",
                        "common_comparisons",
                        "alias_branch_changes",
                        "large_nonalias_errors",
                    )
                },
                "pooled_available_increment_rms_hz": rms(
                    [r["alias_adjusted_error_hz"] for r in errors]
                )
                if errors
                else None,
                "pooled_common_increment_rms_hz": float(
                    np.sqrt(
                        sum(
                            r["common_comparisons"] * r["common_increment_rms_hz"] ** 2
                            for r in increments
                            if r["common_comparisons"]
                        )
                        / sum(r["common_comparisons"] for r in increments)
                    )
                )
                if sum(r["common_comparisons"] for r in increments)
                else None,
                "pooled_raw_increment_rms_hz": rms([r["raw_error_hz"] for r in errors])
                if errors
                else None,
                "p95_abs_increment_error_hz": float(
                    np.quantile([abs(r["alias_adjusted_error_hz"]) for r in errors], 0.95)
                )
                if errors
                else None,
                "global_comparisons": len(global_errors),
                "global_increment_rms_hz": rms(
                    [r["alias_adjusted_error_hz"] for r in global_errors]
                )
                if global_errors
                else None,
                "global_raw_increment_rms_hz": rms([r["raw_error_hz"] for r in global_errors])
                if global_errors
                else None,
                "global_alias_branch_changes": sum(
                    r["alias_branch_change"] != 0 for r in global_errors
                ),
                "paired_common_increment_rms": bootstrap_scan_ratio(
                    [
                        (
                            r["session_id"],
                            r["common_increment_rms_hz"],
                            baseline_increments[r["session_id"]]["common_increment_rms_hz"],
                        )
                        for r in increments
                        if r["common_increment_rms_hz"] is not None
                    ]
                ),
            }
        )
    runtime_rows = []
    for fs in (2500000, 5000000):
        for name in profiles:
            rows = [
                r
                for d in docs
                if d["sample_rate_hz"] == fs
                for r in d["rows"]
                if r["profile"] == name and r["imposed_shift_hz"] == 0
            ]
            runtime_rows.append(
                {
                    "profile": name,
                    "sample_rate_hz": fs,
                    "probes": len(rows),
                    "median_acquisition_ms": float(
                        np.median([r["acquisition_s"] * 1000 for r in rows])
                    ),
                    "median_glrt_ms": float(np.median([r["scoring_s"] * 1000 for r in rows])),
                }
            )
    write_json(
        args.output / "summary.json",
        {
            "summary": summary,
            "track_rows": track_rows,
            "increment_rows": increment_rows,
            "shift_details": shifts,
            "runtime_rows": runtime_rows,
            "replay_runtime_s": sum(d["runtime_s"] for d in docs),
            "limits": (
                "Baseline-selected target phases and tracks. No frequency gate in candidate "
                "selection; no error clipping. Alias-adjusted and raw increment errors both "
                "retained. Cubic errors are self-consistency."
            ),
        },
    )
    with (args.output / "summary.csv").open("w", newline="") as f:
        simple = [{k: v for k, v in r.items() if not isinstance(v, dict)} for r in summary]
        writer = csv.DictWriter(f, fieldnames=list(simple[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(simple)
    labels = [
        name.replace("fine", "").replace("_conditioned", "/").replace("_fft", "\n")
        for name in profiles
    ]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    colors = ["#137ba1" if name.endswith("fft512") else "#df772b" for name in profiles]
    axes[0].bar(labels, [r["pooled_common_increment_rms_hz"] for r in summary], color=colors)
    axes[1].bar(labels, [r["median_self_block_rms_hz"] for r in summary], color=colors)
    axes[0].set_ylabel("Reacquired increment error RMS (Hz; alias-adjusted)")
    axes[1].set_ylabel("Median held-out cubic RMS (RF-normalized Hz)")
    for ax in axes:
        ax.set_xlabel(
            "Acquisition fine/conditioned steps (Hz)\nGLRT grid points: blue 512, orange 8192"
        )
        ax.grid(axis="y", alpha=0.2)
    fig.suptitle(
        "Historical joint search · six scans · 237 probes · acquisition rerun after every shift"
    )
    fig.tight_layout()
    fig.savefig(args.output / "joint-comparison.png", dpi=170)
    plt.close(fig)
    for row in summary:
        print(json.dumps(row))


if __name__ == "__main__":
    main()
