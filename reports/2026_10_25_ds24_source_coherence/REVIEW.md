# Fast-scan localization: what to retain, what to stop, and what to test next

Reviewed 2026-10-25 against the saved DS23/DS24 comparisons, recent causal
identity studies, and this iteration's native-observation audit. This is a
research assessment, not a new algorithm release or a claim of improved
position accuracy. The retained reference is fresh ALGO02-v1 with qualified
causal signed orbital-timing means and equal-assignment-prior family comparison.

**We made a substantial early improvement, but the recent experiments mostly
narrow explanations rather than deliver a transferable precision gain.** The
strongest measured limitation is the similarity between position changes and
satellite orbital timing/shape changes in Doppler. Individual association,
source-construction and receiver-model errors remain possible. We have not
established an irreducible accuracy floor or independently verified every
accepted satellite identity.

## The results that should guide decisions

The rows below are separate matched experiments. Their gains cannot be added
together. Both c=0 and fitted-c results are shown where position is compared;
c is the learned RF-dependent calibration coefficient.

| Experiment | c=0 mean error | Fitted-c mean error | Decision |
| --- | ---: | ---: | --- |
| ALGO01 to ALGO02, 404 common DS23 outputs | 1.870 to 1.520 km | 1.870 to 1.508 km | Retain the substantial improvement; qualified output count decreased from 407/413 to 404/413. |
| Signed-prior reference to equal-prior family comparison, 410 DS23 scans | 1.509 to 1.479 km | 1.498 to 1.469 km | Useful modest improvement; fitted c improves 40 scans, worsens 34 and leaves 336 unchanged. Temporal-block uncertainty still limits the aggregate claim. |
| Full DS23 recovery candidate | Worsens | 1.469 to 1.591 km | Reject: fitted-c association rises 70.08% to 75.08%, but P95 worsens 3.157 to 3.473 km. |
| DS24 all eight / CH1-4 / CH5-8, same 24 usable scans | 1.202 / 1.538 / 2.040 km | 1.220 / 1.558 / 2.040 km | All eight channels help on average; the benefit is limited by shared information. |
| Smooth RX1 correction, 24 development scans | 1.202 to 1.112 km | 1.220 to 1.120 km | Development lead, subsequently tested. |
| Same frozen RX1 correction, eight later scans | 1.243 to 1.240 km | 1.239 to 1.224 km | Development-sized gain did not transfer; P95 worsens in both arms. Keep the reference. |

The original graph, EM, Hough and multiple-hypothesis constructors already
achieved roughly 90-93% polynomial membership on DSX01 S01. That is different
from satellite identification and from membership in the position likelihood.
For the reviewed DS24 24-scan cohort, the likelihood contains 78,067/108,600
original GLRT winners (71.8849%). This is 24 usable inputs from a frozen
34-recording population, not 34 successful localizations. Higher postfit
coverage does not necessarily add measurements to the position fit.

