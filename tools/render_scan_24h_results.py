#!/usr/bin/env python3
"""Render long orbital fits and complete a common-support window comparison."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from evaluate_scan_glrt_rms import bootstrap_scan_ratio, canonical_delta, fit, rms, write_json
from evaluate_scan_pnt_cohort import make_arc, orbit_bank, score_arc
from evaluate_scan_pnt_longitudinal import polynomial_predict

from leo.analysis.research.scan_pnt_experiment import (
    interpolate_bank,
    polynomial_comparison,
    remove_offsets,
    split_segments,
)


def common_windows(root):
    rows = []
    names = ("window_10ms", "fft_512", "window_40ms", "window_80ms")
    for path in sorted((root / "raw-replay-refined").glob("*.json")):
        doc = json.loads(path.read_text())
        evidence = json.loads((root / "evidence" / path.name).read_text())
        track = next(s for s in evidence["series"] if s["tracklet_id"] == doc["tracklet_id"])
        alias = 1 / 4.4e-6 * 11.2e9 / track["actual_rf_hz"]
        by = {
            name: {r["index"]: r for r in doc["results"] if r["profile"] == name and "y_hz" in r}
            for name in names
        }
        shared = sorted(set.intersection(*(set(by[name]) for name in names)))
        base_t = np.array([by["fft_512"][i]["t_s"] for i in shared])
        folds = np.floor((base_t - base_t.min()) / 3).astype(int) % 5
        # All profiles use identical observation IDs and block assignments.
        for name in names:
            selected = [by[name][i] for i in shared]
            t = np.array([r["t_s"] for r in selected])
            delta = np.array([r["frequency_delta_hz"] for r in selected])
            y = np.array([r["y_hz"] for r in selected]) - delta + canonical_delta(delta, alias)
            segment = np.array(["one"] * len(t))
            full = fit(t, y, segment, np.ones(len(t), bool), 3)
            pred = np.zeros(len(t))
            for fold in np.unique(folds):
                pred[folds == fold] = fit(t, y, segment, folds != fold, 3)[folds == fold]
            rows.append(
                {
                    "session_id": doc["session_id"],
                    "sample_rate_hz": doc["sample_rate_hz"],
                    "profile": name,
                    "common_points": len(t),
                    "baseline_points": len(by["fft_512"]),
                    "full_rms_hz": rms(y - full),
                    "blocked_rms_hz": rms(y - pred),
                }
            )
    summaries = []
    for rate in (0, 2500000, 5000000):
        baseline = {
            r["session_id"]: r
            for r in rows
            if r["profile"] == "fft_512" and (not rate or r["sample_rate_hz"] == rate)
        }
        for name in names:
            selected = [
                r
                for r in rows
                if r["profile"] == name and (not rate or r["sample_rate_hz"] == rate)
            ]
            summary = {
                "profile": name,
                "sample_rate_hz": rate,
                "tracks": len(selected),
                "common_points": sum(r["common_points"] for r in selected),
            }
            for key in ("full_rms_hz", "blocked_rms_hz"):
                summary["median_" + key] = float(np.median([r[key] for r in selected]))
                summary["paired_" + key] = bootstrap_scan_ratio(
                    [(r["session_id"], r[key], baseline[r["session_id"]][key]) for r in selected]
                )
            summaries.append(summary)
    write_json(
        root / "window-common-support.json",
        {
            "rows": rows,
            "summaries": summaries,
            "policy": (
                "Intersection of available timing estimates across all four windows; "
                "identical source IDs and baseline-time block folds. Six unavailable "
                "80-ms probes excluded from every window, explicitly."
            ),
        },
    )
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    for rate, color in ((2500000, "#177c9b"), (5000000, "#b9552d")):
        selected = [
            next(r for r in summaries if r["profile"] == name and r["sample_rate_hz"] == rate)
            for name in names
        ]
        for ax, key in zip(axes, ("median_full_rms_hz", "median_blocked_rms_hz"), strict=True):
            ax.plot(
                [10, 20, 40, 80],
                [r[key] for r in selected],
                "o-",
                color=color,
                label=f"{rate / 1e6:g} Msps (6 tracks)",
            )
    for ax, title in zip(axes, ("Full cubic fit", "Held-out 3-second blocks"), strict=True):
        ax.set_title(title)
        ax.set_xlabel("GLRT probe window (ms)")
        ax.set_ylabel("Median RMS (Hz)")
        ax.set_xticks([10, 20, 40, 80])
        ax.grid(alpha=0.2)
        ax.legend()
    fig.suptitle("Same 531 observations on 12 recorded tracks · timing re-estimated")
    fig.tight_layout()
    fig.savefig(root / "window-size-common-support.png", dpi=170)
    plt.close(fig)


def orbital_figures(root):
    hypotheses = []
    for path in (root / "orbit-results").glob("*.json"):
        doc = json.loads(path.read_text())
        hypotheses.extend({**e, "session_id": doc["session_id"]} for e in doc["episodes"])
    passing = [e for e in hypotheses if e["match"]["candidate_pass"]]
    longest = max(passing, key=lambda e: np.ptp(e["support_s"]))
    standalone = max(
        [e for e in passing if "join_proposal" not in e], key=lambda e: np.ptp(e["support_s"])
    )
    strongest = min(passing, key=lambda e: e["match"]["primary"]["heldout_rms_hz"])
    chosen = [longest, standalone, strongest]
    fig, axes = plt.subplots(2, 3, figsize=(17, 8), gridspec_kw={"height_ratios": [2, 1]})
    for column, ep in enumerate(chosen):
        doc = json.loads((root / "evidence" / f"{ep['session_id']}.json").read_text())
        inv = doc["inventory"]
        arc = make_arc(doc, ep["members"])
        training, _ = split_segments(arc)
        bank = orbit_bank(
            (root / "evidence" / inv["tle_file"]).read_text(), inv["reference_utc_ns"]
        )
        match = ep["match"]["primary"]
        idx = np.flatnonzero(bank["numbers"] == match["norad"])[0]
        prediction = interpolate_bank(
            bank["doppler"][[idx]], bank["times"], arc.time_s + match["tau_s"]
        )[0]
        residual = remove_offsets(arc.frequency_hz - prediction, arc.segment, training)
        for name in np.unique(arc.segment):
            mask = arc.segment == name
            source = next(s for s in doc["series"] if s["tracklet_id"] == name)
            label = f"CH{source['channel']}{source['edge'][0].upper()} RX{source['receiver']}"
            axes[0, column].scatter(
                arc.time_s[mask], (prediction[mask] + residual[mask]) / 1000, s=10, label=label
            )
            axes[1, column].scatter(arc.time_s[mask], residual[mask], s=10)
        grid = np.linspace(arc.time_s.min(), arc.time_s.max(), 300)
        line = interpolate_bank(bank["doppler"][[idx]], bank["times"], grid + match["tau_s"])[0]
        axes[0, column].plot(grid, line / 1000, "k-", lw=1.5, label="Frozen TLE fit")
        axes[0, column].set_title(
            f"{ep['match']['name']} · NORAD {match['norad']}\n"
            f"{np.ptp(ep['support_s']):.1f} s · held-out RMS {match['heldout_rms_hz']:.1f} Hz"
        )
        axes[0, column].legend(fontsize=7, ncol=2)
        axes[0, column].set_ylabel("RF-normalized Doppler (kHz)")
        axes[1, column].set_ylabel("Residual (Hz)")
        axes[1, column].set_xlabel("Time from scan start (s)")
        for ax in axes[:, column]:
            ax.grid(alpha=0.2)
    fig.suptitle(
        "Long Starlink candidate tracks · one frequency offset per source tracklet "
        "· identity unconfirmed"
    )
    fig.tight_layout()
    fig.savefig(root / "long-starlink-candidate-fits.png", dpi=170)
    plt.close(fig)
    # Test the 64-s handoff without choosing a new satellite/time shift on the right.
    ep = longest
    doc = json.loads((root / "evidence" / f"{ep['session_id']}.json").read_text())
    by = {e["episode_id"]: e for e in doc["episodes"]}
    join = ep["join_proposal"]
    left = make_arc(doc, by[join["left_track_id"]]["members"])
    right = make_arc(doc, by[join["right_track_id"]]["members"])
    inv = doc["inventory"]
    bank = orbit_bank((root / "evidence" / inv["tle_file"]).read_text(), inv["reference_utc_ns"])
    independent = []
    for member_id in (join["left_track_id"], join["right_track_id"]):
        member = by[member_id]
        arc = make_arc(doc, member["members"])
        polynomial = polynomial_comparison(arc)
        independent.append(
            {**member, "polynomial": polynomial, "match": score_arc(arc, bank, polynomial)}
        )
    write_json(root / "handoff-independent-members.json", independent)
    selected = next(
        e["match"]["primary"] for e in independent if e["episode_id"] == join["left_track_id"]
    )
    idx = np.flatnonzero(bank["numbers"] == selected["norad"])[0]
    calibrate, test = split_segments(right, 0.4)
    left_train, _ = split_segments(left)
    prediction = interpolate_bank(
        bank["doppler"][[idx]], bank["times"], right.time_s + selected["tau_s"]
    )[0]
    residual = remove_offsets(right.frequency_hz - prediction, right.segment, calibrate)
    nulls = []
    for degree in (1, 2, 3):
        pred = polynomial_predict(left, right, left_train, 0, degree)
        res = remove_offsets(right.frequency_hz - pred, right.segment, calibrate)
        nulls.append({"degree": degree, "right_heldout_rms_hz": rms(res[test])})
    write_json(
        root / "handoff-transfer.json",
        {
            "session_id": ep["session_id"],
            "left": join["left_track_id"],
            "right": join["right_track_id"],
            "norad_selected_on_left": selected["norad"],
            "tau_selected_on_left_s": selected["tau_s"],
            "right_heldout_rms_hz": rms(residual[test]),
            "right_offset_calibration_points": int(calibrate.sum()),
            "right_test_points": int(test.sum()),
            "polynomial_transfer_controls": nulls,
            "limitation": (
                "Post-hoc selected handoff; right is one receiver and one edge. "
                "Offset fitted on its first 40 percent; no right-side satellite "
                "or time-offset reselection."
            ),
        },
    )
    summary = {
        "hypotheses": len(hypotheses),
        "standalone": sum("join_proposal" not in e for e in hypotheses),
        "joins": sum("join_proposal" in e for e in hypotheses),
        "passing": len(passing),
        "passing_joins": sum("join_proposal" in e for e in passing),
        "wrong_time_controls": sum(len(e["controls"]) for e in hypotheses),
        "wrong_time_passing": sum(c["candidate_pass"] for e in hypotheses for c in e["controls"]),
        "passing_hypotheses": passing,
        "figure_hypotheses": [
            {"session_id": e["session_id"], "episode_id": e["episode_id"]} for e in chosen
        ],
    }
    write_json(root / "orbit-summary.json", summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    common_windows(args.output)
    orbital_figures(args.output)


if __name__ == "__main__":
    main()
