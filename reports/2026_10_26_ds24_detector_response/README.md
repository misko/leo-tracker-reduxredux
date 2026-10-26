# Fast-scan review and a narrow CFO measurement repair

2026-10-26 UTC. The review recommends concentrating on measurement integrity
and independent orbital information. Increasing nominal association or adding
optimizer starts has not reliably improved localization. The retained
ALGO02-lineage reference remains in place; this study does not promote a new
ALGO or claim a geographic gain.

The latest bounded control identifies a specific estimator effect: the deployed
GLRT residual grid can leave small acquisition-frequency errors unchanged.
Making the maximum continuous **inside the original winning residual cell**
reduces single-source synthetic RMS error from about 16.6 Hz to 2.2–2.4 Hz.
Fresh signed-frequency/rate controls also improve. This is a measurement-model
result, with recorded-window checks reported separately below.

## What the accumulated experiments establish

These are different matched cohorts, not successive improvements to one common
benchmark. The full review and its source reports are
[published here](../2026_10_26_ds24_candidate_continuity/README.md).

| Experiment | Result | Consequence |
| --- | --- | --- |
| ALGO01 → ALGO02, 404 common DS23 outputs | Mean error 1.870 → 1.520 km with c=0; 1.870 → 1.508 km with fitted c | Retain the improvement; qualified availability changes from 407/413 to 404/413 |
| Equal-prior family comparison, 410 DS23 cases | Means 1.509 → 1.479 km c=0 and 1.498 → 1.469 km fitted c | Retain the modest gain with its same-site limitations |
| Broad graph recovery candidate | Association 70.08 → 75.08%, but fitted-c mean error 1.469 → 1.591 km and P95 3.157 → 3.473 km; c=0 also worsens | Extra associated points alone are an unsuitable optimization target |
| All / low / high channels, same 24 usable DS24 cases | Fitted-c mean 1.220 / 1.558 / 2.040 km; c=0 1.202 / 1.538 / 2.040 km | All channels already help on average; their information is correlated |
| Thirty continuous restarts | Final positions agree within 2.06 cm for the tested assignments | More of the same continuous multistart is low priority |
| Earlier RX2 pilot remeasurement, 322 curves | Median polynomial scatter 78.07 → 22.18 Hz without a qualified cohort position gain | Smoother frequency curves do not establish better localization |
| Shared RX1 correction | Development fitted-c mean 1.220 → 1.120 km; later eight cases 1.239 → 1.224 km with worse tails; later c=0 1.243 → 1.240 km | The larger development gain did not transfer |
| Candidate CFO/epoch continuity | No extra benefit from epoch cost; recorded rule qualifies 0/117 owners; one-source controls also produce extra smooth paths | Smoothness alone is insufficient evidence for source count or satellite identity |

The reviewed DS24 reference has 78,067/108,600 distinct original GLRT winners
in the position likelihood (71.8849%), on 24 usable cases from a frozen 34-fast
population. Polynomial membership and postfit associations have different
meanings and denominators. All these data and the later eight cases are exposed
development evidence; new-location generalization remains untested.

## The main information bottleneck remains shared orbital uncertainty

In the reviewed local DS24 model, median weak-direction SD is 534 m. Making
receiver terms hypothetically known changes it to 386 m; orbital timing known
gives 110 m; timing and shape known gives 56 m. Timing and weak-position
correlation reaches a median 0.935. These are conditional model diagnostics,
**not achieved errors or a demonstrated accuracy floor**.

Both bands frequently observe the same uncertain satellite motion. Their weak
position directions differ by only 17.7 degrees in the reviewed calculation.
The nominal 40-degree receiver pointing separation is not a measured bearing
or a spatial baseline. The fast cohort uses 10 MS/s throughout, so it cannot
identify a sample-rate effect. Current evidence therefore favors shared
orbital/position ambiguity plus specific measurement failures over a generic
optimizer-local-minimum explanation.

We should also avoid interpreting the earlier approximately 0.54 km result as
single-scan performance: it used causal averaging under a stationary-receiver
assumption. That does not meet the intended moving-receiver use case and is
outside this investigation.

## A concrete estimator effect and a minimal correction

The exact deployed detector acquires CFO on a fine grid with interpolation,
then scores 64 pilot symbols using a 512-bin residual-frequency transform.
Residual bins are about 443.892 Hz apart. The final CFO is **not simply
quantized at this spacing**, because acquisition is interpolated. But a zero
residual bin cannot correct a small error inherited from that interpolation.

Saved stage attribution finds zero fractional GLRT residual for all 48 receiver
outputs in the original 24-window single-source control. Their entire final
CFO error is inherited from acquisition. A 200 Hz/s chirp changes frequency by
only 4 Hz over the complete 20 ms window, insufficient to explain errors near
19.5 Hz solely through an in-window timestamp choice.

