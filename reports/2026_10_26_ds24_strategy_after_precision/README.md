# Fast-scan strategy after the CFO and precision experiments

Review date: 2026-10-26 UTC. This is a review of completed work and a ranked
research plan. It introduces no new localization result, operational policy,
ALGO version or RF collection. Three SOL xhigh reviewers independently checked
numerical mechanisms, evidence quality and the prerequisites for temporal
replication. Their notes accompany this report.

The recommendation is to retain the ALGO02-lineage reference and concentrate
on two questions: whether the precisely specified CFO refinement transfers,
and whether the model's learned weights are supported by measurement evidence.
Independent orbital information remains the larger structural opportunity.
Another broad association sweep or optimizer restart campaign has weaker
support. Recent work has produced more diagnostic progress than demonstrated
dataset-wide accuracy improvement.

## What the experiments actually achieved

These rows have different matched cohorts; they are not additive stages of one
benchmark. Geographic figures are fitted-c unless both settings are shown.
The linked studies retain c=0 controls, availability and rejected trials.

| Direction | Evidence | Assessment |
| --- | --- | --- |
| Graph, EM, Hough and multiple-hypothesis polynomial construction | Approximately 90–93% polynomial membership on DSX01 S01 | Useful curve extraction; membership does not establish satellite identity or position information |
| ALGO01 to ALGO02 | On 404 common DS23 outputs, mean error 1.870→1.508 km fitted-c and 1.870→1.520 km c=0; qualified outputs 407/413→404/413 | A substantial retained improvement, with an availability tradeoff |
| Equal-prior satellite-family comparison | On 410 available DS23 scans, mean 1.498→1.469 km fitted-c and 1.509→1.479 km c=0 | A modest retained gain; same-site and temporally dependent evidence |
| Broad recovery candidate | Association 70.08→75.08%, mean error 1.469→1.591 km, P95 3.157→3.473 km; c=0 also worsens | Reject as a localization improvement |
| All channels versus either half | Same 24 usable DS24 fast scans: fitted-c mean CH1–8 / CH1–4 / CH5–8 = 1.220 / 1.558 / 2.040 km; c=0 = 1.202 / 1.538 / 2.040 km | All eight channels already help on average |
| Continuous restarts and transferred labels | Thirty restarts agree within 2.06 cm; four half-channel label transfers yield no qualified better full-data solution | Weak support for generic multistart as the remedy for those tested assignments |
| Smooth RX1 correction | Development mean 1.220→1.120 km; eight later scans 1.239→1.224 km, with worse P95; later c=0 changes only 1.243→1.240 km | The development-sized gain did not transfer |
| RX2 pilot remeasurement | Median fixed-degree scatter 78.07→22.18 Hz across 322 curves, without a qualified cohort accuracy gain | Cleaner curves alone do not establish better positions |
| Complete-owner continuous CFO refinement | Four owners, 159 measurements, two scans: raw error reductions 91–139 m across both c settings; only one scan passes paired retention | A concrete candidate for bounded replication, not a general improvement yet |

Sources: [ALGO02](../2026_10_19_algo02_ds23_full/README.md),
[family comparison](../2026_10_22_ds23_family_cavity_full_assessment/README.md),
[recovery candidate](../2026_10_23_algo04_candidate_full_ds23/README.md),
[channel and information analysis](../2026_10_24_ds24_bottlenecks/README.md),
[later receiver validation](../2026_10_25_ds24_phase_shape_validation/README.md),
[measurement cohort](../2026_10_19_ds23_rx2_measurement_cohort/README.md),
and [complete-owner refinement](../2026_10_26_ds24_complete_owner_refinement/README.md).

The 24-scan DS24 reference uses 78,067/108,600 original GLRT winners in the
position likelihood, or 71.8849%. Ten additional members of the frozen
34-recording population lack the required frozen upstream inputs. Polynomial
membership, postfit-only association, and actual position-likelihood membership
must remain separate. A 90% association target is a useful aspiration, but is
not an acceptance objective by itself.

The earlier approximately 0.54 km DS23 mean came from causal averaging under a
declared stationary-receiver assumption. It is not single-scan performance and
does not address the intended moving receiver. No stationary pooling or motion
prototype is proposed here.
[Stationary study](../2026_10_19_ds23_stationary_consensus/README.md).

## The main bottleneck and the remaining uncertainties

The strongest demonstrated ambiguity is between receiver position and satellite
orbital timing/shape. A displacement along a satellite's orbit can resemble a
receiver displacement in the measured Doppler. Repeated channels observing that
satellite share its orbital error. In the local DS24 calculation, the strongest
timing/weak-position correlation has median 0.935; bands share a median eleven
calibration families and their weak directions differ by only 17.7 degrees.

![Conditional information diagnostic](figures/conditional_information.png)

The 534→110→56 m values are conditional weak-direction scales when selected
nuisances are hypothetically known. They are not achieved position errors,
calibrated confidence or proof of an irreducible floor. They identify missing
information, not permission to narrow the orbital prior until the answer improves.
Receiver calibration also matters, but its analogous 534→386 m effect is smaller.

