"""Saved-result arithmetic/plots only; imports no orbit model or fitter."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def derive(result, plan):
    if result["status"] != "complete" or result["full_calls"] != 6 or result["fixed_calls"] != 6:
        raise ValueError("complete six-state result required")
    if len(result["rows"]) != 6 or [r["name"] for r in result["rows"]] != [
        s[0] for s in plan["saved_states"]
    ]:
        raise ValueError("state inventory mismatch")
    base = result["rows"][0]
    rows = []
    for r, saved in zip(result["rows"], plan["saved_states"], strict=True):
        vector = np.asarray(saved[1], dtype=float)
        if hashlib.sha256(vector.tobytes()).hexdigest() != r["vector_sha256"]:
            raise ValueError("saved vector digest mismatch")
        if (
            abs(saved[2] - r["objective"]) > 1e-6
            or abs(r["nll"] + r["prior"] - r["objective"]) > 1e-9
            or abs(r["normalization_nll"] + r["density_nll"] - r["nll"]) > 1e-9
        ):
            raise ValueError("objective/decomposition identity mismatch")
        row = dict(
            name=r["name"],
            objective_delta=r["objective"] - base["objective"],
            fixed_mask_objective_delta=r["fixed_mask_nll"] + r["prior"] - base["objective"],
            mask_cost=r["nll"] - r["fixed_mask_nll"],
            normalization_delta=r["normalization_nll"] - base["normalization_nll"],
            density_delta=r["density_nll"] - base["density_nll"],
            prior_delta=r["prior"] - base["prior"],
            visibility_added=r["visibility_added"],
            visibility_removed=r["visibility_removed"],
            interpolation_cells_changed=r["interpolation_cells_changed"],
            winding_changed=r["winding_changed"],
            common_gradient=r["common_gradient"],
        )
        if (
            abs(row["objective_delta"] - row["fixed_mask_objective_delta"] - row["mask_cost"])
            > 1e-9
        ):
            raise ValueError("mask decomposition mismatch")
        rows.append(row)
    plus, minus = result["rows"][1:3]
    step = plan["saved_states"][1][1][7] - plan["saved_states"][0][1][7]
    derivative = (
        plus["fixed_mask_nll"] + plus["prior"] - minus["fixed_mask_nll"] - minus["prior"]
    ) / (2 * step)
    return dict(
        rows=rows,
        common_step_s=step,
        base_common_gradient=base["common_gradient"],
        fixed_mask_central_score_derivative=derivative,
        derivative_discrepancy=derivative - base["common_gradient"],
        curvature_from_gradient=(plus["common_gradient"] - minus["common_gradient"]) / (2 * step),
        maximum_mask_vs_normalization_difference=max(
            abs(r["mask_cost"] - r["normalization_delta"]) for r in rows
        ),
    )


def plot(summary, target):
    rows = summary["rows"][1:]
    labels = ["+10 µs", "−10 µs", "Newton ×1", "Newton ×½", "Newton ×¼"]
    x = np.arange(len(rows))
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4), layout="constrained")
    axes[0].bar(
        x - 0.22,
        [r["fixed_mask_objective_delta"] for r in rows],
        0.22,
        label="Fixed-mask objective change",
        color="#257c91",
    )
    axes[0].bar(
        x, [r["mask_cost"] for r in rows], 0.22, label="Visibility contribution", color="#d98936"
    )
    axes[0].bar(
        x + 0.22,
        [r["objective_delta"] for r in rows],
        0.22,
        label="Actual objective change",
        color="#9a4965",
    )
    axes[0].axhline(0, color="black", linewidth=0.7)
    axes[0].set(
        xticks=x,
        xticklabels=labels,
        ylabel="Change from unchanged base (NLL + prior)",
        title="Visibility reverses the proposed improvement",
    )
    axes[0].tick_params(axis="x", rotation=20)
    axes[0].legend(fontsize=8)
    step = summary["common_step_s"]
    probe = summary["rows"][1:3]
    d = np.array([step, -step])
    axes[1].plot(
        d * 1e6,
        [r["fixed_mask_objective_delta"] * 1e3 for r in probe],
        "o",
        label="Saved fixed-mask probes",
        color="#257c91",
    )
    xx = np.linspace(-step, step, 101)
    yy = summary["base_common_gradient"] * xx + 0.5 * summary["curvature_from_gradient"] * xx**2
    axes[1].plot(xx * 1e6, yy * 1e3, label="Local gradient + curvature", color="#343e52")
    axes[1].set(
        xlabel="Common timing change (µs)",
        ylabel="Fixed-mask objective change ×1,000",
        title="Smooth score agrees with the analytic derivative",
    )
    axes[1].axhline(0, color="black", linewidth=0.7)
    axes[1].legend(fontsize=8)
    fig.suptitle("DS17-033: six saved states, no new optimization", fontsize=14)
    fig.savefig(target, dpi=170)
    plt.close(fig)


def main():
    protocol_path = HERE / "protocol.json"
    result_path = HERE / "result.json"
    plan = json.loads(protocol_path.read_text())
    result = json.loads(result_path.read_text())
    digest = hashlib.sha256(protocol_path.read_bytes()).hexdigest()
    if (
        result["protocol_sha256"] != digest
        or result["upstream_protocol_sha256"] != plan["upstream_protocol_sha256"]
        or result["member"] != plan["member"]
    ):
        raise ValueError("result protocol/member binding mismatch")
    if json.loads((HERE / "attempt.json").read_text())["protocol_sha256"] != digest:
        raise ValueError("attempt binding mismatch")
    mismatches = [
        name
        for name, expected in plan["source_sha256"].items()
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected
    ]
    if mismatches:
        raise ValueError("frozen source mismatches: " + repr(mismatches))
    summary = derive(result, plan)
    summary["integrity"] = dict(
        protocol_sha256=digest,
        result_sha256=hashlib.sha256(result_path.read_bytes()).hexdigest(),
        verified_source_files=len(plan["source_sha256"]),
        states=6,
        full_objective_calls=result["full_calls"],
        fixed_mask_calls=result["fixed_calls"],
        elapsed_s=result["elapsed_s"],
        scope="saved arithmetic only; no new model calls",
    )
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    plot(summary, HERE / "visibility-decomposition.png")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
