"""Offline lock gating on the frozen, previously acquired wideband PSS candidates."""

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from leo.analysis.research import causal_pss_lock
from leo.analysis.research.causal_pss_lock import (
    PssLockConfig,
    PssLockObservation,
    track_pss_observations,
)


def panels(axes, decisions, summary, gate):
    times = np.array([d.time_s for d in decisions])
    t = times - times[0]
    phase = np.array([d.observed_phase_s for d in decisions])
    phase = np.unwrap(phase * 750 * 2 * np.pi) / (750 * 2 * np.pi)
    center = np.median(phase)
    prediction = np.array(
        [np.nan if d.predicted_phase_s is None else d.predicted_phase_s for d in decisions]
    )
    # Put predictions on the same circular display branch as the observed phase.
    prediction += np.rint((phase - prediction) * 750) / 750
    innovation = np.array([np.nan if d.innovation_s is None else d.innovation_s for d in decisions])
    for label, color, name in (
        ("acquiring", "#929292", "Acquiring"),
        ("lock_acquired", "#929292", "Lock acquired"),
        ("accepted", "#157f91", "Accepted"),
        ("rejected", "#c54a42", "Rejected"),
        ("lost_lock", "black", "Lock lost"),
    ):
        mask = np.array([d.status == label for d in decisions])
        if mask.any():
            axes[0].scatter(
                t[mask], (phase[mask] - center) * 1e6, s=5, alpha=0.65, color=color, label=name
            )
            axes[1].scatter(t[mask], innovation[mask] * 1e9, s=5, alpha=0.65, color=color)
    axes[0].plot(
        t,
        (prediction - center) * 1e6,
        color="#303030",
        lw=0.7,
        alpha=0.7,
        label="Prediction from earlier accepted points",
    )
    axes[1].axhspan(-gate * 1e9, gate * 1e9, color="#157f91", alpha=0.1)
    axes[1].axhline(gate * 1e9, color="#157f91", ls="--", lw=0.8)
    axes[1].axhline(-gate * 1e9, color="#157f91", ls="--", lw=0.8)
    axes[0].set_title(
        f"{summary['capture_id'][-6:]}: {summary['accepted_count']} accepted, "
        f"{summary['rejected_count']} rejected; {summary['lost_count']} lock losses"
    )
    rms = summary["accepted_prediction_rms_ns"]
    axes[1].set_title(
        f"Accepted one-step prediction RMS: {rms:.1f} ns"
        if rms is not None
        else "No accepted prediction measurements"
    )
    axes[0].set_ylabel("Frame timing − median (µs)")
    axes[1].set_ylabel("Measured timing − prior prediction (ns)")
    for ax in axes:
        ax.set_xlabel("Seconds into selected interval")
        ax.grid(alpha=0.2)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    if args.output.resolve().is_relative_to(Path("/mnt/qnap01")):
        raise ValueError("QNAP is read-only")
    args.output.mkdir(exist_ok=False)
    config = PssLockConfig()
    protocol = dict(
        configuration=asdict(config),
        input=str(args.source),
        input_summary_sha256=hashlib.sha256(
            (args.source / "summary.json").read_bytes()
        ).hexdigest(),
        analyzer_sha256=hashlib.sha256(Path(causal_pss_lock.__file__).read_bytes()).hexdigest(),
        gating_is_causal=True,
        candidate_acquisition_is_causal=False,
        condition="Previously selected block/trajectory hypotheses are held fixed; "
        "no claim of end-to-end causal acquisition. Accepted RMS is conditional on gating.",
    )
    (args.output / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    records = [
        r for r in json.loads((args.source / "summary.json").read_text()) if r["lane"] == "native25"
    ]
    fig, axs = plt.subplots(5, 2, figsize=(13, 15), constrained_layout=True)
    summaries = []
    for row, r in enumerate(records):
        folder = args.source / r["capture_id"]
        modes = {
            m["mode_id"]: m
            for f in folder.glob("native25-*.json")
            for m in json.loads(f.read_text())["result"]["modes"]
        }
        points = []
        for mid in r["selected_mode_ids"]:
            mode = modes[mid]
            for w in mode["windows"]:
                points.append(
                    PssLockObservation(
                        w["fractional_global_device_sample"] / 25e6,
                        w["frame_phase_samples"] / 25e6,
                        w["peak_to_local_median"],
                        mode["continuity_segment_index"],
                    )
                )
        points.sort(key=lambda p: p.time_s)
        decisions = track_pss_observations(tuple(points), config)
        accepted = [d.innovation_s for d in decisions if d.status == "accepted"]
        rejected = [d.innovation_s for d in decisions if d.status == "rejected"]
        summary = dict(
            capture_id=r["capture_id"],
            frame_count=len(decisions),
            accepted_count=len(accepted),
            rejected_count=len(rejected),
            acquiring_count=sum(d.status == "acquiring" for d in decisions),
            lock_acquired_count=sum(d.status == "lock_acquired" for d in decisions),
            lost_count=sum(d.status == "lost_lock" for d in decisions),
            accepted_fraction_after_acquisition=len(accepted)
            / max(1, len(accepted) + len(rejected)),
            accepted_prediction_rms_ns=float(np.sqrt(np.mean(np.square(accepted))) * 1e9)
            if accepted
            else None,
            original_all_frame_quadratic_rms_ns=r["heldout_rms_ns"],
        )
        summaries.append(summary)
        (args.output / f"{r['capture_id']}.json").write_text(
            json.dumps(dict(summary=summary, decisions=[asdict(d) for d in decisions]), indent=2)
            + "\n"
        )
        panels(axs[row], decisions, summary, config.innovation_gate_s)
        if row == 0:
            focus, focus_axes = plt.subplots(1, 2, figsize=(13, 4), constrained_layout=True)
            panels(focus_axes, decisions, summary, config.innovation_gate_s)
            focus_axes[0].legend(fontsize=7)
            focus.suptitle(
                "Causal timing gate after PSS acquisition — rejected measurements stay visible"
            )
            focus.savefig(args.output / "pss-lock-first-dwell.png", dpi=160)
            plt.close(focus)
        print(json.dumps(summary), flush=True)
    axs[0, 0].legend(fontsize=7)
    fig.suptitle(
        "Five wideband dwells: causal prediction and explicit outlier rejection\n"
        "Fixed ±120 ns gate; maximum unsupported coast 250 ms; acquired candidates held fixed"
    )
    fig.savefig(args.output / "pss-lock-five-dwells.png", dpi=150)
    plt.close(fig)
    (args.output / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n")


if __name__ == "__main__":
    main()