All compared fast recordings are 10 MS/s, so the current cohort cannot identify
a sample-rate effect. The nominal 40-degree feed separation provides coverage
diversity; it is not a measured bearing or a spatial receiver baseline. Current
evidence does not identify either more bandwidth or a different pointing angle
as the principal remedy. Correct satellite labels remain uncertain: agreement
between related methods is not independent identity truth, and the restart
result does not rule out discrete assignment minima.

More exact numerical treatment is also not an unexplored cure. Earlier nonlinear
phase integration, Gaussian log-volume removal, phase-dependent shape design,
parent orbit covariance, soft identities and cross-family priors have already
been tested. Their measured effects were small, mixed or unqualified. The
[methods inventory](../2026_10_25_ds24_next_directions_review/methods/FINDINGS.md)
and [previous review](../2026_10_25_ds24_review_next_actions/README.md) document
the scopes. Those negative results close specific variants, not every possible
physical model.

## What the newest experiment changes

The continuous CFO refiner maximizes the same GLRT64 score inside the original
frequency cell, with the acquisition, epoch and membership fixed. This estimator
has prior art in the [August report](../2026_08_23_470384_continuous_glrt.md).
The new contribution is exact deployed-runtime replay, complete fixed-owner
coverage and controlled position propagation, rather than a new estimator.

The original complete-owner experiment mixed measurement changes with changes
in learned precision. The subsequent factorial crossed original/refined CFO
with original/refined full precision packets in 16 matched fits. A packet
contains both fragment-noise and nuisance-prior precisions.

![CFO versus precision effects](figures/factorial_position_errors.png)

At the original fixed precision packet, CFO refinement reduces error by
132.8/132.6 m in DS24-0010, but only 17.8/20.4 m in DS24-0011, in c=0/fitted-c
order. In 0011 most of the full endpoint movement follows the precision packet:
the symmetric packet-effect vector is approximately 82–87 m, versus 22 m for
CFO. These are vector lengths, not additive percentages of geographic gain.
The old local CFO response prediction agrees with the isolated nonlinear CFO
movement within 0.35–2.32 m. Its previous large miss in 0011 mainly reflected
precision feedback, not an inaccurate local CFO derivative.

This supports a narrower conclusion than “we fixed the frequency and therefore
fixed position.” There is a real, modest measurement-intervention lead in 0010;
0011 also exposes sensitivity to learned uncertainty. Neither higher GLRT score
nor a geographically favorable precision packet establishes physical CFO truth.
The conditional-Gaussian factorial and the operational VI objective remain
different models; their baseline endpoints are not silently interchanged.
[Full factorial](../2026_10_26_ds24_cfo_precision_factorial/README.md).

The 0011 rejection needs equally careful interpretation. All original likelihood
points remain and the individual fits pass their residual/owner/phase checks.
The additional paired experiment guard fails because 57 postfit-only IDs cease
to pass the slope gate in c=0. The two statistics change 2.999997→3.007648 and
2.906247→3.056059 around a threshold of 3. That is not evidence of a gross new
orbit mismatch, and preserving old labels is not physical truth. It also does
not justify retrospectively waiving a frozen rule because GPS improved. Any
future acceptance-policy change needs its own controls, with likelihood evidence
and postfit compatibility reported separately.

## Ranked next decisions

### 1. Replicate the concrete measurement intervention

Use the four already nominated later recordings, selected before correction
outcomes, with the exact retained baseline and the same RF-only complete-owner
selection. Preserve both c arms, every requested scan, numerical failures and
the original-reference fallback. Freeze the correction and evaluation policy
before seeing geographic outcomes. Four scans can expose a transfer failure;
they cannot establish a reliable tail distribution or new-location generalization.

The metadata review has now reconciled all four full tracking contracts and
ordered raw-authority chains. Numerical preparation and new-scan baselines are
held while this strategy review completes. The checked capture metadata does
not establish an applicable evaluation position, and the earlier exposure audit
was incomplete. Therefore call this a later replication panel, not an untouched
holdout, and resolve the site reference before reporting errors.

The full retained producer is ALGO02 discovery and salvage followed by causal
signed-prior, family comparison and equal-assignment-prior adoption. A simpler
seed fit is not the same baseline. One earlier case took about 122 seconds on
this route, so the proposed 120-second per-case cap may yield honest timeouts.
If a different budget is needed, change and freeze it before new execution;
do not substitute a cheaper algorithm after a failure.

The old-case fixed-state replay reproduces both c arms' curved/predictive
objective, gates and counts without a new optimizer run. However, the preparation
review found a copied owner-selection denominator differs from the original
ranked-family rule. Matching the two old selections does not certify that copy.
It remains an explicit unresolved prerequisite; future nominations must use the
original rule exactly, with a meaningful equivalence test before freezing them.

