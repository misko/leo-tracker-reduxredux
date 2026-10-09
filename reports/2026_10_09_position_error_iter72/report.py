"""Final ordinary direct-start and smooth-pilot assessment, no new fits."""

import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent


def read(path):
    return json.loads(path.read_text())


hard_path = REPORTS / "2026_10_09_position_error_iter55/summary.json"
smooth_path = REPORTS / "2026_10_09_position_error_iter60/summary.json"
hard, smooth = read(hard_path), read(smooth_path)
assert hard["complete"] and smooth["complete"], "Wait for both complete summaries"
assert hard["receipts"] == 384 and len(smooth["paired_indices"]) == 32
if (HERE / "summary.json").exists():
    raise FileExistsError("Preserve first full comparison")
arms = ("fitted-c", "zero-c")
metrics = {}
for arm in arms:
    rows = [r for r in hard["rows"] if r["arm"] == arm]
    qualified = [r for r in rows if r.get("fit", {}).get("converged")]
    closest = min(qualified, key=lambda r: (r["error_km"], r["index"])) if qualified else None
    metrics[arm] = dict(
        hard_all_winner=hard["winners"][arm],
        hard_matched_winner=smooth["winners"]["hard"][arm],
        smooth_matched_winner=smooth["winners"]["smooth"][arm],
        all_converged=len(qualified),
        all_failed=sum(r.get("fit") is not None and not r["fit"]["converged"] for r in rows),
        all_infeasible=sum(r.get("fit") is None for r in rows),
        closest_qualified_evaluation_only=closest,
        matched_metrics={m: smooth["metrics"][m][arm] for m in ("hard", "smooth")},
        matched_changes=smooth["paired_changes"][arm],
    )
summary = dict(
    metrics=metrics,
    source_sha256={
        str(p.relative_to(REPORTS.parent)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (hard_path, smooth_path)
    },
    limitation=(
        "Consumed single-scan development; unequal wall budgets and late execution overlap; "
        "no cohort replacement"
    ),
)
(HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
fig, axes = plt.subplots(1, 2, figsize=(11, 4), layout="constrained")
for ax, arm in zip(axes, arms, strict=True):
    keys = ("hard_all_winner", "hard_matched_winner", "smooth_matched_winner")
    ax.bar(
        np.arange(3),
        [metrics[arm][k]["error_km"] for k in keys],
        color=("#999999", "#227c9d", "#ee7733"),
    )
    ax.set_xticks(
        np.arange(3), ["Hard: all starts", "Hard: matched32", "Smooth: matched32"], rotation=15
    )
    ax.set(title=arm, ylabel="Score-selected position error (km)")
fig.suptitle("Completed ordinary-start diagnostic; no recovered joint seed")
fig.savefig(HERE / "winners.png", dpi=160)
text = """# Iteration72: completed ordinary-start direct and smooth diagnostics

All192 ordinary endpoints have paired hard-model receipts, including five
explicitly infeasible endpoints in each c arm. The smooth pilot has all32 regions
completed in both arms, with exactly matching hard controls. No recovered joint
seed was used. These are consumed single-recording diagnostics, not replacement
DS18 benchmark results or an independent-validation success.

![Score-selected position errors](winners.png)

## Selected results

| Arm | Search | Winning source | Error km | Frequency RMS Hz | Objective |
|---|---|---:|---:|---:|---:|
"""
for arm in arms:
    for key, label in (
        ("hard_all_winner", "Hard all192"),
        ("hard_matched_winner", "Hard matched32"),
        ("smooth_matched_winner", "Smooth matched32"),
    ):
        row = metrics[arm][key]
        text += (
            f"| {arm} | {label} | {row['index']} | {row['error_km']:.6f} | "
            f"{row['fit']['posterior_rms_hz']:.3f} | {row['fit']['objective']:.3f} |\n"
        )
text += """
Each winner minimizes its own model's objective among qualified candidates,
with deterministic index ties. Reference error enters afterward. Objective values
across hard/smooth models are not directly comparable. The all-start hard result
uses more starts than the32-region pilot and is not a matched-budget comparator.

## Convergence and failure accounting

| Arm | All hard: conv / fail / infeasible | Matched hard: conv / fail | Smooth: conv / fail |
|---|---:|---:|---:|
"""
for arm, m in metrics.items():
    h, s = m["matched_metrics"]["hard"], m["matched_metrics"]["smooth"]
    text += (
        f"| {arm} | {m['all_converged']} / {m['all_failed']} / {m['all_infeasible']} | "
        f"{h['converged']} / {h['failed']} | {s['converged']} / {s['failed']} |\n"
    )
text += """
Both completed-source inventories preserve the three earlier regional calibration
failures in their parent inventory. No failed fit becomes eligible merely because
the optimizer reports success. No diagnostic result is substituted into cohort
means. Full per-source coverage and paired regressions are in the source reports.

## Evaluation-only reachability check

The closest qualified hard-model endpoint is an evaluation diagnostic; it does
not select an operational winner or a seed for a future scan.

| Arm | Closest qualified source | Error km | Objective | Operational winner objective |
|---|---:|---:|---:|---:|
"""
for arm, m in metrics.items():
    row = m["closest_qualified_evaluation_only"]
    text += (
        f"| {arm} | {row['index']} | {row['error_km']:.6f} | "
        f"{row['fit']['objective']:.3f} | {m['hard_all_winner']['fit']['objective']:.3f} |\n"
    )
text += """
These observations distinguish sampled hypotheses from the model's selected
answer; they cannot justify truth-guided retention. The earlier1.15km recovered
joint seed remains diagnostic because of its reference-guided ancestry. Direct
ordinary starts and the clock-proposal/cross-arm sequence are different searches.
The latter is running separately in iteration71 with the fixed source policy.

## Execution limitations

Hard fits use20seconds/600iterations; smooth fits use90seconds/600iterations,
following measured implementation cost. This is not an equal-wall-budget test.
Late fits overlapped the eight-worker iteration69 run, where unchanged controls
showed reduced evaluation counts and four convergence losses at20seconds.
Iteration70 restored all16 original numerical solutions under two workers and a
larger allowance. Therefore this first-attempt comparison cannot isolate horizon
smoothness from available numerical work. Preserve the original receipts and
report limitations; any controlled repeat requires separate frozen execution.

The numerical models and scientific convergence gates remained fixed. Reporting
updates only mark complete coverage and disclose execution overlap. Results are
descriptive evidence, not grounds for deploying a new default.

## Dataset and goal status

Full-cohort means remain1.360148km fitted-c /1.738896km zero-c over63DS16,
51DS17 and34DS18. The original48/additional15 DS16 membership and consumed24/
other10 DS18 exposure accounting remain intact. The below1km goal is unachieved.
Uniform three-dataset policy evaluation and independent validation remain required.
No production, contract, fixture, QNAP or RF changes occurred.

[Complete hard report](../2026_10_09_position_error_iter55/README.md),
[matched hard/smooth report](../2026_10_09_position_error_iter60/README.md), and
[execution qualification](../2026_10_09_position_error_iter70/README.md) provide
the full receipts, metrics and limitations. This report's summary pins its source
summaries by SHA256 and refuses to overwrite the completed snapshot.
"""
(HERE / "README.md").write_text(text)
print(
    {
        a: {
            k: metrics[a][k]["error_km"]
            for k in ("hard_all_winner", "hard_matched_winner", "smooth_matched_winner")
        }
        for a in arms
    }
)
