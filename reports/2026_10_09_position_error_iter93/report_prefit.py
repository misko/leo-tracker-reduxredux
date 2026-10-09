"""Describe immutable four-prefit receipts, retaining post-fit audit failures."""

import hashlib
import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    protocol_path = HERE / "prefit-protocol.json"
    plan = json.loads(protocol_path.read_bytes())
    digest = sha(protocol_path)
    for name, expected in plan["source_sha256"].items():
        assert sha(ROOT / name) == expected, name
    inputs = json.loads((HERE / "prefit-input-verification.json").read_bytes())
    assert inputs["protocol_sha256"] == digest
    assert abs(inputs["reconstructed_objective"] - inputs["original_objective"]) <= 1e-6
    rows, hashes = [], {}
    for start in plan["starts"]:
        for solver in plan["solvers"]:
            path = HERE / "prefit-attempts" / f"{start}-{solver}.json"
            record = json.loads(path.read_bytes())
            assert record["protocol_sha256"] == digest
            assert (record["start"], record["solver"]) == (start, solver)
            assert record["fit"]["vector"][:2] == record["initial_vector"][:2]
            rows.append(record)
            hashes[str(path.relative_to(HERE))] = sha(path)
    statuses = Counter(r["status"] for r in rows)
    labels = [
        r["start"].replace("ordinary-coarse", "Ordinary").replace("zero-timing", "Zero timing")
        + "\n"
        + r["solver"]
        for r in rows
    ]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), constrained_layout=True)
    colors = ["#197278" if r["fit"]["converged"] else "#b24b35" for r in rows]
    axes[0].bar(labels, [r["fit"]["stationarity"] for r in rows], color=colors)
    axes[0].axhline(
        plan["stationarity_threshold"], color="black", linestyle="--", label="Acceptance threshold"
    )
    axes[0].set_yscale("log")
    axes[0].set_ylabel("Independent projected-gradient stationarity")
    axes[0].legend(fontsize=8)
    baseline = inputs["original_objective"]
    axes[1].bar(labels, [r["fit"]["objective"] - baseline for r in rows], color=colors)
    axes[1].set_ylabel("Objective above coarse state\n(lower is better)")
    for ax in axes:
        ax.tick_params(axis="x", labelsize=8)
    fig.suptitle("Fixed-position prefits: numerical qualification is not a rescued position")
    fig.savefig(HERE / "prefit-comparison.png", dpi=180)
    plt.close(fig)
    lines = [
        "# Four-prefit replay: calibration failure remains unresolved",
        "",
        "**Both ordinary-start prefits stop immediately without meeting independent "
        "stationarity. Zeroing timing produces qualified prefits with substantially worse "
        "objectives. No final position rescue has been demonstrated.**",
        "",
        "Four numerical fitter calls returned and all immutable receipts exist. "
        f"Driver statuses are `{dict(statuses)}`: both bounded receipts report a post-fit "
        "instrumentation failure, "
        "`AttributeError: PositionFit has no attribute get`, "
        "when the driver treats the typed terminal fit as a mapping. Their numerical fit "
        "and returned-state gradient audit were already preserved; terminal finite-difference "
        "audits are missing. This driver defect is explicit and is not an optimizer failure "
        "or permission to rewrite original receipts.",
        "",
        "![Four fixed-position prefit comparisons](prefit-comparison.png)",
        "",
        "| Start | Solver | Driver | Numerically qualified | Objective | Stationarity | "
        "Evaluations | Seconds | Posterior RMS Hz | Signal windows |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        fit = row["fit"]
        lines.append(
            f"| {row['start']} | {row['solver']} | {row['status']} | {fit['converged']} | "
            f"{fit['objective']:.6f} | {fit['stationarity']:.9f} | {fit['evaluations']} | "
            f"{fit['elapsed_s']:.3f} | {fit['posterior_rms_hz']:.3f} | "
            f"{fit['signal_windows']:.3f} |"
        )
    lines += [
        "",
        "## What this establishes",
        "",
        "The causal bank/order and input bindings reproduce the original coarse objective "
        f"exactly at reconstruction: `{inputs['original_objective']:.12f}`. All frozen "
        "source hashes match. The saved shared coarse stationarity was0.001535439; "
        "both ordinary-start replay returns are approximately0.001527615, still above "
        "the unchanged0.001 threshold. Both report optimizer success but evaluate only "
        "one feasible state; bounded reports five optimizer iterations. Neither uses "
        "the20-second allowance. More elapsed-time budget alone cannot force continued "
        "optimization after that termination.",
        "",
        "The largest returned projected-gradient coordinate is relative timing basis12 "
        "(vector coordinate20). It is also the largest raw scaled coordinate; one active "
        "constraint is recorded, but projecting it does not remove this residual component. "
        "Both returned vectors are feasible. Tight-step central differences at1e-5 and1e-6 "
        "are around+0.00151 and support a remaining derivative above the acceptance "
        "threshold. At1e-4 the sign reverses to about−0.00126. That step sensitivity limits "
        "claims of smooth local behavior and deserves a separate objective/constraint "
        "continuation diagnostic; these checks alone do not identify its numerical cause.",
        "",
        "Zero-timing starts converge below threshold, but their objectives are roughly "
        "7278–7295 higher, with only374–385 signal windows versus2067 for the ordinary "
        "state. A lower posterior RMS in one return does not overturn the matched model "
        "score. This is a different, poorer prefit basin, not proof of useful calibration "
        "recovery. No sampled position changed in any attempt.",
        "",
        "## Root-cause scope and next gate",
        "",
        "The existing path sampled an ordinary rank-one retained region at5km spacing "
        "and discarded it after calibration prefit failure in all three separation passes. "
        "Recovery eligibility collected failed points only at40km spacing, leaving this "
        "retained5km failure without bounded calibration recovery. That coverage gap is "
        "confirmed independently of position error. The replay now shows that simply "
        "using the existing bounded fitter from the same state also remains unqualified; "
        "expanding eligibility alone is not a demonstrated numerical cure.",
        "",
        "The published final B7 state converged in both arms; its approximately55.685km "
        "fitted-c and53.945km c0 errors remain the current result. The original calibration "
        "exception retained no retry terminal vector, so exact historical retry behavior "
        "cannot be recovered from this replay. Independent stationarity rejection is "
        "appropriate under the current policy; neither relaxing its threshold nor selecting "
        "the omitted region using reference error is justified by these receipts.",
        "",
        "Any continuation must be separately frozen, preserve original attempts, use "
        "the ordinary score-selected hypothesis and unchanged stationarity/prior/bounds, "
        "and retain a derivative/feasibility audit. A calibrated region still requires "
        "matched c0/fitted-c downstream association and final fitting with model-only "
        "winner selection before position improvement can be measured. These four prefits "
        "are fitted-c/shared calibration scope, not a full c ablation. Production remains "
        "unchanged and reserves remain closed.",
        "",
        "[Receipt hashes and verification](prefit-report-verification.json); "
        "[frozen replay policy](prefit-protocol.json); "
        "[confirmed calibration path](CALIBRATION_PATH.md).",
    ]
    (HERE / "PREFIT_RESULTS.md").write_text("\n".join(lines) + "\n")
    verification = dict(
        protocol_sha256=digest,
        source_hashes_verified=len(plan["source_sha256"]),
        reconstruction_objective_delta=inputs["reconstructed_objective"]
        - inputs["original_objective"],
        attempts=4,
        numerical_returns=4,
        driver_statuses=dict(statuses),
        original_receipt_sha256=hashes,
        no_position_rescue_claim=True,
    )
    (HERE / "prefit-report-verification.json").write_text(json.dumps(verification, indent=2) + "\n")


if __name__ == "__main__":
    main()
