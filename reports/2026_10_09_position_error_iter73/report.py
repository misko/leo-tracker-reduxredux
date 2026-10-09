"""Explain fixed-state score differences without changing inference."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
rows = json.loads((HERE / "results.json").read_text())["rows"]
comparisons = []
for arm in ("fitted-c", "zero-c"):
    winner = next(r for r in rows if r["label"] == "operational-winner" and r["arm"] == arm)
    closest = next(r for r in rows if r["label"] == "closest-evaluation-only" and r["arm"] == arm)
    recovered = min(
        (
            r
            for r in rows
            if r["label"] == "historical-recovered" and r["arm"] == arm and r["converged"]
        ),
        key=lambda r: r["objective"],
    )
    for name, row in (
        ("Closest ordinary (evaluation only)", closest),
        ("Recovered diagnostic (oracle ancestry)", recovered),
    ):
        comparisons.append(
            dict(
                arm=arm,
                label=name,
                winner=winner,
                alternative=row,
                deltas={k: row["components"][k] - v for k, v in winner["components"].items()},
                total_delta=row["objective"] - winner["objective"],
            )
        )
(HERE / "summary.json").write_text(json.dumps(dict(comparisons=comparisons), indent=2) + "\n")
fig, axes = plt.subplots(1, 2, figsize=(12, 4), layout="constrained")
components = ("frequency_nll", "relative_timing", "clock", "common_timing")
labels = ("Observation likelihood", "Relative timing", "Smooth clock", "Common timing")
colors = ("#227c9d", "#ee7733", "#228833", "#aa4499")
for ax, arm in zip(axes, ("fitted-c", "zero-c"), strict=True):
    selected = [r for r in comparisons if r["arm"] == arm]
    for j, (key, label, color) in enumerate(zip(components, labels, colors, strict=True)):
        ax.bar(
            np.arange(2) + (j - 1.5) * 0.18,
            [r["deltas"][key] for r in selected],
            width=0.18,
            label=label,
            color=color,
        )
    ax.scatter(
        np.arange(2),
        [r["total_delta"] for r in selected],
        color="black",
        marker="D",
        label="Total score delta",
        zorder=4,
    )
    ax.axhline(0, color="black", linewidth=0.7)
    ax.set_xticks(
        np.arange(2), ["Closest ordinary\nevaluation only", "Recovered diagnostic\noracle ancestry"]
    )
    ax.set(title=arm, ylabel="Cost relative to ordinary score winner (lower is better)")
axes[0].legend(fontsize=8)
fig.suptitle("Same common-bank model: likelihood and timing penalty compete")
fig.savefig(HERE / "components.png", dpi=160)
text = """# Iteration73: the nearby ordinary solution loses on observation fit, not timing penalty

**The3.43km fitted-c hypothesis already has a much smaller timing penalty than
the58.40km winner. It loses because its observation-likelihood cost is worse by
more than that penalty advantage.** The historical recovered solution combines
low timing penalty with a better observation fit, but retains oracle ancestry.
This audit changes no fits, starts, priors, winners or dataset errors.

![Score component differences](components.png)

## Fixed-state reconstruction

Commit `06e548ee2` froze12 saved states before evaluation: both ordinary score
winners, both closest qualified evaluation-only states from the completed direct
search, and all eight historical iteration52 states. Rebuild the same common145
bank/ordinary clock frame, sigma1/common3 and joint100 model. Direct evaluations
reproduce every saved objective within1e-6; the four components sum to objective
within1e-7 and clock penalties reproduce within1e-7. No optimization is run.

The raw key `frequency_nll` is the **full observation mixture likelihood**,
including visibility, detection/clutter and normalization terms. It is not just
squared frequency residual. RMS is reported separately and must not stand in for
the full score or for position accuracy.

| Arm | State | Error km | Obs. NLL | Relative timing | Clock | Common timing | Total | RMS Hz |
|---|---|---:|---:|---:|---:|---:|---:|---:|
"""
shown = []
for c in comparisons:
    if c["winner"] not in shown:
        shown.append(c["winner"])
    shown.append(c["alternative"])
for r in shown:
    c = r["components"]
    text += (
        f"| {r['arm']} | {r['label']} | {r['error_km']:.6f} | {c['frequency_nll']:.3f} | "
        f"{c['relative_timing']:.3f} | {c['clock']:.3f} | {c['common_timing']:.3f} | "
        f"{r['objective']:.3f} | {r['frequency_rms_hz']:.3f} |\n"
    )
text += """
## Cost differences from each arm's ordinary winner

| Arm | Alternative | Obs. delta | Relative timing | Clock | Common timing | Total delta |
|---|---|---:|---:|---:|---:|---:|
"""
for r in comparisons:
    d = r["deltas"]
    text += (
        f"| {r['arm']} | {r['label']} | {d['frequency_nll']:+.3f} | "
        f"{d['relative_timing']:+.3f} | {d['clock']:+.3f} | "
        f"{d['common_timing']:+.3f} | {r['total_delta']:+.3f} |\n"
    )
text += """
The timing prior favors the nearby ordinary state strongly, but its observation
fit remains poor. In the historical recovered state, observation cost is still
worse than the distant winner, yet the timing-prior saving more than compensates.
Thus the same objective can favor a recovered nearby state when one is available.
The direct ordinary search has not reached that complete state; a position near
the receiver is insufficient if its other fitted parameters remain in a different
minimum. These fixed endpoints differ in multiple parameters, so the audit does
not isolate clocks as the sole cause or prove a connecting optimization path.

It would be premature to fix this by tuning a stronger prior from one scan's
reference error. Iteration71 instead tests the already specified clock proposals
and cross-arm continuation uniformly across all ordinary regions and both source
types. Its result will test a search-mechanism hypothesis; this decomposition does
not supply any new seed to that running experiment.

## Receiver-pair diagnostic, with identity caveat

Across516 same-time/RF singleton pairs, the fraction of corrected differences
within250Hz is about0.2% for the closest ordinary state, versus21–23% for the
distant winner and recovered diagnostic. The all-pair median absolute difference
is about44–47kHz in all these states. Most pairs are therefore not a demonstrated
common-satellite sample. Neither that median nor the within250Hz fraction is an
independent physical clock truth measurement or an operational selection score.
They only motivate robust pair-derived proposals; no duplicate pair penalty is
added to the likelihood. Raw per-state counts/fractions remain in results.json.

## Truth isolation and goal status

The closest-state label uses reference position only for post-fit root-cause
evaluation. It is explicitly prohibited as a future operational seed-selection
rule. Historical recovered states carry the iteration31 reference-guided region
ancestry, despite the reference-free bank construction. They remain diagnostic.
No reference coordinate affects an operational bank, region, prior or winner.

All148 cohort means remain1.360148km fitted-c /1.738896km zero-c, with63DS16,
51DS17 and34DS18 fully accounted for and their exposure labels preserved.
No completed cohort result is replaced. Independent validation remains required.
Production hard60 recovery, fitted-c default and longest16 PNGs remain unchanged;
no new RF collection or public-contract/fixture changes. The below1km goal remains
active. Ruff passes and the component plot was inspected.

[Raw fixed-state audit](results.json), [differences](summary.json) and
[frozen protocol](protocol.json) retain all evidence, including the unqualified
historical state that was never eligible to win.
"""
(HERE / "README.md").write_text(text)
print([(r["arm"], r["label"], r["total_delta"]) for r in comparisons])
