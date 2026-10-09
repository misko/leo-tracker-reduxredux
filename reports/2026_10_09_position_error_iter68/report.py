"""Describe proposal availability without position-reference evaluation."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
data = json.loads((HERE / "results.json").read_text())
rows = data["rows"]
feasible = [r for r in rows if r["status"] == "feasible"]
summary = dict(
    endpoints=len(rows),
    feasible=len(feasible),
    infeasible=len(rows) - len(feasible),
    pairs=sorted({r["pairs"] for r in feasible}),
    accepted_controls=len(feasible),
    accepted_new_clock_starts=sum(len(r["starts"]) - 1 for r in feasible),
    rejected_new_clock_starts=sum(len(r["rejected"]) for r in feasible),
    endpoints_with_new_starts=sum(len(r["starts"]) > 1 for r in feasible),
    max_historical_residual_difference_hz=max(
        r["max_residual_difference_hz"] for r in data["qualification"]
    ),
)
(HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
fig, axes = plt.subplots(1, 2, figsize=(11, 4), layout="constrained")
axes[0].scatter([r["index"] for r in feasible], [len(r["starts"]) - 1 for r in feasible], s=12)
axes[0].set(
    xlabel="Frozen ordinary endpoint index",
    ylabel="Accepted extra clock starts",
    title="Unchanged control retained separately",
    yticks=range(5),
)
slopes = [p["slope_hz_s"] for r in feasible for p in r["proposals"]]
axes[1].hist(slopes, bins=np.linspace(-120, 120, 25), color="#227c9d")
axes[1].set(
    xlabel="Proposed relative slope correction (Hz/s)",
    ylabel="Proposal count",
    title="Before per-receiver hard60 feasibility check",
)
fig.savefig(HERE / "inventory.png", dpi=160)
text = f"""# Iteration68: observation reconstruction and ordinary clock-proposal inventory

**All eight historical pair/residual reconstructions pass.** The same helper
generates {summary["accepted_new_clock_starts"]} feasible extra clock starts from
{summary["endpoints_with_new_starts"]} of187 feasible ordinary endpoints. This is
an input/preparation audit, not an optimization experiment or localization gain.

![Ordinary proposal availability](inventory.png)

## Historical observation-path qualification

Commit `bb61524fe` froze the executable and523 source/input hashes before execution.
Both consumed recordings are loaded through the existing scientific input path.
For each of their four saved fitted-c states, the audit rebuilds singleton
receiver pairs directly from prepared observation times, RF and receiver IDs.
Pair indices exactly match the iteration34 receipts. Nuisance corrections are
rebuilt from each state's baseline, affine/RF parameters and smooth-clock
coefficients, then subtracted from measured frequencies.

All eight circular residual arrays match within1e-7Hz; the observed maximum
difference is **{summary["max_historical_residual_difference_hz"]:.3g}Hz**.
Historical reference-guided states appear only in this isolated qualification.
They do not initialize the ordinary proposal census below. No optimizer runs,
reference errors, or new satellite assignments are used in either part.

## Ordinary proposal census

The census includes all192 ordinary endpoints from iteration53. The five already
infeasible shared-frame transports remain explicit and receive no proposals.
Every other endpoint uses its saved transported seed and clock coefficients with
the ordinary common145-bank calibration frame. Each contains{summary["pairs"]}
singleton receiver pairs; this is the available-pair count, not confirmed
same-satellite support. The unchanged iteration36 consensus generator supplies
up to two line proposals, each tried with both receiver anchors.

| Item | Count |
|---|---:|
| All endpoints | {summary["endpoints"]} |
| Feasible / previously infeasible | {summary["feasible"]} / {summary["infeasible"]} |
| Unchanged controls retained | {summary["accepted_controls"]} |
| Accepted extra clock starts | {summary["accepted_new_clock_starts"]} |
| Extra starts rejected by residual slope bound | {summary["rejected_new_clock_starts"]} |
| Endpoints with at least one accepted extra start | {summary["endpoints_with_new_starts"]} |

No clipping is used. The ±60 bound applies to each receiver's resulting affine
coefficient in the shared frame. Proposed relative corrections can exceed60
while the resulting coefficients remain feasible, or be smaller and still fail.
This is not an absolute physical-clock drift measurement. The plot's proposal
slope distribution precedes this feasibility check.

Every feasible endpoint receives the same rule, without reference-error ranking
or choosing the historically useful region. Results preserve masks, starts,
rejections and the original192-member endpoint inventory. This does not commit
to fitting every proposal: the next experiment still needs a frozen, bounded,
uniform start/continuation budget and matched c arms. Candidate observations and
existing source calibration are reused; no extra pair likelihood is introduced.

## Interpretation and remaining work

Iteration67 reproduced the historical generator from saved residuals. This audit
closes the prepared-observation-to-residual path and demonstrates that ordinary
starts can supply proposals through the same array interface. It does not show
that these starts reach or select a better position. The existing direct hard
and smooth fitting jobs remain separate and unchanged.

The full148 cohort results remain1.360148km fitted-c /1.738896km c0, with all
63DS16,51DS17,34DS18 members accounted for. The known/reference position is
evaluation-only. All experiments here are consumed-data development. A common
bank and selection policy must be evaluated uniformly across those datasets;
independent validation remains required. The diagnostic1.15km result still cannot
replace the DS18 failure. Production, contracts, fixtures and RF collection are
unchanged. The below1km goal remains active.

[Raw results](results.json), [summary](summary.json), and [frozen protocol](protocol.json)
retain the audit evidence. Source checks and assertions passed; Ruff passes and
the visualization was inspected. The seven helper/generator tests passed in
iteration67; their numerical source is unchanged here.
"""
(HERE / "README.md").write_text(text)
print(summary)
