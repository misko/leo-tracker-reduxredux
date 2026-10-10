"""Postseal visualization of frozen build output; no model evaluations."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def publish(result, directory):
    directory = Path(directory)
    if not result["both_terminal"]:
        raise ValueError("Both branches must be terminal")
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8), layout="constrained")
    maximum_error = max(
        [
            endpoint["position_evaluation"]["error_km"]
            for row in result["branches"].values()
            for endpoint in row["arms"].values()
            if endpoint.get("position_evaluation")
        ]
        or [1.0]
    )
    axes[1].set_ylim(0, maximum_error * 1.1)
    for index, branch in enumerate(("native", "zero")):
        row = result["branches"][branch]
        regions = row["regions"]
        axes[0].bar(
            index,
            sum(r.get("calibration_available", False) for r in regions),
            color=("#357a99" if branch == "native" else "#999999"),
        )
        axes[0].text(
            index,
            3.12,
            f"{sum(r.get('calibration_available', False) for r in regions)}/3",
            ha="center",
        )
        for armindex, arm in enumerate(("fitted-c", "zero-c")):
            endpoint = row["arms"][arm]
            x = index + (-0.16 if armindex == 0 else 0.16)
            if endpoint.get("position_evaluation"):
                axes[1].bar(
                    x,
                    endpoint["position_evaluation"]["error_km"],
                    0.28,
                    color=("#357a99" if armindex == 0 else "#d39a42"),
                    label=arm if index == 0 else None,
                )
        if all(e["status"] == "no-selected-endpoint" for e in row["arms"].values()):
            axes[1].text(
                index, maximum_error * 0.35, "No endpoint\n(no error imputed)", ha="center"
            )
        elapsed = result["slices"][branch]["known_elapsed_s"]
        axes[2].bar(index, elapsed, color=("#357a99" if branch == "native" else "#999999"))
    for axis in axes:
        axis.set_xlim(-0.5, 1.5)
        axis.set_xticks([0, 1], ["Native-led", "Zero-led"])
        axis.grid(axis="y", alpha=0.2)
        axis.set_axisbelow(True)
    axes[0].set_ylabel("Available calibration regions")
    axes[0].set_ylim(0, 3.6)
    axes[1].set_ylabel("Position error (km), evaluation only")
    if axes[1].get_legend_handles_labels()[0]:
        axes[1].legend()
    axes[2].set_ylabel("Known summed slice runtime (s)")
    fig.suptitle("DS18-022: consumed discovery-policy diagnostic")
    fig.savefig(directory / "comparison.png", dpi=160)
    plt.close(fig)
    parity_statement = (
        "The fresh native control reproduced its historical endpoint and full-state "
        "parity checks passed."
        if result.get("control_parity", {}).get("passed")
        else "Fresh native control parity failed; historical baseline equivalence is withheld."
    )
    lines = [
        "# Zero-led discovery did not produce an endpoint",
        "",
        "Both branches completed one bounded slice. "
        + parity_statement
        + " All three zero-led retained "
        "regions failed calibration with `AssertionError`; association and final fits were not "
        "reached. No position error or fallback is imputed for that branch.",
        "",
        "![Coverage, position and runtime](comparison.png)",
        "",
        "| Discovery | Region | Calibration | Failure | Fitted-c finals qualified/attempted "
        "| c=0 finals qualified/attempted |",
        "|---|---|---|---|---|---|",
    ]
    for branch, row in result["branches"].items():
        for region in row["regions"]:
            finals = region.get("finals") or {}
            counts = []
            for arm in ("fitted-c", "zero-c"):
                cell = finals.get(arm, {})
                counts.append(f"{cell.get('qualified', 0)}/{cell.get('attempts', 0)}")
            lines.append(
                f"| {branch} | {region['name']} | "
                f"{region.get('calibration_status', 'unavailable')} | "
                f"{region.get('failure_reason') or '—'} | {counts[0]} | {counts[1]} |"
            )
    lines += [
        "",
        "| Discovery | Arm | Endpoint | Error km | Frequency RMS Hz | Qualified |",
        "|---|---|---|---|---|---|",
    ]
    for branch, row in result["branches"].items():
        for arm, endpoint in row["arms"].items():
            position = endpoint.get("position_evaluation", {}).get("error_km")
            frequency = endpoint.get("frequency", {}).get("posterior_rms_hz")
            lines.append(
                f"| {branch} | {arm} | {endpoint['status']} | "
                f"{position if position is not None else 'unavailable'} | "
                f"{frequency if frequency is not None else 'unavailable'} | "
                f"{endpoint.get('qualified', 'not reached')} |"
            )
    lines += [
        "",
        "| Discovery | Completed/claimed slices | Known runtime seconds | Unfinished claims |",
        "|---|---|---|---|",
    ]
    for branch, row in result["slices"].items():
        lines.append(
            f"| {branch} | {row['completed']}/{row['claimed']} | "
            f"{row['known_elapsed_s']:.6f} | {row['unfinished_claims']} |"
        )
    lines += [
        "",
        "This is one consumed scan, not an independent validation or population mean. "
        "Zero-led failure receipts do not identify the assertion's root cause. Different banks "
        "and policies are not selected by raw likelihood. Native matched c arms and frequency "
        "effects remain separate from position accuracy; the absent zero-led endpoint is not an "
        "accuracy result. This result does not measure whether zero-led discovery improves "
        "localization and supports no production change.",
        "",
        "Source-only follow-up identifies a probable unsupported c=0-to-fitted-c handoff. "
        "The inherited [105 recovery](../2026_10_09_position_error_iter105/run.py) skips its "
        "prefit qualification when the saved coarse fit reports convergence. "
        "[103 validated_postfit](../2026_10_09_position_error_iter103/run.py) then tests "
        "stationarity with `rf_arm='fitted-c'`. A constrained c=0 optimum need not be stationary "
        "when c is freed. The blank assertion receipts do not retain which conjunct failed, "
        "so this source finding is a probable integration/admission failure, not evidence that "
        "zero-led discovery is poor. A separately frozen transition diagnostic is required; "
        "the failed branch is not rerun or admitted by relaxing its gate.",
        "",
        "Full raw region/stage coverage, qualification, fresh-control parity and evaluation "
        "binding are retained in the [verified results archive](RESULT_ARCHIVE.md), including SUMMARY.json.",
    ]
    with (directory / "RESULTS.md").open("x") as stream:
        stream.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    publish(json.loads((HERE / "SUMMARY.json").read_text()), HERE)
