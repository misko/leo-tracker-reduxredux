# Lag-structure discovery feasibility

## Motivation

The FP64 scoring experiment removes an isolated-stage barrier but leaves
candidate discovery unimplemented within the real-time budget. Test whether
pilot temporal structure gives sufficiently narrow timing proposals.

## Problem

Raw PSD frequency ranking and simple adjacent-window tracking already lost too
many original hits. The reduced native differential detector has different
window/candidate coverage and cannot establish full-search individual recall.

## Solution

Fold lag products at lags 1, 3 and 5 samples using the physical frame offsets,
then correlate against the pilot template's lag structure. Compare centered
pilot-power correlation and a fixed sum of percentile ranks of lag1, lag3,
lag5 and power scores. Input to the
estimator is current-window IQ, the rate and its edge template only. Original
candidate coordinates are read only by the evaluator after proposal formation.

## Method

Development selection: four evenly spaced metadata entries per rate/edge
group in the existing DS7 704-dwell input manifest, 32 dwells total. Each dwell
has 22 receiver-windows; no window or receiver is skipped. No new RF collection.

For each score array retain at most 32 nonnegative local maxima, using circular
five-sample exclusion and descending score/ascending epoch ties. Report region
coverage at K=2,4,8,16,32, with +/-2 and +/-8 sample regions. Coverage uses
ordinary absolute epoch distance (not wrap distance), matching the existing
hit-association coordinate convention. Power uses signed correlation and only
strictly positive peaks; lag magnitudes are nonnegative. Flat arrays produce
no proposals.

Count each original margin>=0.025 candidate in the denominator, including
duplicates, regardless of whether the new method proposes anything. Also
report originally positive windows with at least one covered original entry.
This is **timing-region coverage**, not recovered GLRTs: no CFO refinement,
final scoring, candidate multiplicity, competition or one-to-one association
has been validated. It is neither an upper bound nor a promise of final recall.

No thresholds are fitted to labels. The variants and budgets above are an
exploratory comparison; choosing a winner afterward requires validation on
additional recordings and actual IQ-to-GLRT execution. Host feature timing is
not an ARM throughput measurement. Do not port a narrow proposal with poor
2.5 MS/s coverage merely because the kernel is cheap.
