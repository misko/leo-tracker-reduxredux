"""Seal complete clock-conditioned diagnostics, including failed coarse fits."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from band_calibrated_merge_study import REPORT
from clock_conditioned_merge_study import DESTINATION, verify
from continuous_merge_study import sha, write

PUBLIC = REPORT / "clock-conditioned"


def main():
    protocol_path = DESTINATION / "protocol.json"
    protocol = json.loads(protocol_path.read_bytes())
    verify(protocol["bindings"])
    results, seal = [], {}
    for case in protocol["cases"]:
        for calibration in case["calibrations"]:
            for mode in protocol["modes"]:
                path = (
                    DESTINATION
                    / case["dataset"]
                    / case["session_id"]
                    / (calibration + "-" + mode + ".json")
                )
                if not path.exists():
                    raise ValueError("all fixed conditions required before report: " + str(path))
                data = json.loads(path.read_bytes())
                if data["protocol_sha256"] != sha(protocol_path):
                    raise ValueError("result protocol differs")
                seal[str(path)] = sha(path)
                receipt = {
                    k: data[k]
                    for k in ("case", "calibration", "mode", "status", "reason", "elapsed_s")
                }
                if data["status"] == "complete":
                    audit = data["audit"]
                    branches = []
                    for branch in audit["branches"]:
                        branches.append(
                            {
                                "start_hz_per_s": branch["start_hz_per_s"],
                                "original_support_score": branch["original_support_score"],
                                "passes": [
                                    {
                                        k: p[k]
                                        for k in (
                                            "pass",
                                            "conditioning_slopes_hz_per_s",
                                            "restored_slopes_hz_per_s",
                                            "slope_clipped",
                                            "candidate_indices",
                                        )
                                    }
                                    | {"accepted_joins": p["proposal_audit"]["selected_joins"]}
                                    for p in branch["passes"]
                                ],
                            }
                        )
                    receipt.update(
                        bootstrap_seconds=audit["seconds"],
                        selected_branch=audit["selected_branch"],
                        branches=branches,
                        catalogue_numbers=data["catalogue_numbers"],
                        seed_vector=data["seed"]["vector"],
                        fits=data["fits"],
                    )
                results.append(receipt)
    comparisons = []
    for case in protocol["cases"]:
        for calibration in case["calibrations"]:
            for proposal in ("original", "joined"):
                pair = [
                    next(
                        r
                        for r in results
                        if r["case"]["session_id"] == case["session_id"]
                        and r["calibration"] == calibration
                        and r["mode"] == proposal + "-" + arm
                    )
                    for arm in ("control", "conditioned")
                ]
                control, conditioned = pair
                comparison = {
                    "dataset": case["dataset"],
                    "session_id": case["session_id"],
                    "calibration": calibration,
                    "proposal": proposal,
                    "complete": all(r["status"] == "complete" for r in pair),
                }
                if comparison["complete"]:
                    costs = [
                        r["branches"][r["selected_branch"]]["original_support_score"] for r in pair
                    ]
                    choose = 1 if costs[1] < costs[0] - 1e-9 else 0
                    comparison.update(
                        same_bank=control["catalogue_numbers"] == conditioned["catalogue_numbers"],
                        coherence_costs=costs,
                        coherence_change=costs[1] - costs[0],
                        retrospective_incumbent_choice=("conditioned" if choose else "control"),
                        fits={
                            arm: {
                                "control": control["fits"][arm],
                                "conditioned": conditioned["fits"][arm],
                                "both_stationary": all(r["fits"][arm]["converged"] for r in pair),
                                "objective_change": conditioned["fits"][arm]["objective"]
                                - control["fits"][arm]["objective"],
                                "incumbent_selected": pair[choose]["fits"][arm],
                            }
                            for arm in ("fitted-c", "zero-c")
                        },
                    )
                comparisons.append(comparison)
    complete = [r for r in results if r["status"] == "complete"]
    for receipt in complete:
        assert set(receipt["fits"]) == {"fitted-c", "zero-c"}
        for fit in receipt["fits"].values():
            np.testing.assert_array_equal(fit["vector"][:2], receipt["case"]["point"])
            assert len(fit["vector"]) == len(receipt["seed_vector"])
        assert abs(receipt["fits"]["zero-c"]["vector"][6]) <= 1e-10
    qualified = [
        f for c in comparisons if c["complete"] for f in c["fits"].values() if f["both_stationary"]
    ]
    same_bank = [
        f
        for c in comparisons
        if c["complete"] and c["same_bank"]
        for f in c["fits"].values()
        if f["both_stationary"]
    ]
    summary = {
        "conditions": len(results),
        "complete_initializers": len(complete),
        "coarse_attempts": sum(len(r["fits"]) for r in complete),
        "stationary_coarse_attempts": sum(
            f["converged"] for r in complete for f in r["fits"].values()
        ),
        "paired_conditions": len(comparisons),
        "coherence_worse_pairs": sum(c.get("coherence_change", 0) > 1e-6 for c in comparisons),
        "retrospective_control_selected": sum(
            c.get("retrospective_incumbent_choice") == "control" for c in comparisons
        ),
        "both_stationary_comparisons": len(qualified),
        "lower_coarse_objective_comparisons": sum(f["objective_change"] < -1e-6 for f in qualified),
        "same_bank_stationary_comparisons": len(same_bank),
        "same_bank_lower_coarse_objective": sum(f["objective_change"] < -1e-6 for f in same_bank),
        "bootstrap_seconds_range": [
            min(r["bootstrap_seconds"] for r in complete),
            max(r["bootstrap_seconds"] for r in complete),
        ],
        "clipped_passes": sum(
            any(p["slope_clipped"]) for r in complete for b in r["branches"] for p in b["passes"]
        ),
        "all_c_pairs_common_bank_seed_point_priors_budget": True,
    }
    write(PUBLIC / "protocol.json", protocol)
    write(PUBLIC / "numerical-seal.json", seal)
    (PUBLIC / "results.json").write_text(
        json.dumps(
            {
                "rows": results,
                "comparisons": comparisons,
                "summary": summary,
                "script_sha256": sha(Path(__file__)),
                "reference_usage": "none",
                "scope": protocol["scope"],
                "retrospective_selection_scope": (
                    "Compare two already computed states using the same original-support coherence "
                    "cost only. Both c arms share selection before inspecting coarse scores. "
                    "This is an offline incumbent audit with common preprocessing work, not an "
                    "executed production initializer or independent validation."
                ),
            },
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    )
    fig, axes = plt.subplots(2, 2, figsize=(15, 9), constrained_layout=True)
    for column, proposal in enumerate(("original", "joined")):
        rows = [c for c in comparisons if c["proposal"] == proposal and c["complete"]]
        positions = np.arange(len(rows))
        labels = [
            (
                c["session_id"].removeprefix("fast-").removeprefix("scan-fw-")[:4]
                + " "
                + c["calibration"]
            )
            for c in rows
        ]
        axes[0, column].bar(
            positions,
            [c["coherence_change"] / 1e6 for c in rows],
            color=["#d85a4a" if c["coherence_change"] > 0 else "#177ca5" for c in rows],
        )
        axes[0, column].set(
            ylabel="Original-support coherence cost change (million)",
            title=proposal.title() + " proposals · lower is better",
        )
        for offset, arm, color in ((-0.18, "fitted-c", "#1679ac"), (0.18, "zero-c", "#d87814")):
            values = [
                c["fits"][arm]["objective_change"] if c["fits"][arm]["both_stationary"] else 0.0
                for c in rows
            ]
            axes[1, column].bar(positions + offset, values, width=0.35, color=color, label=arm)
            for x, c in zip(positions + offset, rows, strict=True):
                if not c["fits"][arm]["both_stationary"]:
                    axes[1, column].plot(x, 0, "kx", markersize=8)
        axes[1, column].set(
            ylabel="Fixed-point coarse objective change",
            title="Cross-bank operational scores; × means no qualified comparison",
        )
        axes[1, column].legend()
        for row in range(2):
            axes[row, column].axhline(0, color="black", lw=0.8)
            axes[row, column].set_xticks(positions, labels, rotation=50, ha="right", fontsize=8)
            axes[row, column].grid(alpha=0.2)
    fig.suptitle(
        "Common-clock conditioning on eight fixed development recordings\n"
        "One data-selected fixed point per scan; no final B7 or position improvement claim"
    )
    fig.savefig(PUBLIC / "coherence-and-coarse-effects.png", dpi=180)
    plt.close(fig)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
