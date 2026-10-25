# Fast-scan localization: updated review and next directions

Review date: 2026-10-25. This consolidates the accumulated DS23/DS24 work and
the two bounded experiments in this report. The retained operational reference
is fresh ALGO02-v1 with qualified causal signed orbital-timing means and
equal-assignment-prior family comparison. This iteration adds no qualified
position result, changes no operational associations and promotes no new ALGO.

The strongest measured limitation is weak separation of receiver position from
satellite orbital timing and shape. Individual identity, track-construction and
receiver-model failures remain. We have not proved that all accepted identities
are right, that the uncertainty model is calibrated, or that the remaining error
is an irreducible physical limit.

## What has worked, and what has not transferred

These are separate matched cohorts; the improvements cannot be added together.
Both c=0 and fitted-c controls are present in the source reports. Fitted c is the
learned RF-dependent calibration coefficient, not a satellite identity score.

| Tested change / cohort | c=0 mean position error, km | Fitted-c mean position error, km | What it supports |
| --- | ---: | ---: | --- |
| ALGO01 to ALGO02, 404 common DS23 outputs | 1.870 to 1.520 | 1.870 to 1.508 | A substantial within-site improvement, with qualified coverage decreasing from 407/413 to 404/413. |
| Signed-prior reference to equal-prior family comparison, 410 DS23 scans | 1.509 to 1.479 | 1.498 to 1.469 | A modest gain; fitted c improves 40 scans, worsens 34 and leaves 336 unchanged. Temporal dependence limits confidence in the aggregate. |
| DS24 all eight / CH1–4 / CH5–8, 24 usable fast scans | 1.202 / 1.538 / 2.040 | 1.220 / 1.558 / 2.040 | All eight channels already help on average. Individual scan regressions still matter. |
| Smooth RX1 correction, 24 development scans | 1.202 to 1.112 | 1.220 to 1.120 | A promising development result. |
| Same frozen RX1 correction, eight later scans | 1.243 to 1.240 | 1.239 to 1.224 | Little mean gain transferred; P95 worsened in both arms. Keep the reference. |

The rejected full DS23 recovery candidate increased fitted-c GLRT association
from 70.08% to 75.08%, but worsened mean error from 1.469 to 1.591 km and P95
from 3.157 to 3.473 km. Its c=0 arm also worsened. Separately, RX2 remeasurement
reduced median polynomial scatter from 78.07 to 22.18 Hz on 322 curves without
a qualified cohort position gain. These are direct counterexamples to using
coverage or residual RMS as the main improvement criterion.

The original graph, EM, Hough and multiple-hypothesis experiments achieved high
polynomial membership. That is not satellite identification. Keep three counts:
points represented by a polynomial, satellite-compatible postfit points, and
points entering the position likelihood. The reviewed 24-scan DS24 likelihood
uses 78,067/108,600 original winners, 71.8849%; these are the usable inputs from
a frozen 34-recording cohort, not 34 successful localizations.

