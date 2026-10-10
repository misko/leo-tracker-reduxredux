"""Post-terminal catalogue diagnostic reporting; no model or reference ports."""

# Ruff: Markdown table literals intentionally keep each rendered row together.
# ruff: noqa: E501

import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARMS = ("fitted-c", "zero-c")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_terminal(root, directory):
    protocol = directory / "protocol.json"
    plan = json.loads(protocol.read_text())
    digest = sha(protocol)
    members = plan["members"]
    labels = [m["label"] for m in members]
    if len(labels) != 12 or len(set(labels)) != 12:
        raise ValueError("Exact twelve-member authority required")
    for group in ("sources", "inputs"):
        for name, expected in plan[group].items():
            if sha(root / name) != expected:
                raise ValueError("Frozen binding changed: " + name)
    rows, receipts = [], {}
    for label in labels:
        path = directory / "results" / (label + ".json")
        claim = path.with_suffix(".claim.json")
        for receipt in (path, claim):
            document = json.loads(receipt.read_text())
            if document.get("label") != label or document.get("protocol_sha256") != digest:
                raise ValueError("Foreign receipt or claim")
            receipts[str(receipt.relative_to(root))] = sha(receipt)
        row = json.loads(path.read_text())
        snapshot = path.with_suffix(".snapshots.json")
        if snapshot.exists():
            saved = json.loads(snapshot.read_text())
            if (
                saved.get("label") != label
                or saved.get("protocol_sha256") != digest
                or saved.get("selection") != row.get("snapshots")
            ):
                raise ValueError("Foreign or inconsistent snapshot receipt")
            receipts[str(snapshot.relative_to(root))] = sha(snapshot)
        if row.get("status") not in ("complete", "failed"):
            raise ValueError("All twelve must be terminal before reporting")
        if row.get("optimizer_calls") != 0:
            raise ValueError("Unexpected optimization")
        calls = row.get("ordinary_endpoint_evaluations", 0)
        if not isinstance(calls, int) or not 0 <= calls <= 2:
            raise ValueError("Endpoint call budget exceeded")
        if any(arm not in ARMS for arm in row.get("arms", {})):
            raise ValueError("Unexpected arm")
        rows.append(row)
    return rows, dict(protocol_sha256=digest, receipts=receipts)


def summarize(rows):
    labels = [r["label"] for r in rows]
    if len(rows) != 12 or len(set(labels)) != 12:
        raise ValueError("Full twelve-member coverage required")
    if any(r.get("status") not in ("complete", "failed") for r in rows):
        raise ValueError("Nonterminal coverage")
    counts = {s: sum(r["status"] == s for r in rows) for s in ("complete", "failed")}
    arms = {}
    for arm in ARMS:
        entries = []
        for row in rows:
            value = row.get("arms", {}).get(arm)
            if value is None:
                continue
            p = value["projection"]
            total = p["total_weighted_energy"]
            original = value["original_weight"]
            entries.append(
                dict(
                    label=row["label"],
                    member_status=row["status"],
                    total_weighted_energy=total,
                    energy_fractions={
                        key: p[key] / total if total > 0 else None
                        for key in (
                            "nuisance_energy",
                            "spatial_conditional_energy",
                            "outside_energy",
                        )
                    },
                    retained_rows=p["retained_rows"],
                    original_row_count=p["original_row_count"],
                    positive_weight_rows=p["positive_weight_rows"],
                    prediction_delta_rms_hz=value["prediction_delta_rms_hz"],
                    original_weight=original,
                    omitted_original_weight=value["omitted_original_weight"],
                    omitted_weight_fraction=value["omitted_original_weight"] / original
                    if original > 0
                    else None,
                    original_candidates=len(value["original_ids"]),
                    common_valid_candidates=len(value["common_valid_ids"]),
                    propagation_filtered_candidates=len(value["propagation_filtered_ids"]),
                    visibility_changes=value["visibility_changes"],
                    event_normalizer_nll_delta=value["event_normalizer_nll_delta"],
                    event_normalizer_scope=value["event_normalizer_scope"],
                )
            )
        arms[arm] = dict(available=len(entries), unavailable=12 - len(entries), entries=entries)
    return dict(
        counts=counts,
        arms=arms,
        members=[
            dict(
                label=r["label"],
                status=r["status"],
                error=r.get("error"),
                outcome=r.get("outcome"),
                admissions=r.get("admissions", {}),
                snapshots=r.get("snapshots"),
                propagation=r.get("propagation"),
                reconstruction_completed=r.get("reconstruction_completed", False),
                reconstruction_work=r.get("reconstruction_work"),
                ordinary_endpoint_evaluations=r.get("ordinary_endpoint_evaluations", 0),
                elapsed_s=r.get("elapsed_s"),
                available_arms=list(r.get("arms", {})),
            )
            for r in rows
        ],
        terminal_all_complete=counts["failed"] == 0,
        full_metrics_available=(
            counts["failed"] == 0
            and all(
                arms[arm]["available"] == 12
                and all(
                    e["common_valid_candidates"] == e["original_candidates"]
                    for e in arms[arm]["entries"]
                )
                for arm in ARMS
            )
        ),
    )


