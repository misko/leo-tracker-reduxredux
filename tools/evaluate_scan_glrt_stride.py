#!/usr/bin/env python3
"""Compare denser GLRT fits against identical held-out first-probe observations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from evaluate_scan_glrt_rms import bootstrap_scan_ratio, rms, write_json
from replay_scan_glrt_stride import probe_starts


def polynomial_prediction(t, y, query_t, weight):
    if len(t) < 5 or not np.all(np.isfinite(y)) or np.any(weight <= 0):
        raise ValueError("insufficient finite training support")
    reference = float(np.mean(t))
    scale = max(float(np.ptp(t)), 1.0)
    design = np.polynomial.polynomial.polyvander((t - reference) / scale, 3)
    query = np.polynomial.polynomial.polyvander((query_t - reference) / scale, 3)
    w = np.sqrt(weight)
    coef, _, rank, _ = np.linalg.lstsq(design * w[:, None], y * w, rcond=None)
    if rank != 4:
        raise ValueError("rank-deficient training curve")
    return query @ coef


def fit_from_visits(dense, baseline, allowed_visits, query_visits):
    selected = [r for r in dense if r["visit_index"] in allowed_visits]
    t = np.array([r["t_s"] for r in selected])
    y = np.array([r["y_hz"] for r in selected])
    visit = np.array([r["visit_index"] for r in selected])
    # Equal total fit weight per receiver visit, including when some probes fail.
    weights = np.array([1 / np.count_nonzero(visit == v) for v in visit])
    qt = np.array([baseline[v]["t_s"] for v in query_visits])
    return polynomial_prediction(t, y, qt, weights)


def evaluate(document, name, starts, scored_starts=None):
    scored_starts = starts if scored_starts is None else scored_starts
    baseline = {r["visit_index"]: r for r in document["results"] if r["start_ms"] == 0}
    visits = sorted(baseline)
    if len(visits) != document["input_visits"]:
        raise ValueError("baseline visit inventory is incomplete")
    attempted = [r for r in document["results"] if r["start_ms"] in starts]
    scored = [r for r in document["results"] if r["start_ms"] in scored_starts]
    complete = [r for r in attempted if "y_hz" in r]
    retained = [r for r in complete if r["margin"] >= 0.025]
    baseline_y = np.array([baseline[v]["y_hz"] for v in visits])
    baseline_t = np.array([baseline[v]["t_s"] for v in visits])
    folds = np.floor((baseline_t - baseline_t.min()) / 3).astype(int) % 5
    out = {
        "session_id": document["session_id"],
        "sample_rate_hz": document["sample_rate_hz"],
        "profile": name,
        "visits": len(visits),
        "attempted_probes": len(attempted),
        "complete_probes": len(complete),
        "passing_probes": len(retained),
        "complete_fraction": len(complete) / len(attempted),
        "passing_fraction": len(retained) / len(attempted),
        "scheduled_probes_per_visit": len(scored_starts),
        "eligible_probes_per_visit": len(starts),
        "scored_probes": len(scored),
        "compute_ms_per_visit": sum(r["runtime_ms"] for r in scored) / len(visits),
    }
    try:
        full = fit_from_visits(retained, baseline, set(visits), visits)
        pred = np.zeros(len(visits))
        for fold in np.unique(folds):
            training = {v for v, f in zip(visits, folds, strict=True) if f != fold}
            testing = [v for v, f in zip(visits, folds, strict=True) if f == fold]
            pred[folds == fold] = fit_from_visits(retained, baseline, training, testing)
        cut = int(0.6 * len(visits))
        tail = fit_from_visits(retained, baseline, set(visits[:cut]), visits[cut:])
        out.update(
            status="ok",
            common_full_rms_hz=rms(baseline_y - full),
            common_blocked_rms_hz=rms(baseline_y - pred),
            common_tail_rms_hz=rms(baseline_y[cut:] - tail),
        )
    except ValueError as error:
        out.update(status="insufficient_support", reason=str(error))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    docs = [json.loads(p.read_text()) for p in (args.output / "raw").glob("*.json")]
    profiles = {f"stride_{s}ms": probe_starts(s) for s in (120, 60, 40, 20, 10)}
    profiles["stride_10ms_projected"] = probe_starts(10, project_nonoverlap=True)
    profiles.update({f"single_offset_{offset}ms": [offset] for offset in (50, 100)})
    rows = [
        evaluate(
            doc,
            name,
            starts,
            probe_starts(10) if name == "stride_10ms_projected" else starts,
        )
        for doc in docs
        for name, starts in profiles.items()
    ]
    summaries = []
    for rate in (0, 2500000, 5000000):
        baseline = {
            r["session_id"]: r
            for r in rows
            if r["profile"] == "stride_120ms" and (rate == 0 or r["sample_rate_hz"] == rate)
        }
        for profile in profiles:
            all_rows = [
                r
                for r in rows
                if r["profile"] == profile and (rate == 0 or r["sample_rate_hz"] == rate)
            ]
            ok = [r for r in all_rows if r["status"] == "ok"]
            row = {
                "profile": profile,
                "sample_rate_hz": rate,
                "tracks": len(all_rows),
                "fit_tracks": len(ok),
                "scheduled_probes_per_visit": all_rows[0]["scheduled_probes_per_visit"],
                "eligible_probes_per_visit": len(profiles[profile]),
                "complete_fraction": sum(r["complete_probes"] for r in all_rows)
                / sum(r["attempted_probes"] for r in all_rows),
                "passing_fraction": sum(r["passing_probes"] for r in all_rows)
                / sum(r["attempted_probes"] for r in all_rows),
            }
            for key in (
                "common_full_rms_hz",
                "common_blocked_rms_hz",
                "common_tail_rms_hz",
                "compute_ms_per_visit",
            ):
                row["median_" + key] = float(np.median([r[key] for r in ok])) if ok else None
            row["paired_blocked"] = bootstrap_scan_ratio(
                [
                    (
                        r["session_id"],
                        r["common_blocked_rms_hz"],
                        baseline[r["session_id"]]["common_blocked_rms_hz"],
                    )
                    for r in ok
                ]
            )
            summaries.append(row)
    write_json(
        args.output / "stride-summary.json",
        {
            "source_visits": sum(d["input_visits"] for d in docs),
            "profiles": profiles,
            "rows": rows,
            "summaries": summaries,
            "evaluation": (
                "Fixed zero-offset observations; all probes of an entire visit "
                "share one fold. Cubic fitting with equal total weight per visit. "
                "Threshold 0.025 affects training only."
            ),
            "limitations": (
                "Frozen strong tracks and propagated acquisition seeds; no blind "
                "reacquisition, no end-to-end discovery comparison. "
                "Resampling unit is scan, not overlapping probe."
            ),
        },
    )
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    for rate, color in ((2500000, "#187f98"), (5000000, "#b45730")):
        selected = [
            next(
                r
                for r in summaries
                if r["profile"] == f"stride_{s}ms" and r["sample_rate_hz"] == rate
            )
            for s in (120, 60, 40, 20, 10)
        ]
        for ax, key in zip(
            axes, ("median_common_blocked_rms_hz", "median_compute_ms_per_visit"), strict=True
        ):
            ax.plot(
                [120, 60, 40, 20, 10],
                [r[key] for r in selected],
                "o-",
                color=color,
                label=f"{rate / 1e6:g} Msps",
            )
    for ax in axes:
        ax.invert_xaxis()
        ax.set_xticks([120, 60, 40, 20, 10])
        ax.set_xlabel("Probe stride within each 120 ms visit (ms)")
        ax.grid(alpha=0.2)
        ax.legend()
    axes[0].set_ylabel("Median common held-out RMS (Hz)")
    axes[1].set_ylabel("Scoring compute per visit (ms)")
    fig.suptitle("20 ms GLRT window · 12 frozen tracks · whole visits held out together")
    fig.tight_layout()
    fig.savefig(args.output / "stride-rms.png", dpi=160)
    plt.close(fig)
    for row in summaries:
        if row["sample_rate_hz"] == 0:
            print(row)


if __name__ == "__main__":
    main()