Sources: [ALGO02](https://github.com/misko/leo-tracker-reduxredux/blob/main/reports/2026_10_19_algo02_ds23_full/README.md),
[family comparison](https://github.com/misko/leo-tracker-reduxredux/blob/main/reports/2026_10_22_ds23_family_cavity_full_assessment/README.md),
[rejected recovery](https://github.com/misko/leo-tracker-reduxredux/blob/main/reports/2026_10_23_algo04_candidate_full_ds23/README.md),
[channel comparison](https://github.com/misko/leo-tracker-reduxredux/blob/main/reports/2026_10_24_ds24_channel_halves/README.md),
[later RX1 test](https://github.com/misko/leo-tracker-reduxredux/blob/a3ae6254d2dee7dc25e794eac06279fee9631c03/reports/2026_10_25_ds24_phase_shape_validation/README.md).

![Separate matched comparisons and the limited transfer of the RX1 correction](review_figures/measured_results.png)

The overview and information figure below are unchanged figures from the
previous evidence synthesis, copied with source hashes in
`review_figures/provenance.json`. Their underlying comparisons have not been
rerun for this review.

## Which explanations remain credible?

**Orbital timing and geometry are the strongest measured limitation.** In the
DS24 local information diagnostic, the median weakest-direction scale is
534 m. Treating receiver terms as known changes this to 386 m, orbital timing
as known to 110 m, and timing plus shape as known to 56 m. The median strongest
timing/weak-position correlation is 0.935. Bands share a median 11 calibration
families, and their weak directions differ by only 17.7 degrees. Extra channels
often measure the same orbit uncertainty again. These conditional scales are
neither achieved errors nor calibrated confidence bounds; the experiment does
not justify making unknown orbital corrections artificially certain.

![Local conditional information controls, not achieved position accuracy](review_figures/conditional_information.png)

**A missed continuous minimum is a lower priority for the tested models.**
Thirty targeted restarts return within 2.06 cm of the original solution. Four
half-channel label transfers supply no qualified better full-data solution.
This does not rule out discrete identity alternatives or prove global
optimality over every possible assignment.

**Frequency precision and receiver discrepancy contribute, but do not explain
the whole error.** Remeasuring 322 RX2 curves reduces median fixed-degree
scatter from 78.07 to 22.18 Hz without a qualified cohort position gain. The
later RX1 correction improves CFO RMS much more consistently than geography.
On its worst later case, fitted-c RMS improves 5.917 Hz while position worsens
261 m. Cleaner residuals do not uniquely locate the receiver.

**Identity and source selection are still incompletely tested.** Independent
pipeline variants usually agree on accepted labels, but can share the same
mistake. Recent new-family studies include close causal alternatives and
arm-dependent preferences. The small synthetic nomination pilot ranks every
generating physical label first, but its generator and final scorer use
different parent conditioning, and its polynomial nulls are extremely easy
mismatches. It does not establish a calibrated false-association rate for
real near-ties, crossings or winner-selected GLRT observations.

**Sample rate and antenna direction remain unisolated.** All compared usable
fast scans have 10 MS/s. They cannot establish a causal sample-rate effect.
The nominal 40-degree feed separation supplies sky coverage; there is no
calibrated bearing measurement or separated geolocation baseline in the
current position likelihood.

The [bottleneck report](https://github.com/misko/leo-tracker-reduxredux/blob/main/reports/2026_10_24_ds24_bottlenecks/README.md)
contains the information, restart, receiver and hardware evidence. The
[methods inventory](https://github.com/misko/leo-tracker-reduxredux/blob/main/reports/2026_10_25_ds24_next_directions_review/methods/FINDINGS.md)
records the already-tested soft identities, temporal recovery, noise evidence,
nonlinear phase and log-volume variants.

## What the newest evidence changes

The previous ordinary full-catalogue CH5 comparison favored 57450 as a plausible
explanation of the complete 57-point DS24-0013 RX2 CH5 source. The later CH5-only
prediction conditioned on that candidate. The complete CH3 witness
strongly preferred unresolved status over sharing that candidate. CH4's
complete-source comparison hit its numerical budget. These are conditional
model results, not independent satellite identification.

This iteration reconstructs every original native winner and graph index in
the scan. CH4 is a single 43-point owner whose quartic was already marked
`structure_flagged`; its saved adjacent residual correlation is about 0.823.
There is no recorded receiver, RF or graph-owner change near the apparent
250-second departure, and the archived alternate peaks do not establish a
second coherent continuation following CH5's prediction. A smooth ownership
mistake remains possible, but the claimed crossing is not demonstrated.
CH3 has a real isolated endpoint after a 7.8-second gap and an intervening
unassigned winner. Neither observation should be deleted or promoted to an
independent source by inspection.

The apparent CH4 physical prefix near the middle cut lasts only 14.524 s.
The exact historical runner required at least 20 s before its separate
curvature test, so that portion could never enter its curved-calibration
salvage route. This explains a proposal limitation. It does not establish a
correct identity or authorize short/linear evidence to calibrate offsets and
drifts. A separately qualified predictive role would be a different question.

![Original native ownership and unchanged CH5-only predictions](ownership/crossing_detail02.png)

See [native findings](ownership/FINDINGS.md), [historical support check](eligibility/FINDINGS.md)
and [this iteration's terminal comparison](README.md). Same-probe alternative
peaks are competing candidate hypotheses from one probe, not additional
independent observations.

The prior active-parent phase-dependent shape control is now closed: on two
families and 20 fixed position probes its largest local movement proxy was
0.571 m, below the declared 25 m materiality threshold. This specific omitted
coupling does not justify a broad optimizer experiment. Its limit is the fixed
noise-precision, single-family treatment; it is not a complete hierarchical
posterior calculation.

The old cached 2,442.510 Hz CH5 residual is also not a verified 57450 fit. A
historical row was relabeled without recomputing its cached metrics. The
[published provenance correction](https://github.com/misko/leo-tracker-reduxredux/blob/b4de477876ab879c29ef0ef2ffdd0e11339f1349/reports/2026_10_25_ds24_ch5_prediction/mechanism/FINDINGS.md)
preserves the evidence; new whole-source calculations are unaffected.

## Recommended next work, in priority order

### 1. Follow the now-specific partial-compatibility result once, then move on

The frozen CH4 comparison completed on all 100 CH5+CH4 observations. The
physical-portion-plus-unresolved-remainder class beats whole physical, whole
polynomial and two-piece polynomial controls in both arms, after averaging
the predeclared cuts and allocations. Its full-domain log-evidence lower
bound exceeds every competitor's upper bound by at least 2.969/3.277 units.
The entire attempt, including an input-path failure and smoke checks, uses
52.710 worker-seconds; no position fit or new association is adopted.

This is a concrete new lead: under these priors, the separate CH5 source's
full physical prediction contributes more than the flexibility of another polynomial piece.
It does not determine the physical cause or independently identify 57450.
Window diagnostics distribute weight across 14-point and 21-point prefixes;
both are shorter than the historical 20-second calibration prerequisite.
The breakpoint is not precisely identified.
This tests one declared proper-polynomial scale. It neither isolates the
effect of curvature nor establishes robustness to other unresolved-source priors.

One bounded ordinary-catalogue challenge of competing explanations for these
portions is now justified. Keep all original observations and an unresolved
outcome, do not force 57450 onto the favorable part, and seek a separately
supported continuation. If identities remain ambiguous or no continuation
exists, retain unresolved status and move on. Do not turn this result into a
blanket splitting policy, repeated cap extension or relaxed calibration gate.

### 2. Test blind association under an exactly matched observation model

This is the highest-value unfinished algorithm diagnostic. Create a small
curve-level control in two archived fast geometries where generation and
scoring use exactly the same radio background, orbital priors, shared
uncertainty, aliases and visibility law. Include plausible competing physical
satellites and unresolved curves, not only extreme broad polynomial examples.
Use artificial receiver positions independent of the evaluation GPS.

Run the ordinary catalogue nomination and source-assignment path beside a
known-label control on the same observations and budgets. The blind path must
not receive the generating label. Record nomination, physical/null ranking,
source qualification and position separately. This is a bounded mechanism
test; a tiny panel cannot calibrate a population false-match rate.

The outcome has a direct implementation decision:

* A good known-label result but failed blind result implicates nomination,
  ownership or identity selection; isolate the stage before adding more data.
* A poor known-label result under the same generative law calls for an
  information/inference diagnosis, with an accurate small reference calculation
  before blaming the optimizer or orbit prior.
* Successful matched-law controls with persistent real-data failures point
  toward missing measurement/physical effects or selection effects absent
  from that simulator. They do not identify which effect without another test.

The former synthetic studies already test many parts of this chain. The new
content must be matching the actual law and exposing blind selection, not
another inherited-label simulation or millions of draws around one old mode.

### 3. Spend recovery effort on new position information

Use the existing unused-source inventory to choose a source by expected
information in the weakest position direction after receiver and orbital
uncertainty are retained. Compare one such choice against one length-selected
choice from the same eligible pool and compute budget. The inventory already
selects different sources in three of four scans; its predicted weak-direction
improvements are only about 5, 21, 18 and 127 m, so do not promise a large gain.
The 127 m case relies on the already-examined, unqualified 0013/60108
assignment. Do not recycle those owners or the already-known 0011/0012
identity competitors as new discoveries. Availability of an unexhausted,
informative source must be checked before starting another position trial.

A new channel of the same satellite may validate identity or receiver behavior.
A genuinely different satellite direction may improve geometry. Keep these
benefits distinct and retain shared uncertainty. Conditional information is
for allocating work, not accepting an identity. A source must survive ordinary
causal alternatives and an unresolved outcome before it can move position.
Preserve existing likelihood IDs and report any lost postfit IDs explicitly.

### 4. Check for a genuinely additional observable in the existing recordings

If the preceding tests expose an information limitation, run a short feasibility
audit of existing timing, signal-power, synchronization and pose metadata.
Determine whether it supports an independently calibrated observable that can
separate position from orbital timing. Neither nominal feed direction nor an
uncalibrated frame timestamp supplies such a constraint by itself.

This is a metadata and observability decision first. Missing calibration is a
stop result. It does not authorize new RF collection, hardware purchases,
stationary multi-scan pooling or a moving-trajectory prototype. Another CFO
estimator experiment should name a specific measurable bias, retain fixed
windows/native IDs, and show independent predictive benefit before localization.

## Branches to deprioritize and release criteria

Do not repeat generic continuous multistart, unrestricted recovery, blanket
phase narrowing, unconstrained per-track corrections, active-family-only soft
labels, log-volume removal or the now-small phase-dependent shape correction.
Causal TLE-history forecasts, correlated orbit priors, temporal HMM recovery
and physical sample-clock corrections have already been tested; revisiting
them needs a new, falsifiable mechanism. Better in-sample fit alone is
insufficient.

Use two bounded engineering branches and one independent SOL xhigh reviewer.
Every branch should end with a concrete implementation decision, including
stopping an unproductive direction. Do not spend another full-dataset run on a
change without a credible small-study mechanism and preserved qualification.

For a candidate release, freeze a complete policy before evaluation and keep
matched c=0/fitted-c observations, candidates, other priors and budgets. Report
frequency score, polynomial membership, postfit association, actual likelihood
membership, qualification, runtime, position mean/median/tails and failures
separately. Preserve exact reference fallbacks. Then evaluate the broader DS23
population and an exposure-checked unused recording block; all presently
reviewed DS24 examples are development evidence. A fresh split of already
inspected scans does not create unseen validation, and same-site success does
not establish new-location transfer.

Inference retains causal TLEs and the 25 by 25 km region centered at
37.906, -122.545. The known evaluation coordinate remains excluded from
nomination, fitting, prior tuning and acceptance decisions.
