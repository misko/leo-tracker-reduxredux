#!/usr/bin/env python3
"""Report the bounded sparse-position exploration without scoring partial runs."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any

BUDGETS = (399, 798, 1597)
LABELS = {
    "formal-orbit-correction-v6": "Original formal",
    "legacy-strict-fixed-orbit": "Fixed-orbit baseline",
    "sparse-student-fixed250": "Original memberships, Student fixed 250 Hz",
    "sparse-gaussian-fixed250": "Original memberships, Gaussian fixed 250 Hz",
    "sparse-gaussian-learned": "Original memberships, Gaussian learned scale",
    "shape3-formal": "Packet 3, formal",
    "shape3-gaussian-fixed250": "Packet 3, Gaussian fixed 250 Hz",
    "shape5-formal": "Packet 5, formal",
    "shape5-gaussian-fixed250": "Packet 5, Gaussian fixed 250 Hz",
    "geometry-fisher-formal": "Geometry-Fisher, formal",
}


def read_json(path: Path | None) -> Any | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text())


def rows(document: Any | None) -> list[dict[str, Any]]:
    if document is None:
        return []
    if isinstance(document, list):
        return document
    return document.get("runs", document.get("results", []))


def require_complete_primary(document: Any | None, expected: int, label: str) -> None:
    observed = len(rows(document))
    if observed != expected:
        raise ValueError(f"refusing to score incomplete {label}: {observed}/{expected} runs")


def exact_by_job(document: Any | None) -> dict[str, dict[str, Any]]:
    return {row["job_id"]: row for row in rows(document)}


def summarize_contrast(document: Any | None, exact: Any | None) -> list[dict[str, Any]]:
    """Normalize the standalone contrast solver's fraction/seed exact summary."""
    if document is None:
        return []
    exact_rows = (exact or {}).get("rows", [])
    checks = {(float(r["fraction"]), int(r["seed"])): r["exact"] for r in exact_rows}
    output = []
    for budget in BUDGETS:
        group = [r for r in rows(document) if int(r.get("fitting_observations", -1)) == budget]
        converged = [r for r in group if r.get("status") == "converged"]
        qualified = [
            r
            for r in converged
            if checks.get((float(r["fraction"]), int(r["seed"])), {}).get("passed")
        ]
        errors = [float(r["horizontal_error_m"]) for r in qualified]
        output.append(
            {
                "model": "gaussian-contrast",
                "label": "Gaussian contrast",
                "budget": budget,
                "total": len(group),
                "converged": len(converged),
                "exact_checked": sum(
                    (float(r["fraction"]), int(r["seed"])) in checks for r in converged
                ),
                "exact_passed": len(qualified),
                "qualified": len(qualified),
                "sub_km_qualified": sum(x < 1000.0 for x in errors),
                "qualified_error_min_m": min(errors) if errors else None,
                "qualified_error_median_m": median(errors) if errors else None,
                "qualified_error_max_m": max(errors) if errors else None,
            }
        )
    return output


def summarize_laplace(document: Any | None, exact: Any | None) -> list[dict[str, Any]]:
    """Require exact agreement and an interior solution for Laplace qualification."""
    if document is None:
        return []
    exact_rows = (exact or {}).get("rows", [])
    checks = {(float(r["fraction"]), int(r["seed"])): r for r in exact_rows}
    output = []
    for budget in BUDGETS:
        group = [r for r in rows(document) if int(r.get("fitting_observations", -1)) == budget]
        converged = [r for r in group if r.get("status") == "converged"]
        checked = [r for r in converged if (float(r["fraction"]), int(r["seed"])) in checks]
        exact_passed = [
            r
            for r in checked
            if checks[(float(r["fraction"]), int(r["seed"]))].get("exact", {}).get("passed") is True
        ]
        qualified = []
        for row in checked:
            check = checks[(float(row["fraction"]), int(row["seed"]))]
            exact_pass = check.get("exact", {}).get("passed") is True
            interior = float(check.get("minimum_rate_bound_margin_s_h", 0.0)) > 0.0
            if exact_pass and interior:
                qualified.append(row)
        errors = [float(r["horizontal_error_m"]) for r in qualified]
        output.append(
            {
                "model": "laplace-contrast",
                "label": "Laplace contrast",
                "budget": budget,
                "total": len(group),
                "converged": len(converged),
                "exact_checked": len(checked),
                "exact_passed": len(exact_passed),
                "qualified": len(qualified),
                "sub_km_qualified": sum(x < 1000.0 for x in errors),
                "qualified_error_min_m": min(errors) if errors else None,
                "qualified_error_median_m": median(errors) if errors else None,
                "qualified_error_max_m": max(errors) if errors else None,
            }
        )
    return output


