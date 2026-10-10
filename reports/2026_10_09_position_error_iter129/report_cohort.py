"""Postseal pilot reporting; no observations, predictions, objectives or fits."""

import hashlib
import json
import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BRANCHES = ("native", "fixed")
ARMS = ("fitted-c", "zero-c")
TERMINAL = {"complete", "failed", "incomplete", "budget-exhausted", "not-run-search-failed"}


def compact_receipt(receipt):
    """Discard large association arrays after recording each raw-file byte hash."""
    result = {
        key: receipt.get(key)
        for key in (
            "status",
            "label",
            "branch",
            "reason",
            "reasons",
            "fallback_available",
            "elapsed_s",
        )
    }
    result["operational"] = receipt.get("operational", {})
    result["regions"] = []
    for name, region in receipt.get("regions", {}).items():
        recovery = region.get("recovery") or {}
        calibration = recovery.get("result") or {}
        finals = region.get("finals", [])
        result["regions"].append(
            dict(
                name=name,
                calibration_status=calibration.get("status"),
                calibration_available=calibration.get("calibration") is not None,
                reason=recovery.get("reason") or calibration.get("error"),
                association_available=bool((region.get("association") or {}).get("result")),
                finals={
                    arm: dict(
                        attempts=sum(f.get("arm") == arm for f in finals),
                        qualified=sum(
                            f.get("arm") == arm and bool((f.get("fit") or {}).get("converged"))
                            for f in finals
                        ),
                    )
                    for arm in ARMS
                },
            )
        )
    result["joint_stages"] = {
        stage: {arm: bool(fit.get("converged")) for arm, fit in arms.items()}
        for stage, arms in receipt.get("attempts", {}).items()
        if stage != "removed_satellites"
    }
    result["point_failures"] = receipt.get("point_failures", [])
    result["searches"] = receipt.get("searches", {})
    return result


def load_rows(plan, output, digest):
    rows, hashes = [], {}
    for member in plan["members"]:
        row = dict(label=member["label"], dataset=member["dataset"], phases={})
        for phase in ("search", *BRANCHES):
            path = Path(output) / member["label"] / phase / "result.json"
            if not path.exists():
                row["phases"][phase] = dict(status="missing")
                continue
            data = path.read_bytes()
            receipt = json.loads(data)
            if receipt.get("protocol_sha256") != digest or receipt.get("label") != member["label"]:
                raise ValueError("foreign member/phase receipt")
            if phase != "search" and receipt.get("branch") != phase:
                raise ValueError("foreign branch")
            if receipt.get("status") not in TERMINAL:
                raise ValueError("nonterminal result file")
            if phase != "search" and receipt.get("fallback_available") is not False:
                raise ValueError("undeclared fallback")
            value = compact_receipt(receipt)
            # Reporting needs sealed fit/selection, not another copy of association arrays.
            value["operational"] = {
                arm: {
                    key: operation.get(key)
                    for key in (
                        "fit",
                        "region_source",
                        "basin",
                        "accepted_stage",
                        "start",
                        "calibration_penalty",
                    )
                }
                for arm, operation in receipt.get("operational", {}).items()
            }
            row["phases"][phase] = value
            hashes[str(path)] = hashlib.sha256(data).hexdigest()
        rows.append(row)
    return rows, hashes


def sealed(rows):
    return len(rows) == 12 and all(
        row["phases"][phase]["status"] in TERMINAL
        for row in rows
        for phase in ("search", *BRANCHES)
    )


def summarize(rows, *, evaluate=None):
    if evaluate is not None and not sealed(rows):
        raise ValueError("all twelve selections must seal before reference evaluation")
    output = []
    for row in rows:
        value = dict(
            label=row["label"],
            dataset=row["dataset"],
            statuses={p: r["status"] for p, r in row["phases"].items()},
            failure_reasons={
                p: r.get("reason") or r.get("reasons") for p, r in row["phases"].items()
            },
            phase_elapsed_s={p: r.get("elapsed_s") for p, r in row["phases"].items()},
            discovery=row["phases"]["search"].get("searches", {}),
            point_failures=row["phases"]["search"].get("point_failures", []),
            regions={b: row["phases"][b].get("regions", []) for b in BRANCHES},
            joint_stages={b: row["phases"][b].get("joint_stages", {}) for b in BRANCHES},
            arms={},
        )
        for arm in ARMS:
            armrow = {}
            for branch in BRANCHES:
                receipt = row["phases"][branch]
                operation = receipt.get("operational", {}).get(arm)
                if not operation:
                    armrow[branch] = dict(status="no-selected-endpoint")
                    continue
                fit = operation["fit"]
                if not fit.get("converged"):
                    raise ValueError(
                        "unqualified operational endpoint; do not evaluate as selected"
                    )
                item = dict(
                    status="selected",
                    qualified=bool(fit.get("converged")),
                    frequency={
                        key: fit.get(key)
                        for key in ("objective", "posterior_rms_hz", "signal_windows")
                    },
                    stationarity=fit.get("stationarity"),
                    selection={
                        key: operation.get(key)
                        for key in ("basin", "region_source", "start", "accepted_stage")
                    },
                )
                if evaluate is not None:
                    item["error_km"] = evaluate(row["label"], branch, arm, operation)
                armrow[branch] = item
            if all("error_km" in armrow[b] for b in BRANCHES):
                armrow["delta_km"] = armrow["fixed"]["error_km"] - armrow["native"]["error_km"]
            value["arms"][arm] = armrow
        output.append(value)
    return dict(
        all_terminal=sealed(rows),
        rows=output,
        full_comparison_complete=sealed(rows)
        and all(
            row["phases"][p]["status"] == "complete" for row in rows for p in ("search", *BRANCHES)
        )
        and all(r["arms"][a][b].get("qualified") for r in output for a in ARMS for b in BRANCHES),
        note="Fresh matched controls; failures retained; no archived/deployed parity claim",
    )


