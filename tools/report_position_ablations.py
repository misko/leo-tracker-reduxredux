#!/usr/bin/env python3
"""Render sealed positioning ablations without refitting or selecting winners."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def read(path):
    return json.loads(Path(path).read_text())


def groups(rows):
    output = []
    for model in ("formal-orbit-correction-v6", "legacy-strict-fixed-orbit"):
        for method in ("density", "pass"):
            for fraction in (1 / 32, 1 / 16, 1 / 8, 1 / 4, 1 / 2, 1.0):
                selected = [
                    r
                    for r in rows
                    if r["model"] == model and r["method"] == method and r["fraction"] == fraction
                ]
                if fraction == 1 and not selected:
                    selected = [r for r in rows if r["model"] == model and r["fraction"] == 1]
                if not selected:
                    continue
                good = [r for r in selected if r["status"] == "converged"]

                def distribution(key, good=good):
                    values = [r[key] for r in good if r.get(key) is not None]
                    return (
                        [float(np.min(values)), float(np.median(values)), float(np.max(values))]
                        if values
                        else None
                    )

                output.append(
                    {
                        "model": model,
                        "method": method,
                        "fraction": fraction,
                        "converged": len(good),
                        "total": len(selected),
                        "subkm_all_attempts": sum(
                            r.get("horizontal_error_m", float("inf")) < 1000 for r in good
                        ),
                        "fitting_count_range": [
                            min(r["actual_fitting_count"] for r in selected),
                            max(r["actual_fitting_count"] for r in selected),
                        ],
                        "error_m": distribution("horizontal_error_m"),
                        "heldout_rms_hz": distribution("evaluation_rms_hz"),
                        "supported_evaluation_count": distribution(
                            "supported_evaluation_observations"
                        ),
                    }
                )
    return output


def fmt(distribution):
    return (
        "unavailable"
        if distribution is None
        else f"{distribution[1]:,.1f} ({distribution[0]:,.1f}–{distribution[2]:,.1f})"
    )


def render(factorial_path, sparse_path, previous_path, output, factorial_exact=None):
    factorial = read(factorial_path)["runs"]
    checks = {r["job_id"]: r for r in read(factorial_exact)["runs"]} if factorial_exact else {}
    sparse = read(sparse_path)["runs"]
    previous = [
        r
        for r in read(previous_path)["runs"]
        if r["method"] in ("density", "pass") and r["fraction"] in (0.25, 0.5)
    ]
    previous = [
        {**r, "model": "formal-orbit-correction-v6"}
        if r["model"] == "formal-orbit-correction"
        else r
        for r in previous
    ]
    rows = sparse + previous
    if len(factorial) != 16 or len(sparse) != 242 or len(previous) != 160:
        raise ValueError("incomplete benchmark: expected 16 factorial, 242 new, 160 previous runs")
    if any(r.get("status") == "missing" for r in factorial + rows):
        raise ValueError("cannot publish an incomplete benchmark")
    summary = groups(rows)
    output.mkdir(parents=True, exist_ok=True)
    (output / "grouped-results.json").write_text(json.dumps(summary, indent=2) + "\n")
    figure, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    for column, method in enumerate(("density", "pass")):
        for model, color, label in (
            ("formal-orbit-correction-v6", "#2166ac", "Formal model"),
            ("legacy-strict-fixed-orbit", "#b35806", "Strict fixed-orbit baseline"),
        ):
            data = [g for g in summary if g["method"] == method and g["model"] == model]
            axes[0, column].plot(
                [g["fraction"] for g in data],
                [g["error_m"][1] if g["error_m"] else np.nan for g in data],
                "o-",
                color=color,
                label=label,
                zorder=3 if model.startswith("formal") else 2,
            )
            for g in data:
                if g["error_m"]:
                    axes[0, column].vlines(
                        g["fraction"], g["error_m"][0], g["error_m"][2], color=color, alpha=0.4
                    )
            axes[1, column].plot(
                [g["fraction"] for g in data],
                [100 * g["converged"] / g["total"] for g in data],
                "o-",
                color=color,
                label=label,
            )
        axes[0, column].set(
            title="Observation thinning" if method == "density" else "Whole-track selection",
            yscale="log",
            ylabel="Converged horizontal error (m); median and range",
        )
        axes[0, column].axhline(1000, color="gray", ls="--", lw=1)
        axes[1, column].set(
            ylabel="Converged runs (%)",
            ylim=(-3, 103),
            xlabel="Fraction of original fitting pool (requested)",
        )
        for axis in axes[:, column]:
            axis.set_xscale("log", base=2)
            axis.set_xticks(
                [1 / 32, 1 / 16, 1 / 8, 1 / 4, 1 / 2, 1], ["1/32", "1/16", "1/8", "1/4", "1/2", "1"]
            )
            axis.grid(alpha=0.25)
        axes[0, column].legend(fontsize=8)
    figure.suptitle(
        "Causal fixed-identity positioning: accuracy and failures\n"
        "20 seeded subsets per reduced fraction; full pool once; no truth-based model selection"
    )
    figure.savefig(output / "data-size.png", dpi=160)
    plt.close(figure)
    figure, axes = plt.subplots(1, 2, figsize=(14, 8), sharey=True, constrained_layout=True)
    labels = []
    for i, row in enumerate(factorial):
        labels.append(row["model"].replace("-", " / "))
        color = "#2166ac" if row["status"] == "converged" else "#b2182b"
        marker = "o" if row["status"] == "converged" else "x"
        if checks.get(row["job_id"], {}).get("passed") is False:
            color, marker = "#d95f02", "D"
        axes[0].scatter(
            row.get("horizontal_error_m", np.nan),
            i,
            color=color,
            marker=marker,
        )
        axes[1].scatter(
            row.get("evaluation_rms_hz", np.nan),
            i,
            color=color,
            marker=marker,
        )
    axes[0].set_yticks(range(len(labels)), labels)
    axes[0].invert_yaxis()
    axes[0].set(xlabel="Horizontal error (m)", xscale="log")
    axes[1].set(xlabel="Random held-out RMS (Hz)")
    for axis in axes:
        axis.grid(alpha=0.25)
    figure.suptitle(
        "All 16 combinations on identical full data and external starts\n"
        "Blue: converged; red ×: nonconverged; orange diamond: failed propagation tolerance"
    )
    figure.savefig(output / "factorial.png", dpi=160)
    plt.close(figure)
    lines = [
        "## All 16 full-data model combinations",
        "",
        "1 enables a factor; 0 removes it. Orbit0 freezes the pre-capture predicted correction; "
        "it does not remove that causal prior mean. Scale0 fixes measurement sigma at the "
        "predeclared 250 Hz. Robust0 uses the normalized Gaussian likelihood. "
        "Correlation0 treats innovations as independent.",
        "",
        "| Orbit / correlation / robust / learned scale | Status | Error, m | "
        "Held-out RMS, Hz | Fitted sigma, Hz | Exact propagation max error, Hz |",
        "|---|---|---:|---:|---:|---|",
    ]
    for r in factorial:
        check = checks.get(r["job_id"])
        qualification = (
            (f"{check['maximum_absolute_hz']:.4f} ({'pass' if check['passed'] else 'FAIL'})")
            if check
            else "not checked"
        )
        lines.append(
            f"| {r['model']} | {r['status']} | "
            f"{r.get('horizontal_error_m', float('nan')):,.1f} | "
            f"{r.get('evaluation_rms_hz', float('nan')):.2f} | "
            f"{r.get('measurement_sigma_hz', float('nan')):.2f} | {qualification} |"
        )
    lines += [
        "",
        "![Full factorial](artifacts/2026_09_21_position_ablations/factorial.png)",
        "",
        "## Sample-size results",
        "",
        "Medians and ranges below include converged fits only. The convergence and sub-km "
        "columns retain every attempted seed in their denominator. A reported converged fit "
        "is an optimizer outcome, not independently verified acquisition "
        "or calibrated uncertainty.",
        "",
        "| Model | Selection | Fraction | Fitting observations | Converged | "
        "Sub-km / all attempts | Error median (range), m | Held-out RMS median (range), Hz |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for g in summary:
        count = g["fitting_count_range"]
        lines.append(
            f"| {'Formal' if g['model'].startswith('formal') else 'Baseline'} | {g['method']} | "
            f"1/{round(1 / g['fraction'])} | {count[0]}–{count[1]} | "
            f"{g['converged']}/{g['total']} | {g['subkm_all_attempts']}/{g['total']} | "
            f"{fmt(g['error_m'])} | {fmt(g['heldout_rms_hz'])} |"
        )
    lines += [
        "",
        "![Accuracy and convergence by fraction]"
        "(artifacts/2026_09_21_position_ablations/data-size.png)",
        "",
    ]
    (output / "tables.md").write_text("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factorial", type=Path, required=True)
    parser.add_argument("--sparse", type=Path, required=True)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--factorial-exact", type=Path)
    args = parser.parse_args()
    render(args.factorial, args.sparse, args.previous, args.output, args.factorial_exact)
