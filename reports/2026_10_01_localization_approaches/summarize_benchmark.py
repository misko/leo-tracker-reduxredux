"""Descriptive reporting for audited, complete panels; never used by a fitter."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def stats(rows):
    good = [r for r in rows if r["accepted"]]
    errors = [r["error_m"] for r in good]
    times = [r["runtime_s"] for r in rows if r["runtime_s"] is not None]

    def percentile(values, quantile):
        return float(np.percentile(values, quantile)) if values else None

    thresholds = (1000, 2000, 5000, 10000)
    counts = {
        str(threshold): sum(error <= threshold for error in errors) for threshold in thresholds
    }
    return dict(
        planned=len(rows),
        accepted=len(good),
        median_error_m=percentile(errors, 50),
        p90_error_m=percentile(errors, 90),
        worst_error_m=max(errors) if errors else None,
        median_runtime_s=percentile(times, 50),
        p90_runtime_s=percentile(times, 90),
        maximum_runtime_s=max(times) if times else None,
        within_threshold_counts=counts,
        within_threshold_fraction_of_planned={
            threshold: count / len(rows) for threshold, count in counts.items()
        },
        unsuccessful=[r["unit_id"] for r in rows if not r["accepted"]],
    )


def paired(left, right):
    a = {r["unit_id"]: r for r in left if r["accepted"]}
    b = {r["unit_id"]: r for r in right if r["accepted"]}
    ids = sorted(a.keys() & b.keys())
    delta = [a[u]["error_m"] - b[u]["error_m"] for u in ids]
    return dict(
        paired_count=len(ids),
        left_better_by_more_than_1m=sum(d < -1 for d in delta),
        right_better_by_more_than_1m=sum(d > 1 for d in delta),
        within_1m=sum(abs(d) <= 1 for d in delta),
        median_left_minus_right_m=float(np.median(delta)) if delta else None,
        paired_left_median_m=float(np.median([a[u]["error_m"] for u in ids])) if ids else None,
        paired_right_median_m=float(np.median([b[u]["error_m"] for u in ids])) if ids else None,
    )


def require_official_audit(document):
    if (
        not document.get("passed")
        or not document.get("require_complete")
        or not document.get("this_companion_is_required_for_final_acceptance")
    ):
        raise ValueError("Complete passing companion audit is required before reporting")


def build_panels(controls, primary, two_stage):
    panels = {"Historical primary": controls["primary-evaluation.json"]["rows"]}
    panels["Historical two-stage"] = [
        dict(
            unit_id=row["unit_id"],
            dataset=row["dataset"],
            accepted=row["effective_accepted"],
            error_m=row["effective_error_m"],
            runtime_s=row["total_runtime_s"],
        )
        for row in controls["continuation-evaluation.json"]["rows"]
    ]
    for stage, document in (("primary", primary), ("two-stage", two_stage)):
        for arm in document["arms"]:
            rows = [row for row in document["rows"] if row["arm"] == arm]
            if len(rows) != 64 or not all(row["attempted"] for row in rows):
                raise ValueError(f"Incomplete panel: {stage} {arm}")
            panels[f"{arm} {stage}"] = rows
    return panels


def aligned_dataset_rows(panels, labels, dataset):
    unit_order = [
        row["unit_id"] for row in panels["Historical two-stage"] if row["dataset"] == dataset
    ]
    result = {}
    for label in labels:
        by_unit = {row["unit_id"]: row for row in panels[label] if row["dataset"] == dataset}
        if set(by_unit) != set(unit_order):
            raise ValueError(f"Per-dataset unit mismatch: {label} {dataset}")
        result[label] = [by_unit[unit] for unit in unit_order]
    return unit_order, result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--two-stage", type=Path, required=True)
    parser.add_argument("--official-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    official_audit = json.loads(args.official_audit.read_text())
    require_official_audit(official_audit)
    bindings = json.loads(
        (ROOT / "plans/localization-approaches-2026-10-01/evaluator-bindings.json").read_text()
    )
    controls = {}
    for b in bindings["controls"]:
        path = ROOT / b["path"]
        if digest(path) != b["sha256"]:
            raise ValueError(f"Historical control changed: {path}")
        controls[path.name] = json.loads(path.read_text())
    panels = build_panels(
        controls, json.loads(args.primary.read_text()), json.loads(args.two_stage.read_text())
    )
    output = dict(
        qualification=(
            "Descriptive single-site regression panel; errors conditional on acceptance, "
            "threshold counts use the fixed all-64 denominator. Historical control used a "
            "40 s acquisition sub-budget; new arms use 50 s. Stage-matched paired summaries "
            "include only units accepted by both methods."
        ),
        input_sha256={
            str(p): digest(p) for p in (args.primary, args.two_stage, args.official_audit)
        },
        summaries={label: stats(rows) for label, rows in panels.items()},
        by_dataset={
            label: {
                d: stats([r for r in rows if r["dataset"] == d]) for d in ("DS9", "DS10", "DS11")
            }
            for label, rows in panels.items()
        },
        paired={
            f"{a} minus {b}": paired(panels[a], panels[b])
            for a, b in [
                ("A1 two-stage", "Historical two-stage"),
                ("B1 two-stage", "Historical two-stage"),
                ("B1 two-stage", "A1 two-stage"),
            ]
        },
    )
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    import matplotlib.pyplot as plt

    colors = {"Historical": "#64748b", "A1": "#0284c7", "B1": "#c2410c"}
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.6))
    for label, rows in panels.items():
        color = colors[label.split()[0]]
        errors = sorted(r["error_m"] for r in rows if r["accepted"])
        endpoint = max(15000.0, errors[-1] if errors else 0.0)
        xs = [0.0, *errors, endpoint]
        ys = [0.0, *[i / 64 for i in range(1, len(errors) + 1)], len(errors) / 64]
        axs[0].step(
            xs,
            ys,
            where="post",
            label=f"{label}: {len(errors)}/64",
            color=color,
            linestyle="--" if label.endswith("primary") else "-",
        )
    axs[0].set(
        xlabel="Horizontal error (meters)",
        ylabel="Fraction of all 64 scans",
        xlim=(0, 15000),
        ylim=(0, 1.01),
    )
    axs[0].legend(fontsize=8)
    labels = ["Historical two-stage", "A1 two-stage", "B1 two-stage"]
    axs[1].boxplot(
        [[r["runtime_s"] for r in panels[label] if r["runtime_s"] is not None] for label in labels],
        tick_labels=["Historical", "Faster greedy", "Soft association"],
    )
    axs[1].set(ylabel="End-to-end time including continuation (seconds)")
    axs[1].axhline(90, color="#64748b", linestyle=":", linewidth=1)
    axs[1].axhline(180, color="#64748b", linestyle=":", linewidth=1)
    for ax in axs:
        ax.grid(alpha=0.2)
    fig.suptitle("Independent single-scan localization: same 64 recordings")
    fig.tight_layout()
    fig.savefig(args.output / "comparison.png", dpi=180)
    plt.close(fig)
    fig, axs = plt.subplots(3, 1, figsize=(11, 8), sharey=True)
    accepted_errors = [r["error_m"] for label in labels for r in panels[label] if r["accepted"]]
    failure_marker = max(15000.0, max(accepted_errors, default=0.0) * 1.05)
    for ax, dataset in zip(axs, ("DS9", "DS10", "DS11"), strict=True):
        unit_order, aligned = aligned_dataset_rows(panels, labels, dataset)
        for j, label in enumerate(labels):
            rows = aligned[label]
            x = np.arange(len(unit_order)) + (j - 1) * 0.15
            ax.scatter(
                [x[i] for i, r in enumerate(rows) if r["accepted"]],
                [r["error_m"] for r in rows if r["accepted"]],
                s=22,
                label=label,
                color=colors[label.split()[0]],
            )
            ax.scatter(
                [x[i] for i, r in enumerate(rows) if not r["accepted"]],
                [failure_marker for r in rows if not r["accepted"]],
                marker="x",
                s=40,
                color=colors[label.split()[0]],
            )
        ax.set_xticks(
            np.arange(len(unit_order)),
            [unit.split("-")[1] for unit in unit_order],
            rotation=60,
            fontsize=7,
        )
        ax.set_title(dataset, loc="left")
        ax.set_ylabel("Error (m)")
        ax.grid(alpha=0.2)
    axs[0].legend(fontsize=8, loc="upper left")
    fig.suptitle("Two-stage errors; × above the data means unresolved/failed, not a measured error")
    fig.tight_layout()
    fig.savefig(args.output / "per-scan.png", dpi=180)
    plt.close(fig)
    print(json.dumps(output["summaries"], indent=2))


if __name__ == "__main__":
    main()
