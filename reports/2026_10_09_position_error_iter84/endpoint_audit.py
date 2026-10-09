"""Retrospective fixed-endpoint comparison; never fit or select an endpoint."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def extra_penalty(fit, geometry):
    count = len(fit["vector"]) - 8
    slope = np.asarray(fit["clock_coefficients"][-(count + 2):-2]) / 100
    projector = np.asarray(geometry["projector"])
    assert projector.shape == (count, count)
    assert np.allclose(projector, projector.T, atol=1e-10)
    assert np.allclose(projector @ projector, projector, atol=1e-10)
    strength = (1 / geometry["protected_sigma_hz_s"]**2
                - 1 / geometry["wide_sigma_hz_s"]**2)
    return float(0.5 * strength * slope @ projector @ slope)


def main():
    digest = hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
    plan = json.loads((HERE / "protocol.json").read_text())
    rows, coverage = [], []
    for binding in plan["members"]:
        member = binding["member"]
        label = member["inventory_label"]
        path = HERE / "results" / f"{label}.json"
        result = json.loads(path.read_text()) if path.exists() else {"status": "pending"}
        coverage.append(dict(label=label, status=result["status"]))
        if result["status"] != "complete":
            continue
        assert result["protocol_sha256"] == digest and result["member"] == member
        for arm in ("fitted-c", "zero-c"):
            uniform = result["raw"]["uniform0.5"][arm]
            protected = result["raw"]["protected0.25"][arm]
            pu = extra_penalty(uniform, result["geometry"])
            pp = extra_penalty(protected, result["geometry"])
            rows.append(dict(
                label=label, arm=arm,
                both_qualified=uniform["converged"] and protected["converged"],
                before_km=uniform["error_km"], after_km=protected["error_km"],
                error_delta_km=protected["error_km"] - uniform["error_km"],
                endpoint_shift_km=float(np.linalg.norm(
                    np.asarray(protected["vector"][:2]) - uniform["vector"][:2])),
                extra_penalty_before=pu, extra_penalty_after=pp,
                delta_under_uniform=protected["objective"] - pp - uniform["objective"],
                delta_under_protected=protected["objective"] - uniform["objective"] - pu,
                rms_delta_hz=protected["posterior_rms_hz"] - uniform["posterior_rms_hz"],
            ))
    complete = sum(r["status"] == "complete" for r in coverage)
    output = dict(complete=complete, membership=148, coverage=coverage, rows=rows)
    (HERE / "endpoint-audit.json").write_text(json.dumps(output, indent=2) + "\n")
    lines = ["# Geometry-prior fixed-endpoint audit", "",
             f"**{complete}/148 recordings complete.** "
             "Partial audits are not full-cohort performance claims.", "",
             "No new optimization or operational selection. At an unchanged endpoint, the "
             "protected model adds 0.5 × (1/0.25² − 1/0.5²) × sᵀPs, where s is the "
             "satellite-slope coordinate vector in Hz/s and P is the frozen projector. "
             "Subtracting that penalty reconstructs the uniform objective exactly in algebra. "
             "Each score comparison below therefore uses one fixed objective.", "",
             "Positive delta means the protected endpoint loses to the uniform endpoint "
             "under that column's model. Opposite signs show a changed regularization "
             "preference between these endpoints, not proof of global optimality or a "
             "physical cause. Reference errors only order this retrospective diagnostic table; "
             "they never select operational results or priors.", "",
             "| Largest fitted-c regressions | Before km | After km | Shift km | "
             "Score delta under uniform | Score delta under protected | RMS delta Hz |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    qualified = [r for r in rows if r["both_qualified"]]
    fitted = sorted([r for r in qualified if r["arm"] == "fitted-c"],
                    key=lambda r: r["error_delta_km"], reverse=True)
    for row in fitted[:8]:
        lines.append(f"| {row['label']} | " + " | ".join(
            f"{row[k]:.6f}" for k in ("before_km", "after_km", "endpoint_shift_km",
                                     "delta_under_uniform", "delta_under_protected",
                                     "rms_delta_hz")) + " |")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), layout="constrained")
    for ax, arm in zip(axes, ("fitted-c", "zero-c"), strict=True):
        for dataset in ("DS16", "DS17", "DS18"):
            group = [r for r in qualified if r["arm"] == arm and r["label"].startswith(dataset)]
            ax.scatter([r["extra_penalty_after"] - r["extra_penalty_before"] for r in group],
                       [r["error_delta_km"] for r in group], label=f"{dataset}: {len(group)}",
                       alpha=0.7, s=20)
        ax.axhline(0, color="gray", linestyle="--")
        ax.set(title=arm, xlabel="Change in added geometry penalty",
               ylabel="Position error change, km (+ worse)")
        ax.legend()
    fig.suptitle(f"Retrospective audit: {complete}/148 complete; qualified pairs only")
    fig.savefig(HERE / "endpoint-audit.png", dpi=160)
    plt.close(fig)
    lines += ["", "![Penalty and position changes](endpoint-audit.png)", "",
              "Raw unqualified pairs and full membership remain in endpoint-audit.json. "
              "Operational fallbacks and all performance metrics belong to RESULTS.md. "
              "Consumed development only; no deployment or independent validation claim."]
    (HERE / "ENDPOINT_AUDIT.md").write_text("\n".join(lines) + "\n")
    print(complete, "recordings audited; no fitting")


if __name__ == "__main__":
    main()
