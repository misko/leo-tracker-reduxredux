"""Visualize bounded orbital/timing results and explicit truncation proposals."""

import hashlib
import json

import matplotlib
import numpy as np
from associate_merged_track_catalogue import write
from diagnose_s01_ch2_t000 import OUTPUT, TARGET
from fit_s01_ch2_orbit_timing import DESTINATION, MODELS, warp
from inventory_clipped_phase_cohort import ROOT

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def run():
    results = json.loads((DESTINATION / "results.json").read_text())
    transfer = json.loads((DESTINATION / "clock_transfer.json").read_text())
    saved = json.loads((OUTPUT / "fitted_c/past_profiles.json").read_text())["current_rows"][0]
    times = np.array(saved["times_s"])
    rows = results["fitted_c/all_curved/rx1_clock_rate_5000ppm"]["rows"]
    target = results["fitted_c/all_curved/rx1_clock_rate_5000ppm"]["target"]
    fig, axes = plt.subplots(2, 2, figsize=(14, 9), layout="constrained")
    axes[0, 0].plot(times, saved["residual_hz"], ".-", color="gray", label="Existing causal orbit")
    for case, color in (("all_curved", "seagreen"), ("omit_target", "royalblue")):
        r = results[f"fitted_c/{case}/rx1_clock_rate_5000ppm"]
        axes[0, 0].plot(
            times,
            r["target"]["residual_hz"],
            ".-",
            color=color,
            label=f"RX1 clock rate, {case}: {r['target']['rms_hz']:.1f} Hz",
        )
    axes[0, 0].axhline(0, color="black", lw=0.7)
    axes[0, 0].set(
        title="Full 80-point track: shared timing proposal",
        ylabel="Residual (Hz)",
        xlabel="Seconds from S01 start",
    )
    models = [
        "phase_only",
        "mean_motion_rev_day",
        "inclination_deg",
        "raan_deg",
        "e_cos_omega",
        "e_sin_omega",
        "bstar",
        "rx1_clock_offset_s",
        "rx1_clock_rate_100ppm",
        "rx1_clock_rate_5000ppm",
    ]
    labels = [
        "Phase only",
        "Mean motion + phase",
        "Inclination + phase",
        "RAAN + phase",
        "e cos ω + phase",
        "e sin ω + phase",
        "B* + phase",
        "RX1 offset + phase",
        "RX1 rate ±100 ppm + phase",
        "RX1 rate ±5000 ppm + phase",
    ]
    for offset, case, color in (
        (-0.2, "target_only", "darkorange"),
        (0, "all_curved", "seagreen"),
        (0.2, "omit_target", "royalblue"),
    ):
        for j, model in enumerate(models):
            r = results[f"fitted_c/{case}/{model}"]["target"]
            axes[0, 1].scatter(
                r["rms_hz"],
                j + offset,
                color=color,
                marker="o",
                facecolors=color if r["passing"] else "none",
                s=38,
                label=case if j == 0 else None,
            )
    axes[0, 1].set(
        yticks=range(len(models)),
        yticklabels=labels,
        xlabel="Target RMS (Hz)",
        title="Filled markers pass all per-track gates",
    )
    axes[0, 1].invert_yaxis()
    t = np.linspace(220, 300, 100)
    for case, color in (("all_curved", "seagreen"), ("omit_target", "royalblue")):
        r = results[f"fitted_c/{case}/rx1_clock_rate_5000ppm"]
        delta = warp(r["model"], r["delta"], t, 1, r["timing_reference_s"]) - t
        axes[1, 0].plot(t, delta * 1000, color=color, label=f"{case}: {r['delta']:.0f} ppm")
    axes[1, 0].axhline(0, color="black", lw=0.7)
    axes[1, 0].set(
        title="Actual-time correction relative to recorded RX1 time",
        xlabel="Seconds from S01 start",
        ylabel="Timing correction (ms)",
    )
    transferred = [r for r in transfer["fitted_c/all_curved"]["rows"] if r["receiver"] == 1]
    positions = np.arange(len(transferred))
    axes[1, 1].bar(
        positions - 0.18,
        [r["old_rms_hz"] for r in transferred],
        width=0.36,
        color="gray",
        label="Existing model",
    )
    axes[1, 1].bar(
        positions + 0.18,
        [r["new_rms_hz"] for r in transferred],
        width=0.36,
        color=["seagreen" if r["new_passes"] else "firebrick" for r in transferred],
        label="Same clock correction, other models frozen",
    )
    axes[1, 1].set(
        xticks=positions,
        xticklabels=[r["component"].replace("S01-RX1-", "") for r in transferred],
        title="Transfer to other overlapping curved RX1 families",
        ylabel="RMS (Hz)",
    )
    for ax in axes.flat:
        ax.grid(alpha=0.2)
        ax.legend(fontsize=7)
    fig.suptitle(
        "62811: orbital and receiver-clock sensitivity, fixed GPS and hardware\n"
        "Corrections are diagnostic; filled target markers do not establish a satellite identity"
    )
    fig.savefig(DESTINATION / "model_comparison.png", dpi=170)
    plt.close(fig)

    prefix_data = json.loads((OUTPUT / "shortening_diagnostic.json").read_text())["fitted_c"]
    prefixes = prefix_data["prefixes"]

    def maximum_ratio(r):
        d = r["diagnostics"]
        return max(
            d["slope_z"] / 3,
            d["quadratic_bic_gain"] / 10,
            d["maximum_step_z"] / 4,
            abs(d["lag1_acf"]) * np.sqrt(r["points"]) / 4,
        )

    safe = [r for r in prefixes if r["span_s"] >= 20 and maximum_ratio(r) <= 0.8 and r["passes"]]
    proposal = max(safe, key=lambda r: r["points"])
    track = json.loads((OUTPUT / "target.json").read_text())
    count = proposal["points"]
    before, after = track["observation_ids"][:count], track["observation_ids"][count:]
    assert set(before).isdisjoint(after) and before + after == track["observation_ids"]
    write(
        DESTINATION / "truncation_proposal.json",
        dict(
            parent=TARGET,
            minimum_span_s=20,
            maximum_structure_gate_ratio=0.8,
            chosen_prefix=proposal,
            maximum_structure_ratio=maximum_ratio(proposal),
            retained_candidate_observation_ids=before,
            explicitly_unassociated_tail_observation_ids=after,
            retained_points=len(before),
            tail_points=len(after),
            longest_ordinary_passing_prefix=prefix_data["longest_passing_prefix"],
            posthoc_diagnostic_not_adopted=True,
            selection_policy_requires_false_acceptance_and_complexity_calibration=True,
            frozen_final_candidate_competition_artifact="prefix_candidate_competition.json",
            phase_reoptimized_candidate_competition_not_repeated=True,
        ),
    )
    fig, ax = plt.subplots(figsize=(12, 4.7), layout="constrained")
    cut = (times[count - 1] + times[count]) / 2
    ax.plot(
        times[:count],
        np.array(saved["residual_hz"])[:count],
        "o-",
        ms=4,
        color="seagreen",
        label=f"Candidate retained prefix: {count} points",
    )
    ax.plot(
        times[count:],
        np.array(saved["residual_hz"])[count:],
        "x-",
        ms=5,
        color="firebrick",
        label=f"Retained as unassociated: {80 - count} points",
    )
    ax.axvline(cut, color="black", ls="--", label="Proposed truncation boundary")
    ax.axhline(0, color="gray", lw=0.6)
    ax.set(
        title=f"Truncation proposal: {count} points, {proposal['rms_hz']:.1f} Hz RMS\n"
        "Residuals shown on the original common-offset axis; no observations deleted",
        xlabel="Seconds from S01 start",
        ylabel="Original orbit residual (Hz)",
    )
    ax.grid(alpha=0.2)
    ax.legend(fontsize=8)
    fig.savefig(DESTINATION / "truncation_proposal.png", dpi=170)
    plt.close(fig)
    curved = set(json.loads((DESTINATION / "protocol.json").read_text())["curved_members"])
    assert len(results) == 60
    assert all(set(r["calibration_members"]) <= curved for r in results.values())
    assert all(
        TARGET not in r["calibration_members"] for k, r in results.items() if "/omit_target/" in k
    )
    comparisons = {}
    for case in ("target_only", "all_curved", "omit_target"):
        for model in MODELS:
            a, b = results[f"c0/{case}/{model}"], results[f"fitted_c/{case}/{model}"]
            comparisons[f"{case}/{model}"] = dict(
                target_status_equal=a["target"]["passing"] == b["target"]["passing"],
                passing_ids_equal=[r["component"] for r in a["rows"] if r["passing"]]
                == [r["component"] for r in b["rows"] if r["passing"]],
                target_rms_c0_hz=a["target"]["rms_hz"],
                target_rms_fitted_c_hz=b["target"]["rms_hz"],
            )
    write(
        DESTINATION / "validation.json",
        dict(
            model_case_arm_results=len(results),
            calibrated_curved_only=True,
            omit_target_membership_verified=True,
            lossless_truncation_proposal=True,
            maximum_interpolation_error_hz=max(
                r["interpolation_max_error_hz"] for r in results.values()
            ),
            c_arm_comparisons=comparisons,
            pooled_accepted_curved_points=sum(
                r["points"] for r in rows if r["passing"] and r["active_curvature"]
            ),
            clock_proposal_target_rms_hz=target["rms_hz"],
            source_sha256={
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (
                    ROOT / "tools/fit_s01_ch2_orbit_timing.py",
                    ROOT / "tools/transfer_s01_ch2_clock.py",
                    ROOT / "tools/render_s01_ch2_orbit_timing.py",
                )
            },
        ),
    )
    print(
        json.dumps(
            dict(truncation_points=count, tail_points=80 - count, clock_target_rms=target["rms_hz"])
        )
    )


if __name__ == "__main__":
    run()
