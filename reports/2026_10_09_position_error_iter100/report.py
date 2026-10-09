"""Arithmetic and visualization of saved Newton qualification, without evaluation."""
# ruff: noqa: E501

import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def read(number):
    return json.loads(
        (HERE.parent / f"2026_10_09_position_error_iter{number}/result.json").read_text()
    )


def main():
    result, original, scalar = read(100), read(95), read(99)
    fitted = result["fit"]
    assert result["status"] == "complete" and fitted["converged"]
    assert fitted["stationarity"] <= 0.001
    plan = json.loads((HERE / "protocol.json").read_text())
    verified = {}
    for name, expected in plan["source_sha256"].items():
        actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        assert actual == expected, name
        verified[name] = actual
    assert (
        result["protocol_sha256"]
        == hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
    )
    np.testing.assert_array_equal(fitted["initial_vector"], scalar["fit"]["vector"])
    np.testing.assert_array_equal(
        np.asarray(fitted["vector"])[:2], np.asarray(fitted["initial_vector"])[:2]
    )
    assert fitted["objective"] <= fitted["objective_ceiling"]
    assert all(row["feasible"] for row in fitted["trials"] if row["evaluated"])
    audit = fitted["curvature_audits"][0]
    hessian = np.asarray(audit["hessian"])
    eigenvalues = np.asarray(audit["eigenvalues"])
    np.testing.assert_allclose(np.linalg.eigvalsh(hessian), eigenvalues, rtol=1e-11, atol=1e-8)
    assert eigenvalues.min() > audit["positive_definite_threshold"]
    deltas = np.asarray(fitted["vector"]) - np.asarray(fitted["initial_vector"])
    postfit95 = original["calibration"]["result"]["postfit"]
    summary = dict(
        scope="Stored-receipt arithmetic only; no objective evaluation, refit or reference-coordinate access",
        objective=fitted["objective"],
        initial_objective=fitted["initial_objective"],
        objective_change=fitted["objective"] - fitted["initial_objective"],
        initial_stationarity=scalar["fit"]["stationarity"],
        final_stationarity=fitted["stationarity"],
        evaluations=fitted["evaluations"],
        rounds=fitted["rounds"],
        elapsed_s=result["elapsed_s"],
        physical_constraints_minimum=fitted["physical_constraints_minimum"],
        active_rank=audit["active_rank"],
        tangent_dimension=audit["tangent_dimension"],
        eigenvalue_min=float(eigenvalues.min()),
        eigenvalue_max=float(eigenvalues.max()),
        hessian_condition=float(eigenvalues.max() / eigenvalues.min()),
        hessian_asymmetry_max=audit["asymmetry_max"],
        hessian_asymmetry_relative_max=float(audit["asymmetry_max"] / np.max(abs(hessian))),
        timing_basis_max_change_s=float(np.max(abs(deltas[7:]))),
        largest_physical_parameter_change=float(np.max(abs(deltas))),
        saved95_support=postfit95["signal_windows"],
        saved95_rms_hz=postfit95["posterior_rms_hz"],
        qualified100_support="Not persisted or recomputed in this no-evaluation report",
        candidate_count=len(result["input_verification"]["satellite_indices"]),
        position_change_km=deltas[:2].tolist(),
        source_closure_verified=len(verified),
        result_sha256=hashlib.sha256((HERE / "result.json").read_bytes()).hexdigest(),
        report_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    )
    (HERE / "verification.json").write_text(json.dumps(summary, indent=2) + "\n")
    figure, axes = plt.subplots(1, 2, figsize=(10.5, 4.2), constrained_layout=True)
    values = [
        postfit95["stationarity"],
        read(97)["fit"]["stationarity"],
        scalar["fit"]["stationarity"],
        fitted["stationarity"],
    ]
    axes[0].plot(
        ["95 postfit", "97 coordinate", "99 tangent", "100 Newton"], values, "o-", color="#247F87"
    )
    axes[0].set_yscale("log")
    axes[0].axhline(0.001, color="#777777", linestyle="--", label="Unchanged qualification gate")
    axes[0].set_ylabel("Full independent stationarity residual")
    axes[0].set_title("Joint curvature qualifies the fixed-position fit")
    axes[0].legend(fontsize=8)
    axes[1].semilogy(np.arange(1, len(eigenvalues) + 1), eigenvalues, "o-", color="#AE7835")
    axes[1].set_xlabel("Reduced-Hessian eigenmode (sorted)")
    axes[1].set_ylabel("Curvature in scaled tangent coordinates")
    axes[1].set_title(f"Positive definite; condition≈{summary['hessian_condition']:,.0f}")
    for axis in axes:
        axis.grid(alpha=0.15)
        axis.spines[["top", "right"]].set_visible(False)
    figure.suptitle("ac11 calibration recovery — localization remains untested")
    figure.savefig(HERE / "qualification.png", dpi=160)
    plt.close(figure)
    lines = [
        "# Iteration100: corrected calibration postfit now qualifies",
        "",
        "The reduced-Hessian Newton polish qualified the saved failed postfit without changing the position, model, priors, physical constraints or 0.001 stationarity requirement. This recovers the calibration prerequisite; **it does not yet establish a better position**.",
        "",
        "![Qualification and reduced curvature](qualification.png)",
        "",
        "| Quantity | Saved99 start | Qualified100 |",
        "|---|---:|---:|",
        f"| Objective, same corrected model | {fitted['initial_objective']:.12f} | {fitted['objective']:.12f} |",
        f"| Full scaled KKT residual | {scalar['fit']['stationarity']:.10g} | {fitted['stationarity']:.10g} |",
        "| Fixed regional position | (−47.5,−62.5)km | Unchanged |",
        "",
        f"One accepted Newton round used **{fitted['evaluations']} evaluations**: initial evaluation, 42 central gradient probes for 21 tangent coordinates, and three damped trials. The objective decreased by {abs(summary['objective_change']):.9g}; no score increase was needed. The initial 128 ULP ceiling and full qualification gate remained enforced.",
        "",
        "## Why this succeeded",
        "",
        "The earlier coordinate step tried to leave an active coupled timing constraint. Scalar tangent steps stayed feasible and improved the fit, but did not resolve all coupled residual directions. The 21-dimensional reduced Hessian accounts for those couplings simultaneously while remaining on the same active face.",
        "",
        f"Its eigenvalues range from **{summary['eigenvalue_min']:.6f}** to **{summary['eigenvalue_max']:.6f}**, giving condition number **{summary['hessian_condition']:.2f}**. Every eigenvalue exceeds the numerical positive-definite threshold {audit['positive_definite_threshold']:.6g}; no ridge or eigenvalue clipping was used. Maximum pre-symmetrization disagreement is {summary['hessian_asymmetry_max']:.6g}, or {summary['hessian_asymmetry_relative_max']:.6g} of the largest Hessian entry. This supports numerical consistency of this local calculation, not a global-optimum claim.",
        "",
        f"The active normal has rank 1. Minimum physical constraint slack after the step is {summary['physical_constraints_minimum']:.6g}. Maximum timing-basis coordinate movement is {summary['timing_basis_max_change_s']:.6g}s; this is a basis-coordinate change, not an individual satellite or receiver clock correction.",
        "",
        "## Support, c coverage and remaining test",
        "",
        f"The model retains {summary['candidate_count']} candidates and the same observations. The saved iteration95 starting postfit had effective signal support {summary['saved95_support']:.6f} and posterior RMS {summary['saved95_rms_hz']:.6f}Hz. The iteration100 solver did not persist refreshed support/RMS, so this read-only report does not claim those quantities remained numerically identical or recompute them.",
        "",
        "This remains shared fitted-c calibration. Neither c arm has a new regional final or B7 position, and no fresh ordinary-only B7 parity measurement exists yet. Separately frozen iteration98 must carry the qualified calibration through association, both c finals, the unchanged regional winner policy and baseline/candidate B7 replays. Only that comparison can establish whether the user's 55.7km fitted-c failure improves.",
        "",
        f"Verified {len(verified)} frozen source/input hashes, receipt protocol binding, exact saved99 initial vector, unchanged position, feasible evaluated trials, objective ceiling and recorded Hessian eigenvalues. No model evaluation or fit was run to produce this report. This consumed single case is not cohort or independent validation.",
        "",
        "Sources: [protocol](protocol.json), [result and all trials](result.json), [verification](verification.json), [iteration99](../2026_10_09_position_error_iter99/README.md).",
    ]
    (HERE / "RESULTS.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
