"""Report fixed-track descriptive continuity without proposing a new winner."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
data = json.loads((HERE / "results.json").read_text())
rows = []
for r in data["rows"]:
    a = [t["ordered"] for t in r["tracks"]]
    b = [t["permuted"] for t in r["tracks"]]

    def soft(ts):
        return sum(t["soft_same_numerator"] for t in ts) / sum(
            t["soft_signal_pair_mass"] for t in ts
        )

    rows.append(
        dict(
            label=r["label"],
            arm=r["arm"],
            source_index=r["source_index"],
            converged=r["converged"],
            signal_fraction=sum(t["signal_mass"] for t in a) / sum(t["windows"] for t in a),
            soft_same=soft(a),
            permuted_soft_same=soft(b),
            switches=sum(t["map_satellite_switches"] for t in a),
            signal_pairs=sum(t["map_signal_pairs"] for t in a),
            median_dominant_share=float(np.median([t["dominant_satellite_share"] for t in a])),
        )
    )
(HERE / "summary.json").write_text(json.dumps(dict(rows=rows), indent=2) + "\n")
fig, axes = plt.subplots(1, 2, figsize=(12, 4), layout="constrained")
for ax, arm in zip(axes, ("fitted-c", "zero-c"), strict=True):
    selected = [
        next(
            r
            for r in rows
            if r["label"] == label
            and r["arm"] == arm
            and (label != "historical-recovered" or r["source_index"] == index)
        )
        for label, index in (
            ("operational-winner", None),
            ("closest-evaluation-only", None),
            ("historical-recovered", 4 if arm == "fitted-c" else 5),
        )
    ]
    for offset, key, label, color in (
        (-0.2, "signal_fraction", "Satellite posterior mass", "#999999"),
        (0, "soft_same", "Adjacent same identity", "#227c9d"),
        (0.2, "permuted_soft_same", "Permuted same identity", "#ee7733"),
    ):
        ax.bar(
            np.arange(3) + offset, [r[key] for r in selected], width=0.2, label=label, color=color
        )
    ax.set_xticks(
        np.arange(3),
        ["Distant winner", "Closest ordinary\nevaluation only", "Recovered\noracle ancestry"],
    )
    ax.set(title=arm, ylim=(0, 1), ylabel="Track-membership-weighted fraction")
axes[0].legend(fontsize=8)
fig.suptitle("Wrong and recovered states both retain temporal association structure")
fig.savefig(HERE / "continuity.png", dpi=160)
text = f"""# Iteration74: simple continuity diagnostics do not distinguish the recovered state

**The distant winner is already temporally structured on the existing orbit-blind
tracks.** Its fitted-c adjacent same-satellite agreement is0.712 versus0.701 for
the recovered diagnostic. Both exceed their within-track permutation values.
The ordinary3.43km state is less coherent at0.599 and assigns much less mass to
satellites. These descriptive statistics do not provide a clean rule that ranks
the recovered state over the distant winner.

![Fixed-track continuity](continuity.png)

## Frozen scope and coverage

Commit `522383983` froze code and inputs before execution. The same12 fixed states
as iteration73 are evaluated under the unchanged common145 joint model; each
saved objective reconstructs within1e-6. No fit, bank, prior or operational winner
changes. Known receiver coordinates do not enter this audit's computations.
The closest state's prior selection was explicitly evaluation-only; historical
recovered states retain oracle ancestry and cannot initialize operational work.

Use all24 existing prepared bootstrap tracks, generated without orbit or receiver
reference information. Preparation keeps up to12 long tracks per receiver after
minimum15-window/15-second requirements. Therefore this is a fixed bootstrap
subset, not a census of all possible tracks. It covers
**{data["unique_track_windows"]}/{data["observations"]} unique windows**, with
{data["track_memberships"]} track memberships; one membership is duplicated.
Overlapping memberships are reported rather than treated as independent samples.

## Statistics and their meaning

For adjacent windows, sum products of same-satellite posterior probabilities and
divide by the product of total satellite posterior masses. Aggregate numerator
and denominator across the fixed tracks. This is posterior same-identity agreement
conditioned on both observations being signal; it is not a known-identity accuracy
measurement. Satellite mass is reported separately so clutter-dominated tracks
cannot appear strong merely through conditional normalization.

The MAP switch statistic counts identity changes only when both adjacent maximum
posterior states are satellites; clutter transitions do not count as satellite
switches. The dominant share is the median across tracks of the largest satellite's
share of total satellite mass. One deterministic within-track permutation, shared
across all states, provides descriptive time-order contrast. It preserves each
track's membership and posterior distribution. This is not an independent null
sample, confidence interval or significance test.

| State | Arm | Source | Qualified | Signal | Adjacent | Permuted | Switches / pairs | Dominant |
|---|---|---:|---|---:|---:|---:|---:|---:|
"""
for r in rows:
    text += (
        f"| {r['label']} | {r['arm']} | {r['source_index']} | {r['converged']} | "
        f"{r['signal_fraction']:.3f} | {r['soft_same']:.3f} | {r['permuted_soft_same']:.3f} | "
        f"{r['switches']} / {r['signal_pairs']} | {r['median_dominant_share']:.3f} |\n"
    )
text += """
The raw switch fraction slightly favors some recovered states, while soft adjacent
agreement and signal fraction favor the distant winner. Thus there is no consistent
separation across these simple statistics. Both families can explain temporally
structured frequency trajectories under different timing/clock assignments.
This supports investigating complete joint minima rather than treating the wrong
answer as necessarily a sequence of unrelated per-window coincidences.

## Decision and limits

Do not add a continuity cutoff or pick its weight from this scan's reference
errors. The audit does not rule out a proper joint track likelihood or temporal
association model; testing one would require a frozen generative model, gradients,
matched c arms and ordinary starts, followed by uniform DS16/DS17/DS18 evaluation
and independent validation. The present subset and posterior diagnostics cannot
prove which satellite identities are physically correct.

Iteration71 continues its fixed ordinary clock-proposal and cross-arm search,
unchanged by these evaluation diagnostics. No result replaces the full148 cohort:
mean1.360148km fitted-c /1.738896km zero-c, with complete63/51/34 membership and
preserved exposure labels. No RF collection, production or contract changes.
The below1km goal remains active.

Three synthetic tests pass: coherent versus clutter-only tracks, alternating
identities, and satellite-column permutation invariance within floating-point
roundoff. All12 score reconstructions pass. Ruff passes and the plot was inspected.
[Raw results](results.json) contain every fixed track's indices and ordered/
permuted statistics; [summary](summary.json) contains every state, including the
unqualified historical state. [Protocol](protocol.json) retains the frozen hashes.
"""
(HERE / "README.md").write_text(text)
