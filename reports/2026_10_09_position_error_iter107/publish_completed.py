"""Format completed reporting snapshots, plots and integrity; no inference calls."""

import argparse
import hashlib
import json
import runpy
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(stem):
    source = HERE / (stem + "_COMPLETE_SNAPSHOT.json")
    data = json.loads(source.read_text())
    rows = data["rows"]
    assert len(rows) == (63 if stem == "DS16" else 193)
    assert not data["metrics"]["full_census_position_metrics_withheld"]
    if stem == "FULL193":
        assert len(data["subset_snapshot_sha256"]) == 4
        data["subset_integrity_sha256"] = {}
        for name, digest in data["subset_snapshot_sha256"].items():
            assert sha(HERE / name) == digest
            prefix = name.split("_COMPLETE_SNAPSHOT")[0].lower()
            manifest = HERE / (prefix + "-complete-integrity.json")
            bound = json.loads(manifest.read_text())
            artifacts = bound.get(
                "artifacts", bound.get("artifact_sha256", bound.get("artifacts_sha256"))
            )
            assert [v for k, v in artifacts.items() if Path(k).name == name] == [digest]
            data["subset_integrity_sha256"][manifest.name] = sha(manifest)
    protocol = HERE / "protocol.json"
    if protocol.exists():
        assert sha(protocol) == data["protocol_sha256"]
        plan = json.loads(protocol.read_text())
        report = runpy.run_path(str(HERE / "report.py"))
        groups = {"historical48": [], "additional15": []}
        for member in plan["members"]:
            if member["member"].get("dataset") == "DS16":
                group = "historical48" if member["member"]["legacy_labels"] else "additional15"
                groups[group].append(report["member_label"](member))
        assert len(groups["historical48"]) == 48 and len(groups["additional15"]) == 15
        data["ds16_coverage_groups"] = {
            g: {
                "labels": labels,
                "metrics": report["aggregate"]([r for r in rows if r["label"] in labels]),
            }
            for g, labels in groups.items()
        }
        source.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    png = HERE / (stem.lower() + "-complete.png")
    runpy.run_path(str(HERE / "plot_completed.py"))["plot"](data, png)
    lines = [
        f"# {stem}: completed matched recovery comparison",
        "",
        f"All {len(rows)} members are terminal. These are consumed development recordings, "
        "not independent validation. Known coordinates were used only after sealed selections "
        "for this report. No new fits, objective evaluations or RF collection were performed.",
        "",
        "| Dataset | Arm | Phase | Mean km | Median km | p95 km | Worst km |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    fit = data["metrics"]["arms"]["fitted-c"]
    lines[4:4] = [
        f"Fitted-c mean changes from {fit['baseline']['mean_km']:.6f} to "
        f"{fit['candidate']['mean_km']:.6f}km; median changes from "
        f"{fit['baseline']['median_km']:.6f} to {fit['candidate']['median_km']:.6f}km. "
        "The 0.4km mean target is not achieved.",
        "",
    ]
    if stem == "FULL193":
        lines[4:4] = [
            "This full census merges the four sealed completed dataset reports. Their integrity "
            "manifests and all 386 current baseline/candidate phase receipt hashes were verified "
            "before publication; no additional recording reconstruction or reference query was "
            "needed for the merge.",
            "",
        ]
    for dataset, metrics in data["datasets"].items():
        for arm, value in metrics["arms"].items():
            for phase in ("baseline", "candidate"):
                m = value[phase]
                lines.append(
                    f"| {dataset} | {arm} | {phase} | "
                    + " | ".join(
                        f"{m[k]:.6f}" for k in ("mean_km", "median_km", "p95_km", "worst_km")
                    )
                    + " |"
                )
    if "ds16_coverage_groups" in data:
        for group, value in data["ds16_coverage_groups"].items():
            for arm, metrics in value["metrics"]["arms"].items():
                for phase in ("baseline", "candidate"):
                    m = metrics[phase]
                    lines.append(
                        f"| DS16 {group} | {arm} | {phase} | "
                        + " | ".join(
                            f"{m[k]:.6f}" for k in ("mean_km", "median_km", "p95_km", "worst_km")
                        )
                        + " |"
                    )
    if stem != "DS16":
        for arm, value in data["metrics"]["arms"].items():
            for phase in ("baseline", "candidate"):
                m = value[phase]
                lines.append(
                    f"| Full193 | {arm} | {phase} | "
                    + " | ".join(
                        f"{m[k]:.6f}" for k in ("mean_km", "median_km", "p95_km", "worst_km")
                    )
                    + " |"
                )
    lines += [
        "",
        "p95 uses linear interpolation. DS16 includes all 63 authority members: "
        "the historical 48 and all 15 additional members. DS18 includes its sealed unpublished "
        "member; its ten unmatched exposure records are not claimed unseen. Newer development "
        "includes only 001–008 and 017–053; reserves 009–016 remain closed.",
        "",
    ]
    if "ds16_coverage_groups" in data:
        labels = data["ds16_coverage_groups"]["additional15"]["labels"]
        lines.append(
            "Additional DS16 membership (authority legacy-label mapping, not index "
            "range): " + ", ".join(labels) + "."
        )
    changed = [
        r["label"] for r in rows if not all(all(p.values()) for p in r["exact_parity"].values())
    ]
    lines += [
        "Selected vector/clock/objective changes: " + (", ".join(changed) or "none") + ".",
        "",
    ]
    lines += [
        "| Changed member | Fitted before km | Fitted after km | Zero before km | Zero after km |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        if row["label"] in changed:
            values = [
                row["arms"][a][p]["error_km"]
                for a in ("fitted-c", "zero-c")
                for p in ("baseline", "candidate")
            ]
            lines.append(
                "| " + row["label"] + " | " + " | ".join(f"{value:.9f}" for value in values) + " |"
            )
    lines.append("")
    worst = max(rows, key=lambda r: r["arms"]["fitted-c"]["candidate"]["error_km"])
    lines.append(
        f"Remaining fitted-c worst case: {worst['label']} at "
        f"{worst['arms']['fitted-c']['candidate']['error_km']:.6f}km. "
        "The unchanged median means this recovery experiment does not demonstrate "
        "a broad improvement in typical position error."
    )
    lines.append("")
    for arm, value in data["metrics"]["arms"].items():
        regressions = value["paired_regressions"]
        lines.append(
            f"{arm}: {len(regressions)} paired regressions (>1e−9km): "
            + (", ".join(f"{r['label']} ({r['delta_km']:+.9f}km)" for r in regressions) or "none")
            + "."
        )
    trigger_count = sum(r["trigger_count"] for r in rows)
    recoveries = [v for r in rows for v in r["recoveries"]]
    lines += [
        "",
        f"There were {trigger_count} triggers and {len(recoveries)} saved recovery outcomes. "
        f"Candidate fallbacks: {sum(bool(r['candidate_fallback']) for r in rows)}. "
        f"Explicit baseline/candidate terminal failures: "
        f"{sum(r['baseline_status'] != 'complete' for r in rows)}/"
        f"{sum(r['candidate_status'] != 'complete' for r in rows)}.",
        "",
        "Recovery outcomes: "
        + json.dumps(
            {
                s: sum(v["calibration_status"] == s for v in recoveries)
                for s in sorted({v["calibration_status"] for v in recoveries})
            }
        )
        + ".",
        "",
    ]
    failed_recoveries = [
        r["label"] for r in rows if any(not v["calibration_qualified"] for v in r["recoveries"])
    ]
    lines.append(
        "Members with unqualified recovered calibration: "
        + (", ".join(failed_recoveries) or "none")
        + "."
    )
    for arm in ("fitted-c", "zero-c"):
        reached = [v for v in recoveries if v["association_available"]]
        qualified = sum(v["final_qualified_counts"][arm] for v in reached)
        lines.append(
            f"Recovered-region {arm} finals: {qualified}/{3 * len(reached)} qualified; "
            f"{3 * len(reached) - qualified} raw unqualified finals are retained."
        )
    for phase in ("baseline", "candidate"):
        failures = sum(len(r["stage_failures"][phase]) for r in rows)
        lines.append(
            f"{phase}: {failures} explicit stage failures; full member-level details "
            "remain in the JSON snapshot."
        )
    for phase in ("baseline", "candidate"):
        seconds = sum(r["runtime"][phase]["known_elapsed_s"] for r in rows)
        slices = sum(r["runtime"][phase]["completed_slices"] for r in rows)
        lines.append(
            f"{phase}: {seconds:.3f}s across {slices} completed slices; this is persisted "
            "slice elapsed time, not a sum of nested optimizer times or a CPU benchmark."
        )
        for arm in ("fitted-c", "zero-c"):
            endpoints = [r["arms"][arm][phase] for r in rows]
            rms = [v["posterior_rms_hz"] for v in endpoints]
            support = [v["signal_windows"] for v in endpoints]
            lines.append(
                f"{phase} {arm}: {sum(v['converged'] for v in endpoints)}/{len(rows)} "
                f"selected endpoints qualified; mean/median RMS {np.mean(rms):.6f}/"
                f"{np.median(rms):.6f}Hz; mean signal-window support {np.mean(support):.6f}."
            )
    lines += [
        "",
        "| Dataset | Arm | Phase | Mean RMS Hz | Mean signal-window support |",
        "|---|---|---|---:|---:|",
    ]
    for dataset in data["datasets"]:
        selected = [r for r in rows if r["dataset"] == dataset]
        for arm in ("fitted-c", "zero-c"):
            for phase in ("baseline", "candidate"):
                endpoints = [r["arms"][arm][phase] for r in selected]
                lines.append(
                    f"| {dataset} | {arm} | {phase} | "
                    f"{np.mean([v['posterior_rms_hz'] for v in endpoints]):.6f} | "
                    f"{np.mean([v['signal_windows'] for v in endpoints]):.6f} |"
                )
    lines += [
        "",
        "The candidate is a shadow recovery pass over an already completed fresh baseline. "
        "Its elapsed time is additional replay/recovery cost, not standalone pipeline runtime "
        "or evidence that the candidate is faster than baseline. Operational total cost would "
        "include the baseline analysis plus any recovery work.",
        "",
        "Frequency fit is separate from positioning. Banks and associations may change "
        "between regions; final B7 objective changes do not establish better localization. "
        "The regional winner is selected before B3–B7 using the existing regional score and "
        "calibration penalty. Ordinary regions are preserved; no reference-guided selection "
        "or cross-model score selection is introduced.",
        "The c arms use the same recording inputs, ordinary search policy, priors and budgets; "
        "c=0 locks static c and its RF time terms. Adaptive associations and final satellite "
        "support can differ by arm, so the reported fitted/zero differences describe the "
        "matched pipeline ablation, not a fixed-final-bank causal estimate.",
        "",
        f"![Matched position errors]({png.name})",
        "",
        f"[Full membership, failures and receipt hashes]({source.name}). "
        "The full raw corpus (57GB) remains intact locally and is not remotely published. "
        "A measured 139MB phase receipt compressed to 23MB with deterministic gzip6, "
        "implying a multi-GB archive rather than a lean Git artifact. The compact snapshot "
        "binds all phase receipts by SHA256; remote report reproduction uses that snapshot, "
        "while full raw replay requires the retained local receipts. No complete raw archive "
        "was created or claimed remotely reproducible.",
    ]
    markdown = HERE / (stem + "_COMPLETE_SNAPSHOT.md")
    markdown.write_text("\n".join(lines) + "\n")
    integrity = {
        "protocol_sha256": data["protocol_sha256"],
        "subset_snapshot_sha256": data.get("subset_snapshot_sha256", {}),
        "receipt_sha256": data["receipt_sha256"],
        "artifacts": {
            p.name: sha(p)
            for p in (
                source,
                markdown,
                png,
                HERE / "report_completed.py",
                HERE / "report.py",
                HERE / "plot_completed.py",
                HERE / "publish_completed.py",
            )
            if p.exists()
        },
    }
    if stem == "FULL193":
        integrity["artifacts"]["merge_completed.py"] = sha(HERE / "merge_completed.py")
    (HERE / (stem.lower() + "-complete-integrity.json")).write_text(
        json.dumps(integrity, indent=2) + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stem", choices=("DS16", "FULL193"))
    main(parser.parse_args().stem)
