"""Report persisted scalar-polish failure without evaluating the model."""

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
    assert result["protocol_sha256"] == sha(HERE / "protocol.json")
    assert result["status"] == "complete"
    for name, expected in protocol["source_sha256"].items():
        assert sha(ROOT / name) == expected, name
    fit = result["fit"]
    np.testing.assert_array_equal(fit["initial_vector"], fit["vector"])
    assert not fit["converged"] and not fit["accepted"]
    newton = [row for row in fit["trials"] if row["kind"] == "newton"]
    assert len(newton) == 3 and all(not row["feasible"] for row in newton)
    summary = {
        "source_hashes_verified": len(protocol["source_sha256"]),
        "protocol_sha256": sha(HERE / "protocol.json"),
        "result_sha256": sha(HERE / "result.json"),
        "stationarity": fit["stationarity"],
        "unchanged_gate": 0.001,
        "coordinate": 22,
        "raw_gradient": fit["gradient"][22],
        "objective_unchanged": fit["objective"] == fit["initial_objective"],
        "vector_unchanged": True,
        "evaluations": fit["evaluations"],
        "infeasible_newton_trials": len(newton),
        "publication_sequence": "Protocol frozen and pushed at af2c6bb40 before execution",
        "scope": "Negative scalar algorithm result, no downstream position change",
    }
    (HERE / "verification.json").write_text(json.dumps(summary, indent=2) + "\n")
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.4), constrained_layout=True)
    axes[0].bar(
        ["Raw coordinate 22", "Full projected KKT"],
        [abs(fit["gradient"][22]), fit["stationarity"]],
        color=["#dd8452", "#4c72b0"],
    )
    axes[0].set_yscale("log")
    axes[0].axhline(0.001, linestyle="--", color="black", label="Unchanged gate")
    axes[0].set_ylabel("Scaled derivative magnitude")
    axes[0].legend()
    axes[1].bar(
        [str(row["damping"]) for row in newton],
        [-1000 * row["scaled_step"] for row in newton],
        color="#c44e52",
    )
    axes[1].set_xlabel("Frozen Newton damping")
    axes[1].set_ylabel("Negative timing-basis step\nmagnitude (ms)")
    axes[1].set_title("All three steps infeasible")
    fig.suptitle("ac11: scalar polish blocked by coupled timing constraint")
    fig.savefig(HERE / "qualification-failure.png", dpi=170)
    plt.close(fig)
    text = f"""# Scalar refinement fails at the coupled timing boundary

**Iteration97 did not qualify the corrected postfit.** The unchanged independent KKT
is {fit["stationarity"]:.12g}, above the 0.001 gate. The scalar routine accepted no
step, performed {fit["evaluations"]} objective/gradient evaluations, and returned
the exact original vector and objective ({fit["objective"]:.12g}). The published
fitted-c position error remains 55.685 km; no downstream position improvement was established.

![Scalar derivative versus projected KKT and infeasible trials](qualification-failure.png)

The chosen relative-timing basis coordinate is 22. Its raw scaled derivative is
{fit["gradient"][22]:.12g}, while the largest full projected KKT component is only
{fit["stationarity"]:.12g}. An active coupled timing constraint absorbs most of the
raw gradient. Moving this coordinate alone in the negative Newton direction violates
the physical constraint; moving jointly along a feasible tangent may behave differently.

The +1e-5 curvature probe is feasible, but increases the objective by
{fit["trials"][0]["objective"] - fit["objective"]:.12g}; the -1e-5 probe is infeasible.
The forward-gradient curvature estimate is {newton[0]["curvature"]:.12g}.
The frozen full, half and quarter Newton steps are respectively
{", ".join(f"{row['scaled_step']:.12g}" for row in newton)} seconds in this
timing-basis coefficient. All are infeasible and therefore receive no objective evaluation.

This establishes a limitation of **single-coordinate refinement** at a coupled
boundary. It does not prove mathematical impossibility of convergence, an incorrect
physical bound, or that no feasible joint direction improves the objective/KKT.
The independent gate still rejects this endpoint; solver termination alone is not
a convergence certificate. Iteration96's interior scalar rescue remains valid,
but does not generalize to this boundary case without further testing.

## Provenance and scope

All {len(protocol["source_sha256"])} frozen source/input hashes match, including
inherited93/94/95/96 receipts. The protocol was frozen and pushed at `af2c6bb40`
before execution. The source vector is the saved failed95 corrected postfit;
its saved and reconstructed objective agree exactly. Every probe and rejected
step remains in [result.json](result.json). See [verification](verification.json).

This is a fitted-c calibration diagnostic with fixed position, unchanged hard60,
priors, physical constraints, 128-ULP ceiling and qualification gate. It is not a
matched position-accuracy ablation. No reference-guided start, new RF collection,
production change or additional model evaluation was used to create this report.
"""
    (HERE / "RESULTS.md").write_text(text)
    names = [
        "RESULTS.md",
        "qualification-failure.png",
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
