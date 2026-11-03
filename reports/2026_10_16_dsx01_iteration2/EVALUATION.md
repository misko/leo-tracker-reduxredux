# DSX01 iteration 2: exact profiles and controlled candidate restoration

The active user objective is to brainstorm, debug and iterate toward recovering
a larger fraction of the 15 GLRT sections. The previous goal turn made progress:
it measured every window and the timing distributions. The current turn uses
those results to fix measured proposal-selection failures, without replacing
the frozen population or choosing a different winning method per window.

All 693 observations in all 15 requested windows and all 20,084 whole-recording
observations remain the comparison populations. Original persisted contracts,
recordings, production workers and earlier scientific artifacts are unchanged.
No new RF acquisition is involved. Candidate numbers and window memberships
from earlier diagnoses are never algorithm inputs.

## Fixed-bank comparison

Compare original, frozen A with its original 180-evaluation allowance, A with a
matched 1,000-evaluation allowance, the original-objective continuation with
1,000 evaluations, and the new exact-profile method with 1,000 evaluations.
Every new run has a 120-second wall cap. This explicitly extends the initial
180-call experiment; the larger allowance is not attributed to the method alone.
The matched A and continuation controls distinguish allocation from algorithm.

The exact method profiles each satellite's timing on all training observations,
changing one physical timing per profile column. Both gained and lost frequency
support contribute to the unchanged conditional singleton likelihood and its
normalizer. Coarse timings cover the existing physical ±20 s bounds at 0.5 s
spacing; 0.05 s local refinement follows. Profile calls are recorded separately
from full objective evaluations: one matrix projection supplies many independent
coordinate comparisons, not one ordinary full-model evaluation. The algorithm
does not use the previous 48-arc cap or sampled 70% coherence gate.

Up to two profile rounds propose individual timing changes; bounded q-only
refits rank and accept them on the exact shared training objective. A final
joint refinement uses the remaining allowance. Original timing priors (common
sigma 3 s, relative sigma 2 s), actual RF scaling, physical calibration and
classification remain unchanged. The common regional KKT gate remains 0.001.
A numerical exactness check on 12 independent actual S03 coordinate changes
agrees with direct full-model evaluation to less than 1e-7 objective units.

The controlled c=0 sensitivity uses the same observations, banks, other priors,
proposals, initialization policy and allowance. It constrains coefficient c to
zero while refitting the other parameters; it is not a fixed-calibration score.
Frequency effects are separate from configured-reference position distances.

## Candidate-expansion arm

Restore only omitted members of each recording's ORIGINAL causal regional
catalogue. Keep its exact TLE digest and collection binding; there is no latest
snapshot, provider switch, guided satellite ID or new detection in this arm.
Screen all eligible omitted candidates with training-only physical predictions;
select up to eight additions using the separately documented generic evidence
and novelty policy. Screening is explicitly a proposal, not a localization fit.

The expansion adapter keeps every original candidate, calibration function,
clock basis and original total satellite timing. New total timings start at
zero. A positive new q needs mass from the unchanged 1.6 detection budget:
old probabilities are scaled by K/(K+m), additions start at 1.6/(K+m), and any
bounded-coordinate projection error is reported. Exact q preservation is not
claimed. Pair expanded-profile and expanded-continuation runs on the identical
selected bank and transported seed. Reuse the same selected additions for the
fitted-c and c=0 comparison; this is conditional on the fitted-c screening
policy, rather than an independently reselected c=0 catalogue experiment.

## Excluded-data and interpretation

Fixed-bank early-to-late and late-to-early runs rebuild neutral parameter seeds
and zero band contrasts, and exclude held CFO from profiles, q fitting and
selection. Their bank still comes from full-recording discovery, so validation
is candidate-conditioned and retrospective, not pristine end-to-end discovery.
No temporal result is selected to improve a particular challenge window.

Report per-window counts, new and lost memberships, same-point RMS, original
support losses outside the challenge, timing distributions, convergence and
runtime. An 80% net-restoration threshold is only the existing descriptive
grouping, not a success gate or an algorithm parameter. Satellite identity is
unlabelled, and a high association count does not prove that a trajectory is
assigned to the right spacecraft. Distance to the operator-configured station
is not independently surveyed position error. DS21/DS22 remain separate
localization benchmarks.

The goal is not complete merely because an in-sample count rises. Unexplained
support losses, poor held prediction, unresolved candidate identity or poor
localization remain outstanding evidence to investigate, not exclusions from
the report. Nothing here promotes a model to production.
