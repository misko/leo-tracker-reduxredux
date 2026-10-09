"""Full-membership endpoint metrics and plots, including every fallback."""

import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ARMS = ("fitted-c", "zero-c")
NAMES = ("upstream", "control-refit", "satellite-slope")


def main():
    rows = json.loads((HERE / "results.json").read_text())["rows"]
    summaries = {}
    lines = [
        "# Iteration 77: uniform full-cohort pipeline endpoint comparison",
        "",
        "All 148 consumed recordings are included: DS16 63 (original48 plus added15), "
        "DS17 51, DS18 34 (prior consumed24 plus other10, now also consumed). "
        "No new fits, exclusions, reference-guided choices, or reserve outcomes enter this audit. "
        "Freeze commit `c6e942e15` pins every input before aggregation.",
        "",
        "The three alternatives use the stored operational endpoint before the final "
        "extension, the accepted control refit, and the accepted satellite-slope fit. "
        "Each includes its original convergence fallback. The same endpoint policy is applied "
        "to every scan. The final endpoint exactly reproduces iteration65 in both c arms.",
        "",
        "| Dataset | Arm | Endpoint | Mean km | Median km | p95 km | Worst km | "
        "Mean frequency RMS Hz | Improved / regressed / tied versus upstream |",
        "|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    for dataset in ("DS16", "DS17", "DS18", "Pooled"):
        members = [r for r in rows if dataset == "Pooled" or r["member"]["dataset"] == dataset]
        summaries[dataset] = {}
        for arm in ARMS:
            summary = {}
            baseline = np.array([r["endpoints"]["upstream"][arm]["error_km"] for r in members])
            for name in NAMES:
                fits = [r["endpoints"][name][arm] for r in members]
                errors = np.array([r["error_km"] for r in fits])
                frequency = [
                    r["posterior_rms_hz"] for r in fits if r["posterior_rms_hz"] is not None
                ]
                delta = errors - baseline
                summary[name] = dict(
                    n=len(fits),
                    mean=float(errors.mean()),
                    median=float(np.median(errors)),
                    p95=float(np.percentile(errors, 95)),
                    worst=float(errors.max()),
                    improved=int(sum(delta < -0.001)),
                    regressed=int(sum(delta > 0.001)),
                    tied=int(sum(abs(delta) <= 0.001)),
                    accepted_converged=sum(bool(r["converged"]) for r in fits),
                    source_stage_counts=dict(Counter(r["stage"] for r in fits)),
                    frequency_rms_mean_hz=float(np.mean(frequency)) if frequency else None,
                    frequency_rms_available=len(frequency),
                )
                m = summary[name]
                lines.append(
                    f"| {dataset} | {arm} | {name} | {m['mean']:.6f} | {m['median']:.6f} | "
                    f"{m['p95']:.6f} | {m['worst']:.6f} | {m['frequency_rms_mean_hz']:.3f} | "
                    f"{m['improved']} / {m['regressed']} / {m['tied']} |"
                )
            summaries[dataset][arm] = summary
    for ax, arm in zip(axes, ARMS, strict=True):
        for name in NAMES:
            errors = sorted(r["endpoints"][name][arm]["error_km"] for r in rows)
            ax.step(errors, np.arange(1, 149) / 148, where="post", label=name)
        ax.set(
            xscale="log",
            xlabel="Position error, km (log scale)",
            ylabel="Fraction of all 148 recordings",
            title=arm,
        )
        ax.axvline(1, color="gray", linestyle="--", linewidth=0.7)
        ax.legend()
    fig.savefig(HERE / "endpoints.png", dpi=170)
    plt.close(fig)
    lines += [
        "",
        "![Full-cohort endpoint distributions](endpoints.png)",
        "",
        "## Interpretation and limits",
        "",
        "Frequency RMS is reported separately; improved frequency fit does not prove improved "
        "position. Objectives across these changed models are not compared. c=0 locks both "
        "static c and RF-time terms; candidate banks, observations, other priors and stage "
        "budgets are matched within each endpoint. These remain conditional ablations with "
        "shared fitted-derived banks and starting states. Later endpoints add computation.",
        "",
        "The full [per-member results](results.json) retain membership and exposure metadata; "
        "[summary.json](summary.json) records accepted convergence and fallback source stages, "
        "plus RMS availability. Accepted convergence is not raw final-stage convergence: a "
        "qualified fallback can mask a failed final attempt. Original attempts remain in the "
        "pinned source files and [iteration65](../2026_10_09_position_error_iter65/README.md). "
        "No failed or missing fit is silently removed from the position denominator.",
        "",
        "These are exploratory endpoint comparisons on previously consumed data, not new "
        "independent validation. They do not justify choosing different endpoints per scan "
        "from reference errors. Any candidate change needs a frozen uniform rule, complete "
        "DS16/DS17/DS18 reporting, and randomized independent-group validation. Production "
        "and the outcome-unexamined POST18 reserve remain unchanged.",
    ]
    lines.insert(
        2,
        "**Removing the satellite-slope stage would worsen the pooled mean.** "
        "Fitted-c improves from 1.399896 to 1.360148 km with that stage "
        "(107 improved, 40 regressed, 1 tied); zero-c improves from 1.824159 to "
        "1.738896 km (101 improved, 45 regressed, 2 tied). The control refit leaves "
        "all fitted-c errors tied within 1 m. The slope stage slightly worsens the "
        "largest error, so it helps broad accuracy without solving the catastrophic case.\n",
    )
    lines += [
        "",
        "## Remaining work",
        "",
        "The final fitted-c total error is 201.301943 km over 148 scans. Even an "
        "evaluation-only hypothetical replacement of its worst 53.140384 km error "
        "by exactly zero leaves mean 1.001092 km. This is arithmetic, not a candidate "
        "result or permission to replace a scan. A tail rescue must be accompanied by "
        "some broader improvement to satisfy the strict below-1 km target.",
        "",
        "Keep the existing slope stage while completing the frozen ordinary-start clock "
        "experiment. A subsequent uniformly applied slope-prior sensitivity experiment "
        "could test broad-error improvement, with matched c arms and a separate protocol; "
        "do not tune a prior per scan or select from true position error. This audit "
        "alone supplies no new prior value and does not justify deployment.",
    ]
    (HERE / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n")
    (HERE / "README.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(summaries["Pooled"], indent=2))


if __name__ == "__main__":
    main()
