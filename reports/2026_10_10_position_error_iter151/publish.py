"""Cohort postseal publication; no evaluation or model ports."""

import json
import math
from pathlib import Path


def cell(value):
    """Keep multiline failure receipts readable inside Markdown tables."""
    if value is None or value == [] or value == {}:
        return "none reported"
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    return text.replace("|", "&#124;").replace("\n", "<br>")


def number(value, digits=6):
    return "unavailable" if value is None or not math.isfinite(value) else f"{value:.{digits}f}"


def qualification_lines(summary):
    lines = [
        "", "Selected endpoints and retained-region coverage:", "",
        "| Member | Branch | Qualified selected / 2 | Missing selected | "
        "Qualified calibrations / known regions | Unavailable regions | "
        "Qualified regional finals / recorded attempts | Qualified joint fits / recorded attempts |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary["rows"]:
        for branch in ("native", "zero"):
            endpoints = [row["arms"][arm][branch] for arm in ("fitted-c", "zero-c")]
            selected = sum(bool(e.get("qualified")) for e in endpoints)
            missing = sum(e.get("status") != "selected" for e in endpoints)
            regions = row.get("regions", {}).get(branch, [])
            known = [r for r in regions if r.get("finals") is not None]
            unavailable = 3 - len(known)
            calibrated = sum(r.get("calibration_status") == "qualified" for r in known)
            calibration_counts = f"{calibrated}/{len(known)}" if known else "unavailable"
            finals = [v for r in known for v in r["finals"].values()]
            joint = [v for arms in row.get("joint_stages", {}).get(branch, {}).values() for v in arms.values()]
            final_counts = (
                f"{sum(v['qualified'] for v in finals)}/{sum(v['attempts'] for v in finals)}"
                if known else "unavailable"
            )
            joint_counts = f"{sum(bool(v) for v in joint)}/{len(joint)}" if joint else "unavailable"
            lines.append(
                f"| {row['label']} | {branch} | {selected}/2 | {missing} | "
                f"{calibration_counts} | {unavailable} | {final_counts} | {joint_counts} |"
            )
    lines += ["", "Counts describe recorded attempts, not all possible starts. Missing terminal "
              "regions are unavailable, never assumed to have zero attempts. Partial stage receipts "
              "remain in the summary even when terminal counts are unavailable."]
    return lines


def cost_and_failure_lines(summary):
    lines = ["", "Recorded phase invocation costs:", "",
             "| Member | Search seconds | Native seconds | Zero-led seconds | Recorded sum seconds | Unknown phases |",
             "|---|---:|---:|---:|---:|---:|"]
    for row in summary["rows"]:
        values = [row.get("phase_elapsed_s", {}).get(p) for p in ("search", "native", "zero")]
        known = [v for v in values if v is not None and math.isfinite(v)]
        total = number(sum(known), 3) if known else "unavailable"
        lines.append(f"| {row['label']} | " + " | ".join(number(v, 3) for v in values)
                     + f" | {total} | {3-len(known)} |")
    lines += ["", "Recorded sums omit unknown phases; they are not imputed zero. These are "
              "summed invocation times, not controller wall time or an embedded-speed benchmark. "
              "Shared bootstrap work is counted in the search phase.", "",
              "Failure and qualification reasons:", "",
              "| Member | Phase / stage | Status or reason |", "|---|---|---|"]
    count = 0
    for row in summary["rows"]:
        for phase, status in row["statuses"].items():
            reason = row.get("failure_reasons", {}).get(phase)
            if status != "complete" or reason:
                lines.append(f"| {row['label']} | {phase} | {cell(status)}; {cell(reason)} |")
                count += 1
        for failure in row.get("point_failures", []):
            lines.append(f"| {row['label']} | discovery point | {cell(failure)} |")
            count += 1
        for branch, regions in row.get("regions", {}).items():
            for region in regions:
                reason = region.get("reason")
                if reason or region.get("status") == "unavailable-in-terminal":
                    lines.append(f"| {row['label']} | {branch}/{region['name']} | "
                                 f"{cell(reason or region['status'])} |")
                    count += 1
        for branch, stages in row.get("joint_stages", {}).items():
            for stage, arms in stages.items():
                for arm, qualified in arms.items():
                    if not qualified:
                        lines.append(f"| {row['label']} | {branch}/{stage}/{arm} | unqualified recorded fit |")
                        count += 1
        for phase, stages in row.get("partial_stage_coverage", {}).items():
            for stage in stages:
                if stage.get("claim") and not stage.get("completed"):
                    lines.append(f"| {row['label']} | {phase} | unresolved claim: {cell(stage.get('key'))} |")
                    count += 1
                for record in stage.get("qualification_records", []):
                    if record.get("error") or record.get("reason") or record.get("qualified") is False or record.get("converged") is False:
                        lines.append(f"| {row['label']} | {phase}/{cell(record.get('payload_path'))} | {cell(record)} |")
                        count += 1
    if not count:
        lines.append("| All members | All recorded phases | No failure reason reported |")
    return lines


def publish(summary, directory, plot):
    if not summary.get("all_terminal") or len(summary["rows"]) != 12:
        raise ValueError("all 36 phases must seal before publication")
    directory = Path(directory)
    screen = summary.get("progression", {})
    if "passed" not in screen:
        raise ValueError("sealed progression receipt required; publisher does not decide it")
    plot(summary, directory / "position_errors.png")
    lines = [
        "# Fresh native versus zero-c discovery",
        "",
        "Consumed twelve-member conditional pilot, not independent validation. "
        "Both branches use fresh discovery and the same frozen handoff policy. "
        "Final c arms are matched within each branch. Banks can differ across "
        "discovery policies; frequency scores are not used as cross-policy position evidence.",
        "",
        f"**Predeclared progression screen: {'PASS' if screen['passed'] else 'FAIL'}.** "
        "This displays the frozen reporter's decision receipt, not a new policy decision "
        "or deployment authorization.",
        "",
        "Criteria: complete matched endpoints for all twelve in both final c arms; "
        "fitted-c mean strictly improves over the fresh native control; no fitted-c "
        "member regression exceeds 1 km. c=0 results remain a separately reported sensitivity.",
        "",
        f"Complete comparison: {bool(summary.get('full_comparison_complete'))}; "
        f"fitted-c paired coverage: {screen.get('paired_fitted', 'unavailable')}/12; "
        f"mean fitted-c delta: {number(screen.get('mean_fitted_delta_km'))} km; "
        f"maximum fitted-c delta: {number(screen.get('worst_fitted_regression_km'))} km. "
        "Positive deltas mean zero-led regression. With incomplete coverage, displayed "
        "deltas describe only available pairs and cannot pass the screen.",
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
    lines += qualification_lines(summary)
    lines += cost_and_failure_lines(summary)
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
        "",
        "Raw receipts remain local. Published byte hashes identify retained evidence; "
        "this is not a remote standalone replay bundle. See "
        "[publication scope](PUBLICATION_POLICY.md).",
        "",
        "The [runtime audit](ENVIRONMENT_AUDIT.md) records one shard's interpreter-path "
        "deviation, and the [host observations](HOST_IO_OBSERVATION.md) document I/O "
        "contention included in timed budgets. The [handoff analysis](HANDOFF_OBSERVATIONS.md) "
        "explains why this comparison includes conditional repair opportunities as "
        "well as discovery differences; it does not isolate the grid alone.",
    ]
    with (directory / "RESULTS.md").open("x") as stream:
        stream.write("\n".join(lines) + "\n")
    with (directory / "SUMMARY.json").open("x") as stream:
        json.dump(summary, stream, indent=2, allow_nan=False)
