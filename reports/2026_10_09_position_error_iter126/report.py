"""Report sealed fixed-endpoint frame diagnostics, never position accuracy."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    plan = json.loads((HERE / "protocol.json").read_text())
    digest = hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
    rows = []
    for binding in plan["members"]:
        label = binding["member"]["inventory_label"]
        path = HERE / "results" / f"{label}.json"
        assert path.exists(), label
        row = json.loads(path.read_text())
        assert row["member"] == binding["member"] and row["protocol_sha256"] == digest
        assert row["status"] in ("complete", "failed")
        rows.append(row)
    complete = [r for r in rows if r["status"] == "complete"]
    metrics = {}
    if len(complete) == 12:
        for arm in ("fitted-c", "zero-c"):
            metrics[arm] = {}
            for field in (
                "nll_delta",
                "normalizer_delta",
                "prediction_delta_rms_hz",
                "visibility_changed",
            ):
                values = [r["arms"][arm][field] for r in complete]
                metrics[arm][field] = {
                    "median": float(np.median(values)),
                    "minimum": float(np.min(values)),
                    "maximum": float(np.max(values)),
                }
    summary = {
        "coverage": {"expected": 12, "complete": len(complete), "failed": 12 - len(complete)},
        "full12_metrics": metrics,
        "runtime_sum_s": sum(r["elapsed_s"] for r in rows),
        "score_parity_max": max(
            (
                abs(r["arms"][a]["original_score_parity_delta"])
                for r in complete
                for a in ("fitted-c", "zero-c")
            ),
            default=None,
        ),
        "scope": "Fixedendpoint frame-model frequency audit; no fit, accuracy, covariance or likelihood-based model winner claim",
    }
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    fig, axes = plt.subplots(2, 2, figsize=(13, 7), layout="constrained")
    labels = [r["member"]["inventory_label"] for r in complete]
    for i, arm in enumerate(("fitted-c", "zero-c")):
        axes[i, 0].bar(labels, [r["arms"][arm]["prediction_delta_rms_hz"] for r in complete])
        axes[i, 0].set(title=f"{arm}: orbit frequency change", ylabel="RMS Hz")
        axes[i, 1].plot(
            labels, [r["arms"][arm]["nll_delta"] for r in complete], marker="o", label="NLL delta"
        )
        axes[i, 1].plot(
            labels,
            [r["arms"][arm]["normalizer_delta"] for r in complete],
            marker="x",
            label="normalizer delta",
        )
        axes[i, 1].set(title=f"{arm}: alternate minus original", ylabel="Dimensionless")
        axes[i, 1].legend()
        for axis in axes[i]:
            axis.tick_params(axis="x", rotation=65, labelsize=8)
    fig.savefig(HERE / "comparison.png", dpi=140)
    plt.close(fig)
    text = [
        "# Relative orbital phase versus ECEF query timing",
        "",
        f"Coverage {len(complete)}/12 complete; {12 - len(complete)} failed. Full12 metrics withheld unless all12 complete. No optimizer ran and endpoints were unchanged.",
        "",
        "![Frequency and score effects](comparison.png)",
        "",
        "|Arm|Quantity|Median|Min|Max|",
        "|---|---|---:|---:|---:|",
    ]
    for arm, fields in metrics.items():
        for field, s in fields.items():
            text.append(f"|{arm}|{field}|{s['median']:.6g}|{s['minimum']:.6g}|{s['maximum']:.6g}|")
    text += [
        "",
        f"Original objective parity max {summary['score_parity_max']}; summed receipt costs {summary['runtime_sum_s']:.3f}s, not parallel wall time.",
        "",
        "This is a different physical timing convention, not a demonstrated bug fix. Relative phase undoes constant-rate Earth rotation while common timestamp timing remains unchanged. Priors cancel at fixed endpoints. Alternative NLL and frequency changes do not establish better position accuracy or choose the physical model. Visibility derivatives are omitted; temporal data gradients are not complete objective stationarity tests. Precision GMST curvature and direct propagation are outside this approximation. No known receiver coordinates entered.",
        "",
        "|Member|Status|Failure|",
        "|---|---|---|",
    ]
    text += [f"|{r['member']['inventory_label']}|{r['status']}|{r.get('error', '')}|" for r in rows]
    (HERE / "RESULTS.md").write_text("\n".join(text) + "\n")


if __name__ == "__main__":
    main()