def summarize(document: Any, exact: Any | None, label_suffix: str = "") -> list[dict[str, Any]]:
    checks = exact_by_job(exact)
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows(document):
        count = int(row.get("actual_fitting_count", -1))
        if count in BUDGETS:
            grouped[(row["model"], count)].append(row)
    output = []
    for (model, budget), group in sorted(grouped.items()):
        converged = [r for r in group if r.get("status") == "converged"]
        checked = [r for r in converged if r.get("job_id") in checks]
        qualified = [r for r in checked if checks[r["job_id"]].get("passed") is True]
        errors = [float(r["horizontal_error_m"]) for r in qualified]
        output.append(
            {
                "model": model,
                "label": LABELS.get(model, model) + label_suffix,
                "budget": budget,
                "total": len(group),
                "converged": len(converged),
                "exact_checked": len(checked),
                "exact_passed": len(qualified),
                "qualified": len(qualified),
                "sub_km_qualified": sum(x < 1000.0 for x in errors),
                "qualified_error_min_m": min(errors) if errors else None,
                "qualified_error_median_m": median(errors) if errors else None,
                "qualified_error_max_m": max(errors) if errors else None,
            }
        )
    return output


def completion_status(
    label: str,
    evaluation_path: Path | None,
    plan_path: Path | None = None,
    results_dir: Path | None = None,
    expected_default: int | None = None,
) -> dict[str, Any]:
    evaluation = read_json(evaluation_path)
    plan = read_json(plan_path)
    expected_ids = {job["job_id"] for job in plan.get("jobs", [])} if plan else set()
    expected = len(expected_ids) or expected_default
    if evaluation is not None:
        observed = len(rows(evaluation))
        complete = expected is None or observed == expected
        return {
            "label": label,
            "status": "complete" if complete else "partial",
            "observed": observed,
            "expected": expected,
            "scored": False,
        }
    observed_ids: set[str] = set()
    if results_dir and results_dir.exists():
        for path in results_dir.glob("*.json"):
            try:
                packet = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            job_id = packet.get("job_id") or packet.get("request", {}).get("job_id")
            if job_id and (not expected_ids or job_id in expected_ids):
                observed_ids.add(job_id)
    observed = len(observed_ids)
    status = "partial" if observed else "pending"
    return {
        "label": label,
        "status": status,
        "observed": observed,
        "expected": expected,
        "scored": False,
    }


def fmt_range(row: dict[str, Any]) -> str:
    if not row["qualified"]:
        return "—"
    lo, mid, hi = (
        row[x]
        for x in ("qualified_error_min_m", "qualified_error_median_m", "qualified_error_max_m")
    )
    return f"{lo:,.0f} / {mid:,.0f} / {hi:,.0f}"


def markdown_table(summary: list[dict[str, Any]]) -> str:
    lines = [
        "| Intervention | Budget | Converged | Exact pass / checked | Qualified sub-km | "
        "Qualified error min / median / max |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        lines.append(
            f"| {row['label']} | {row['budget']:,} | {row['converged']}/{row['total']} | "
            f"{row['exact_passed']}/{row['exact_checked']} | "
            f"{row['sub_km_qualified']}/{row['total']} | {fmt_range(row)} m |"
        )
    return "\n".join(lines)