def aggregate(summary):
    import numpy as np

    result = {}
    for dataset in ("DS16", "DS17", "DS18", "all12"):
        rows = [r for r in summary["rows"] if dataset == "all12" or r["dataset"] == dataset]
        result[dataset] = {}
        for arm in ARMS:
            paired = [r for r in rows if "delta_km" in r["arms"][arm]]
            value = dict(
                membership=len(rows),
                paired=len(paired),
                missing=len(rows) - len(paired),
                full_dataset_metrics_available=len(paired) == len(rows),
                branches={},
            )
            for branch in BRANCHES:
                errors = np.array([r["arms"][arm][branch]["error_km"] for r in paired])
                value["branches"][branch] = (
                    None
                    if not len(errors)
                    else dict(
                        mean_km=float(np.mean(errors)),
                        median_km=float(np.median(errors)),
                        p95_km=float(np.quantile(errors, 0.95)),
                        worst_km=float(np.max(errors)),
                        metric_scope="full paired membership"
                        if len(paired) == len(rows)
                        else "available paired subset only",
                    )
                )
            deltas = [r["arms"][arm]["delta_km"] for r in paired]
            value["regressions"] = sum(delta > 0 for delta in deltas)
            value["regressions_over_0_1km"] = sum(delta > 0.1 for delta in deltas)
            value["improvements"] = sum(delta < 0 for delta in deltas)
            result[dataset][arm] = value
    return result


def evaluation_callback(plan, rows):
    if not sealed(rows):
        raise ValueError("all twelve selections must seal before reference authority access")
    authority_path = ROOT / "reports/2026_10_09_position_error_iter107/protocol.json"
    if (
        hashlib.sha256(authority_path.read_bytes()).hexdigest()
        != "24df105bf4618947162f9438ea2a77115d1baa134a00b5f7b48279942848d227"
    ):
        raise ValueError("postfit evaluation authority changed")
    report = runpy.run_path(str(authority_path.parent / "report.py"))
    authority = json.loads(authority_path.read_text())
    members = {
        m["member"].get("inventory_label", m["member"].get("dataset_label")): m
        for m in authority["members"]
    }
    requested = {m["label"]: m for m in plan["members"]}
    documents = {}

    def evaluate(label, branch, arm, operation):
        if label not in documents:
            member = members[label]
            if member["member"]["session_id"] != requested[label]["membership"]["session_id"]:
                raise ValueError("evaluation session differs")
            document = report["evaluation_document"](member)
            sanitized = json.loads(
                (ROOT / requested[label]["binding"]["document_path"]).read_text()
            )
            for key in (
                "session_id",
                "input_manifest_sha256",
                "analysis_manifest_sha256",
                "evidence_sha256",
            ):
                if document[key] != sanitized[key]:
                    raise ValueError("evaluation input differs: " + key)
            if document["configuration"]["prior"] != sanitized["configuration"]["prior"]:
                raise ValueError("evaluation prior differs")
            documents[label] = document
        return report["evaluate_fit"](operation, documents[label])["error_km"]

    return evaluate


