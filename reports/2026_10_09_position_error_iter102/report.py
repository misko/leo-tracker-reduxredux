"""Persisted direct qualification report; no model evaluation."""
# ruff: noqa: E501

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
    for name, digest in protocol["source_sha256"].items():
        assert sha(ROOT / name) == digest, name
    rows = []
    for stage, attempt in result["attempts"].items():
        fit = attempt["fit"]
        assert attempt["qualified"] and fit["converged"] and fit["stationarity"] <= 0.001
        assert attempt["objective_verified"] and fit["objective"] <= fit["objective_ceiling"]
        np.testing.assert_array_equal(attempt["original_vector"], fit["initial_vector"])
        np.testing.assert_array_equal(fit["initial_vector"][:2], fit["vector"][:2])
        rows.append(
            dict(
                stage=stage,
                final_kkt=fit["stationarity"],
                initial_kkt=fit["accepted"][0]["before_stationarity"],
                evaluations=fit["evaluations"],
                rounds=fit["rounds"],
                polish_s=attempt["polish_elapsed_s"],
                reconstruction_s=attempt["reconstruction_elapsed_s"],
                objective_delta=fit["objective"] - fit["initial_objective"],
            )
        )
    summary = dict(
        rows=rows,
        verified_hashes=len(protocol["source_sha256"]),
        protocol_sha256=sha(HERE / "protocol.json"),
        result_sha256=sha(HERE / "result.json"),
        position_scope="No new position",
    )
    (HERE / "verification.json").write_text(json.dumps(summary, indent=2) + "\n")
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.4), constrained_layout=True)
    x = np.arange(len(rows))
    axes[0].bar(x - 0.18, [r["initial_kkt"] for r in rows], 0.36, label="Saved endpoint")
    axes[0].bar(x + 0.18, [r["final_kkt"] for r in rows], 0.36, label="Direct reduced Newton")
    axes[0].set_yscale("log")
    axes[0].axhline(0.001, color="black", linestyle="--", label="Unchanged gate")
    axes[0].set_ylabel("Full projected KKT")
    axes[0].legend(fontsize=7)
    axes[1].bar(x - 0.18, [r["reconstruction_s"] for r in rows], 0.36, label="Reconstruction")
    axes[1].bar(x + 0.18, [r["polish_s"] for r in rows], 0.36, label="Qualification polish")
    axes[1].set_yscale("log")
    axes[1].set_ylabel("Measured elapsed seconds")
    axes[1].legend(fontsize=7)
    for axis in axes:
        axis.set_xticks(x, ["Prefit", "Corrected postfit"])
    fig.suptitle("ac11: both saved endpoints qualify directly; position unchanged")
    fig.savefig(HERE / "qualification.png", dpi=170)
    plt.close(fig)
    lines = [
        "# Direct qualification of two saved calibration endpoints",
        "",
        "**Both saved endpoints qualify in one reduced-Hessian round and 46 evaluations each.**",
        "The full independent 0.001 gate, hard60, priors, fixed hypothesis position and",
        "initial-objective 128-ULP ceiling remain unchanged. No new final position was produced.",
        "",
        "![Qualification and separate reconstruction cost](qualification.png)",
        "",
        "| Endpoint | Initial KKT | Final KKT | Evaluations | Polish s | Reconstruction s | Score delta |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['stage']} | {row['initial_kkt']:.9g} | {row['final_kkt']:.9g} | "
            f"{row['evaluations']} | {row['polish_s']:.4f} | "
            f"{row['reconstruction_s']:.4f} | {row['objective_delta']:.12g} |"
        )
    lines += [
        "",
        "The polish timing excludes reconstruction. These timings describe two consumed",
        "single-scan saved endpoints, not whole-pipeline overhead or a fleet runtime guarantee.",
        "All returned position coordinates exactly equal their initial coordinates.",
        "",
        "## Conditional scope",
        "",
        "The prefit attempt starts directly from the original ordinary coarse receipt.",
        "The postfit attempt starts directly from the saved iteration95 corrected endpoint,",
        "whose receiver correction was built from iteration96's qualified prefit.",
        "Neither attempt chains iteration99's tangent-gradient refinements. Nevertheless,",
        "this is not yet an end-to-end test that builds the correction from the newly",
        "directly qualified prefit and independently qualifies its ensuing postfit.",
        "That complete path requires a separately frozen experiment.",
        "",
        "These results support a cheaper direct numerical qualification path at the tested",
        "states. They establish no additional positioning gain, RF interpretation or independent",
        "validation. Iteration98's matched position rescue remains a separate conditional result.",
        "No reference-guided seed, per-scan threshold, new RF collection or production edit occurred.",
        "",
        f"All {summary['verified_hashes']} frozen source/input hashes match.",
        "Protocol preparation was published at `38fc8678d` before execution.",
        "Every numerical trial remains in [result.json](result.json); see [verification](verification.json)",
        "and [artifact hashes](report-integrity.json). This report reads persisted receipts only.",
    ]
    (HERE / "RESULTS.md").write_text("\n".join(lines) + "\n")
    names = [
        "report.py",
        "RESULTS.md",
        "verification.json",
        "qualification.png",
        "protocol.json",
        "result.json",
    ]
    (HERE / "report-integrity.json").write_text(
        json.dumps({n: sha(HERE / n) for n in names}, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