def plot(summary, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(3, 2, figsize=(13, 12), layout="constrained")
    for column, arm in enumerate(ARMS):
        entries = summary["arms"][arm]["entries"]
        x = np.arange(len(entries))
        bottom = np.zeros(len(entries))
        for key, label in (
            ("nuisance_energy", "Nuisance span"),
            ("spatial_conditional_energy", "Additional spatial span"),
            ("outside_energy", "Outside combined span"),
        ):
            values = np.array(
                [
                    e["energy_fractions"][key] if e["energy_fractions"][key] is not None else np.nan
                    for e in entries
                ]
            )
            axes[0, column].bar(x, values, bottom=bottom, label=label)
            bottom += np.nan_to_num(values)
        axes[0, column].set(
            title=f"{arm}: {len(entries)}/12 available",
            ylabel="Fraction of retained weighted Δ² energy",
            ylim=(0, 1.05),
        )
        axes[1, column].bar(x, [e["prediction_delta_rms_hz"] for e in entries])
        axes[1, column].set(ylabel="Unweighted common-candidate Δ RMS (Hz)")
        for key, label, marker in (
            ("spatial_conditional_energy", "Additional spatial", "o"),
            ("outside_energy", "Outside combined span", "x"),
        ):
            values = [e["energy_fractions"][key] for e in entries]
            positive = np.array([v if v is not None and v > 0 else np.nan for v in values])
            zero_count = sum(v == 0 for v in values if v is not None)
            undefined_count = sum(v is None for v in values)
            axes[2, column].plot(
                x,
                positive,
                marker=marker,
                linestyle="none",
                label=f"{label} (zero {zero_count}, undefined {undefined_count})",
            )
        axes[2, column].set(yscale="log", ylabel="Small energy fractions (log; positives only)")
        axes[2, column].legend(fontsize=8)
        for ax in axes[:, column]:
            ax.set_xticks(x, [e["label"] for e in entries], rotation=65, ha="right")
        axes[0, column].legend(fontsize=8)
    fig.suptitle("Fixed endpoint catalogue sensitivity; missing arms omitted, never imputed")
    fig.savefig(path, dpi=150)
    plt.close(fig)


def markdown(summary):
    outcomes = {}
    for row in summary["members"]:
        key = row["outcome"] or row["status"]
        outcomes[key] = outcomes.get(key, 0) + 1
    findings = []
    for arm in ARMS:
        entries = summary["arms"][arm]["entries"]
        fractions = [
            e["energy_fractions"]["nuisance_energy"]
            for e in entries
            if e["energy_fractions"]["nuisance_energy"] is not None
        ]
        if fractions:
            findings.append(
                f"{arm}: nuisance-span fraction {100 * min(fractions):.6f}%–"
                f"{100 * max(fractions):.6f}% across {len(fractions)} nonzero-energy comparisons"
            )
    lines = [
        "# Iteration 144 catalogue sensitivity",
        "",
        "The frozen reference-free policy inspects at most 10 distinct earlier catalogue payloads "
        "within 24 hours and selects the first changed payload for the original satellite bank. "
        "The original endpoints, responsibilities, derivative spans and candidate policy remain fixed.",
        "",
        "Recorded outcomes: "
        + ", ".join(f"{key}: {value}" for key, value in outcomes.items())
        + ".",
        " ".join(findings)
        + (
            ". This is local prediction-space absorption, not a fitted catalogue "
            "comparison or evidence of improved localization."
            if findings
            else ""
        ),
        "",
        f"All 12 members are terminal: {summary['counts']['complete']} complete, {summary['counts']['failed']} failed. Failed members and partial arms remain in coverage. No optimizer was run.",
        "",
        "This consumed development diagnostic changes catalogue predictions at fixed endpoints. It establishes neither position improvement nor independent validation. Local free derivative spans exclude priors and bounds; their energy fractions are not covariance or calibrated uncertainty.",
        "",
        "![Catalogue sensitivity](catalogue_sensitivity.png)",
        "",
        "Fractions use retained common-candidate weighted Δ² energy. Zero-energy fractions are undefined. Frequency RMS uses unweighted retained observation×candidate rows. Missing arms are omitted from the figure, never assigned zero; the tables disclose their denominators and omitted original responsibility-weight mass. Visibility counts and event-normalizer changes are separate from the frozen-visibility derivative projection.",
        "The third figure row expands small additional spatial/outside fractions on a logarithmic "
        "axis. Exact zeros and undefined fractions are counted in its legend and omitted from that "
        "axis; no plotting floor is substituted.",
        "",
        "| Member | Status | Admissions | Available arms | Error |",
        "|---|---|---|---|---|",
    ]
    for r in summary["members"]:
        admissions = ", ".join(f"{k}: {v['status']}" for k, v in r["admissions"].items())
        lines.append(
            f"| {r['label']} | {r['status']} | {admissions} | {', '.join(r['available_arms']) or 'none'} | {str(r['error'] or '').replace('|', '/')} |"
        )
    for arm in ARMS:
        lines += [
            "",
            f"## {arm}",
            "",
            f"Available {summary['arms'][arm]['available']}/12; unavailable {summary['arms'][arm]['unavailable']}/12.",
            "",
            "| Member | Rows retained/original (positive W) | Candidates common/original | Δ RMS Hz | Original W | Omitted W (%) | Visibility changes | Event NLL Δ |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for e in summary["arms"][arm]["entries"]:
            omitted = (
                "undefined"
                if e["omitted_weight_fraction"] is None
                else f"{100 * e['omitted_weight_fraction']:.3f}%"
            )
            event = (
                "unavailable"
                if e["event_normalizer_nll_delta"] is None
                else f"{e['event_normalizer_nll_delta']:.6g}"
            )
            lines.append(
                f"| {e['label']} ({e['member_status']}) | {e['retained_rows']}/{e['original_row_count']} ({e['positive_weight_rows']}) | {e['common_valid_candidates']}/{e['original_candidates']} | {e['prediction_delta_rms_hz']:.6g} | {e['original_weight']:.6g} | {e['omitted_original_weight']:.6g} ({omitted}) | {e['visibility_changes']} | {event} |"
            )
        lines += [
            "",
            "| Member | Retained weighted Δ² energy | Nuisance % | Additional spatial % | Outside % |",
            "|---|---|---|---|---|",
        ]
        for e in summary["arms"][arm]["entries"]:
            fractions = [
                "undefined" if value is None else f"{100 * value:.4f}"
                for value in e["energy_fractions"].values()
            ]
            lines.append(
                f"| {e['label']} | {e['total_weighted_energy']:.8g} | {' | '.join(fractions)} |"
            )
    lines += [
        "",
        "Full-cohort aggregate conclusions are withheld when any member fails. No changed earlier catalogue is a recorded complete outcome without a sensitivity arm, not a zero effect. Snapshot inspection/admission errors and propagation filtering are preserved in [summary.json](summary.json). [REPORT_INTEGRITY.json](REPORT_INTEGRITY.json) binds protocol, terminal claims, receipts and generated artifacts.",
    ]
    return "\n".join(lines) + "\n"


def main():
    rows, integrity = load_terminal(ROOT, HERE)
    summary = summarize(rows)
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    plot(summary, HERE / "catalogue_sensitivity.png")
    (HERE / "RESULTS.md").write_text(markdown(summary))
    integrity["artifacts"] = {
        name: sha(HERE / name)
        for name in (
            "summary.json",
            "catalogue_sensitivity.png",
            "RESULTS.md",
            "report.py",
            "test_report.py",
        )
    }
    (HERE / "REPORT_INTEGRITY.json").write_text(json.dumps(integrity, indent=2) + "\n")


if __name__ == "__main__":
    main()
