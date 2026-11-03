"""Summarize known-site releases and local downhill certificates without global claims."""

from __future__ import annotations

import json

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, snapshot_files
from prepare_scans import ROOT
from truth_start_diagnostic import VARIANTS


def local_descent_verified(audit):
    analytic = np.asarray(audit["gradient_per_km"])
    numerical = np.asarray(audit["central_difference_gradient_per_km"])
    agrees = bool(np.allclose(analytic, numerical, rtol=1e-3, atol=1e-3))
    decreases = any(row["step_m"] <= 1 and row["loss_change"] < -1e-6
                    for row in audit["fixed_nuisance_downhill_steps"])
    return agrees and decreases


def evaluate():
    output = ROOT / "truth-start-comparison.json"
    if output.exists():
        raise FileExistsError(output)
    sessions = json.loads((ROOT / "protocol-soft.json").read_text())["sessions"]
    paths = [ROOT / "truth-start-diagnostic" / f"{session}-{variant}.json"
             for variant in VARIANTS for session in sessions]
    if not all(path.exists() for path in paths):
        raise ValueError("all six restart fits must be finished")
    hashes = snapshot_files([__file__, *paths])
    records = [json.loads(path.read_text()) for path in paths]
    rows = []
    for record in records:
        assert_snapshot_unchanged(record["source_hashes"])
        audit = record["start_audit"]
        fit = record["fit"]
        rows.append({
            "session": record["session"], "variant": record["variant"],
            "final_error_km": record["final_error_km"], "success": fit["success"],
            "final_objective": fit["objective"], "truth_objective": audit["objective"],
            "loss_decrease": record["loss_decrease_from_truth"],
            "distance_to_previous_solution_km": record["distance_to_previous_solution_km"],
            "position_gradient_at_truth": audit["gradient_per_km"],
            "finite_difference_gradient_at_truth": audit["central_difference_gradient_per_km"],
            "downhill_steps": audit["fixed_nuisance_downhill_steps"],
            "local_descent_verified": local_descent_verified(audit),
            "nuisance_profile_success": record["nuisance_profile_phases"][-1]["success"],
            "final_projected_gradient_norm": fit["projected_gradient_inf_norm"],
            "release_elapsed_s": fit["elapsed_s"],
        })
    assert_snapshot_unchanged(hashes)
    result = {"schema": "ds13-truth-start-comparison/v1", "rows": rows,
              "source_hashes": hashes,
              "scope": "Known-position diagnostic, no independent validation. A verified descent "
                       "excludes local/global optimality of that complete joint state, but does "
                       "not exclude every possible nuisance basin at the same location or "
                       "certify global optimality of the returned displaced solutions."}
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    return result, records


def plot(result, records):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    sessions = list(dict.fromkeys(row["session"] for row in result["rows"]))
    figure, axes = plt.subplots(2, 2, figsize=(12, 10))
    colors = {"baseline-profiled": "C0", "baseline-seed": "C1", "common-rf-profiled": "C2"}
    for column, session in enumerate(sessions):
        axes[0, column].scatter(0, 0, marker="*", s=170, color="black", label="True start")
        for record in records:
            if record["session"] != session:
                continue
            variant = record["variant"]
            trace = record["fit"]["trace"]
            positions = np.asarray([row["position_km"] for row in trace])
            displacement = positions - np.asarray(record["true_position_km"])
            label = f"{variant}: {record['final_error_km']:.2f} km"
            axes[0, column].plot(displacement[:, 0], displacement[:, 1],
                                 color=colors[variant], label=label)
            axes[0, column].scatter(*displacement[-1], color=colors[variant], marker="s")
            axes[1, column].plot(
                [row["elapsed_s"] for row in trace],
                [row["objective"] - record["start_audit"]["objective"] for row in trace],
                color=colors[variant], label=variant)
        axes[0, column].set_title(session)
        axes[0, column].set_aspect("equal", adjustable="datalim")
        axes[0, column].set_xlabel("East displacement from truth (km)")
        axes[1, column].set_xlabel("Seconds after releasing position")
        axes[1, column].axhline(0, color="gray", linestyle=":")
        for axis in axes[:, column]:
            axis.grid(alpha=0.25)
            axis.legend(fontsize=8)
    axes[0, 0].set_ylabel("North displacement from truth (km)")
    axes[1, 0].set_ylabel("Objective change from true-position start (lower is better)")
    figure.suptitle("Known-position restarts: does optimization stay at the true location?")
    figure.tight_layout()
    figure.savefig(ROOT / "truth-start-paths.png", dpi=150)
    figure.savefig(ROOT / "truth-start-paths.svg")
    plt.close(figure)


if __name__ == "__main__":
    result, records = evaluate()
    plot(result, records)
    for row in result["rows"]:
        print(json.dumps(row), flush=True)
