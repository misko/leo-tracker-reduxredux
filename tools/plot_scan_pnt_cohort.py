#!/usr/bin/env python3
"""Render cohort research figures and a compact numeric report index."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from evaluate_scan_pnt_cohort import make_arc, write_json
from evaluate_scan_pnt_longitudinal import BASE, states

from leo.analysis.research.scan_pnt_experiment import (
    doppler_from_ecef,
    remove_offsets,
    split_segments,
)
from leo.sky.propagation import parse_element_sets

COLORS = ["#1976a3", "#c65b35", "#408749", "#8655a3"]


def stats(values) -> dict:
    array = np.asarray(list(values), float)
    return {
        "n": len(array),
        "median": float(np.median(array)),
        "p10": float(np.percentile(array, 10)),
        "p90": float(np.percentile(array, 90)),
        "min": float(array.min()),
        "max": float(array.max()),
    }


def ecdf(ax, values, label, color=None):
    values = np.sort(np.asarray(list(values), float))
    ax.plot(values, np.arange(1, len(values) + 1) / len(values), label=label, color=color)


def save(fig, path: Path):
    fig.savefig(path, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output
    longitudinal = json.loads((out / "longitudinal.json").read_text())
    scans = [json.loads(path.read_text()) for path in (out / "results").glob("*.json")]
    scans.sort(key=lambda row: row["inventory"]["reference_utc_ns"])
    episodes = [ep for scan in scans for ep in scan["episodes"]]
    passed = [ep for ep in episodes if ep["match"]["candidate_pass"]]
    controls = [control for ep in episodes for control in ep["controls"]]
    docs = {
        scan["session_id"]: json.loads(
            (out / "evidence" / f"{scan['session_id']}.json").read_text()
        )
        for scan in scans
    }
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.alpha": 0.2,
            "legend.frameon": False,
            "figure.constrained_layout.use": True,
        }
    )
    x = np.arange(len(scans))
    labels = [row["inventory"]["captured_at"][11:16] for row in scans]
    fig, axes = plt.subplots(3, 1, figsize=(14, 9), sharex=True)
    rates = [row["inventory"]["sample_rate_hz"] / 1e6 for row in scans]
    axes[0].bar(x, rates, color=[COLORS[0] if rate == 2.5 else COLORS[1] for rate in rates])
    axes[0].set_ylabel("Sample rate (MS/s)")
    axes[1].plot(
        x, [row["inventory"]["valid_duty_ppm"] / 10000 for row in scans], "o-", color=COLORS[0]
    )
    axes[1].set_ylabel("Capture duty (%)")
    axes[2].bar(x, [len(row["episodes"]) for row in scans], label="All episodes", color="#cbdce4")
    axes[2].bar(
        x,
        [sum(ep["match"]["candidate_pass"] for ep in row["episodes"]) for row in scans],
        label="Candidate screen passes",
        color=COLORS[0],
    )
    axes[2].set_ylabel("Episodes")
    axes[2].set_xticks(x, labels, rotation=60)
    axes[2].set_xlabel("Capture start, 2026-09-07 UTC (fixed 07:49–15:49 review window)")
    axes[2].legend(ncol=2)
    fig.suptitle("24 complete 300 s scans • 12 at each sample rate • 502 consolidated episodes")
    save(fig, out / "01-capture-inventory.png")

    atlas = out / "scan-atlas"
    atlas.mkdir(exist_ok=True)
    for scan in scans:
        doc = docs[scan["session_id"]]
        fig, axes = plt.subplots(4, 1, figsize=(14, 9), sharex=True)
        for source in doc["series"]:
            ax = axes[source["channel"] - 1]
            ax.scatter(
                source["t_s"],
                np.array(source["y_hz"]) / 1000,
                s=8,
                color=COLORS[0 if source["edge"] == "lower" else 1],
                marker="o" if source["receiver"] == 0 else "x",
                alpha=0.7,
            )
        for i, ax in enumerate(axes):
            ax.set_ylabel(f"CH{i + 1}\nCFO (kHz at 11.2 GHz)")
            ax.set_xlim(0, 300)
        axes[-1].set_xlabel("Device time since first sample (s)")
        fig.suptitle(
            f"{scan['session_id']} • {scan['inventory']['captured_at'][:19]} UTC\n"
            "Fractional GLRT paths; blue=lower, orange=upper; dot=RX0, cross=RX1"
        )
        save(fig, atlas / f"{scan['session_id']}.png")

    fig, axes = plt.subplots(1, 3, figsize=(16, 4.5))
    for degree, color in zip((1, 2, 3), COLORS, strict=False):
        ecdf(
            axes[0],
            [ep["polynomial"]["models"][degree - 1]["heldout_rms_hz"] for ep in episodes],
            f"Degree {degree}",
            color,
        )
    ecdf(
        axes[0],
        [ep["polynomial"]["selected_heldout_rms_hz"] for ep in episodes],
        "Order selected in training",
        "black",
    )
    ecdf(
        axes[0],
        [ep["match"]["primary"]["heldout_rms_hz"] for ep in episodes],
        "TLE ±2 s",
        COLORS[3],
    )
    axes[0].set_xscale("log")
    axes[0].set_xlabel("Held-out RMS (Hz)")
    axes[0].set_ylabel("Fraction of 502 episodes")
    axes[0].legend(fontsize=8)
    orders = Counter(ep["polynomial"]["selected_degree"] for ep in episodes)
    axes[1].bar([1, 2, 3], [orders[d] for d in (1, 2, 3)], color=COLORS[:3])
    axes[1].set_xticks([1, 2, 3], ["Linear", "Quadratic", "Cubic"])
    axes[1].set_ylabel("Training-selected episode count")
    for rate, color in ((2.5, COLORS[0]), (5.0, COLORS[1])):
        rows = [
            ep
            for scan in scans
            if scan["inventory"]["sample_rate_hz"] == rate * 1e6
            for ep in scan["episodes"]
        ]
        ecdf(
            axes[2],
            [ep["match"]["primary"]["heldout_rms_hz"] for ep in rows],
            f"{rate:g} MS/s",
            color,
        )
    axes[2].set_xscale("log")
    axes[2].set_xlabel("TLE held-out RMS (Hz)")
    axes[2].legend()
    fig.suptitle(
        "Local curvature and orbit prediction: same later measurements, training-only selection"
    )
    save(fig, out / "02-model-order-and-rate.png")

    edges = longitudinal["edge_validation"]
    ratios = np.array(
        [row["shared_heldout_rms_hz"] / row["independent_heldout_rms_hz"] for row in edges]
    )
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.5))
    axes[0].scatter(
        [row["independent_heldout_rms_hz"] for row in edges],
        [row["shared_heldout_rms_hz"] for row in edges],
        s=12,
        alpha=0.5,
    )
    axes[0].plot([1, 1e6], [1, 1e6], "k--", lw=1)
    axes[0].set_xscale("log")
    axes[0].set_yscale("log")
    axes[0].set_xlabel("Separate edge held-out RMS (Hz)")
    axes[0].set_ylabel("Shared edge held-out RMS (Hz)")
    ecdf(axes[1], ratios, "387 accepted links")
    axes[1].axvline(1, color="black", ls="--")
    axes[1].set_xscale("log")
    axes[1].set_xlabel("Shared / separate held-out RMS")
    axes[1].set_ylabel("Fraction of links")
    gains = [row["scaled_design_rate_precision_gain"] for row in edges]
    ecdf(axes[2], gains, "Formal rate-SE gain")
    axes[2].set_xscale("log")
    axes[2].axvline(1, color="black", ls="--")
    axes[2].set_xlabel("Mean separate rate SE / shared rate SE")
    fig.suptitle(
        "Upper/lower normalization + separate offsets: held-out smoothing and formal precision"
    )
    save(fig, out / "03-upper-lower-validation.png")

    fig, axes = plt.subplots(1, 3, figsize=(16, 4.5))
    for chosen, label, color in (
        (False, "Other episodes", "#bcc5cc"),
        (True, "Screen passes", COLORS[0]),
    ):
        subset = [ep for ep in episodes if ep["match"]["candidate_pass"] == chosen]
        axes[0].scatter(
            [ep["match"]["primary"]["training_rms_hz"] for ep in subset],
            [ep["match"]["primary"]["heldout_rms_hz"] for ep in subset],
            s=12,
            label=label,
            color=color,
            alpha=0.65,
        )
    axes[0].set_xscale("log")
    axes[0].set_yscale("log")
    axes[0].set_xlabel("TLE training RMS (Hz)")
    axes[0].set_ylabel("Held-out RMS (Hz)")
    axes[0].legend()
    for name, label in (
        ("rate_only", "Rate ±100 Hz/s"),
        ("curvature_only", "Curvature 10% + 5 Hz"),
        ("primary", "Full shape 10% + 5 Hz"),
    ):
        ecdf(axes[1], [ep["match"][name]["near_count"] for ep in episodes], label)
    axes[1].set_xscale("log")
    axes[1].set_xlabel("Near-tie candidate count (different declared tolerances)")
    axes[1].legend(fontsize=8)
    ecdf(
        axes[2],
        [ep["match"]["primary"]["heldout_rank"] for ep in episodes],
        "Training winner's held-out rank",
    )
    axes[2].set_xscale("log")
    axes[2].set_xlabel("Held-out rank")
    axes[2].set_ylabel("Fraction of episodes")
    fig.suptitle("Catalogue identity evidence across all 502 episodes (candidate-only)")
    save(fig, out / "04-catalogue-evidence.png")

    fig, axes = plt.subplots(1, 3, figsize=(16, 4.5))
    axes[0].hist(
        [ep["match"]["primary"]["tau_s"] for ep in episodes],
        bins=np.arange(-2.125, 2.3, 0.25),
        color=COLORS[0],
    )
    axes[0].set_xlabel("Training-selected orbit time τ (s)")
    axes[0].set_ylabel("Episodes")
    for mode, label in (
        ("nominal", "τ=0"),
        ("primary", "τ within ±2 s"),
        ("wide", "τ within ±5 s"),
    ):
        ecdf(axes[1], [ep["match"][mode]["heldout_rms_hz"] for ep in episodes], label)
    axes[1].set_xscale("log")
    axes[1].set_xlabel("Held-out RMS (Hz)")
    axes[1].legend()
    axes[2].scatter(
        [ep["match"]["primary"]["heldout_rms_hz"] for ep in episodes],
        [ep["match"]["wide"]["heldout_rms_hz"] for ep in episodes],
        s=10,
        alpha=0.5,
    )
    axes[2].plot([1, 1e5], [1, 1e5], "k--", lw=1)
    axes[2].set_xscale("log")
    axes[2].set_yscale("log")
    axes[2].set_xlabel("±2 s held-out RMS (Hz)")
    axes[2].set_ylabel("±5 s held-out RMS (Hz)")
    fig.suptitle("Bounded orbit timing: added flexibility is judged on held-out data")
    save(fig, out / "05-orbit-time-sensitivity.png")

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    ecdf(
        axes[0],
        [ep["match"]["primary"]["heldout_rms_hz"] for ep in episodes],
        "Correct observation time",
        COLORS[0],
    )
    ecdf(
        axes[0],
        [item["primary"]["heldout_rms_hz"] for item in controls],
        "Whole catalogue searched at ±10 min",
        COLORS[1],
    )
    axes[0].set_xscale("log")
    axes[0].set_xlabel("Held-out RMS (Hz)")
    axes[0].set_ylabel("Fraction of searches")
    axes[0].legend()
    p = len(passed)
    c = sum(row["candidate_pass"] for row in controls)
    axes[1].bar([0, 1], [100 * p / len(episodes), 100 * c / len(controls)], color=COLORS[:2])
    axes[1].set_xticks(
        [0, 1], [f"Correct time\n{p}/{len(episodes)}", f"Wrong time\n{c}/{len(controls)}"]
    )
    axes[1].set_ylabel("Frozen screen pass rate (%)")
    fig.suptitle(
        "Negative controls measure time specificity; they do not calibrate identity probability"
    )
    save(fig, out / "06-wrong-time-controls.png")

    hits = defaultdict(list)
    for si, scan in enumerate(scans):
        for ep in scan["episodes"]:
            if ep["match"]["candidate_pass"]:
                hits[ep["match"]["primary"]["norad"]].append((si, ep))
    recurring = {row["norad"] for row in longitudinal["recurrences"]}
    display = sorted(hits, key=lambda num: (num not in recurring, -len(hits[num]), num))[:25]
    fig, ax = plt.subplots(figsize=(14, 9))
    for yi, num in enumerate(display):
        for si, ep in hits[num]:
            ax.scatter(
                si + np.mean(ep["support_s"]) / 1200,
                yi,
                s=50,
                color=COLORS[ep["channel"] - 1],
                marker="D" if num in recurring else "o",
            )
    ax.set_yticks(
        np.arange(len(display)),
        [f"{num}{'  • recurring' if num in recurring else ''}" for num in display],
    )
    ax.invert_yaxis()
    ax.set_xticks(x, labels, rotation=60)
    ax.set_xlabel("Capture time UTC; channel colors CH1/CH2/CH3/CH4")
    ax.set_ylabel("NORAD candidate (25 shown; full registry in JSON)")
    fig.suptitle(
        "Time-indexed candidate registry: four candidates recur after approximately five hours"
    )
    save(fig, out / "07-candidate-registry.png")

    recurrences = longitudinal["recurrences"]
    fig, axes = plt.subplots(len(recurrences), 2, figsize=(15, 3 * len(recurrences)))
    for i, rec in enumerate(recurrences):
        later = next(row for row in scans if row["session_id"] == rec["later_session"])
        earlier = next(row for row in scans if row["session_id"] == rec["earlier_session"])
        ep = next(ep for ep in later["episodes"] if ep["episode_id"] == rec["later_episode"])
        arc = make_arc(docs[later["session_id"]], ep["members"])
        cat = parse_element_sets((out / "evidence" / earlier["inventory"]["tle_file"]).read_text())
        sat = cat.satellites[cat.satellite_numbers.index(rec["norad"])]
        p, v = states(sat, later["inventory"]["reference_utc_ns"], arc.time_s, rec["old_tau_s"])
        training, evaluation = split_segments(arc)
        residual = remove_offsets(
            arc.frequency_hz - doppler_from_ecef(p, v, BASE), arc.segment, training
        )
        axes[i, 0].scatter(
            arc.time_s[training],
            residual[training],
            s=10,
            color="#bac5cc",
            label="Later pass offset calibration",
        )
        axes[i, 0].scatter(
            arc.time_s[evaluation],
            residual[evaluation],
            s=14,
            color=COLORS[0],
            label="Later pass held-out",
        )
        axes[i, 0].axhline(0, color="black", lw=0.7)
        axes[i, 0].set_ylabel(f"NORAD {rec['norad']}\nResidual (Hz)")
        axes[i, 0].set_xlabel("Later scan device time (s)")
        vals = [
            rec["frozen_old_tle_nominal_heldout_hz"],
            rec["frozen_old_tle_tau_heldout_hz"],
            rec["updated_tle_refit_heldout_hz"],
        ]
        axes[i, 1].barh([0, 1, 2], vals, color=COLORS[:3])
        axes[i, 1].set_yticks(
            [0, 1, 2], ["Old TLE, τ=0", "Old TLE, frozen τ", "Updated TLE, refit τ"]
        )
        axes[i, 1].set_xlabel("Held-out RMS (Hz)")
        for j, value in enumerate(vals):
            axes[i, 1].text(value + 4, j, f"{value:.1f}", va="center")
    axes[0, 0].legend(fontsize=8)
    fig.suptitle("Repeat-pass prediction from the earlier catalogue: identity and old τ are frozen")
    save(fig, out / "08-frozen-recurrence-predictions.png")

    handoffs = longitudinal["handoffs"]
    fig, ax = plt.subplots(figsize=(13, 5))
    for i, item in enumerate(handoffs):
        ax.scatter(i, item["tle_heldout_hz"], color=COLORS[0], marker="D", s=70)
        ax.scatter(i, min(item["polynomial_heldout_hz"]), color=COLORS[1], marker="x", s=70)
    ax.set_xticks(
        np.arange(len(handoffs)),
        [f"{item['session_id'][-5:]}\n{item['left']}→{item['right']}" for item in handoffs],
    )
    ax.set_yscale("log")
    ax.set_ylabel("Unseen right-segment RMS (Hz)")
    ax.scatter([], [], color=COLORS[0], marker="D", label="TLE selected using left training")
    ax.scatter(
        [],
        [],
        color=COLORS[1],
        marker="x",
        label="Best of three left-only polynomials (conservative null)",
    )
    ax.legend(fontsize=9)
    fig.suptitle(
        "Seven RF-supported channel joins: one survives the declared predictive handoff screen"
    )
    save(fig, out / "09-channel-handoff-tests.png")

    positions = [row for row in longitudinal["positioning"] if row["included"]]
    fig, axes = plt.subplots(1, 3, figsize=(17, 5))
    mode_labels = {
        "nominal_2d": "Fixed TLE, known height",
        "known_site_tau_2d": "τ calibrated at known site",
        "nominal_3d": "Fixed TLE, free height",
        "joint_bounded_tau_2d": "Position + bounded τ",
    }
    for mi, (mode, label) in enumerate(mode_labels.items()):
        solutions = [
            next(item for item in row["modes"] if item["mode"] == mode)["solutions"][0]
            for row in positions
        ]
        if mi != 2:
            axes[0].scatter(
                [row["enu_km"][0] for row in solutions],
                [row["enu_km"][1] for row in solutions],
                s=25,
                label=label,
                color=COLORS[mi],
            )
        ecdf(axes[1], [row["horizontal_error_m"] for row in solutions], label, COLORS[mi])
        ecdf(axes[2], [row["heldout_rms_hz"] for row in solutions], label, COLORS[mi])
    axes[0].scatter([0], [0], color="black", marker="+", s=120)
    axes[0].set_xlabel("East error (km)")
    axes[0].set_ylabel("North error (km)")
    axes[0].set_aspect("equal", adjustable="datalim")
    axes[1].set_xscale("log")
    axes[1].set_xlabel("Horizontal error against known site (m)")
    axes[1].legend(fontsize=8)
    axes[2].set_xscale("log")
    axes[2].set_xlabel("Held-out Doppler RMS (Hz)")
    fig.suptitle(
        "Conditional positioning on 19 eligible scans: "
        "low residual is insufficient for accurate location"
    )
    save(fig, out / "10-positioning-ablation.png")

    pooled = longitudinal["pooled_positioning"]
    fig, axes = plt.subplots(1, 3, figsize=(17, 5))
    for mode, label in (
        ("nominal", "Fixed TLE"),
        ("robust_nominal", "Robust fixed TLE"),
        ("known_site_tau", "Known-site τ calibration"),
    ):
        selected = [next(row for row in point["modes"] if row["mode"] == mode) for point in pooled]
        axes[0].plot(
            [row["scan_count"] for row in pooled],
            [row["horizontal_error_m"] for row in selected],
            "o-",
            label=label,
        )
        axes[1].plot(
            [row["scan_count"] for row in pooled[:-1]],
            [row["future_scan_heldout_rms_hz"] for row in selected[:-1]],
            "o-",
            label=label,
        )
    axes[0].set_ylabel("Conditional horizontal error (m)")
    axes[0].set_xlabel("Eligible scans accumulated")
    axes[0].set_yscale("log")
    axes[0].legend(fontsize=8)
    axes[1].set_ylabel("Later-scan held-out RMS (Hz)")
    axes[1].set_xlabel("Earlier scans used for position")
    for noise, label in (
        ("independent_100hz", "Independent 100 Hz noise"),
        ("five_sample_correlated_100hz", "Five-sample correlated noise"),
    ):
        ecdf(
            axes[2],
            [
                row["horizontal_error_m"]
                for row in longitudinal["synthetic_positioning"]
                if row["noise_type"] == noise
            ],
            label,
        )
    axes[2].set_xlabel("Synthetic horizontal error (m)")
    axes[2].set_ylabel("Fraction of 20 trials")
    axes[2].legend(fontsize=8)
    fig.suptitle("Accumulating evidence helps; synthetic trials isolate the noise-limited geometry")
    save(fig, out / "11-pooled-position-and-simulation.png")

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    conflicts = longitudinal["conflicts"]
    counts = Counter(row["session_id"] for row in conflicts)
    axes[0].bar(x, [counts[row["session_id"]] for row in scans], color=COLORS[1])
    axes[0].set_xticks(x, labels, rotation=60)
    axes[0].set_ylabel("Overlapping cross-channel pairs\nwith same candidate NORAD")
    axes[0].set_xlabel("Capture time UTC")
    for mi, (mode, label) in enumerate(mode_labels.items()):
        vals = [
            next(item for item in row["modes"] if item["mode"] == mode)["solutions"]
            for row in positions
        ]
        spreads = [
            np.linalg.norm(np.array(item[0]["enu_km"][:2]) - np.array(item[1]["enu_km"][:2])) * 1000
            for item in vals
        ]
        ecdf(axes[1], np.maximum(spreads, 1e-4), label, COLORS[mi])
    axes[1].set_xscale("log")
    axes[1].set_xlabel("Distance between two initializations' solutions (m)")
    axes[1].set_ylabel("Fraction of eligible scans")
    axes[1].legend(fontsize=8)
    fig.suptitle("Failure modes: channel exclusivity conflicts and position/orbit ambiguity")
    save(fig, out / "12-conflicts-and-identifiability.png")

    registry = []
    for norad, items in sorted(hits.items()):
        conflicted = any(row["norad"] == norad for row in conflicts)
        registry.append(
            {
                "norad": norad,
                "name": items[0][1]["match"]["name"],
                "status": "candidate_with_channel_conflict"
                if conflicted
                else "repeat_pass_candidate"
                if norad in recurring
                else "single_pass_candidate",
                "identity_claimed": False,
                "observations": [
                    {
                        "session_id": scans[si]["session_id"],
                        "episode_id": ep["episode_id"],
                        "channel": ep["channel"],
                        "support_s": ep["support_s"],
                        "reference_utc_ns": scans[si]["inventory"]["reference_utc_ns"],
                        "tle_digest": scans[si]["inventory"]["tle_digest"],
                        "tau_s": ep["match"]["primary"]["tau_s"],
                        "heldout_rms_hz": ep["match"]["primary"]["heldout_rms_hz"],
                    }
                    for si, ep in items
                ],
            }
        )
    write_json(
        out / "candidate-registry.json",
        {"schema_version": 1, "candidate_only": True, "satellites": registry},
    )
    summary = {
        "scan_count": len(scans),
        "episode_count": len(episodes),
        "candidate_pass_count": len(passed),
        "unique_candidate_norads": len(hits),
        "wrong_time_search_count": len(controls),
        "wrong_time_pass_count": sum(row["candidate_pass"] for row in controls),
        "valid_duty_pct": stats(row["inventory"]["valid_duty_ppm"] / 10000 for row in scans),
        "calendar_valid_duty_pct": sum(
            row["inventory"]["visit_count"] * row["inventory"]["valid_visit_ms"] / 1000
            for row in scans
        )
        / 28800
        * 100,
        "utc_bracket_ms": stats(
            row["inventory"]["timing"]["first_sample_bracket_width_ns"] / 1e6 for row in scans
        ),
        "candidate_heldout_hz": stats(ep["match"]["primary"]["heldout_rms_hz"] for ep in passed),
        "episode_duration_s": stats(ep["support_s"][1] - ep["support_s"][0] for ep in episodes),
        "edge_link_count": len(edges),
        "edge_shared_heldout_better_count": int(np.count_nonzero(ratios < 1)),
        "edge_shared_over_separate_heldout_ratio": stats(ratios),
        "edge_formal_rate_precision_gain": stats(gains),
        "polynomial_selected_counts": dict(orders),
        "training_bic_fallback_count": sum(
            ep["polynomial"]["selection_criterion"] == "training_bic" for ep in episodes
        ),
        "heldout_rank1_count": sum(ep["match"]["primary"]["heldout_rank"] == 1 for ep in episodes),
        "tau_at_primary_boundary": sum(ep["match"]["primary"]["at_boundary"] for ep in episodes),
        "nominal_primary_same_identity": sum(
            ep["match"]["nominal"]["norad"] == ep["match"]["primary"]["norad"] for ep in episodes
        ),
        "primary_wide_same_identity": sum(
            ep["match"]["wide"]["norad"] == ep["match"]["primary"]["norad"] for ep in episodes
        ),
        "wide_heldout_better_count": sum(
            ep["match"]["wide"]["heldout_rms_hz"] < ep["match"]["primary"]["heldout_rms_hz"]
            for ep in episodes
        ),
        "near_counts": {
            name: stats(ep["match"][name]["near_count"] for ep in episodes)
            for name in ("rate_only", "curvature_only", "primary")
        },
        "method_heldout_hz": {
            name: stats(ep["match"][name]["heldout_rms_hz"] for ep in episodes)
            for name in ("nominal", "primary", "wide")
        },
        "polynomial_heldout_hz": {
            str(d): stats(ep["polynomial"]["models"][d - 1]["heldout_rms_hz"] for ep in episodes)
            for d in (1, 2, 3)
        },
        "adaptive_polynomial_heldout_hz": stats(
            ep["polynomial"]["selected_heldout_rms_hz"] for ep in episodes
        ),
        "rf_join_count": sum(len(row["joins"]) for row in scans),
        "rf_supported_join_count": len(handoffs),
        "predictive_handoff_pass_count": sum(row["supported"] for row in handoffs),
        "channel_conflict_pairs": len(conflicts),
        "channel_conflict_norads": len({row["norad"] for row in conflicts}),
        "positioning_scan_count": len(positions),
        "positioning_modes": {
            mode: {
                "horizontal_error_m": stats(
                    next(item for item in row["modes"] if item["mode"] == mode)["solutions"][0][
                        "horizontal_error_m"
                    ]
                    for row in positions
                ),
                "heldout_hz": stats(
                    next(item for item in row["modes"] if item["mode"] == mode)["solutions"][0][
                        "heldout_rms_hz"
                    ]
                    for row in positions
                ),
                "converged_count": sum(
                    next(item for item in row["modes"] if item["mode"] == mode)["solutions"][0][
                        "converged"
                    ]
                    for row in positions
                ),
            }
            for mode in mode_labels
        },
        "pooled_positioning": [
            {
                "scan_count": row["scan_count"],
                "modes": [
                    {k: v for k, v in mode.items() if k not in ("nuisance_parameters",)}
                    for mode in row["modes"]
                ],
            }
            for row in pooled
        ],
        "synthetic_positioning": {
            noise: stats(
                row["horizontal_error_m"]
                for row in longitudinal["synthetic_positioning"]
                if row["noise_type"] == noise
            )
            for noise in ("independent_100hz", "five_sample_correlated_100hz")
        },
        "recurrences": recurrences,
    }
    write_json(out / "summary.json", summary)
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k not in ("pooled_positioning", "recurrences")},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
