"""Cohort postseal publication; no evaluation or model ports."""

import json
from pathlib import Path


def publish(summary, directory, plot):
    if not summary.get("all_terminal") or len(summary["rows"]) != 12:
        raise ValueError("all 36 phases must seal before publication")
    directory = Path(directory)
    plot(summary, directory / "position_errors.png")
    lines = [
        "# Fresh native versus zero-c discovery",
        "",
        "Consumed twelve-member conditional pilot, not independent validation. "
        "Both branches use fresh discovery and the same frozen handoff policy. "
        "Final c arms are matched within each branch. Banks can differ across "
        "discovery policies; frequency scores are not used as cross-policy position evidence.",
        "",
        "![Matched position errors and missing endpoints](position_errors.png)",
        "",
        "| Dataset | Arm | Paired/members | Native mean/median/p95/worst km | "
        "Zero-led mean/median/p95/worst km | Regressions |",
        "|---|---|---:|---|---|---:|",
    ]
    for dataset, arms in summary["aggregates"].items():
        for arm, value in arms.items():
            cells = []
            for branch in ("native", "zero"):
                m = value["branches"][branch]
                cells.append(
                    "unavailable"
                    if m is None
                    else " / ".join(
                        f"{m[k]:.4f}" for k in ("mean_km", "median_km", "p95_km", "worst_km")
                    )
                )
            lines.append(
                f"| {dataset} | {arm} | {value['paired']}/{value['membership']} | "
                f"{cells[0]} | {cells[1]} | {value['regressions']} |"
            )
    lines += [
        "",
        "Incomplete pairs produce available-subset metrics only; full-member "
        "metrics are withheld. Missing endpoints are never imputed.",
        "",
        "| Member | Search | Native | Zero | Fitted-c delta km | c=0 delta km |",
        "|---|---|---|---|---:|---:|",
    ]
    for row in summary["rows"]:
        deltas = [row["arms"][a].get("delta_km") for a in ("fitted-c", "zero-c")]
        cells = ["missing" if d is None else f"{d:+.6f}" for d in deltas]
        lines.append(
            f"| {row['label']} | {row['statuses']['search']} | "
            f"{row['statuses']['native']} | {row['statuses']['zero']} | "
            f"{cells[0]} | {cells[1]} |"
        )
    lines += [
        "",
        "Frequency fit remains separate from accuracy:",
        "",
        "| Member | Arm | Native RMS Hz | Zero-led RMS Hz |",
        "|---|---|---:|---:|",
    ]
    for row in summary["rows"]:
        for arm in ("fitted-c", "zero-c"):
            cells = []
            for branch in ("native", "zero"):
                x = row["arms"][arm][branch].get("frequency", {}).get("posterior_rms_hz")
                cells.append("unavailable" if x is None else f"{x:.6f}")
            lines.append(f"| {row['label']} | {arm} | {cells[0]} | {cells[1]} |")
    lines += [
        "",
        "Failure reasons, regional qualification counts, intermediate joint attempts, "
        "partial stage/claim coverage, invocation costs and receipt hashes are retained "
        "in [SUMMARY.json](SUMMARY.json). Unknown terminal regions are unavailable, "
        "not completed zero-attempt regions. The progression screen is a consumed "
        "pilot decision receipt, not deployment authorization.",
    ]
    with (directory / "RESULTS.md").open("x") as stream:
        stream.write("\n".join(lines) + "\n")
    with (directory / "SUMMARY.json").open("x") as stream:
        json.dump(summary, stream, indent=2, allow_nan=False)
