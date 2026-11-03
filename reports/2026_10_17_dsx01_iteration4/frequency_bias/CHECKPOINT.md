# Frequency-bias checkpoint — 2026-10-17

Completed: empirical constant absolute-Hz per-satellite model with two fixed
global prior widths, all-five matched fitted/zero-c full-recording comparisons,
S01/S04 own-model continuation controls, original-production and matched-b0
paired reporting, 215-pair timing histograms, all-15-window coverage plots, and
both-direction bias-only conditional prediction on all five sources.

38 full-data receipts, zero execution failures; 30 primary and eight controls.
16,078 actual objective calls, 1,680 cached candidate-profile calls. Per-inference
cap 1,000 actual objective calls/120 seconds, maximum observed 611. Four full
endpoints miss strict projected stationarity and remain labelled rejected.

40 conditional receipts, zero execution failures; 4,815 actual cached density
objectives, 3,360 cached profiles. Cap 300/30 seconds, maximum observed 261.
One training orbit projection and one post-selection held projection per fit.
35 endpoints meet strict bias stationarity. 39/40 worsen excluded-half NLL.
No physical/calibration/q coordinates move in conditional inference. Baseline
is explicitly full-data-conditioned, precluding a clean cold-validation claim.

σ1000 fitted-c descriptively assigns 462/693 original challenge winners and
strongly restores 8/15 windows, versus b0 continuation 422/693 and immutable
original96/693. All five σ1000 fitted endpoints are strict. Original normalized
new/lost remain separately labelled from matched continuation new/lost; all
populations and satellite identity changes are preserved. σ1000 still leaves
bad configured-reference distances >100 km and fails conditional prediction.
No width/model is promoted based on these in-sample counts.

Nine hardware-free component tests passed under the pinned scientific runtime.
They cover exact b0 nesting, all model derivatives, q normalization, soft
visibility, shared absolute-Hz physics, proper prior/gauge, bounded profiles,
held-CFO perturbation invariance through both optimizers, conditional cached
likelihood equivalence, sign recovery and objective caps.

No additional runs are active or needed for this checkpoint. No new RF,
production edits, changes to earlier sealed directories, commit or push. The
manifest covers all artifacts in this directory except itself. Receipt hashes
bind inference sources; reports do not alter scientific endpoints.
