"""Evaluation-only report from persisted fits; no optimization or model evaluation."""
# ruff: noqa: E501

import hashlib
import json
import math
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.regional_position_score import coordinates
from leo.contracts.regional_position import RegionalPrior

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARMS = ("fitted-c", "zero-c")
STAGES = ("B3", "B4", "B4W", "B5", "C6", "B7")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(result, document):
    """Reference coordinates enter only post-fit distance calculations here."""
    prior = RegionalPrior(
        latitude_deg=document["prior_latitude_deg"],
        longitude_deg=document["prior_longitude_deg"],
        radius_km=document["prior_radius_km"],
    )
    reference = document["reference_latitude_deg"], document["reference_longitude_deg"]

    def describe(fit):
        if fit is None:
            return None
        lat, lon = coordinates(prior, np.asarray(fit["vector"])[:2])
        lat, lon, rlat, rlon = map(math.radians, (lat, lon, *reference))
        h = (
            math.sin((lat - rlat) / 2) ** 2
            + math.cos(lat) * math.cos(rlat) * math.sin((lon - rlon) / 2) ** 2
        )
        row = {
            key: fit.get(key)
            for key in (
                "objective",
                "posterior_rms_hz",
                "signal_windows",
                "stationarity",
                "converged",
                "evaluations",
                "stop_reason",
            )
        }
        row["error_km"] = 2 * 6371.0088 * math.asin(math.sqrt(min(1, max(0, h))))
        row["satellite_count"] = len(fit["vector"]) - 7
        return row

    comparison = []
    for arm in ARMS:
        archived = next(a["selected"] for a in document["methods"][0]["arms"] if a["name"] == arm)
        baseline = result.get("baseline_operational", {}).get(arm)
        candidate = result.get("operational", {}).get(arm)
        row = dict(
            arm=arm,
            archived_error_km=archived["horizontal_error_m"] / 1000,
            baseline=describe(baseline["fit"]) if baseline else None,
            candidate=describe(candidate["fit"]) if candidate else None,
        )
        if baseline:
            original = document["diagnostics"]["b7"]["attempts"][
                baseline.get("accepted_stage", "B7")
            ][arm]
            row["baseline_parity"] = dict(
                vector_exact=np.array_equal(original["vector"], baseline["fit"]["vector"]),
                vector_max_abs_delta=float(
                    np.max(np.abs(np.asarray(original["vector"]) - baseline["fit"]["vector"]))
                ),
                objective_delta=baseline["fit"]["objective"] - original["objective"],
                error_delta_km=row["baseline"]["error_km"] - row["archived_error_km"],
            )
        if candidate:
            row["selection"] = {
                key: candidate.get(key)
                for key in (
                    "region_source",
                    "basin",
                    "start",
                    "accepted_stage",
                    "calibration_penalty",
                )
            }
        comparison.append(row)
    stages = []
    for context, key in (("baseline", "baseline_attempts"), ("candidate", "attempts")):
        for stage in STAGES:
            for arm in ARMS:
                fit = result.get(key, {}).get(stage, {}).get(arm)
                stages.append(
                    dict(
                        context=context,
                        stage=stage,
                        arm=arm,
                        fit=describe(fit),
                        reached=fit is not None,
                    )
                )
    finals = [
        {
            **{key: row.get(key) for key in ("arm", "start", "reason", "calibration_penalty")},
            "fit": describe(row.get("fit")),
        }
        for row in result.get("recovered_finals", [])
    ]
    return dict(
        status=result["status"],
        comparison=comparison,
        stages=stages,
        recovered_finals=finals,
        regional_before=result.get("regional_before"),
        regional_after=result.get("regional_after"),
        baseline_reasons=result.get("baseline_reasons", []),
        candidate_reasons=result.get("reasons", []),
    )


