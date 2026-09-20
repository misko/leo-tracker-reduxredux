"""Evaluate sealed causal and retrospective fits on the identical RF cohort."""

import argparse
import json
from pathlib import Path

import numpy as np
from replay_regional_doppler import digest, write_json
from report_orbit_clock_stability import horizontal_error


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ["causal", "retrospective", "reranking", "reference", "output"]:
        p.add_argument("--" + key, type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(exist_ok=False)
    causal = json.loads(a.causal.read_text())
    retro = json.loads(a.retrospective.read_text())
    rerank = json.loads(a.reranking.read_text())
    ref = json.loads(a.reference.read_text())
    if (
        not causal["strictly_causal"]
        or causal["offline_noncausal"]
        or not rerank["strictly_causal"]
    ):
        raise ValueError("strict causal evidence required")
    if causal["parent_digest"] != retro["parent_digest"] or causal["rerank_digest"] != digest(
        a.reranking
    ):
        raise ValueError("comparison provenance mismatch")
    for r in rerank["rows"]:
        if not (
            r["winning_epoch_utc_ns"] < r["capture_start_utc_ns"]
            and r["winning_collected_utc_ns"] < r["capture_start_utc_ns"]
        ):
            raise ValueError("future TLE in strict comparison")
    rows = []
    for policy, data in [("Strictly pre-capture", causal), ("Retrospective", retro)]:
        for m in data["models"]:
            rows.append(
                dict(
                    policy=policy,
                    selection=m["selection"],
                    clock_model=m["clock_model"],
                    error_m=horizontal_error(m, ref),
                    heldout_rms_hz=m["evaluation_rms_hz"],
                    observations=m["observations"],
                    episodes=m["episodes"],
                    converged=m["converged"],
                    clock_at_bound=m["clock_at_bound"],
                    clock_s=m["clock_s"],
                )
            )
    for m in causal["models"]:
        other = next(
            x
            for x in retro["models"]
            if x["selection"] == m["selection"] and x["clock_model"] == m["clock_model"]
        )
        if (m["observations"], m["episodes"]) != (other["observations"], other["episodes"]):
            raise ValueError("RF cohort differs")
    ages = [
        (r["capture_start_utc_ns"] - r["winning_epoch_utc_ns"]) / 3.6e12 for r in rerank["rows"]
    ]
    collected = [
        (r["capture_start_utc_ns"] - r["winning_collected_utc_ns"]) / 3.6e12 for r in rerank["rows"]
    ]
    stability = []
    for policy, data in [("Strictly pre-capture", causal), ("Retrospective", retro)]:
        for m in data["stability"]:
            stability.append(
                dict(
                    policy=policy,
                    selection=m["selection"],
                    grouping=m["grouping"],
                    fold=m["fold"],
                    error_m=horizontal_error(m, ref),
                )
            )
    out = dict(
        causal_digest=digest(a.causal),
        retrospective_digest=digest(a.retrospective),
        reference_digest=digest(a.reference),
        strictly_causal_winners_verified=len(ages),
        changed_identities=len(causal["changed_assignments"]),
        median_epoch_age_h=float(np.median(ages)),
        min_epoch_age_h=min(ages),
        max_epoch_age_h=max(ages),
        median_collection_age_h=float(np.median(collected)),
        min_collection_age_h=min(collected),
        rows=rows,
        stability=stability,
    )
    write_json(a.output / "evaluation.json", out)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(13, 8), layout="constrained")
    modes = ["fixed", "shared_recorded", "per_recording_recorded"]
    x = np.arange(3)
    for rowidx, selection in enumerate(["all", "selected"]):
        for delta, policy, color in [
            (-0.2, "Strictly pre-capture", "tab:blue"),
            (0.2, "Retrospective", "tab:orange"),
        ]:
            selected = [
                next(
                    r
                    for r in rows
                    if r["selection"] == selection
                    and r["policy"] == policy
                    and r["clock_model"] == mode
                )
                for mode in modes
            ]
            for col, key in enumerate(["error_m", "heldout_rms_hz"]):
                bars = axes[rowidx, col].bar(
                    x + delta, [r[key] for r in selected], 0.4, label=policy, color=color
                )
                axes[rowidx, col].bar_label(bars, fmt="%.0f", fontsize=8)
        for col in range(2):
            axes[rowidx, col].set(
                xticks=x,
                xticklabels=["Fixed UTC", "Shared bounded clock", "Per-recording bounded clocks"],
                ylabel="Horizontal error (m)" if col == 0 else "Held-out RMS (Hz)",
                title=selection.capitalize() + " cohort",
            )
            axes[rowidx, col].grid(axis="y", alpha=0.2)
            axes[rowidx, col].set_axisbelow(True)
        axes[rowidx, 0].axhline(1000, color="black", ls="--", label="1 km")
    axes[0, 0].legend(fontsize=8)
    axes[0, 1].legend(fontsize=8)
    fig.suptitle(
        "Same RF observations: pre-capture-only TLEs versus retrospective elements\n"
        "Reference used only for evaluation; lower RMS does not imply lower position error"
    )
    fig.savefig(a.output / "comparison.png", dpi=160)
    plt.close(fig)
    print(json.dumps({k: v for k, v in out.items() if k != "stability"}, indent=2))


if __name__ == "__main__":
    main()
