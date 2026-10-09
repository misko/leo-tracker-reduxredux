"""Publish complete qualification coverage and position/frequency metrics separately."""

import hashlib
import json
import math
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure

from leo.analysis.regional_position_score import coordinates
from leo.cli.regional_position import REFERENCE
from leo.contracts.regional_position import RegionalPrior

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "2026_10_09_position_error_iter85"
ARMS = ("fitted-c", "zero-c")


def error_km(vector):
    latitude, longitude = coordinates(RegionalPrior(), vector[:2])
    lat, lon, ref_lat, ref_lon = map(math.radians, (latitude, longitude, *REFERENCE))
    h = (
        math.sin((lat - ref_lat) / 2) ** 2
        + math.cos(lat) * math.cos(ref_lat) * math.sin((lon - ref_lon) / 2) ** 2
    )
    return 2 * 6371.0088 * math.asin(math.sqrt(min(1, max(0, h))))


def distribution(values):
    return dict(
        mean=float(np.mean(values)),
        median=float(np.median(values)),
        p95=float(np.percentile(values, 95)),
        worst=float(np.max(values)),
    )


if __name__ == "__main__":
    plan = json.loads((PREVIOUS / "protocol.json").read_text())
    rows, hashes = [], {}
    for binding in plan["members"]:
        member = binding["member"]
        label = member["inventory_label"]
        path = HERE / "qualification" / f"{label}.json"
        result = json.loads(path.read_text())
        assert all(c["passed"] for c in result["comparisons"].values())
        hashes[label] = hashlib.sha256(path.read_bytes()).hexdigest()
        before = json.loads((PREVIOUS / "results" / f"{label}.json").read_text())
        arms = {}
        for arm in ARMS:
            fit = result["operational"][arm]["fit"]
            old = before["stages"]["B0"][arm]
            arms[arm] = dict(
                baseline_error_km=old["error_km"],
                candidate_error_km=error_km(fit["vector"]),
                baseline_rms_hz=old["posterior_rms_hz"],
                candidate_rms_hz=fit["posterior_rms_hz"],
                converged=fit["converged"],
                accepted_stage=result["operational"][arm]["accepted_stage"],
                objective_delta=result["comparisons"][arm]["objective_delta"],
                position_delta_m=result["comparisons"][arm]["position_delta_m"],
            )
        rows.append(dict(member=member, arms=arms))
    metrics = {}
    for dataset in ("DS16", "DS17", "DS18", "pooled"):
        selected = [r for r in rows if dataset == "pooled" or r["member"]["dataset"] == dataset]
        metrics[dataset] = {}
        for arm in ARMS:
            pairs = [r["arms"][arm] for r in selected]
            delta = np.array([r["candidate_error_km"] - r["baseline_error_km"] for r in pairs])
            metrics[dataset][arm] = dict(
                count=len(pairs),
                baseline_km=distribution([r["baseline_error_km"] for r in pairs]),
                candidate_km=distribution([r["candidate_error_km"] for r in pairs]),
                baseline_frequency_rms_hz=distribution([r["baseline_rms_hz"] for r in pairs]),
                candidate_frequency_rms_hz=distribution([r["candidate_rms_hz"] for r in pairs]),
                improved=int((delta < -1e-9).sum()),
                regressed=int((delta > 1e-9).sum()),
                regressions_over_100m=int((delta > 0.1).sum()),
                largest_regression_km=float(delta.max()),
                converged=sum(r["converged"] for r in pairs),
                fallbacks=sum(r["accepted_stage"] != "B7" for r in pairs),
            )
    summary = dict(
        metrics=metrics,
        rows=rows,
        qualification_receipt_sha256=hashes,
        missing_inputs=[],
        excluded=[],
        scope="Fresh production downstream refits from frozen regional inputs; "
        "consumed development data",
    )
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    figure = Figure(figsize=(13, 4), layout="constrained")
    for axis, dataset in zip(figure.subplots(1, 3), ("DS16", "DS17", "DS18"), strict=True):
        subset = [r["arms"]["fitted-c"] for r in rows if r["member"]["dataset"] == dataset]
        axis.scatter(
            [r["baseline_error_km"] for r in subset],
            [r["candidate_error_km"] for r in subset],
            s=22,
            alpha=0.8,
            color="#176b87",
        )
        axis.plot([0.01, 400], [0.01, 400], "--", color="gray", linewidth=1)
        axis.set(
            xscale="log",
            yscale="log",
            xlim=(0.01, 400),
            ylim=(0.01, 400),
            xlabel="Deployed B0 error (km)",
            ylabel="Production B7 error (km)",
            title=f"{dataset}: all {len(subset)} recordings",
        )
        axis.grid(alpha=0.2)
    figure.suptitle("Production B7 qualification • fitted c • below diagonal means improvement")
    figure.savefig(HERE / "position-errors.png", dpi=160)
    lines = [
        "# Full qualification coverage",
        "",
        "All 148 members are consumed development data. No quality exclusions.",
        "",
        "| Dataset | Arm | B0 mean | B7 mean | B7 median | B7 p95 | B7 worst "
        "| Converged | Fallbacks | Regressions |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for dataset, arms in metrics.items():
        for arm, m in arms.items():
            c = m["candidate_km"]
            lines.append(
                f"| {dataset} | {arm} | {m['baseline_km']['mean']:.6f} | {c['mean']:.6f} "
                f"| {c['median']:.6f} | {c['p95']:.6f} | {c['worst']:.6f} "
                f"| {m['converged']}/{m['count']} | {m['fallbacks']} | {m['regressed']} |"
            )
    lines += [
        "",
        "Position errors are in km. Frequency RMS distributions and paired regressions "
        "are separate in [summary.json](summary.json).",
        "",
        "![Position errors](position-errors.png)",
        "",
        "## Membership",
        "",
        "DS16 includes the original 48 and the other 15. DS18 includes the previously "
        "consumed 24 and the other 10; the latter are not claimed unseen. "
        "Member metadata and exposure labels are preserved in summary.json.",
        "",
        "| Member | Session | Fitted-c B0 km | Fitted-c B7 km | Zero-c B7 km | Parity delta m |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        a, z = row["arms"]["fitted-c"], row["arms"]["zero-c"]
        lines.append(
            f"| {row['member']['inventory_label']} | {row['member']['session_id']} "
            f"| {a['baseline_error_km']:.6f} | {a['candidate_error_km']:.6f} "
            f"| {z['candidate_error_km']:.6f} "
            f"| {max(a['position_delta_m'], z['position_delta_m']):.6f} |"
        )
    (HERE / "QUALIFICATION.md").write_text("\n".join(lines) + "\n")
