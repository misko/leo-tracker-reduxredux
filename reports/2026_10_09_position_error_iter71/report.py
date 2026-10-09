"""Matched complete-source comparisons, score selection before truth evaluation."""

import hashlib
import json
import sys
from pathlib import Path

import matplotlib
import numpy as np
from selection import winner

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter52"))
from common_sigma1 import error_km, read  # noqa: E402

from leo.contracts.regional_position import RegionalPrior  # noqa: E402

ARMS = ("fitted-c", "zero-c")
MODES = ("direct", "proposals", "continuation")
plan = read(HERE / "protocol.json")
execution = read(HERE / "execution.json") if (HERE / "execution.json").exists() else {}
stopped = execution.get("status") == "stopped"
digest = hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
receipts = {}
for path in sorted((HERE / "results").glob("*.json")):
    row = read(path)
    assert row["protocol_sha256"] == digest
    assert row["index"] in plan["endpoint_indices"]
    key = (row["index"], row["order"], row["arm"])
    assert key not in receipts
    receipts[key] = row

complete, comparisons = [], []
for index in plan["endpoint_indices"]:
    path = HERE / "regions" / f"{index:03d}.json"
    if not path.exists():
        continue
    saved = read(path)
    assert saved["protocol_sha256"] == digest
    # Marker may appear just after the initial receipt snapshot. Defer that source.
    rows = [r for key, r in receipts.items() if key[0] == index]
    if len(rows) != saved["attempts"]:
        continue
    stage_a = [r for r in rows if r["stage"] == "proposals"]
    assert len(stage_a) == 10
    for arm in ARMS:
        assert winner(stage_a, arm) == saved["before"][arm]
        assert winner(rows, arm) == saved["final"][arm]
        direct = receipts[index, 0, arm]
        comparisons.append(
            dict(
                index=index,
                region=saved["region"],
                arm=arm,
                direct=direct if direct["fit"]["converged"] else None,
                proposals=saved["before"][arm],
                continuation=saved["final"][arm],
            )
        )
    complete.append(index)

# Select among the identical completed-source set before loading the reference.
selected = {}
for arm in ARMS:
    selected[arm] = {}
    for mode in MODES:
        eligible = [r[mode] for r in comparisons if r["arm"] == arm and r[mode] is not None]
        selected[arm][mode] = (
            min(eligible, key=lambda r: (r["fit"]["objective"], r["index"], r["order"]))
            if eligible
            else None
        )

reference = read(REPORTS / "2026_10_08_position_error_iter29/baselines/RESERVED-001.json")
prior = RegionalPrior()
for row in receipts.values():
    row["error_km"] = error_km(prior, row["fit"]["vector"], reference)
for row in comparisons:
    for mode in MODES:
        value = row[mode]
        if value is not None:
            value["error_km"] = error_km(prior, value["fit"]["vector"], reference)
for modes in selected.values():
    for row in modes.values():
        if row is not None:
            row["error_km"] = error_km(prior, row["fit"]["vector"], reference)

changes = {}
for arm in ARMS:
    changes[arm] = {}
    for mode in MODES[1:]:
        counts = dict(
            improved=0, regressed=0, tied=0, gained_convergence=0, lost_convergence=0, both_failed=0
        )
        for row in comparisons:
            if row["arm"] != arm:
                continue
            a, b = row["direct"], row[mode]
            if a is not None and b is not None:
                delta = b["error_km"] - a["error_km"]
                key = "improved" if delta < -0.001 else "regressed" if delta > 0.001 else "tied"
            else:
                key = (
                    "gained_convergence"
                    if b is not None
                    else "lost_convergence"
                    if a is not None
                    else "both_failed"
                )
            counts[key] += 1
        changes[arm][mode] = counts

control_audit = []
for index in complete:
    for arm in ARMS:
        path = REPORTS / "2026_10_09_position_error_iter55/results" / f"{index:03d}-{arm}.json"
        if not path.exists():
            control_audit.append(dict(index=index, arm=arm, status="old control pending"))
            continue
        old, new = read(path)["fit"], receipts[index, 0, arm]["fit"]
        control_audit.append(
            dict(
                index=index,
                arm=arm,
                status="compared",
                same_convergence=old["converged"] == new["converged"],
                objective_delta=new["objective"] - old["objective"],
                max_vector_delta=float(
                    np.max(abs(np.asarray(new["vector"]) - np.asarray(old["vector"])))
                ),
            )
        )

compared_controls = [r for r in control_audit if r["status"] == "compared"]
control_counts = dict(
    compared=len(compared_controls),
    convergence_changes=sum(not r["same_convergence"] for r in compared_controls),
    maximum_absolute_objective_difference=max(
        (abs(r["objective_delta"]) for r in compared_controls), default=0
    ),
)

