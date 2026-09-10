#!/usr/bin/env python3
"""Summarize raw GLRT ablations without removing low-margin evaluation points."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from evaluate_scan_glrt_rms import (
    blocked_prediction,
    bootstrap_scan_ratio,
    canonical_delta,
    chronological_split,
    fit,
    rms,
    write_json,
)
from evaluate_scan_pnt_cohort import orbit_bank

from leo.analysis.research.scan_pnt_experiment import interpolate_bank


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output
    out = []
    curves = {}
    bindings = []
    for path in sorted((root / "raw-replay").glob("*.json")):
        original = json.loads(path.read_text())
        sid = original["session_id"]
        ev = json.loads((root / "evidence" / path.name).read_text())
        track = next(s for s in ev["series"] if s["tracklet_id"] == original["tracklet_id"])
        alias = 1 / 4.4e-6 * 11.2e9 / track["actual_rf_hz"]
        orbit = json.loads((root / "orbit-results" / path.name).read_text())
        matches = [
            e
            for e in orbit["episodes"]
            if track["tracklet_id"] in e["members"] and "join_proposal" not in e
        ]
        bank = None
        match = None
        if matches:
            ep = matches[0]
            match = ep["match"]["primary"]
            inv = ev["inventory"]
            bank = orbit_bank(
                (root / "evidence" / inv["tle_file"]).read_text(), inv["reference_utc_ns"]
            )
            sat_index = np.flatnonzero(bank["numbers"] == match["norad"])[0]
            bindings.append(
                {
                    "session_id": sid,
                    "episode_id": ep["episode_id"],
                    "candidate_pass": ep["match"]["candidate_pass"],
                    "norad": match["norad"],
                    "tau_s": match["tau_s"],
                }
            )
        for namespace in ("raw-replay", "raw-replay-refined"):
            data = json.loads((root / namespace / path.name).read_text())
            curves[sid, namespace] = {}
            for profile in sorted({r["profile"] for r in data["results"]}):
                rows = sorted(
                    [r for r in data["results"] if r["profile"] == profile],
                    key=lambda r: r["index"],
                )
                unavailable = sum("y_hz" not in r for r in rows)
                meta = {
                    "session_id": sid,
                    "sample_rate_hz": data["sample_rate_hz"],
                    "namespace": namespace,
                    "profile": profile,
                    "points": len(rows),
                    "unavailable_count": unavailable,
                }
                if unavailable:
                    out.append({**meta, "status": "incomplete"})
                    continue
                t = np.array([r["t_s"] for r in rows])
                delta = np.array([r["frequency_delta_hz"] for r in rows])
                branch = np.array([r["y_hz"] for r in rows])
                y = branch - delta + canonical_delta(delta, alias)
                segment = np.array(["one"] * len(t))
                training = chronological_split(t, segment)
                full = fit(t, y, segment, np.ones(len(t), bool), 3)
                pred = fit(t, y, segment, training, 3)
                blocked = blocked_prediction(t, y, segment, np.ones(len(t), bool), 3)
                row = {
                    **meta,
                    "status": "ok",
                    "span_s": float(np.ptp(t)),
                    "full_rms_hz": rms(y - full),
                    "tail_rms_hz": rms((y - pred)[~training]),
                    "blocked_rms_hz": rms(y - blocked),
                    "unadjusted_branch_full_rms_hz": rms(
                        branch - fit(t, branch, segment, np.ones(len(t), bool), 3)
                    ),
                    "alias_wrap_count": int(np.count_nonzero(np.rint(delta / alias))),
                    "median_margin": float(np.median([r["margin"] for r in rows])),
                    "passed_fraction": float(np.mean([r["margin"] >= 0.025 for r in rows])),
                    "mean_compute_ms": float(1000 * np.mean([r["runtime_s"] for r in rows])),
                }
                if bank is not None:
                    prediction = interpolate_bank(
                        bank["doppler"][[sat_index]], bank["times"], t + match["tau_s"]
                    )[0]
                    residual = y - prediction
                    residual -= np.mean(residual[training])
                    row.update(
                        fixed_tle_tail_rms_hz=rms(residual[~training]),
                        fixed_tle_candidate_pass=ep["match"]["candidate_pass"],
                    )
                out.append(row)
                curves[sid, namespace][profile] = {
                    "t": t,
                    "y": y,
                    "full": full,
                    "residual": y - full,
                }
    summaries = []
    for namespace in ("raw-replay", "raw-replay-refined"):
        group = [r for r in out if r["namespace"] == namespace]
        baseline = {r["session_id"]: r for r in group if r["profile"] == "fft_512"}
        for profile in sorted({r["profile"] for r in group}):
            for rate in (2500000, 5000000, 0):
                rows = [
                    r
                    for r in group
                    if r["profile"] == profile and (rate == 0 or r["sample_rate_hz"] == rate)
                ]
                ok = [r for r in rows if r["status"] == "ok"]
                row = {
                    "namespace": namespace,
                    "profile": profile,
                    "sample_rate_hz": rate,
                    "tracks": len(rows),
                    "complete_tracks": len(ok),
                    "total_alias_wraps": sum(r["alias_wrap_count"] for r in ok),
                }
                for key in (
                    "full_rms_hz",
                    "tail_rms_hz",
                    "blocked_rms_hz",
                    "median_margin",
                    "passed_fraction",
                    "mean_compute_ms",
                ):
                    row["median_" + key] = float(np.median([r[key] for r in ok]))
                for key in ("full_rms_hz", "tail_rms_hz", "blocked_rms_hz"):
                    row["paired_" + key] = bootstrap_scan_ratio(
                        [(r["session_id"], r[key], baseline[r["session_id"]][key]) for r in ok]
                    )
                summaries.append(row)
    write_json(
        root / "raw-replay-summary.json",
        {
            "rows": out,
            "summaries": summaries,
            "orbit_bindings": bindings,
            "alias_policy": (
                "Preserve the baseline physical branch by subtracting the nearest "
                "integer multiple of (1/4.4us)*(11.2GHz/actualRF). No points removed."
            ),
            "limits": (
                "Same acquisition seeds and preselected strongest long lane in 12 "
                "time-stratified scans. Window changes do not rerun acquisition or "
                "reselect tracks. Unavailable timing estimates are counted explicitly; "
                "complete profiles retain every evaluation observation."
            ),
        },
    )
    for namespace, suffix in (
        ("raw-replay", "fixed-timing"),
        ("raw-replay-refined", "refined-timing"),
    ):
        fig, axes = plt.subplots(1, 3, figsize=(15, 4.7))
        for rate, color in ((2500000, "#177c9b"), (5000000, "#b9552d")):
            chosen = []
            for profile in ("window_10ms", "fft_512", "window_40ms", "window_80ms"):
                chosen.append(
                    next(
                        r
                        for r in summaries
                        if r["namespace"] == namespace
                        and r["profile"] == profile
                        and r["sample_rate_hz"] == rate
                    )
                )
            for ax, key in zip(
                axes,
                ("median_full_rms_hz", "median_blocked_rms_hz", "median_mean_compute_ms"),
                strict=True,
            ):
                ax.plot(
                    [10, 20, 40, 80],
                    [r[key] for r in chosen],
                    "o-",
                    color=color,
                    label=f"{rate / 1e6:g} Msps",
                )
        for ax, title in zip(
            axes,
            ("Full cubic fit RMS", "Held-out 3-second blocks", "Scoring compute per probe"),
            strict=True,
        ):
            ax.set_title(title)
            ax.set_xlabel("GLRT probe window (ms)")
            ax.set_xticks([10, 20, 40, 80])
            ax.grid(alpha=0.2)
            ax.legend()
        axes[0].set_ylabel("Median RMS (Hz)")
        axes[1].set_ylabel("Median RMS (Hz)")
        axes[2].set_ylabel("Milliseconds")
        fig.suptitle(
            "12 recorded tracks · "
            + (
                "timing re-estimated for each window"
                if suffix == "refined-timing"
                else "published timing held fixed"
            )
        )
        fig.tight_layout()
        fig.savefig(root / f"window-size-{suffix}.png", dpi=160)
        plt.close(fig)
    fig, axes = plt.subplots(3, 4, figsize=(18, 10), sharey=False)
    for ax, sid in zip(axes.flat, sorted({k[0] for k in curves}), strict=True):
        c = curves[sid, "raw-replay-refined"]
        for profile, color, label in (
            ("window_10ms", "#849e9a", "10 ms"),
            ("fft_512", "#157ca0", "20 ms"),
            ("window_40ms", "#bc582c", "40 ms"),
            ("window_80ms", "#81378a", "80 ms"),
        ):
            if profile not in c:
                continue
            data = c[profile]
            ax.plot(
                data["t"] - data["t"].min(),
                data["residual"],
                ".-",
                ms=2,
                lw=0.7,
                color=color,
                label=label,
            )
        ax.set_title(sid[-8:])
        ax.grid(alpha=0.2)
        ax.set_xlabel("Time within track (s)")
        ax.set_ylabel("Cubic residual (Hz)")
    axes[0, 0].legend(ncol=2)
    fig.suptitle(
        "Window length changes: same candidate seeds, timing re-estimated, no residual clipping"
    )
    fig.tight_layout()
    fig.savefig(root / "window-residuals-12-tracks.png", dpi=160)
    plt.close(fig)
    for r in summaries:
        if r["sample_rate_hz"] == 0:
            print(r)


if __name__ == "__main__":
    main()