def status_table(statuses: list[dict[str, Any]]) -> str:
    lines = ["| Evaluation | State | Complete results | Scored here |", "|---|---|---:|---:|"]
    for status in statuses:
        denominator = status["expected"] if status["expected"] is not None else "?"
        lines.append(
            f"| {status['label']} | {status['status']} | {status['observed']}/{denominator} | "
            f"{'yes' if status['scored'] else 'no'} |"
        )
    return "\n".join(lines)


def plot_results(
    all_rows: list[dict[str, Any]], exacts: dict[str, dict[str, Any]], output: Path
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    selected = [r for r in all_rows if int(r.get("actual_fitting_count", -1)) in BUDGETS]
    models = [m for m in LABELS if any(r.get("model") == m for r in selected)]
    colors = plt.get_cmap("tab10")
    fig, ax = plt.subplots(figsize=(10.5, 6.2), constrained_layout=True)
    offsets = {m: (i - (len(models) - 1) / 2) * 12 for i, m in enumerate(models)}
    for index, model in enumerate(models):
        group = [r for r in selected if r["model"] == model]
        for row in group:
            check = exacts.get(row.get("job_id"))
            qualified = (
                row.get("status") == "converged"
                and check is not None
                and check.get("passed") is True
            )
            marker = "o" if qualified else "x"
            ax.scatter(
                row["actual_fitting_count"] + offsets[model],
                row["horizontal_error_m"] / 1000,
                marker=marker,
                color=colors(index % 10),
                s=38,
                alpha=0.9,
            )
        ax.scatter([], [], marker="o", color=colors(index % 10), label=LABELS.get(model, model))
    ax.scatter([], [], marker="o", color="black", label="converged + exact-qualified")
    ax.scatter([], [], marker="x", color="black", label="nonconverged, unchecked, or exact-failed")
    ax.axhline(1.0, color="0.35", linewidth=1, linestyle="--")
    ax.set_xticks(BUDGETS, [f"{x:,}" for x in BUDGETS])
    ax.set_xlabel("Fitting-observation budget")
    ax.set_ylabel("Horizontal error after sealed inference (km)")
    ax.set_title("Sparse fixed-identity replay: qualification is part of the result")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(fontsize=7.5, ncol=2)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180)
    plt.close(fig)


def plot_rates(summary: list[dict[str, Any]], output: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    labels = [f"{r['label']}\n{r['budget']:,}" for r in summary]
    convergence = [r["converged"] / r["total"] for r in summary]
    qualification = [r["qualified"] / r["total"] for r in summary]
    x = np.arange(len(summary))
    fig, ax = plt.subplots(figsize=(12, 5.8), constrained_layout=True)
    ax.bar(x - 0.19, convergence, 0.38, label="Converged / all planned")
    ax.bar(x + 0.19, qualification, 0.38, label="Converged and exact-qualified / all planned")
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("Fraction")
    ax.set_xticks(x, labels, rotation=55, ha="right", fontsize=7)
    ax.set_title("Failures remain in the denominator")
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180)
    plt.close(fig)