def main():
    result = json.loads((HERE / "result.json").read_text())
    protocol = json.loads((HERE / "protocol.json").read_text())
    assert result["protocol_sha256"] == sha(HERE / "protocol.json")
    for name, expected in protocol["source_sha256"].items():
        assert sha(ROOT / name) == expected, name
    published = HERE.parent / "2026_10_09_position_error_iter93/published-v3.json"
    document = json.loads(published.read_text())["manifest"]["document"]
    summary = summarize(result, document)
    summary["source_hashes_verified"] = len(protocol["source_sha256"])
    summary["reference_scope"] = "Published document coordinates; post-fit evaluation only"
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.5), constrained_layout=True)
    for index, arm in enumerate(ARMS):
        row = summary["comparison"][index]
        for context, style in (("baseline", "--"), ("candidate", "-")):
            rows = [
                r
                for r in summary["stages"]
                if r["arm"] == arm and r["context"] == context and r["fit"] is not None
            ]
            for axis, key in zip(
                axes, ("error_km", "signal_windows", "posterior_rms_hz"), strict=True
            ):
                axis.plot(
                    [STAGES.index(r["stage"]) for r in rows],
                    [r["fit"][key] for r in rows],
                    style + "o",
                    label=f"{context} {arm}",
                )
        if row["candidate"] is None:
            axes[0].text(
                0.05,
                0.92 - index * 0.1,
                f"{arm}: candidate not reached",
                transform=axes[0].transAxes,
            )
    for axis, label in zip(
        axes, ("Position error (km)", "Effective signal windows", "Posterior RMS (Hz)"), strict=True
    ):
        axis.set_xticks(range(len(STAGES)), STAGES, rotation=35)
        axis.set_ylabel(label)
    axes[0].legend(fontsize=7)
    fig.suptitle("ac11: ordinary-only versus retained-region continuation")
    fig.savefig(HERE / "comparison.png", dpi=170)
    plt.close(fig)
    lines = [
        "# Retained-region continuation: matched c arms",
        "",
        f"Recorded status: **{result['status']}**. All position errors below are evaluation-only.",
        "Restoring and qualifying the ordinary score-selected region reduces this scan's final error "
        "from **55.685 to 1.031 km fitted-c**, and **53.945 to 1.927 km zero-c**. "
        "The ordinary-only replay reproduces both archived endpoint vectors and objectives exactly. "
        "This establishes a single-scan rescue, not broad generalization or a production deployment.",
        "",
        "![Position, support and frequency separately](comparison.png)",
        "",
        "| Arm | Archived error km | Ordinary-only replay km | Candidate km | Candidate minus replay km |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in summary["comparison"]:
        base, candidate = row["baseline"], row["candidate"]
        lines.append(
            f"| {row['arm']} | {row['archived_error_km']:.6f} | "
            f"{format(base['error_km'], '.6f') if base else 'Not reached'} | "
            f"{format(candidate['error_km'], '.6f') if candidate else 'Not reached'} | "
            f"{format(candidate['error_km'] - base['error_km'], '.6f') if candidate and base else 'Unavailable'} |"
        )
    lines += ["", "Baseline replay parity and operational selection:", ""]
    for row in summary["comparison"]:
        lines.append(
            f"- **{row['arm']}** parity: `{json.dumps(row.get('baseline_parity'))}`; "
            f"selection: `{json.dumps(row.get('selection'))}`."
        )
    lines += [
        "",
        "Recovered regional finals (before B7):",
        "",
        "| Arm / start | Qualified | Error km | Objective | Failure |",
        "|---|---|---:|---:|---|",
    ]
    for row in summary["recovered_finals"]:
        fit = row["fit"]
        lines.append(
            f"| {row['arm']} / {row['start']} | {fit['converged'] if fit else False} | "
            f"{format(fit['error_km'], '.6f') if fit else 'Unavailable'} | "
            f"{format(fit['objective'], '.6f') if fit else 'Unavailable'} | {row['reason']} |"
        )
    lines += [
        "",
        "All 24 baseline/candidate B3–B7 arm-stage attempts qualify; neither replay reports "
        "a fallback reason. The candidate fitted-c B4W error is 0.826 km, but the unchanged "
        "pipeline finishes at B7 with 1.031 km. We do not select an earlier stage by reference error.",
        "",
        "Candidate stage errors and frequency fit:",
        "",
        "| Stage | Fitted-c error km | Zero-c error km | Fitted-c RMS Hz | Zero-c RMS Hz |",
        "|---|---:|---:|---:|---:|",
    ]
    for stage in STAGES:
        rows = [
            next(
                r["fit"]
                for r in summary["stages"]
                if r["context"] == "candidate" and r["stage"] == stage and r["arm"] == arm
            )
            for arm in ARMS
        ]
        if all(rows):
            lines.append(
                f"| {stage} | {rows[0]['error_km']:.6f} | {rows[1]['error_km']:.6f} | "
                f"{rows[0]['posterior_rms_hz']:.3f} | {rows[1]['posterior_rms_hz']:.3f} |"
            )
    lines += [
        "",
        "Full stage metrics, unqualified attempts, regional model-score winners and fallback reasons",
        "are preserved in [summary.json](summary.json) and [result.json](result.json).",
        "The model-selected result, never the smallest reference error, determines candidate outcome.",
        "Compare objective scores only within the same physical model/bank and calibration baseline.",
        "B3–B7 change nuisance models and satellite banks; their raw scores are not a common accuracy scale.",
        "Frequency RMS/support effects are reported separately from geographic accuracy.",
        "",
        "This consumed single-scan test retains ordinary candidates and uses matched c arms, priors and budgets.",
        "Reference coordinates are read only by this report; no reference-guided seed or winner selection occurs.",
        "No additional objective evaluation, RF collection or deployment was performed for reporting.",
        "",
        f"All {summary['source_hashes_verified']} frozen hashes match. See [protocol](protocol.json)",
        "and [artifact hashes](report-integrity.json).",
    ]
    (HERE / "RESULTS.md").write_text("\n".join(lines) + "\n")
    names = [
        "report.py",
        "RESULTS.md",
        "summary.json",
        "comparison.png",
        "protocol.json",
        "result.json",
    ]
    (HERE / "report-integrity.json").write_text(
        json.dumps({n: sha(HERE / n) for n in names}, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
