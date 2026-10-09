"""Describe frozen numerical qualification; no objective evaluation or fit."""

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
    plan = json.loads((HERE / "protocol.json").read_text())
    assert result["status"] == "complete" and result["protocol_sha256"] == sha(
        HERE / "protocol.json"
    )
    for name, expected in plan["source_sha256"].items():
        assert sha(ROOT / name) == expected, name
    prior = HERE.parent / "2026_10_09_position_error_iter94"
    old = json.loads((prior / "result.json").read_text())
    fit, old_fit = result["fit"], old["fit"]
    np.testing.assert_array_equal(fit["initial_vector"], old_fit["vector"])
    np.testing.assert_array_equal(fit["vector"][:2], fit["initial_vector"][:2])
    assert fit["converged"] and fit["stationarity"] <= 0.001
    assert fit["objective"] <= fit["objective_ceiling"]
    original_receipts = {}
    verification93 = json.loads(
        (
            HERE.parent / "2026_10_09_position_error_iter93/prefit-report-verification.json"
        ).read_text()
    )
    for name, expected in verification93["original_receipt_sha256"].items():
        path = HERE.parent / "2026_10_09_position_error_iter93" / name
        assert sha(path) == expected, name
        original_receipts[str(path.relative_to(ROOT))] = expected
    original_receipts[str((prior / "result.json").relative_to(ROOT))] = sha(prior / "result.json")
    for parent, name in (("93", "prefit-protocol.json"), ("94", "protocol.json")):
        path = HERE.parent / f"2026_10_09_position_error_iter{parent}" / name
        for file, expected in json.loads(path.read_text())["source_sha256"].items():
            assert sha(ROOT / file) == expected, file
    ulp = float(abs(np.spacing(fit["initial_objective"])))
    delta = fit["objective"] - fit["initial_objective"]
    chosen = fit["accepted"][0]
    trial = fit["trials"][chosen["trial_index"]]
    predicted = trial["raw_scaled_derivative"] ** 2 / (2 * trial["curvature"])
    changed = np.flatnonzero(np.asarray(fit["vector"]) - np.asarray(fit["initial_vector"]))
    assert changed.tolist() == [20]
    audit = result["gradient_audit"]
    assert audit["stationarity"] == fit["stationarity"]
    summary = dict(
        source_hashes_verified=len(plan["source_sha256"]),
        original_receipt_sha256=original_receipts,
        protocol_sha256=sha(HERE / "protocol.json"),
        result_sha256=sha(HERE / "result.json"),
        before_kkt=old_fit["stationarity"],
        after_kkt=fit["stationarity"],
        unchanged_gate=0.001,
        objective_delta=delta,
        objective_delta_ulps=delta / ulp,
        ulp=ulp,
        objective_tolerance_ulps=128,
        predicted_improvement=predicted,
        predicted_improvement_ulps=predicted / ulp,
        changed_coordinate=20,
        changed_basis_coefficient_s=trial["scaled_step"],
        position_unchanged=True,
        evaluations=fit["evaluations"],
        rounds=fit["rounds"],
        elapsed_s=result["elapsed_s"],
        publication_sequence="Local protocol commit db56090b2 before execution; "
        "initial remote push "
        "rejected by concurrent web work; merged 3b0a8c409 and pushed after execution. "
        "No claim of remote prepublication.",
        scope="Numerical prefit qualification only; no downstream position gain established",
    )
    (HERE / "verification.json").write_text(json.dumps(summary, indent=2) + "\n")
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.5), constrained_layout=True)
    axes[0].bar(
        ["Before", "After"],
        [old_fit["stationarity"], fit["stationarity"]],
        color=["#dd8452", "#55a868"],
    )
    axes[0].axhline(0.001, color="black", linestyle="--", label="Unchanged gate")
    axes[0].set(ylabel="Full scaled projected KKT", title="Numerical qualification")
    axes[0].legend(fontsize=8)
    axes[1].bar(
        ["Measured Δscore", "Fixed allowance"], [delta / ulp, 128], color=["#4c72b0", "#cccccc"]
    )
    axes[1].set(ylabel="ULP of initial objective", title="6 ULP change within fixed128 ULP")
    newton = [t for t in fit["trials"] if t["kind"] == "newton"]
    axes[2].scatter(
        [t["scaled_step"] * 1e9 for t in newton],
        [t["stationarity"] for t in newton],
        color="#4c72b0",
    )
    axes[2].scatter(
        [trial["scaled_step"] * 1e9],
        [fit["stationarity"]],
        color="#55a868",
        marker="*",
        s=150,
        label="Selected",
    )
    axes[2].axhline(0.001, color="black", linestyle="--")
    axes[2].set(
        xlabel="Timing-basis coefficient step (ns)",
        ylabel="Full KKT",
        title="Frozen Newton damping trials",
    )
    axes[2].legend(fontsize=8)
    fig.suptitle("ac11: prefit rescued numerically; fixed position unchanged")
    fig.savefig(HERE / "qualification.png", dpi=170)
    plt.close(fig)
    lines = [
        "# Curvature-aware qualification of the lost ordinary region",
        "",
        "**The ordinary failed calibration prefit now qualifies under the unchanged "
        "0.001 stationarity gate.** Full scaled projected KKT falls from "
        f"{old_fit['stationarity']:.12g} to {fit['stationarity']:.12g}, after one round "
        "and six exact objective/gradient evaluations. This does not yet establish a "
        "better final position; the prefit holds position fixed.",
        "",
        "![Qualification, roundoff-sized score change and timing step](qualification.png)",
        "",
        "| Quantity | Before | After |",
        "|---|---:|---:|",
        f"| Exact objective | {fit['initial_objective']:.15g} | {fit['objective']:.15g} |",
        f"| Full KKT | {old_fit['stationarity']:.12g} | {fit['stationarity']:.12g} |",
        "| Qualification gate | 0.001 | 0.001 |",
        "| Horizontal prefit position | Fixed ordinary region | Identical |",
        "",
        "The selected coordinate is 20, relative-timing basis coefficient 12, with a "
        f"step of **{trial['scaled_step']:.12g} s** ({trial['scaled_step'] * 1e9:.6f} ns). "
        "This is a zero-sum basis coefficient, not an independently measured satellite "
        "clock. It changes no position coordinate, candidate bank, RF prior or timing prior.",
        "",
        f"Central gradient probes at ±1e-5 estimate curvature {trial['curvature']:.12g}. "
        f"The predicted scalar score benefit is {predicted:.12g}, only {predicted / ulp:.3f} ULP. "
        f"The measured score instead rises by {delta:.12g}, **{delta / ulp:.0f} ULP**, "
        "consistent with a change below useful score resolution. The globally frozen "
        f"allowance is 128 initial-score ULP ({fit['objective_tolerance']:.12g}). "
        "It is a fixed total ceiling, not a per-step allowance or a relaxed KKT threshold.",
        "",
        "## Gradient evidence and limits",
        "",
        "The algorithm compares full independent KKT over all free coordinates, not "
        "only the stepped coordinate. The independently repeated final audit agrees "
        f"at {audit['stationarity']:.12g}. Its largest remaining component is coordinate "
        f"{audit['coordinate']} ({audit['coordinate_name']}), with scaled raw/projected "
        f"gradient {audit['scaled_raw_gradient']:.12g}. Full returned gradient vectors "
        "and every probe/trial remain in [result.json](result.json).",
        "",
        "| Central scaled step | Objective finite-difference derivative |",
        "|---:|---:|",
    ]
    for check in audit["finite_difference_checks"]:
        lines.append(f"| {check['scaled_step']:.8g} | {check['derivative']:.12g} |")
    lines += [
        "",
        "These checks cover the worst remaining coordinate, not every derivative. "
        "The 1e-5 derivative is close to the analytic gradient; larger-step nonlinearity "
        "and smaller-step objective cancellation limit the finite-difference comparison. "
        "Qualification is proven under the existing numerical gate, not as a global "
        "minimum or complete proof of every gradient implementation.",
        "",
        "## Frozen provenance and publication sequence",
        "",
        f"All **{len(plan['source_sha256'])}** frozen source/input hashes still match. "
        "The original 93 prefit receipt hashes and 94 numerical result are unchanged; "
        "their inherited executable closures also match. This includes the original "
        "failed trials, which are preserved rather than rewritten as successes.",
        "",
        "Protocol and executable sources were committed locally at `db56090b2` before "
        "execution. The first remote push was rejected because concurrent web work "
        "advanced main. After execution, that web commit `3b0a8c409` was merged and "
        "the frozen preparation was pushed. **This is local pre-execution freezing, "
        "not remote prepublication.** The merge did not change the pinned scientific "
        "sources. [Protocol](protocol.json) and [verification](verification.json) "
        "record the source and receipt hashes.",
        "",
        "A separately frozen calibration/association/final-fit continuation is needed "
        "to establish whether retaining this ordinary region improves the published "
        "55.685 km fitted-c failure. No reference-guided seed or score selection, "
        "reserve access, new RF collection or production change occurred.",
    ]
    (HERE / "RESULTS.md").write_text("\n".join(lines) + "\n")
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