The research correction maximizes the continuous extension of the **same**
fixed-candidate correlation score within half a bin of its original maximum.
It preserves the physical samples, acquired CFO used for demodulation, epoch,
fractional epoch, symbols, frame support, normalization and original gate.
The rolled-control score receives the same treatment in its own original cell.
No source, satellite or observation is added. This is neither a new waveform
model nor full within-symbol re-demodulation at the corrected frequency.

Before using any correction, the cached correlations must reproduce the original
discrete exact/control scores and residual. Independent finite-lag and direct
complex-sum calculations must agree on an interior maximum with negative
curvature. Boundary or reference failures remain failed; no wider search or
replacement candidate is used. All 64 receiver slots pass these numerical
checks. Local numerical qualification does not certify a global peak or a
physical source.

Neither the sharper score maximum nor the synthetic 2 Hz result calibrates
real measurement uncertainty. Existing noise assumptions and admission rules
remain unchanged.

| Synthetic control | RX1 midpoint-CFO RMS, original → refined | RX2 midpoint-CFO RMS, original → refined |
| --- | ---: | ---: |
| Original 24 physical windows | 16.552 → 2.191 Hz | 16.633 → 2.350 Hz |
| Eight fresh physical windows, signed CFO and rate | 15.314 → 1.773 Hz | 15.133 → 1.508 Hz |

![Original and refined synthetic frequency errors](measurement/report/frequency_errors.png)

Absolute midpoint error decreases for 56/64 receiver outputs; eight become
worse despite numerical qualification. The improvement is an aggregate result,
not a per-point truth guarantee.

The original error's lag-one correlation changes from approximately −0.766/
−0.765 to −0.046/−0.071. This removes a visible structured component in that
control; it does not establish a universal white-noise measurement model.
The two receiver noise streams share the same generated waveform, and fresh
tests use the detector's sampled-frame template law. They are not independent
physical-waveform validation. Earlier continuous CFO/epoch/time refinement is
[explicit prior art](audit/PRIOR_ART.md); the distinct test here isolates the
exact deployed scope64 residual-grid response.

See the [complete measurement findings](measurement/FINDINGS.md),
[measurement protocol](measurement/PROTOCOL.md),
[implementation](measurement/refiner.py) and [source review](SOURCE_REVIEW.md).

## Select field evidence by its effect on position

The field panel uses the first two chronological usable DS24 scans. Selection
uses saved RF likelihood designs, never GPS error or the measured correction.
All original points of each selected owner belong to both c arms' curved
likelihood. We retain four complete owners and all 159 native points; two fixed
time quantiles per owner nominate eight diagnostic raw windows.

| Case / role | Original owner / family | Complete points | Local 1 Hz RMS susceptibility, c=0 / fitted c |
| --- | --- | ---: | ---: |
| 0010 target | RX1 CH7 T001 / 68566 | 38 | 8.60 / 8.63 m |
| 0010 control | RX2 CH4 T004 / 59244 | 37 | 1.30 / 1.35 m |
| 0011 target | RX2 CH4 T000 / 63936 | 64 | 20.34 / 20.57 m |
| 0011 control | RX1 CH1 T007 / 66341 | 20 | 0.32 / 0.29 m |

![Accepted owners and their conditional susceptibility](influence/report/selected_susceptibility.png)

These scores describe the largest local weak-direction response within a
declared degree-at-most-two smooth perturbation at reference RF, using each
arm's own original weak direction. They are not
observed biases, fitted geographic movements, bad-family diagnoses or expected
gains. The original parent designs are retained exactly. Family 63936 has the
original three physical orbit-mode slots; the other three selected families
do not. Their scores remain conditional on those baseline assumptions.

In particular, the synthetic acquisition error oscillates across visits, while
this susceptibility calculation considers smooth low-order errors. Multiplying
the synthetic 16.6 Hz RMS by these metres-per-hertz figures would not predict
a position gain. The actual complete recorded correction and its temporal
pattern must be propagated through the unchanged model.

The two time quantiles cannot establish the full owner's correction curve or
justify transferring a sparse adjustment to all its points. The
[panel findings](influence/FINDINGS.md) preserve every owner, exclusion,
native ID and raw-window authority. Acquisition CFO is absent from the original
tracking export; it must be recovered by exact detector replay rather than
deduced from the final CFO.

## Recorded replay: material differences, with original parity