**Advance only if** the frozen repair produces useful RF-supported changes and
transferable matched position benefit without hiding availability or tail costs.
A positive small-panel result earns a broader comparison; it does not earn an
ALGO release.

### 2. Determine what the learned precision is responding to

First split the already saved precision intervention into fragment-noise versus
nuisance-prior components. The review found no equivalent control in the completed
factorial. At original CFO, its two diagonal packets already exist; adding
old-noise/new-prior and new-noise/old-prior packets on the two scans in both
c arms needs eight small matched endpoint fits. Freeze that choice before
execution and preserve the conditional objective. Hold observations, identities,
normalization and c arms matched. This answers which model mechanism moves the
solution; it does not choose weights or validate them.

The source review confirms that the saved 159-window replay contains frame-by-64
exact/control correlations and their times; known-frequency synthetic controls
also retain their correlations. A small diagnostic can use these without new
IQ or detector calls. First check a proposed uncertainty law against those
known synthetic frequencies, retaining their shared-waveform dependence and
limited waveform model. Synthetic coverage would not establish field calibration.

Then check whether cached pilot/frame evidence supports a separately measured
estimate of within-window repeatability. Correct for time separation, retain common
acquisition/epoch assumptions, and account for dependence. The field questions
are whether the changed measurements predict held pilot evidence and whether
within-window variability agrees with between-window behavior. Score curvature
or a few correlated frame splits must not become a calibrated standard error.
The normalized GLRT score is not a calibrated log likelihood; its curvature
cannot simply be inverted into frequency variance. Full-window acquisition and
epoch selection also make subsequent frame splits conditional diagnostics.
Polynomial scatter and frame-split proxies already have
[prior experiments](../2026_10_19_ds23_refined_precision/README.md); repeat only
the missing deployed-runtime control with a clear decision.

**Stop** if the available frames cannot distinguish measurement variability from
common bias, interference or model discrepancy. Keep those uncertainties separate
rather than adopting the packet that happens to improve geographic error.

### 3. Obtain independent evidence before adding orbital or receiver freedom

Use a new complete owner chosen without matching it to the preferred correction.
Ask whether a correction learned on one family/RX/band predicts that owner's
frequency behavior without refitting to it, carrying shared orbit and radio
uncertainty. A receiver problem should predict discrepancies across families;
a satellite problem should predict its behavior across receivers. Multiple
channels viewing one satellite do not create independent orbit truth.

Prioritize sources adding a different position direction after nuisance
uncertainty, rather than longest-first recovery. The previous inventory already
tested this ranking, and some attractive sources lacked eligible corroborating
owners. Do not repeat their target-only fits or split one owner and rename it
independent support. If the requisite evidence is absent, move to another scan.
This is the potentially larger accuracy opportunity, but is conditional on
information the current corpus may not contain.

### 4. Keep waveform source overlap as a conditional branch

Synthetic controls demonstrate that two sources can displace CFO while retaining
a strong detector margin, and one source can produce multiple smooth candidate
paths. The tested CFO/epoch continuity rule gave no extra benefit and qualified
zero of 117 recorded owners. A further path search is low priority.

If a field owner still shows a repeatable discrepancy after the simple CFO repair,
compare one and two waveform components on the same small set of stored windows,
with a complexity penalty, separate-frame prediction and one-source controls.
Count per-window alternatives as correlated hypotheses. Proceed to position
only if this identifies a correctable field defect, rather than just increasing
synthetic fit or source count.
[Continuity study](../2026_10_26_ds24_candidate_continuity/README.md).

## How to make the next iteration decisive

Use one SOL xhigh branch for the frozen later-panel replication, one for the
small uncertainty/mechanism control, and one for independent audit and prior-art
checks. Root owns the shared policy and decision. Keep work bounded to existing
recordings and minutes of numerical computation; no new RF collection, broad
campaign, stationary pooling or trajectory model is part of this plan.

Report coverage at the polynomial, satellite-compatible and actual-likelihood
levels; frequency fit; mean/median/tail position error; failures; and runtime.
Preserve matched c=0/fitted-c data, candidates, other priors and budgets. Inference
remains causal, starting from the 25×25 km regional box centered at
37.906, -122.545. GPS is evaluation-only, with applicability verified per cohort.

The current 0010/0011 data are development evidence. Retain the successful
ALGO02-lineage reference until a frozen rule survives broader DS23/DS24 testing.
The practical change in strategy is to demand a transferable correction or a
closed hypothesis from each small experiment before launching another campaign.

## Review sources and reproduction

[Numerical and lineage review](reviews/numerical.md),
[independent critique](reviews/independent.md), and
[transfer and cached-precision review](reviews/transfer_and_precision.md)
record the three SOL branches. [Source manifest](source_manifest.json) binds
their files, the reused figures and the metadata/fixed-state receipts. The
figures are byte-preserved from their linked original studies. No original
scientific output, production component, persisted contract, golden fixture or
recorded IQ was changed. This compact review is not a standalone corpus bundle.
