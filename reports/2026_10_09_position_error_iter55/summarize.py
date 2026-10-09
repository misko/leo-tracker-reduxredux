"""Select by score first, then evaluate against reference coordinates."""

import json
import sys
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter52"))
from common_sigma1 import error_km, read  # noqa: E402

from leo.contracts.regional_position import RegionalPrior  # noqa: E402

receipts = [read(p) for p in sorted((HERE / "results").glob("*.json"))]
paired = {r["index"] for r in receipts if r["arm"] == "fitted-c"} & {
    r["index"] for r in receipts if r["arm"] == "zero-c"
}
complete = len(paired) == 192 and len(receipts) == 384
rows = [r for r in receipts if r["index"] in paired]
winners = {}
for arm in ("fitted-c", "zero-c"):
    eligible = [r for r in rows if r["arm"] == arm and r.get("fit", {}).get("converged")]
    winners[arm] = (
        min(eligible, key=lambda r: (r["fit"]["objective"], r["index"])) if eligible else None
    )
# Only after score selection do reference coordinates enter this reporting step.
reference = read(REPORTS / "2026_10_08_position_error_iter29/baselines/RESERVED-001.json")
prior = RegionalPrior()
for r in receipts:
    if r.get("fit"):
        r["error_km"] = error_km(prior, r["fit"]["vector"], reference)
summary = dict(
    paired_endpoints=len(paired),
    total_endpoints=192,
    receipts=len(receipts),
    total_expected_receipts=384,
    statuses=dict(Counter(r["status"] for r in receipts)),
    winners=winners,
    rows=receipts,
    scope="Consumed-data diagnostic; no cohort replacement or independent validation",
    complete=complete,
)
(HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
fig, axes = plt.subplots(1, 2, figsize=(11, 4), layout="constrained")
for arm, color in (("fitted-c", "#227c9d"), ("zero-c", "#ee7733")):
    for converged, marker in ((True, "o"), (False, "x")):
        subset = [
            r for r in rows if r["arm"] == arm and r.get("fit", {}).get("converged") is converged
        ]
        label = arm + (" converged" if converged else " failed convergence")
        for ax, key in zip(axes, ("objective", "error_km"), strict=True):
            ax.scatter(
                [r["index"] for r in subset],
                [r["fit"][key] if key == "objective" else r[key] for r in subset],
                c=color,
                marker=marker,
                label=label,
                alpha=0.7,
            )
axes[0].set(ylabel="Common-model objective (lower is better)")
axes[1].set(ylabel="Post-selection position error (km)")
for ax in axes:
    ax.set_xlabel("Frozen ordinary endpoint index")
axes[0].legend(fontsize=7)
fig.suptitle(
    f"Ordinary-start diagnostic: {len(paired)}/192 paired endpoints"
)
fig.savefig(HERE / "comparison.png", dpi=160)
text = f"""# Iteration55: ordinary-start common-bank refits

**{'Complete' if complete else 'Partial'}: {len(paired)}/192 endpoint pairs;
{len(receipts)}/384 receipts.** This is
consumed DS18 development evidence, not independent validation, and does not
replace any dataset benchmark result. Only endpoints completed in both arms
participate in the provisional comparison. All192 remain in the denominator.

![Paired objective and position diagnostics](comparison.png)

| Arm | Score-selected endpoint | Objective | Error km | Frequency RMS Hz |
|---|---:|---:|---:|---:|
"""
for arm, winner in winners.items():
    if winner:
        text += (
            f"| {arm} | {winner['index']} | {winner['fit']['objective']:.6f} | "
            f"{winner['error_km']:.6f} | {winner['fit']['posterior_rms_hz']:.3f} |\n"
        )
text += """
## Frozen policy and limitations

The late fits overlapped the iteration69 eight-worker execution, which caused
measured wall-budget truncation in repeated controls. These first-attempt results
are preserved; do not interpret late failures as purely scientific model effects.
Iteration70 restored the original controls with two workers and a larger wall
allowance. Any repeat must have separate receipts and a frozen execution policy.

All187 feasible ordinary endpoints from iteration53 receive both fits with20s,
600-iteration limits. The other5 endpoints remain explicit infeasible receipts
in both arms without clipping. The common145 bank, ordinary clock calibration,
sigma1 relative timing prior, common3 prior, joint100 clock prior, residual slope60
and25km local disks are shared. No recovered diagnostic joint seed is used.
Source and input hashes are checked before fitting; each receipt is immutable
and bound to the frozen protocol. Convergence failures remain ineligible even
when the optimizer reports success. Ties use ascending frozen endpoint index.

The evaluator never calculates reference error. The reporter chooses converged
winners by objective before calculating error. Frequency fit and position error
are shown separately; a lower objective is not proof of greater accuracy.
This experiment does not tune per-scan settings using the known position.
Nevertheless, its region budget and sigma were developed on consumed data.
An ordinary-start success would require uniform policy evaluation across
DS16/DS17/DS18 and new independent validation before a generalization claim.
The completed three-dataset iteration51 run uses a different regional policy;
its full148 assessment is preserved in iteration65. No production, RF,
public-contract or fixture changes.

## Complete endpoint coverage

| Endpoint | Region | Source arm/start | Fitted-c status | Zero-c status |
|---:|---:|---|---|---|
"""
census = read(REPORTS / "2026_10_09_position_error_iter53/results.json")["rows"]
lookup = {(r["index"], r["arm"]): r for r in receipts}
for index, source in enumerate(census):
    statuses = []
    for arm in ("fitted-c", "zero-c"):
        row = lookup.get((index, arm))
        status = row["status"] if row else "pending"
        if row and row.get("fit"):
            status += " converged" if row["fit"]["converged"] else " nonconverged"
        statuses.append(status)
    text += (
        f"| {index} | {source['region']} | {source['source_arm']}/{source['start']} | "
        f"{statuses[0]} | {statuses[1]} |\n"
    )
(HERE / "README.md").write_text(text)
print(summary["paired_endpoints"], summary["receipts"], flush=True)