summary = dict(
    execution=execution,
    planned_sources=64,
    feasible_sources=63,
    complete_indices=complete,
    missing_sources=plan["missing_sources"],
    receipts=len(receipts),
    selected=selected,
    changes=changes,
    comparisons=comparisons,
    control_audit=control_audit,
    control_counts=control_counts,
    failed_fits=sum(not r["fit"]["converged"] for r in receipts.values()),
    elapsed_fit_seconds=sum(r["fit"]["elapsed_s"] for r in receipts.values()),
    receipt_files=[f"results/{i:03d}-{o:02d}-{a}.json" for i, o, a in receipts],
)
(HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
fig, axes = plt.subplots(1, 2, figsize=(11, 4), layout="constrained")
for ax, arm in zip(axes, ARMS, strict=True):
    for mode, color in zip(MODES, ("#777777", "#227c9d", "#ee7733"), strict=True):
        values = [r for r in comparisons if r["arm"] == arm and r[mode] is not None]
        ax.scatter(
            [r["index"] for r in values],
            [r[mode]["error_km"] for r in values],
            color=color,
            s=20,
            alpha=0.65,
            label=mode,
        )
    ax.set(title=arm, xlabel="Frozen source index", ylabel="Score-selected source error (km)")
    ax.legend(fontsize=8)
fig.suptitle(f"Complete matched sources: {len(complete)}/63 feasible; 1 unavailable")
fig.savefig(HERE / "comparison.png", dpi=160)
status_label = "Stopped" if stopped else "Complete" if len(complete) == 63 else "Partial"
text = f"""# Iteration71 results: ordinary clock proposals and continuation

**{status_label}: {len(complete)}/63 feasible sources complete;
one further source unavailable.**
Only completed source pipelines enter the three-way comparison. All64 planned
slots remain in coverage. There are{len(receipts)} fit receipts so far,
including{summary["failed_fits"]} independent-convergence failures.

![Matched source results](comparison.png)

## Score-selected winners on the matched completed-source set

| Arm | Search stage | Source | Objective | Position error km | Frequency RMS Hz |
|---|---|---:|---:|---:|---:|
"""
for arm in ARMS:
    for mode in MODES:
        row = selected[arm][mode]
        if row is None:
            text += f"| {arm} | {mode} | none | — | — | — |\n"
        else:
            text += (
                f"| {arm} | {mode} | {row['index']} | {row['fit']['objective']:.6f} | "
                f"{row['error_km']:.6f} | {row['fit']['posterior_rms_hz']:.3f} |\n"
            )
text += f"""
Reference error is evaluated after winner selection. These are alternative
hypotheses for one consumed recording, not independent dataset samples.
Lower objective or RMS does not establish better position accuracy. The direct
controls are new90-second unchanged-start runs; historical20-second iteration55 differences
are separately retained in summary.json, not silently ignored or substituted.
Currently{control_counts['compared']} controls are compared, with
{control_counts['convergence_changes']} convergence-flag changes and maximum
absolute objective difference{control_counts['maximum_absolute_objective_difference']:.6g}.
This is a numerical reproducibility audit, not an accuracy selection rule.

## Paired source changes relative to the new direct controls

| Arm | Stage | Improved / regressed / tied | Gained / lost convergence | Both unqualified |
|---|---|---:|---:|---:|
"""
for arm in ARMS:
    for mode in MODES[1:]:
        c = changes[arm][mode]
        text += (
            f"| {arm} | {mode} | {c['improved']} / {c['regressed']} / {c['tied']} | "
            f"{c['gained_convergence']} / {c['lost_convergence']} | {c['both_failed']} |\n"
        )
text += """
Position comparisons require both alternatives qualified, with1m tie tolerance.
Convergence gains are not counted as accuracy gains. Earlier eligible candidates
remain available, so a later score improvement can still worsen reference error.
Every fit uses90s/600; proposals and continuation add compute and recenter local
disks. Both arms share starts and stage budgets. No convergence gate is relaxed.

## Source coverage

| Source index | Region | Status |
|---:|---:|---|
"""
census = read(REPORTS / "2026_10_09_position_error_iter53/results.json")["rows"]
for index in plan["endpoint_indices"]:
    status = "complete" if index in complete else "incomplete at stop" if stopped else "pending"
    text += f"| {index} | {census[index]['region']} | {status} |\n"
for row in plan["missing_sources"]:
    text += f"| {row['start']} | {row['region']} | unavailable: {row['reason']} |\n"
text += """
The frozen [experiment policy](README.md) explains the32-region inventory,
three parent calibration failures, common bank, ordinary clock frame, two source
types, priors and tie rules. This consumed single-recording experiment does not
replace any full-cohort result or prove independent generalization. Full148 means
remain1.360148km fitted-c /1.738896km zero-c. Uniform DS16/17/18 assessment and
independent validation remain necessary. Production and RF collection unchanged.
"""
(HERE / "RESULTS.md").write_text(text)
print(len(complete), "complete sources;", len(receipts), "fit receipts")
