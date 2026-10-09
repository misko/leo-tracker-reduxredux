"""Describe persisted active-face refinement; never evaluate the objective."""

import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    result = json.loads((HERE / "result.json").read_text())
    protocol = json.loads((HERE / "protocol.json").read_text())
    assert result["status"] == "complete"
    assert result["protocol_sha256"] == sha(HERE / "protocol.json")
    for name, expected in protocol["source_sha256"].items():
        assert sha(ROOT / name) == expected, name
    fit = result["fit"]
    prior = json.loads((HERE.parent / "2026_10_09_position_error_iter97/result.json").read_text())
    np.testing.assert_array_equal(fit["initial_vector"], prior["fit"]["vector"])
    np.testing.assert_array_equal(fit["vector"][:2], fit["initial_vector"][:2])
    assert not fit["converged"] and fit["stationarity"] > 0.001
    accepted = fit["accepted"]
    initial_kkt = accepted[0]["before_stationarity"]
    history = [initial_kkt, *[row["after_stationarity"] for row in accepted]]
    last = [
        row for row in fit["trials"] if row["round"] == len(accepted) and row["kind"] == "newton"
    ]
    assert all(
        row["feasible"]
        and row["objective"] < fit["objective"]
        and row["stationarity"] > fit["stationarity"]
        for row in last
    )
    delta = fit["objective"] - fit["initial_objective"]
    summary = {
        "source_hashes_verified": len(protocol["source_sha256"]),
        "protocol_sha256": sha(HERE / "protocol.json"),
        "result_sha256": sha(HERE / "result.json"),
        "initial_kkt": initial_kkt,
        "final_kkt": fit["stationarity"],
        "gate": 0.001,
        "accepted_rounds": len(accepted),
        "evaluations": fit["evaluations"],
        "objective_delta": delta,
        "objective_delta_initial_ulps": delta / abs(np.spacing(fit["initial_objective"])),
        "fixed_position_unchanged": True,
        "all_final_newton_trials_lower_score_but_worse_kkt": True,
        "scope": "Negative qualification result; no downstream position improvement",
    }
    (HERE / "verification.json").write_text(json.dumps(summary, indent=2) + "\n")
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.3), constrained_layout=True)
    axes[0].plot(range(len(history)), history, "o-", color="#4c72b0")
    axes[0].axhline(0.001, color="black", linestyle="--", label="Unchanged gate")
    axes[0].set_xlabel("Accepted refinement rounds")
    axes[0].set_ylabel("Full scaled projected KKT")
    axes[0].set_yscale("log")
    axes[0].legend()
    axes[1].bar(
        ["Retained", *[str(row["damping"]) for row in last]],
        [fit["stationarity"], *[row["stationarity"] for row in last]],
        color=["#55a868", "#c44e52", "#c44e52", "#c44e52"],
    )
    axes[1].axhline(0.001, color="black", linestyle="--")
    axes[1].set_xlabel("Final round: retained state / Newton damping")
    axes[1].set_ylabel("Full scaled projected KKT")
    axes[1].set_title("Lower scores, worse qualification")
    fig.suptitle("ac11: tangent scalar refinement improves KKT but does not qualify")
    fig.savefig(HERE / "qualification.png", dpi=170)
    plt.close(fig)
    table = "\n".join(
        f"| {row['damping']} | {row['objective'] - fit['objective']:.12g} | "
        f"{row['stationarity']:.12g} | Feasible, rejected |"
        for row in last
    )
    (
        HERE / "RESULTS.md"
    ).write_text(f"""# Active-face scalar refinement: improvement without qualification

**The corrected calibration still fails the unchanged 0.001 KKT gate.**
Full projected KKT decreases from {initial_kkt:.12g} to {fit["stationarity"]:.12g}
after four accepted rounds and {fit["evaluations"]} objective/gradient evaluations.
Position stays fixed. The published fitted-c error remains 55.685 km;
association and matched c=0/fitted-c final-position testing have not been unlocked.

![Accepted progress and rejected final proposals](qualification.png)

Unlike iteration97's infeasible single-coordinate Newton steps, this routine
projects the scaled gradient into the nullspace of the active constraint normals.
The persisted rounds have one active normal and a 21-dimensional tangent space.
All accepted steps preserve the physical constraints. This demonstrates that
the earlier scalar-coordinate blockage did not prove an absence of feasible
joint refinement.

The retained objective is {fit["objective"]:.12g}, a change of {delta:.12g}
({summary["objective_delta_initial_ulps"]:.0f} initial-score ULP) from its own
corrected starting objective. The fixed 128-ULP ceiling is unchanged and is never
accumulated across rounds. These tiny score changes establish no frequency-fit
or localization gain.

## Why refinement stopped

The final round's three feasible Newton proposals all lower the objective, but
increase the full infinity-norm projected KKT. The frozen selection policy rejects
them because they do not improve independent qualification.

| Damping | Score delta versus retained state | Full KKT | Outcome |
|---|---:|---:|---|
{table}

This is an algorithmic limitation of scalar curvature along a projected-gradient
direction, not a mathematical impossibility of convergence. A lower objective
need not monotonically improve the largest projected-gradient component.
The receipt does not prove that a coupled reduced-Hessian correction will work;
that requires a separately frozen test. Active-face refinement also cannot release
a wrongly active constraint. Qualification remains the full independent gate,
not reduced tangent stationarity or optimizer success.

## Immutable evidence and scope

All {len(protocol["source_sha256"])} frozen source/input hashes match. The original
iteration97 terminal vector is exactly the iteration99 start; reference positions
do not enter it. Every probe, rejected proposal, gradient and accepted state remains
in [result.json](result.json), with [protocol](protocol.json),
[verification](verification.json) and [artifact hashes](report-integrity.json).

This is a consumed single-scan fitted-c calibration diagnostic, not an independent
validation or matched position-accuracy ablation. Hard60, priors, fixed position,
physical constraints and the qualification threshold remain unchanged. No new
RF collection, production edit or additional model evaluation was used for this report.
""")
    names = [
        "RESULTS.md",
        "qualification.png",
        "verification.json",
        "report.py",
        "protocol.json",
        "result.json",
    ]
    (HERE / "report-integrity.json").write_text(
        json.dumps({name: sha(HERE / name) for name in names}, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
