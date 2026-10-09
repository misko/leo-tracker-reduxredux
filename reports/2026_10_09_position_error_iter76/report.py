"""Describe frozen extra-search flags; no operational threshold selection."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def main():
    rows = json.loads((HERE / "results.json").read_text())["rows"]
    plan = json.loads((HERE / "protocol.json").read_text())
    summary = {}
    lines = [
        "# Iteration 76: can timing strain request extra search?",
        "",
        "This is a development audit of all 148 already consumed scans, "
        "not independent validation. "
        "It changes no position estimate, winner, satellite bank, or dataset membership. "
        "No extra-search speed or accuracy benefit has yet been measured.",
        "",
        "Before this audit, commit `33152faef` froze thresholds 3, 5, and 10. "
        "For each initial joint-100 fit, Q is the mean squared orthonormal relative-timing "
        "coefficient divided by the existing 2-second prior variance. Q is basis invariant "
        "but is not a calibrated chi-square statistic. A missing/nonconverged fit or Q above "
        "the threshold in either c arm requests the same extra search budget for both arms. "
        "This would request computation, never discard a scan or accept a position.",
        "",
        "Reference errors enter only after flags are computed. All three thresholds apply "
        "uniformly to DS16/DS17/DS18. The table evaluates flags against the unchanged "
        "iteration-65 final candidate errors, which occur later in the pipeline; successful "
        "existing recovery can therefore make an early flag appear unnecessary.",
        "",
        "| Dataset | Threshold | Flagged / all | Fitted >2 km caught / all | "
        "Zero >2 km caught / all | Fitted >5 km caught / all | Zero >5 km caught / all |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    for dataset, color in zip(
        ("DS16", "DS17", "DS18"), ("tab:blue", "tab:orange", "tab:green"), strict=True
    ):
        members = [r for r in rows if r["member"]["dataset"] == dataset]
        group = dict(membership=len(members), thresholds={})
        for t in plan["thresholds"]:
            flags = [r for r in members if r["flags"][str(t)]]
            record = dict(flagged=len(flags), arms={})
            for arm in ("fitted-c", "zero-c"):
                record["arms"][arm] = {
                    str(e): dict(
                        total=sum(r["errors_km"][arm] > e for r in members),
                        caught=sum(r["errors_km"][arm] > e for r in flags),
                    )
                    for e in plan["evaluation_error_thresholds_km"]
                }
            group["thresholds"][str(t)] = record
            cells = []
            for e in (2, 5):
                for arm in ("fitted-c", "zero-c"):
                    value = record["arms"][arm][str(e)]
                    cells.append(f"{value['caught']} / {value['total']}")
            lines.append(
                f"| {dataset} | {t} | {len(flags)} / {len(members)} | " + " | ".join(cells) + " |"
            )
        group["missing_fit_arms"] = sum(
            not m["available"] for r in members for m in r["metrics"].values()
        )
        group["nonconverged_fit_arms"] = sum(
            m["available"] and not m["converged"] for r in members for m in r["metrics"].values()
        )
        summary[dataset] = group
        for ax, arm in zip(axes, ("fitted-c", "zero-c"), strict=True):
            available = [r for r in members if r["metrics"][arm]["available"]]
            ax.scatter(
                [max(r["metrics"][arm]["normalized_energy"], 1e-6) for r in available],
                [r["errors_km"][arm] for r in available],
                label=dataset,
                color=color,
                alpha=0.65,
                s=20,
            )
            ax.set(
                xscale="log",
                yscale="log",
                xlabel="Initial timing Q (log scale)",
                ylabel="Final error, km (log scale)",
                title=arm,
            )
    for ax in axes:
        for t in plan["thresholds"]:
            ax.axvline(t, color="gray", linestyle=":", linewidth=0.7)
        ax.axhline(1, color="black", linestyle="--", linewidth=0.7)
        ax.legend()
    fig.savefig(HERE / "timing-strain.png", dpi=170)
    plt.close(fig)
    lines += [
        "",
        "![Timing strain versus unchanged position error](timing-strain.png)",
        "",
        "## Coverage and limitations",
        "",
    ]
    for dataset, value in summary.items():
        lines.append(
            f"- {dataset}: {value['membership']} members; "
            f"{value['missing_fit_arms']} missing initial-fit arms; "
            f"{value['nonconverged_fit_arms']} nonconverged initial-fit arms (both arms counted)."
        )
    lines += [
        "",
        "Full per-member flags, errors, exposure metadata, and timing diagnostics are in "
        "[results.json](results.json); all thresholds, including >20 and >100 km coverage, "
        "are in [summary.json](summary.json). Missing/nonconverged fits trigger extra search "
        "rather than disappearing from coverage. DS16 includes all original48 plus added15; "
        "DS18 retains prior consumed labels and makes no unseen claim for the other10.",
        "",
        "The full baseline/candidate position distributions, paired regressions, convergence "
        "fallbacks and separate frequency-fit effects remain the unchanged "
        "[iteration-65 cohort report](../2026_10_09_position_error_iter65/README.md). "
        "This audit has no new frequency fit and cannot establish localization improvement.",
        "",
        "Any useful threshold would need a subsequent frozen uniform end-to-end experiment "
        "that measures actual extra computation and paired accuracy across the full cohort. "
        "Threshold exploration here is consumed-data tuning. New validation must use reproducible "
        "random whole independent groups, preserve exposure labels, "
        "and keep preprocessing training-only. "
        "The 11-recording POST18 reserve remains outcome-unexamined; its chronology alone does not "
        "make it randomized validation. No production change is made.",
        "",
        "## Finding",
        "",
        "All three thresholds flag the remaining >50 km DS18 failure, but each misses "
        "most >2 km errors. Thresholds 3/5/10 flag 33/18/6 of 148 scans and catch only "
        "4/4/3 of 12 fitted-c errors above 2 km (zero-c: 7/5/4 of 30). Thus timing strain "
        "is a possible catastrophic-error search trigger, not a general accuracy test. "
        "With just one remaining >5 km failure, these data cannot establish catastrophic-error "
        "recall on future scans. There is no basis to choose or deploy a threshold yet.",
    ]
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (HERE / "README.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
