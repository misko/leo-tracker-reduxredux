"""Postseal scalar reporting; no scientific or reference calls."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def publish(directory=HERE):
    directory = Path(directory)
    summary = json.loads((directory / "SUMMARY.json").read_text())
    if not summary["both_terminal"] or not summary["control_parity"]["passed"]:
        raise ValueError("Both terminal and native parity required")
    raw = json.loads((directory / "results/zero/result.json").read_text())
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout="constrained")
    lines = [
        "# Qualified handoff recovers a different discovery region",
        "",
        "Native full-state parity passes for both final arms, "
        "with zero objective and vector deltas. "
        "All three zero-led promotions now qualify; no Newton fallback was needed. "
        "This is one consumed DS18-022 diagnostic, not independent validation or a cohort mean.",
        "",
        "![Position and handoff qualification](comparison.png)",
        "",
        "| Discovery | Arm | Error km | Frequency RMS Hz | Region | Final KKT |",
        "|---|---|---:|---:|---|---:|",
    ]
    for bindex, branch in enumerate(("native", "zero")):
        for aindex, arm in enumerate(("fitted-c", "zero-c")):
            value = summary["branches"][branch]["arms"][arm]
            error = value["position_evaluation"]["error_km"]
            axes[0].bar(
                bindex + (-0.16 if aindex == 0 else 0.16),
                error,
                0.28,
                color=("#357a99" if aindex == 0 else "#d39a42"),
                label=arm if bindex == 0 else None,
            )
            lines.append(
                f"| {branch} | {arm} | {error:.6f} | "
                f"{value['frequency']['posterior_rms_hz']:.6f} | "
                f"{value['selection']['region_source']} | "
                f"{value['qualification']['stationarity']:.9g} |"
            )
    axes[0].set_xticks([0, 1], ["Native control", "Zero-led discovery"])
    axes[0].set_ylabel("Position error km (evaluation only)")
    axes[0].legend()
    lines += [
        "",
        "| Region | Zero-c KKT | Freed-c KKT | Promoted KKT | Feasible evaluations | Seconds |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for region, saved in sorted(raw["regions"].items()):
        h = saved["recovery"]["result"]["handoff"]
        values = [
            h["discovery_audit"]["stationarity"],
            h["fitted_audit"]["stationarity"],
            h["promoted_audit"]["stationarity"],
        ]
        axes[1].plot(range(3), values, marker="o", label=region)
        lines.append(
            f"| {region} | {values[0]:.9g} | {values[1]:.9g} | {values[2]:.9g} | "
            f"{h['promoted']['evaluations']} | {h['nonlinear']['elapsed_s']:.6f} |"
        )
    axes[1].axhline(0.001, color="black", linestyle="--", label="Threshold 0.001")
    axes[1].set_yscale("log")
    axes[1].set_xticks(range(3), ["Zero-c", "c freed", "Promoted"])
    axes[1].set_ylabel("Scaled stationarity KKT")
    axes[1].legend(fontsize=9)
    for ax in axes:
        ax.grid(axis="y", alpha=0.2)
    fig.savefig(directory / "comparison.png", dpi=160)
    plt.close(fig)
    lines += ["", "| Branch | Known slice seconds | Calibration regions |", "|---|---:|---:|"]
    for branch in ("native", "zero"):
        lines.append(f"| {branch} | {summary['slices'][branch]['known_elapsed_s']:.6f} | 3/3 |")
    lines += [
        "",
        "Both zero-led final arms select retained-0, `point:-82.5:-67.5`, via B7. "
        "Native selects retained-1, `point:-142.5:-107.5`. Selection used the frozen model rule; "
        "reference errors were calculated only after both branches completed. "
        "The discovery methods can have different banks, so frequency RMS, support and scores "
        "are operational model-specific summaries, not an identical-bank likelihood comparison. "
        "The improved frequency fit alone does not establish position accuracy.",
        "",
        "This consumed motivating case was selected for catastrophic-failure diagnosis. "
        "The ordinary discovery bootstrap remains fitted-derived, so this is not a pure "
        "zero-c pipeline. Final c arms are matched within each branch; no cross-bank score "
        "winner is selected and these results are not spliced into full-cohort metrics. "
        "Promotion evaluation counts are retained feasible evaluation records, not all "
        "objective calls or optimizer iterations.",
        "",
        "Iteration 149 established that zero-c optima were not stationary with c freed. "
        "The separately frozen nonlinear promotion solves that admission transition and retains "
        "the 0.001 qualification gate. This single-case recovery supports a broader matched "
        "evaluation, not deployment or a general accuracy claim.",
        "",
        "Full qualification, support, selected states and receipts are in the "
        "[verified archive](RESULT_ARCHIVE.md).",
    ]
    lines += [
        "",
        "| Branch | Region | Fitted-c qualified/attempted | c=0 qualified/attempted |",
        "|---|---|---:|---:|",
    ]
    for branch in ("native", "zero"):
        for region in summary["branches"][branch]["regions"]:
            fitted = region["finals"]["fitted-c"]
            zero = region["finals"]["zero-c"]
            lines.append(
                f"| {branch} | {region['name']} | {fitted['qualified']}/{fitted['attempts']} | "
                f"{zero['qualified']}/{zero['attempts']} |"
            )
    lines += [
        "",
        "Native has 9/9 qualified regional recovery fitted-c finals and "
        "4/9 qualified regional recovery c=0 finals; zero-led has 9/9 and 8/9 respectively. "
        "These counts cover regional recovery finals; B7 joint alternatives are separate. "
        "Six unqualified c=0 alternatives remain "
        "in the archive. All six regional calibrations and associations were available.",
    ]
    with (directory / "RESULTS.md").open("x") as stream:
        stream.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    publish()