def plot(summary, path):
    if not summary["all_terminal"]:
        raise ValueError("do not publish final error plots before all12 seal")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
    for axis, arm in zip(axes, ARMS, strict=True):
        for index, row in enumerate(summary["rows"]):
            values = row["arms"][arm]
            native, fixed = (values[b].get("error_km") for b in BRANCHES)
            if native is not None and fixed is not None:
                axis.plot(
                    [index - 0.13, index + 0.13], [native, fixed], color="#aaaaaa", linewidth=1.0
                )
            for branch, error, offset, color in (
                ("native", native, -0.13, "#7a7a7a"),
                ("fixed", fixed, 0.13, "#7041a8"),
            ):
                if error is not None:
                    axis.scatter(
                        index + offset,
                        error,
                        color=color,
                        s=30,
                        label=branch if index == 1 else None,
                    )
            if native is None or fixed is None:
                axis.text(
                    index,
                    0.02,
                    "missing",
                    color="#a43939",
                    fontsize=8,
                    rotation=90,
                    ha="center",
                    transform=axis.get_xaxis_transform(),
                )
        axis.set_yscale("symlog", linthresh=0.05)
        axis.set_ylabel(f"{arm} error (km)")
        axis.grid(axis="y", alpha=0.2)
        axis.set_axisbelow(True)
        axis.legend(
            handles=[
                Line2D([], [], color="#7a7a7a", marker="o", linestyle="", label="native"),
                Line2D([], [], color="#7041a8", marker="o", linestyle="", label="fixed"),
            ]
        )
    axes[-1].set_xticks(
        range(len(summary["rows"])),
        [row["label"] for row in summary["rows"]],
        rotation=45,
        ha="right",
    )
    fig.suptitle("Preselected consumed12 · fresh matched discovery · all failures shown")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def publish(summary, hashes, directory):
    """Publish compact sealed evidence; raw local receipts remain unchanged."""
    directory = Path(directory)
    if not summary["all_terminal"]:
        raise ValueError("all twelve selections must seal before publication")
    metrics = aggregate(summary)
    payload = dict(summary=summary, metrics=metrics, receipt_sha256=hashes)
    summary_path = directory / "PILOT_SUMMARY.json"
    summary_path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    plot(summary, directory / "pilot_errors.png")
    lines = [
        "# Fresh native versus fixed-bank discovery on the preselected twelve",
        "",
        "Consumed conditional development, not independent validation. Both policies use "
        "the same fresh 400-point discovery budget, three retained regions and symmetric "
        "downstream calibration. Fitted-c discovery feeds matched fitted-c and zero-c finals. "
        "This research control differs from deployed B7 and has no archived parity claim.",
        "",
        "All twelve members are terminal. Missing endpoints remain explicit; the original "
        "DS16-020 admission failure is preserved. Any separately budgeted successor is a "
        "separate experiment. Frequency fit and objective are descriptive and are not used "
        "to infer position improvement across differing banks.",
        "",
        "![Paired position errors, including missing endpoints](pilot_errors.png)",
        "",
        "| Dataset | Arm | Paired / members | Native mean / median / p95 / worst km | "
        "Fixed mean / median / p95 / worst km | Regressions >0.1 km |",
        "|---|---|---:|---|---|---:|",
    ]
    for dataset, arms in metrics.items():
        for arm, value in arms.items():
            cells = []
            for branch in BRANCHES:
                m = value["branches"][branch]
                cells.append(
                    "missing"
                    if m is None
                    else " / ".join(
                        f"{m[k]:.4f}" for k in ("mean_km", "median_km", "p95_km", "worst_km")
                    )
                )
            lines.append(
                f"| {dataset} | {arm} | {value['paired']} / {value['membership']} | "
                f"{cells[0]} | {cells[1]} | {value['regressions_over_0_1km']} |"
            )
    lines += [
        "",
        "Metrics with missing pairs describe the available paired subset only; "
        "full-member metrics are withheld.",
        "",
        "| Member | Search | Native | Fixed | Fitted-c delta km | Zero-c delta km |",
        "|---|---|---|---|---:|---:|",
    ]
    for row in summary["rows"]:
        delta = [row["arms"][a].get("delta_km") for a in ARMS]
        cells = ["missing" if d is None else f"{d:+.4f}" for d in delta]
        lines.append(
            f"| {row['label']} | {row['statuses']['search']} | "
            f"{row['statuses']['native']} | {row['statuses']['fixed']} | "
            f"{cells[0]} | {cells[1]} |"
        )
    lines += [
        "",
        "Positive delta means fixed-bank regression. Full frequency metrics, "
        "qualification counts, failure reasons and phase elapsed times are retained in "
        "[the compact summary](PILOT_SUMMARY.json). Raw receipts remain local; their byte "
        "hashes are published, not a remote raw-data reproduction bundle.",
        "",
    ]
    (directory / "RESULTS.md").write_text("\n".join(lines))
    artifacts = ("PILOT_SUMMARY.json", "pilot_errors.png", "RESULTS.md", "report_cohort.py")
    (directory / "PILOT_INTEGRITY.json").write_text(
        json.dumps(
            {
                name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                for name in artifacts
            },
            indent=2,
        )
        + "\n"
    )


def main():
    import argparse

    from leo.contracts.digests import canonical_digest

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=HERE / "protocol.json")
    parser.add_argument("--output", type=Path, default=HERE / "results")
    args = parser.parse_args()
    plan = json.loads(args.protocol.read_text())
    for group in ("source_sha256", "input_sha256"):
        for relative, expected in plan[group].items():
            if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
                raise ValueError("Frozen reporting authority changed: " + relative)
    rows, hashes = load_rows(plan, args.output, canonical_digest(plan))
    if not sealed(rows):
        raise ValueError("all twelve selections must seal before reference evaluation")
    summary = summarize(rows, evaluate=evaluation_callback(plan, rows))
    publish(summary, hashes, HERE)


if __name__ == "__main__":
    main()
