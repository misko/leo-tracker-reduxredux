"""Paired hard/smooth reporting, score selection before reference evaluation."""

import hashlib
import json
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from report_policy import ARMS, MODELS, paired_indices, winner  # noqa: E402

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter52"))
from common_sigma1 import error_km, read  # noqa: E402

from leo.contracts.regional_position import RegionalPrior  # noqa: E402

plan = read(HERE / "protocol.json")
receipts = {}
for model, folder in [("hard", REPORTS / "2026_10_09_position_error_iter55"), ("smooth", HERE)]:
    digest = hashlib.sha256((folder / "protocol.json").read_bytes()).hexdigest()
    for index in plan["endpoint_indices"]:
        for arm in ARMS:
            path = folder / "results" / f"{index:03d}-{arm}.json"
            if path.exists():
                row = read(path)
                assert row["protocol_sha256"] == digest
                assert (row["index"], row["arm"]) == (index, arm)
                receipts[model, index, arm] = dict(
                    row, model=model, receipt=str(path.relative_to(REPORTS.parent))
                )
paired = paired_indices(plan["endpoint_indices"], receipts)
winners, metrics = {}, {}
for model in MODELS:
    winners[model], metrics[model] = {}, {}
    for arm in ARMS:
        rows = [receipts[model, i, arm] for i in paired]
        winners[model][arm] = winner(rows)
        fits = [r["fit"] for r in rows if r.get("fit")]
        metrics[model][arm] = dict(
            completed=len(rows),
            converged=sum(f["converged"] for f in fits),
            failed=sum(not f["converged"] for f in fits),
            median_evaluations=float(np.median([f["evaluations"] for f in fits])) if fits else None,
            median_seconds=float(np.median([f["elapsed_s"] for f in fits])) if fits else None,
        )
# Only after winners are fixed, reference coordinates enter evaluation.
reference = read(REPORTS / "2026_10_08_position_error_iter29/baselines/RESERVED-001.json")
prior = RegionalPrior()
for row in receipts.values():
    if row.get("fit"):
        row["error_km"] = error_km(prior, row["fit"]["vector"], reference)
summary = dict(
    paired_indices=paired,
    planned_indices=plan["endpoint_indices"],
    winners=winners,
    metrics=metrics,
    receipts=list(receipts.values()),
    scope="Consumed partial diagnostic, no cohort replacement; unequal model walltime allowances",
)
(HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
fig, axes = plt.subplots(1, 2, figsize=(11, 4), layout="constrained")
for ax, arm in zip(axes, ARMS, strict=True):
    for model, color in [("hard", "#227c9d"), ("smooth", "#ee7733")]:
        for converged, marker in [(True, "o"), (False, "x")]:
            rows = [
                receipts[model, i, arm]
                for i in paired
                if receipts[model, i, arm].get("fit", {}).get("converged") is converged
            ]
            ax.scatter(
                [r["region"] for r in rows],
                [r["error_km"] for r in rows],
                c=color,
                marker=marker,
                label=model + (" converged" if converged else " failed"),
            )
    ax.set(title=arm, xlabel="Ordinary region index", ylabel="Position error after fitting (km)")
    ax.legend(fontsize=7)
fig.suptitle(f"Hard/smooth comparison: {len(paired)}/32 fully paired regions")
fig.savefig(HERE / "comparison.png", dpi=160)
text = f"""# Iteration60: ordinary-start smooth-horizon pilot

**Partial: {len(paired)}/32 fully paired regions.** Each region requires hard and
smooth results in both c arms before entering this comparison. All32 planned
regions remain in coverage. This is consumed DS18 development, not independent
validation; no result replaces a cohort error or establishes an operational fix.

![Paired position outcomes](comparison.png)

## Provisional score-selected winners and computation

| Model | Arm | Winner index | Error km | RMS Hz | Converged/failed | Median evals | Median s |
|---|---|---:|---:|---:|---:|---:|---:|
"""
for model in MODELS:
    for arm in ARMS:
        row, metric = winners[model][arm], metrics[model][arm]
        if row:
            text += (
                f"| {model} | {arm} | {row['index']} | {row['error_km']:.6f} | "
                f"{row['fit']['posterior_rms_hz']:.3f} | "
                f"{metric['converged']}/{metric['failed']} | "
                f"{metric['median_evaluations']:.1f} | {metric['median_seconds']:.2f} |\n"
            )
        else:
            text += (
                f"| {model} | {arm} | none | — | — | "
                f"{metric['converged']}/{metric['failed']} | — | — |\n"
            )
text += """
Winners minimize objective among converged fits, ties by ascending frozen index.
Reference errors are calculated afterward. Cross-model objectives are not treated
as localization improvements. The table's computational medians include failed
fits on the matched completed subset, not just successful winners.

Smooth uses90seconds/600iterations versus hard20seconds/600iterations, following
the measured4.45x evaluation cost. **This is not equal wall-time allowance.**
Both c arms share budgets within each model. No convergence gate is relaxed.
Shared inputs: common145 bank, ordinary calibration, sigma1/common3, joint100,
residual slopes60, local25km, identical ordinary seeds. Global1degree smoothstep
is the model change. No recovered joint seed or reference-guided selection is used.

One first feasible endpoint per successful region is the frozen pilot policy;
it does not use all187 feasible starts. All192 source endpoints,5infeasible and
the3earlier regional calibration failures remain in iterations41/53. Hard
controls use exactly the pilot indices from iteration55. This subset must not
be compared with the best winner over all192 endpoints as if budgets matched.
Prior tuning is consumed development. Uniform policy across DS16/17/18 and
independent validation remain required. Production/RF/contracts unchanged.

## Full pilot coverage

| Endpoint | Hard fitted-c | Hard c0 | Smooth fitted-c | Smooth c0 |
|---:|---|---|---|---|
"""
for i in plan["endpoint_indices"]:
    statuses = []
    for model in MODELS:
        for arm in ARMS:
            row = receipts.get((model, i, arm))
            statuses.append(
                "pending"
                if row is None
                else ("converged" if row.get("fit", {}).get("converged") else "failed")
            )
    text += "| " + str(i) + " | " + " | ".join(statuses) + " |\n"
(HERE / "README.md").write_text(text)
print("Paired regions", len(paired), "/32")