All eight fixed recorded windows complete in one run. The bounded public reader
verifies the selected raw payload and exhausts its containing chunk. The exact
persisted detector policy reproduces every exported candidate on **both**
receivers within the frozen tolerances. Candidate count/order, rank, integer
epoch and admission agree exactly. Across all 96 archived complete fractional
candidate rows, every compared floating field also has zero replay difference.
The replay returns 128 candidate records in total; the other 32 were not in the
historical fractional export and have no corresponding archived-row parity
claim. All returned records are retained. No candidate is substituted or reranked.

Every requested original candidate again has zero discrete fractional residual.
The unchanged continuous refiner passes both frequency and target/control
numerical checks on all eight. The historical code/environment identity remains
unchanged before and after the run.

| Complete owner | Correction at 25% time quantile | Correction at 75% time quantile |
| --- | ---: | ---: |
| DS24-0010 target RX1 CH7 / 68566 | +71.47 Hz | −63.91 Hz |
| DS24-0010 control RX2 CH4 / 59244 | +79.04 Hz | −8.63 Hz |
| DS24-0011 target RX2 CH4 / 63936 | −4.68 Hz | +20.32 Hz |
| DS24-0011 control RX1 CH1 / 66341 | −4.01 Hz | −53.91 Hz |

![Recorded CFO changes at the fixed time quantiles](recorded/report02/cfo_refinement.png)

These are refined-minus-original estimates, **not errors relative to real CFO
truth**. High position susceptibility did not imply the largest correction:
the lower-susceptibility controls also change substantially. Two quantiles per
owner cannot distinguish a smooth bias from oscillating estimator error or
noise. A line through each pair would not establish a receiver drift.

This result justifies examining complete owners with the same fixed estimator;
it does not justify interpolating a correction across their other points,
changing satellite identities, reducing noise estimates or reporting a position
gain. No whole-owner, graph or geographic fit was run. The unchanged admission
decisions remain authoritative even when continuous exact/control scores move.

The recorded branch uses eight paired detector calls and 19.818 cumulative
numerical worker-seconds including preparation, below its original 180-second
cap. Every requested slot is retained. [Recorded protocol](recorded/PROTOCOL.md),
[all replay results](recorded/results.json), and
[original persisted execution authority](recorded/authority.json) bind the
comparison. Raw IQ is read-only and is not copied into this report.
The [recorded findings](recorded/FINDINGS.md) include the corrected distinction
between 128 returned detector records and 96 archived rows available for parity.

## Ranked next directions

1. **Validate this exact CFO repair on complete recorded owners.** First verify
   original detector parity on the fixed diagnostic windows. If the correction
   is material and numerically supported, remeasure the complete nominated
   owners with the unchanged rule. The eight-window parity/materiality check
   above now supports that next step. Assess temporal structure, frame-subset
   prediction and receiver/family dependence. Two-window changes or improved
   in-sample scores alone cannot justify a position claim.
2. **Separate one-source estimator artifacts from true source overlap.** The
   existing one-source counterexample and two-source controls provide a small
   test bed. Compare one versus two waveform components with a complexity
   penalty and prediction on separate frames. Preserve per-window dependence;
   extra smooth candidate paths are not independent detections. Prefer the
   simpler measurement repair if it explains the evidence.
3. **Seek independently supported orbital constraints.** Prioritize complete
   sources that add a different position direction after orbital/receiver
   uncertainty is projected out. Require a proposed satellite correction to
   predict a separately nominated owner across receiver or band. A source's
   own two halves are not an independent witness. Where such evidence is
   absent, retain uncertainty and move to another case.
4. **Run matched geographic validation only after a concrete rule qualifies.**
   Keep native observations, candidates, priors and search budgets matched in
   c=0 and fitted-c arms. Report frequency fit, association, likelihood membership,
   failures, mean/median/P95 and regressions separately. Use an exposure-checked
   later block for a validation claim; the reviewed DS24 data are development.

Stop repeating unchanged generic multistart, blanket prior tightening, broad
recovery, unconstrained receiver curves and source-only orbit fits. Do not tune
to 90% association at the cost of physical support or position accuracy. The
measurement repair is now a concrete candidate to test, while independent
orbital information remains the larger structural opportunity.

## Scope and reproduction

Three SOL xhigh branches cover the exact detector control, accepted-owner panel
and independent review. The measurement branch uses eight new paired detector
calls, reuses 48 old fixed candidates and charges about 14.20 numerical worker-seconds
including preparation. The saved-design panel charges 3.930 seconds. These are
research execution scopes, not embedded throughput measurements.

No production code, persisted contracts, golden fixtures or original corpus is
changed. No new RF is collected; raw storage is read-only. No postscan TLE or GPS
selection is introduced. Inference remains referenced to the existing 25×25 km
region centered at 37.906, −122.545; the supplied true site is evaluation-only.
There is no new position fit in this iteration and therefore no changed
operational association or position metric.