def write_csv(summary: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(summary[0]) if summary else ["model"], lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(summary)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--noise", type=Path, default=Path("/tmp/leo-sparse-noise-evaluation.json"))
    parser.add_argument("--shape", type=Path, default=Path("/tmp/leo-shape-sparse-evaluation.json"))
    parser.add_argument(
        "--noise-exact", type=Path, default=Path("/tmp/leo-sparse-noise-exact/summary.json")
    )
    parser.add_argument(
        "--shape-exact", type=Path, default=Path("/tmp/leo-shape-sparse-exact/summary.json")
    )
    parser.add_argument(
        "--comparator",
        type=Path,
        default=Path("reports/artifacts/2026_09_21_position_ablations/small-data-evaluation.json"),
    )
    parser.add_argument(
        "--twenty-seed-plan", type=Path, default=Path("/tmp/leo-shape-formal-20seeds-plan.json")
    )
    parser.add_argument(
        "--twenty-seed-results", type=Path, default=Path("/tmp/leo-shape-sparse-results")
    )
    parser.add_argument(
        "--twenty-seed-evaluation",
        type=Path,
        default=Path("/tmp/leo-shape-formal-20seeds-evaluation.json"),
    )
    parser.add_argument(
        "--twenty-seed-exact",
        type=Path,
        default=Path("/tmp/leo-shape-formal-20seeds-exact/summary.json"),
    )
    parser.add_argument(
        "--stabilized", type=Path, default=Path("/tmp/leo-sparse-stabilized-results.json")
    )
    parser.add_argument(
        "--contrast", type=Path, default=Path("/tmp/leo-gaussian-contrast-results.json")
    )
    parser.add_argument(
        "--contrast-exact", type=Path, default=Path("/tmp/leo-gaussian-contrast-exact/summary.json")
    )
    parser.add_argument(
        "--geometry", type=Path, default=Path("/tmp/leo-geometry-fisher-evaluation.json")
    )
    parser.add_argument(
        "--geometry-exact", type=Path, default=Path("/tmp/leo-geometry-fisher-exact/summary.json")
    )
    parser.add_argument(
        "--laplace", type=Path, default=Path("/tmp/leo-laplace-contrast-results.json")
    )
    parser.add_argument(
        "--laplace-exact",
        type=Path,
        default=Path("/tmp/leo-laplace-contrast-exact/summary.json"),
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    noise, shape = read_json(args.noise), read_json(args.shape)
    noise_exact, shape_exact = read_json(args.noise_exact), read_json(args.shape_exact)
    replication, replication_exact = (
        read_json(args.twenty_seed_evaluation),
        read_json(args.twenty_seed_exact),
    )
    contrast, contrast_exact = read_json(args.contrast), read_json(args.contrast_exact)
    geometry, geometry_exact = read_json(args.geometry), read_json(args.geometry_exact)
    laplace, laplace_exact = read_json(args.laplace), read_json(args.laplace_exact)
    comparator = read_json(args.comparator)
    try:
        require_complete_primary(noise, 27, "noise evaluation")
        require_complete_primary(shape, 36, "shape evaluation")
    except ValueError as error:
        raise SystemExit(str(error)) from error
    summary = summarize(noise, noise_exact) + summarize(shape, shape_exact)
    replication_summary = (
        summarize(replication, replication_exact, " (20 seeds)") if replication else []
    )
    contrast_summary = summarize_contrast(contrast, contrast_exact)
    geometry_summary = summarize(geometry, geometry_exact) if geometry else []
    laplace_summary = summarize_laplace(laplace, laplace_exact)

    statuses = [
        completion_status(
            "20-seed packet-formal replication",
            args.twenty_seed_evaluation,
            args.twenty_seed_plan,
            args.twenty_seed_results,
            expected_default=120,
        ),
        completion_status("Stabilized same-likelihood solver", args.stabilized, expected_default=9),
        completion_status("Gaussian contrast model", args.contrast, expected_default=9),
        completion_status("Geometry analysis", args.geometry, expected_default=3),
        completion_status("Laplace contrast follow-up", args.laplace, expected_default=9),
    ]
    replication_converged = sum(r.get("status") == "converged" for r in rows(replication))
    replication_exact_complete = (
        replication is not None
        and len(rows(replication)) == 120
        and len(rows(replication_exact)) == replication_converged
    )
    if replication_exact_complete:
        statuses[0]["status"] = "complete and exact-checked"
        statuses[0]["scored"] = True
    if statuses[1]["status"] == "complete":
        statuses[1]["status"] = "complete; 0/9 converged"
    if statuses[2]["status"] == "complete":
        statuses[2]["status"] = "complete; exact check pending"
    if statuses[3]["status"] == "complete":
        statuses[3]["status"] = "complete; exact check pending"
    if contrast_summary and sum(r["exact_checked"] for r in contrast_summary) == sum(
        r["converged"] for r in contrast_summary
    ):
        statuses[2]["status"] = "complete and exact-checked"
        statuses[2]["scored"] = True
    if geometry_summary and sum(r["exact_checked"] for r in geometry_summary) == sum(
        r["converged"] for r in geometry_summary
    ):
        statuses[3]["status"] = "complete and exact-checked"
        statuses[3]["scored"] = True
    if laplace_summary and sum(r["exact_checked"] for r in laplace_summary) == sum(
        r["converged"] for r in laplace_summary
    ):
        statuses[4]["status"] = "complete and exact-checked"
        statuses[4]["scored"] = True
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    write_csv(summary, output / "summary.csv")
    write_csv(replication_summary, output / "twenty-seed-summary.csv")
    write_csv(contrast_summary, output / "contrast-summary.csv")
    write_csv(geometry_summary, output / "geometry-summary.csv")
    write_csv(laplace_summary, output / "laplace-summary.csv")
    exacts = {**exact_by_job(noise_exact), **exact_by_job(shape_exact)}
    plot_results(rows(noise) + rows(shape), exacts, output / "01-errors-and-qualification.png")
    plot_rates(summary, output / "02-convergence-and-qualification.png")
    if replication:
        plot_results(
            rows(replication),
            exact_by_job(replication_exact),
            output / "03-twenty-seed-errors-and-qualification.png",
        )

    comparator_note = "unavailable"
    if comparator:
        original = [
            r
            for r in rows(comparator)
            if r.get("model") == "formal-orbit-correction-v6"
            and r.get("method") == "density"
            and r.get("seed") in (0, 1, 2)
            and r.get("actual_fitting_count") in BUDGETS
        ]
        comparator_note = (
            f"available ({len(original)} matched original-density rows; kept descriptive "
            "because solver and model interventions differ)"
        )
    replication_table = markdown_table(replication_summary) if replication_summary else "Pending."
    contrast_table = markdown_table(contrast_summary) if contrast_summary else "Pending."
    geometry_table = markdown_table(geometry_summary) if geometry_summary else "Pending."
    laplace_table = markdown_table(laplace_summary) if laplace_summary else "Pending."
    figure_dir = "2026_09_21_sparse_position_exploration"
    report = f"""# Sparse-position exploration checkpoint

This bounded single-site replay finds conditional sub-kilometre solutions after
changing sparse-observation membership. It does **not** establish sub-kilometre
accuracy. Identities come from earlier full-archive analysis. Convergence and
exact-propagation agreement are required before an error is qualified.

## Complete initial experiments

{markdown_table(summary)}

Failures remain in every denominator. Missing exact checks never count as passes.

![Initial errors and qualification]({figure_dir}/01-errors-and-qualification.png)

![Convergence and qualification rates]({figure_dir}/02-convergence-and-qualification.png)

## Completed 20-seed replication

{replication_table}

All 81 converged fits pass exact verification; 39 of 120 remain nonconverged.
Packet-3 convergence falls from 17/20 at 399 observations to 2/20 at 1,597.
Packet-5 reaches 20/20 at 798 observations, with 11/20 qualified sub-kilometre.
These are conditional single-site rates.

![All 120 sampling trials]({figure_dir}/03-twenty-seed-errors-and-qualification.png)

## Distinct interventions

The paired comparison holds seed, budget, archived identity mapping, and
evaluation policy fixed while changing sampling membership. The selected source
subset changes. Noise-family and solver changes are separate interventions.

The historical comparator is {comparator_note}. Student fixed-noise restores
convergence in 8/9 initial runs, but errors remain 1.26–3.26 km.

## Completed numerical experiments

{status_table(statuses)}

{contrast_table}

Gaussian contrast has three exact-qualified fits among nine planned runs. Two
are sub-kilometre. Four nonconverged runs and two exact failures remain.

{geometry_table}

Both converged geometry-Fisher fits pass exact propagation. The 798-observation
case has 660 m error. The 1,597-observation fit remains failed despite its 287 m
coordinate. A bounded diagnostic locates failure in Student-t nuisance
reweighting at high sparse-nuisance dimension. It does not qualify the failed
fit.

{laplace_table}

Laplace converges in 4/9 runs. Two 399-observation fits qualify, at 1.61 and
1.65 km. The exact-passing 405 m candidate hits a rate boundary, invalidating
the zero-gradient Laplace assumption, so it is unqualified. Reliable
sub-kilometre performance at 399 observations remains unresolved.

## Why sparse sampling failed

With seed 0 at 1/32, ordinary thinning keeps 399 observations across 320 tracks.
Of those tracks, 248 have one observation and only seven have three or more.
A free frequency offset absorbs a singleton completely: it supplies no
within-track Doppler shape. Three-point sampling uses the same 399 observations
across 133 tracks, all with three separated points.

| Seed 0, 399 observations | Tracks | Singletons | Offset-free contrasts |
|---|---:|---:|---:|
| Ordinary thinning | 320 | 248 | 79 |
| Three-point packets | 133 | 0 | 266 |
| Five-point packets | 80 | 0 | 319 |

Gaussian contrast integrates out track frequency offsets, removing noise-scale
information incorrectly retained by singleton profiles. Its fitted noise is
about 40–77 Hz; the rate-marginal variant gives 73–96 Hz, rather than collapsing
toward the 5 Hz floor. This fixes a modeling pathology but does not establish
a reliable location estimator.

The geometry experiment's 1/8 failure is in the inner robust nuisance solve:
both outer location optimizations succeed, but nuisance reweighting exhausts
60 iterations with 533 offsets and 382 phase-rate corrections. No correction
reaches its bound. More data can therefore increase numerical difficulty even
while improving the available geometric information.

## Reproduction and scope

This report extends the [positioning breakthroughs](2026_09_21_positioning_breakthroughs.md)
and [full ablation and subsampling report](2026_09_21_position_ablation_report.md).

```bash
artifact_dir=reports/artifacts/2026_09_21_sparse_position_exploration
.venv/bin/python tools/report_sparse_position_exploration.py \\
  --noise ${{artifact_dir}}/noise-evaluation.json \\
  --noise-exact ${{artifact_dir}}/noise-exact.json \\
  --shape ${{artifact_dir}}/shape-initial-evaluation.json \\
  --shape-exact ${{artifact_dir}}/shape-initial-exact.json \\
  --twenty-seed-evaluation ${{artifact_dir}}/shape-20seed-evaluation.json \\
  --twenty-seed-exact ${{artifact_dir}}/shape-20seed-exact.json \\
  --stabilized ${{artifact_dir}}/stabilized-results.json \\
  --contrast ${{artifact_dir}}/gaussian-contrast-results.json \\
  --contrast-exact ${{artifact_dir}}/gaussian-contrast-exact.json \\
  --geometry ${{artifact_dir}}/geometry-evaluation.json \\
  --geometry-exact ${{artifact_dir}}/geometry-exact.json \\
  --laplace ${{artifact_dir}}/laplace-contrast-results.json \\
  --laplace-exact ${{artifact_dir}}/laplace-contrast-exact.json \\
  --output-dir reports/2026_09_21_sparse_position_exploration \\
  --report reports/2026_09_21_sparse_position_exploration.md
```

Frozen plans, job packets, checks and source receipts are in the
[artifact directory](artifacts/2026_09_21_sparse_position_exploration/).
The exact executed stabilized-solver source was not recovered; its receipt
distinguishes the retained later diagnostic revision. Its negative 0/9 result
is descriptive, not an exactly reproducible source checkpoint.

Budgets are 399, 798, and 1,597 existing training-pool observations. Truth did
not fit the model or select a run. Full-archive identities mean this does not
demonstrate blind acquisition. Independent sites are still required.

The next numerical step is a scalar per-source solve replacing the joint inner
IRLS system, while retaining the convergence tolerance. Accuracy calibration
requires independent sites.

Validation: 31 targeted tests passed, covering the frozen formal model,
subset invariants, held-out isolation, scalar integration checks and report
qualification. Ruff and whitespace checks passed. These are isolated research
modules; the existing production positioning model was not changed.
"""
    report_path = args.report or output / "report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report)
    print(
        json.dumps(
            {
                "summary_rows": len(summary),
                "statuses": statuses,
                "report": str(report_path),
                "output_dir": str(output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
