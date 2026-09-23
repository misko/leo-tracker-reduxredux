"""Verify the budget extension and render the post-seal model comparison."""

import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


root = Path(__file__).parent
reports = root.parent
joint = json.loads((root / "results/results.json").read_text())
old = json.loads((root / "three_cycle_attempt/results/inference.json").read_text())
conditional_path = reports / "2026_09_23_long_full8h_shared_epoch_position/results/results.json"
conditional = json.loads(conditional_path.read_text())
global_path = reports / "2026_09_23_long_global_epoch_position/results/results.json"
global_model = json.loads(global_path.read_text())
baseline_path = reports / "2026_09_23_long_training_full8h_position/results/results.json"
baseline = json.loads(baseline_path.read_text())
rows = []
for arm, previous, fixed in zip(joint["arms"], old["arms"], conditional["arms"], strict=True):
    assert (arm["prior"], arm["scale_s"]) == (previous["prior"], previous["scale_s"])
    assert (arm["prior"], arm["scale_s"]) == (fixed["prior"], fixed["scale_s"])
    assert arm["trace"][:3] == previous["trace"]
    before = {(r["session_id"], r["track_id"]): r["candidate_id"] for r in fixed["fixed_tracks"]}
    after = {(r["session_id"], r["track_id"]): r["candidate_id"] for r in arm["fixed_tracks"]}
    assert before.keys() == after.keys()
    assert len(before) == 3587
    assert all(t["objective_gain_hz"] >= -1e-7 for t in arm["trace"])
    rows.append(
        {
            "prior": arm["prior"],
            "scale_s": arm["scale_s"],
            "latitude_deg": arm["latitude_deg"],
            "longitude_deg": arm["longitude_deg"],
            "first_three_traces_bit_identical": True,
            "track_count": len(before),
            "net_changed_identities": sum(before[key] != after[key] for key in before),
            "cycles": len(arm["trace"]),
            "outer_stop_reason": arm["outer_stop_reason"],
            "conditional_error_km": fixed["reference_error_km"],
            "joint_error_km": arm["reference_error_km"],
            "training_capped800_rmse_hz": arm["training_capped800_rmse_hz"],
            "reserved_capped800_rmse_hz": arm["reserved_capped800_rmse_hz"],
            "objective_gain_from_conditional_hz": fixed["penalized_objective_rmse_hz"]
            - arm["penalized_objective_rmse_hz"],
            "visibility_failure_count": arm["visibility_failure_count"],
        }
    )
summary = {
    "arms": rows,
    "runtime_s": joint["runtime_s"],
    "bindings": {
        "report_tool": digest(Path(__file__)),
        "joint_results": digest(root / "results/results.json"),
        "original_three_cycle_inference": digest(
            root / "three_cycle_attempt/results/inference.json"
        ),
        "conditional_results": digest(conditional_path),
        "global_results": digest(global_path),
        "baseline": digest(baseline_path),
    },
}
(root / "comparison.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
fig, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
for column, prior in enumerate(("sacramento", "reno")):
    for label, model, color in (
        ("Global epoch, fixed IDs", global_model, "C2"),
        ("Scan epochs, fixed IDs", conditional, "C0"),
        ("Scan epochs + reassignment", joint, "C1"),
    ):
        arms = [a for a in model["arms"] if a["prior"] == prior and a.get("scan_count", 72) == 72]
        scales = [a["scale_s"] for a in arms]
        for row, key in enumerate(("reference_error_km", "reserved_capped800_rmse_hz")):
            axes[row, column].plot(scales, [a[key] for a in arms], "o-", color=color, label=label)
    base = next(s["selected"] for s in baseline["searches"] if s["prior"] == prior)
    axes[0, column].axhline(
        base["reference_error_km"], color="gray", linestyle=":", label="Zero-epoch baseline"
    )
    axes[0, column].axhline(0.3, color="red", linestyle="--", label="300 m target")
    axes[0, column].set_ylim(bottom=0)
    axes[0, column].set_title(prior.title())
    axes[1, column].axhline(base["reserved_capped800_rmse_hz"], color="gray", linestyle=":")
    for row in range(2):
        axes[row, column].set_xscale("log")
        axes[row, column].set_xticks([0.2, 1, 5], labels=["0.2", "1", "5"])
        axes[row, column].minorticks_off()
        axes[row, column].grid(alpha=0.25)
        axes[row, column].set_xlabel("Regularization scale (s; different nuisance counts)")
axes[0, 0].set_ylabel("Post-seal position error (km)")
axes[1, 0].set_ylabel("Held-row capped RMS (Hz)")
axes[0, 1].legend(fontsize=8)
fig.suptitle(
    "72 TRAIN scans · shared location, timing and catalogue assignments\n"
    "Same recorded support; no validation/test accuracy claim"
)
fig.savefig(root / "joint_epoch_comparison.png", dpi=160)
