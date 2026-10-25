# Independent RF audit: one physical-model lead, no qualified identity

The frozen three-owner experiment passes 115 independent artifact checks. All
six owner/arm results and all 48 physical-candidate slots completed, with no
retry, trimming, position fit or geographic input. Scientific computation used
450.754361 worker-seconds (228.171720 s wall), below the 600 s cap. Independent
audit computation, including the preserved first preflight, used 2.565780 s.

| Complete RX2 owner | Points | c0 finite-pool winner | Fitted-c winner | Conservative log-evidence margin, c0 / fitted-c | 60108 ordinary rank, c0 / fitted-c |
| --- | ---: | --- | --- | ---: | ---: |
| CH3/T002 | 24 | unresolved | unresolved | 21.214382 / 20.866276 | 87 / 87 |
| CH5/T001 | 57 | 57450 | 57450 | 29.231576 / 28.446082 | 197 / 197 |
| CH4/T000 | 43 | unresolved | unresolved | 34.421025 / 30.729695 | 143 / 145 |

Each margin is the winner's lower log-evidence bound minus the largest upper
bound among the other eight models, including the proper unresolved comparator.
These prove the declared finite-pool ordering. **None of the 48 candidate scores
meets the stronger absolute 1e-3 objective-precision requirement.** The bounds do
not assert that precision, an exhaustive exact-catalogue exclusion, a calibrated
clutter probability or a validated identity. The three current ordinary top8
pools omit 60108 without a reserve/backfill; that omission is retained rather
than treated as an exact score for 60108. CH4's raw best physical model changes
from 65876 to 65871 between arms, while the unresolved model wins both.

The audit independently reconstructs the six ordinary 1,487-candidate screens
using a positive-ridge Gaussian expression (maximum objective discrepancy
3.260e-9), replays the complete null Gaussian density and strict interval
ordering, and checks all native-ID/time/value arrays, common c0 RF coordinate,
matched c0 candidate pools and original/cavity membership. All 124 source IDs
are mutually disjoint and absent from both original accepted ledgers. Original
membership remains 3,037 curved plus 747 predictive IDs. Per-owner cavity
removals are exact and matched across arms: 929/171 curved/predictive points for
CH3, and 694/129 for each of CH5 and CH4. All hard phase/Gamma/nonempty-support
guards and saved remaining residual gates pass. No original operational
membership or acceptance rule changes.

## Why CH5's 57450 win does not resolve physical adequacy

57450 is index 439 and has **zero accepted curved owners/points and zero
predictive owners/points** in this original parent. Its two archived graph
nominees are the rejected CH4 and CH5 sources. It is not an active calibrated
family removed by this cavity. For CH5, the removed active indices are
578, 733, 907 and 1071; they are competing shortlisted families. Thus the current
win does not demonstrate agreement with an existing accepted 57450 correction.

The archived CH5 RMS is 2442.510071 Hz under an earlier rejected nomination;
its saved graph polynomial RMS is only 20.414466 Hz. The current calculation
uses refreshed parent radio conditioning, symmetric shortlist-family removal,
Gaussian radio uncertainty, an independent 300 Hz source constant, and
nonlinear integration over the causal phase prior and all three physical-mode
coordinates. The original phase-prior parameters for 57450 are location
-1.766182 s and marginal SD 6.391009 s before conditioning on [-15,+15] s.
The full physical-mode block includes level/phase-like components, not just
curvature. These are materially different models from the archived residual.

Indeed the newly saved **causal-mean**, nomination-background residual is still
7786.862 / 8030.457 Hz RMS (c0 / fitted-c), with centered RMS
1665.238 / 1664.766 Hz. These descriptive numbers use neither posterior phase
nor posterior shape/constant adjustments and are not a posterior lack-of-fit
test. The physical-minus-null objectives are -58.481351 / -60.445127;
the null objectives are 736.136601 / 736.137330. A physical model can win this
relative comparison while requiring a substantial orbital/radio correction or
while both models have inadequate absolute predictive behavior. No posterior
residual, prior-pull or whole-owner predictive adequacy threshold is supplied
by the ordering proof.

The smallest useful follow-on is therefore a **discovery-conditioned
whole-source prediction**, not a position campaign or another broad numerical
repair. CH5 is the newly nominated discovery source; keep its full physical
57450 model in every comparison. For each other frozen source separately,
compare a shared 57450 phase/shape correction against an independently
unresolved witness, with unchanged shared parent-radio covariance and separate
source constants. Retain that witness's independently nominated competing
identities as well. CH4 is particularly discriminating because its own 57450
nomination loses to unresolved; it must not be assumed to share CH5's identity.
Use one common candidate-family cavity and both c arms, and predict each whole
witness without training receiver/Gamma on it. Report residual structure,
prior pull and predictive evidence separately. Stop if ownership/support is
unresolved, numerical evidence intervals overlap, or the shared correction
does not predict the complete witness. Failure rejects that corroboration
claim, not the CH5 identity by itself. Do not aggregate overlapping folds into
independent significance. No such follow-on was run here.

## Scope and preserved technical history

All three owners are exposed development data: historical rejected graph
assignments and earlier conditional-information ranking already used them.
Current nomination did not receive those labels. Raw target CFO does not
calibrate parent radio/noise parameters. Each owner gets its own ordinary-top8
family cavity, common to all eight identities and null. This response-dependent
cavity makes the result conditional model comparison, not prior-predictive
calibration or a fitted identity probability. The original RF position itself
was inferred from other parent observations; no geometric independence is
claimed.

Every track value equals its native measured CFO minus two alias periods.
That original graph gauge is preserved. All physical and null models use the
same finite uniform alias set -4 through +4 in that gauge; this is a normalized
finite mixture, not an infinite wrapped density or a gauge-invariant prior.
Visibility is a zero-likelihood event under the original conditioned phase
prior, without renormalizing its surviving visible mass. The unresolved
comparator is a declared broad degree-four curve prior, not empirical clutter.

The zero-run first scientific freeze is preserved. Revision02 changes process
payload serialization and reuses the exact earlier independently audited
augmented-QR null reference, with the original 1e-7 guard and 1e-6 floating
allowance. The first failed audit fixture is also preserved: absolute covariance
comparison encountered cancellation at a 3.82e9 Hz² scale. A scale-aware,
whitened and density comparison passed without changing any scientific
likelihood, precision or empirical gate. The final source/input/RF bindings
remain exact. These are enabling technical corrections, not localization gains.

[Terminal checks and machine-readable results](terminal.json),
[terminal source](terminal.py), [passing preflight](preflight.json),
[preserved first preflight](preflight01.json),
[independent whole-source selection reconstruction](input_check.json),
[conditional comparison algebra](CONDITIONAL_DESIGN.md),
[broader next-direction priorities](NEXT_DIRECTIONS.md),
[scientific protocol](../scientific/protocol02.json),
[RF seal](../scientific/RF_seal.json),
[all candidate results](../scientific/candidate_table.csv),
[descriptive residuals](../scientific/causal_residuals.csv),
[archived residual context](../archived/FINDINGS.md), and
[independent exposure/native-context review](../context/FINDINGS.md).
