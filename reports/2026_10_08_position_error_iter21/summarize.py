"""Summarize all four originally assigned validation scans after availability recovery."""

import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "2026_10_08_position_error_iter20"
ARMS = ("fitted-c", "zero-c")


def main():
    protocol = json.loads((HERE / "protocol.json").read_text())
    for name, digest in protocol["source_sha256"].items():
        assert hashlib.sha256((HERE.parent / name).read_bytes()).hexdigest() == digest, name
    prior = json.loads((PREVIOUS / "summary.json").read_text())
    members = json.loads((PREVIOUS / "validation-protocol.json").read_text())["members"]
    expected = {m["label"] for m in members if m["evaluation_group"] == "validation"}
    cases = [
        row for row in prior["cases"]
        if row["group"] == "validation" and row["status"] == "complete"
    ]
    completion = json.loads((HERE / "result.json").read_text())
    original = json.loads((HERE / "baseline.json").read_text())
    baseline = {
        item["name"]: dict(
            error_km=item["selected"]["horizontal_error_m"] / 1000,
            posterior_rms_hz=item["selected"]["posterior_rms_hz"],
            converged=item["selected"]["converged"],
        )
        for item in original["methods"][0]["arms"]
    }
    result = completion["result"]
    cases.append(dict(
        label=protocol["label"], group="validation", status="complete", baseline=baseline,
        candidate={
            arm: {key: row[key] for key in (
                "error_km", "posterior_rms_hz", "converged", "stage"
            )}
            for arm, row in result["operational"].items()
        },
        stopped=result["stopped"], regions=result["regional_sources"],
    ))
    cases.sort(key=lambda row: row["label"])
    assert len(cases) == 4 and {row["label"] for row in cases} == expected
    metrics = {}
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), layout="constrained")
    x = np.arange(4)
    for arm, color in zip(ARMS, ("tab:blue", "tab:orange"), strict=True):
        metrics[arm] = {}
        for method, style in (("baseline", "--"), ("candidate", "-")):
            errors = [row[method][arm]["error_km"] for row in cases]
            rms = [row[method][arm]["posterior_rms_hz"] for row in cases]
            metrics[arm][method] = dict(
                count=4, mean_km=float(np.mean(errors)), median_km=float(np.median(errors)),
                p95_km=float(np.percentile(errors, 95)), worst_km=float(max(errors)),
                mean_rms_hz=float(np.mean(rms)),
            )
            axes[0].plot(x, errors, style, color=color, marker="o", label=f"{arm}: {method}")
            axes[1].plot(x, rms, style, color=color, marker="o", label=f"{arm}: {method}")
    for ax in axes:
        ax.set_xticks(x, [row["label"] for row in cases], rotation=25)
        ax.grid(alpha=0.2)
    axes[0].axhline(1, color="gray", linewidth=1)
    axes[0].set(ylabel="Position error (km)", title="All four assigned validation scans")
    axes[1].set(ylabel="Posterior frequency RMS (Hz)", title="Frequency fit, reported separately")
    axes[0].legend(fontsize=8)
    fig.savefig(HERE / "completed-holdout.png", dpi=160)
    m = metrics["fitted-c"]
    gates = dict(
        all_four_now_complete=True,
        mean_below_1km=m["candidate"]["mean_km"] < 1,
        mean_no_worse=m["candidate"]["mean_km"] <= m["baseline"]["mean_km"],
        worst_within_10percent=m["candidate"]["worst_km"] <= 1.1 * m["baseline"]["worst_km"],
        all_final_fitted_converged=all(
            row["candidate"]["fitted-c"]["stage"] == "drift-50"
            and row["candidate"]["fitted-c"]["converged"] for row in cases
        ),
    )
    output = dict(
        cases=cases, metrics=metrics, completion_gates=gates,
        completion_passed=all(gates.values()),
        original_first_attempt_passed=prior["passed"],
        original_first_attempt_gates=prior["gates"],
    )
    (HERE / "summary.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({k: v for k, v in output.items() if k != "cases"}, indent=2))


if __name__ == "__main__":
    main()