The [previous evidence synthesis](https://github.com/misko/leo-tracker-reduxredux/blob/82bc36cbd138b7024bd7af4f988032f1da5255cd/reports/2026_10_25_ds24_review_next_actions/README.md)
links the original comparison reports and figures. The two latest experiments
are documented in [this iteration](README.md), with the historical diagnostic
correction in [the provenance findings](mechanism/FINDINGS.md).

## What the bottleneck evidence actually says

Receiver displacement and satellite displacement along an orbit can cause
similar Doppler changes. The reviewed DS24 information study found median
strongest timing/weak-position correlation 0.935. The channel halves share a
median 11 calibration families, and their weakest position directions differ
by only 17.7 degrees. More observations of those families share their orbital
uncertainty; they are not equivalent to additional independent satellites.

A local conditional calculation gives median weak-direction scale 534 m.
Treating receiver terms as known changes it to 386 m, orbital timing as known
to 110 m, and timing plus shape as known to 56 m. These are information
diagnostics under fixed identities, fitted noise and local geometry, not
achieved position errors or permission to tighten those priors.

Thirty targeted continuous restarts agree within 2.06 cm. Four transferred
half-channel assignments yield no qualified better full-data solution. This
reduces the priority of generic continuous multistart for the tested assignments;
it does not rule out different discrete identities. Known-label noiseless
simulations recover within 0.8–2.5 m, while stochastic draws can pass gates and
remain about 1 km wrong. Their generating and approximate inference laws differ,
so they do not establish a physical floor or a clean implementation verdict.

All usable fast recordings in this comparison are 10 MS/s. Sample-rate causality
is therefore unidentified. The nominal 40-degree feed separation changes sky
coverage; it is not a calibrated bearing observation or a spatial baseline.
Neither higher sample rate nor a different angle has demonstrated an accuracy
gain in these data.

## What this iteration changes in our interpretation

The complete 57-point DS24-0013 RX2 CH5 source remains a plausible 57450 candidate
under the tested conditional model. Its previous finite-pool comparison favored
57450 over the other nominated candidates and a proper unresolved polynomial.
The new discovery-only posterior has phase mean about 0.712/0.719 s and SD about
0.037 s in c=0/fitted-c, with all three standardized physical-mode means below
one in magnitude. Those diagnostic moments are numerically stable between the
two tested quadrature rules; they are not independent identity confirmation.
Two of three shape-mode variances remain essentially at their prior values,
so small posterior means do not establish measured orbital corrections.

Conditioning on that whole CH5 source, the complete CH3 source strongly favors
remaining unresolved over sharing 57450, in both c arms. CH4's joint comparison
does not complete its independent numerical reference before the original
budget. It remains unqualified. Neither result proves CH5's candidate false:
CH3/CH4 may simply represent different satellites. Neither supplies the missing
corroboration. There is no basis to force a group, relax its gates, or claim a
new position improvement.

An important historical correction changes the question we should ask. The old
2,442.510 Hz cached residual was carried unchanged when the CH5 row was relabeled;
it is not a verified 57450 fit residual. Actual saved salvage trials found a
32-point prefix at 37.461 Hz and a 31-point suffix at 42.441 Hz, followed by
rejection during refitting. Those alternatives share six points, and their
phases were selected on a 0.25 s grid. They are not independent witnesses or
evidence of a physical timing drift. The exact subsequent failing gate is not
recoverable from the archived intermediate metrics. The new whole-source
results were independently reconstructed and are unaffected by this correction.

The separate active-parent test now reevaluates the three physical-mode columns
at each integrated orbital-timing value, instead of freezing them at one
reference. On two RF-selected families and 20 fixed position probes, its
largest local weak-direction movement proxy is 0.571 m. Both arms pass numerical
checks and fall far below the predeclared 25 m materiality criterion. Close this
specific frozen-Gamma, single-family, resolved-mode mechanism. It does not prove
that every joint nonlinear/noise effect is negligible, but it supplies no
reason for an optimizer or a broad rollout of this change.

## Recommended next decisions

### 1. Test the concrete source-switching hypothesis visible in CH4

The new discovery-only residual plot supplies a more specific lead than another
general parameter sweep. In the fixed graph alias, CH4 stays close to a constant
residual until roughly 250 s, then develops an approximately linear departure,
reaching −3.49/−3.16 kHz in c=0/fitted-c by 264.83 s. CH3's isolated last point
is near the prediction, while its preceding body is several kHz away. These are
observations from saved predictions, not fitted breakpoints or confirmed joins.

First trace native ownership and the original GLRT alternatives near the
apparent crossing and the CH3 gap. Start with the existing one-dimensional
shared-D phase calculation: compare one physical source for the whole witness,
a contiguous physical portion with a proper unresolved remainder, and
piecewise-unresolved controls on all the same points. Integrate over the
predeclared split/allocation alternatives with normalized priors; do not just
take a best cut without charging for its search and extra model complexity.
Only a discriminating result justifies a more expensive two-physical-source
challenge. Nominate its causal alternatives ordinarily; do not assume 57450
correct for the favorable section or discard the remainder. A physical
continuation needs independent support before any partial acceptance.
Check whether the same discrepancy appears in concurrent receiver/channel
evidence before attributing it to a common LNB or orbital correction.

The decisive distinction is whether there are two coherent continuations in
the original observations. If there are, improve graph ownership at crossings.
If there are not, retain unresolved status or test the specific remaining
measurement/physical discrepancy. This is one exposed, bounded diagnosis;
it is not a blanket splitting policy or a revival of the already-tested
active-family HMM. Move on if no discriminating evidence is available.

### 2. Separate nomination failure from uncertainty using a small matched-law control

The most useful next identity experiment is a diagnostic with a definite
implementation decision, not another sweep for a larger association number.
Use a fixed conditional radio/background law, a few physically confusable
causal candidates and an unresolved alternative. Generate and score using the
same priors, covariance, alias measure and visibility normalization. Keep the
ordinary catalogue search separate from a known-label diagnostic on the same
observations; do not inject the generating label into ordinary nomination.
Freeze the same background mean and covariance for generation and every
candidate/null. If a target sharing an active parent's label receives a fresh
independent orbital prior, call it an exogenous-background control; it is not
the original shared-family conditional law.

Record four outcomes separately: whether the true candidate entered the
shortlist; whether it won the finite physical/null comparison; whether the
named predeclared numerical and parent/source gates passed; and how much position information it
would add. A correct generator label need not win every noisy draw. Look for
systematic nomination loss or a concrete mismatch in the score implementation,
not a desired success rate from a tiny sample.
There is no calibrated identity-acceptance rule established for this predictive
factor; passing a numerical or residual gate cannot be relabeled as one.

If the generator's candidate has an adequate common-law fit but is repeatedly
missing from nomination, alter the screen/proposal metric. If it is nominated
but remains ambiguous under the same law, adding search budget will not create
information. If model closure fails, repair that specific mismatch first.
Keep response-selected parent-cavity behavior as a separate sensitivity; this
conditional control is not a full IQ-to-position simulation or an end-to-end
false-association calibration. Cap it at two layouts and minutes. Do not turn
it into another numerical precision campaign for obviously losing candidates.

### 3. Move to the next source with different geometry when corroboration is absent

The existing inventory already ranks sources differently by conditional
information and point count in three of four scans. Use those metadata and
shared-nuisance calculations to allocate effort. Select a next complete owner
without reference to the desired satellite or GPS, retain all its native IDs,
and challenge it against ordinary causal alternatives plus unresolved status.
The current CH5 lead should remain a development candidate unless a defensible
additional witness or another declared identification test becomes available.

An independent owner helps test identity; a different satellite can add orbit
geometry. They are different benefits. Multiple channels of the same satellite
must keep their shared timing/shape uncertainty. A position comparison is useful
only once a source has adequate identity support and non-negligible conditional
information. Compare one information-selected source against one length-selected
source from the same eligible pool and compute budget, preserve original
likelihood IDs, and report actual error only after sealing RF decisions.

### Graph diagnostics must falsify joins rather than trim difficult observations

The CH3 endpoint has leverage near one after a 7.8 s gap; its quartic RMS is
21 Hz but leave-one-out RMS is 380 Hz. CH4 has distributed correlated residuals,
with adjacent correlation 0.823. Those are distinct signatures. A targeted
comparison can put continuation, multiple-source and unresolved hypotheses on
the same complete native observations, charge for extra segments, and ask
whether the proposed pieces predict each other. Keep the orphan contribution
for points a physical model cannot explain.

Do not simply delete the endpoint, split every curve, or assume visible
curvature guarantees identity. Temporal HMMs, orphan mixtures and grouped
recovery already have mixed or negative fast-scan results. Only a newly located,
reproducible construction failure justifies another implementation change.

### 4. Check whether the existing corpus contains an additional usable observable

If the targeted work above yields no independent position information, perform
a bounded metadata feasibility check for calibrated antenna patterns, pose,
per-channel power and synchronization. Their presence and calibration would
need to be demonstrated before defining a bearing or timing likelihood.
Nominal feed directions alone are insufficient. Missing metadata is a stop
result; it is not permission for new RF collection, hardware changes, stationary
multi-scan pooling or a moving-trajectory prototype.

## What to stop repeating and what merits promotion

Deprioritize unchanged generic multistart, unrestricted point recovery, blanket
prior narrowing, broad receiver drift, active-family-only soft identities,
Gaussian log-volume removal and the now-small active-parent phase/shape change.
Prior cross-family timing/covariance and sample-clock experiments also exist;
they should not be presented as unexplored generic cures. The original
[methods inventory](https://github.com/misko/leo-tracker-reduxredux/blob/main/reports/2026_10_25_ds24_next_directions_review/methods/FINDINGS.md)
and previous synthesis document their results and limitations.

Every position comparison must retain matched c=0/fitted-c observations,
candidates, other priors and budgets. Keep likelihood membership, postfit
coverage, frequency score, qualification, runtime and position mean/median/tails
separate. Preserve failures and the exact reference fallback. Causal TLEs and
the 25 by 25 km region centered at 37.906, -122.545 remain the inference setup;
the true coordinate is evaluation-only after RF decisions.

All reviewed DS24 examples are exposed development data. Any fresh validation
claim needs an exposure-checked unused session/time block. Promote an ALGO only
after a frozen broader comparison, including full DS23 evidence, establishes a
defensible gain with adverse tails and failures reported. New-location
generalization remains untested. The next wave should have two bounded tasks
and one independent reviewer, with an explicit stop decision for each branch.
