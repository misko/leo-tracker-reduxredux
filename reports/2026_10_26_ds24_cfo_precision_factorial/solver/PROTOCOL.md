# Native CFO x full frozen precision packet: conditional-Gaussian factorial

Use DS24-0010/0011 with the previous159-ID intervention, unchanged original
parents, same candidates/aliases/masks/points/powers/nominal noise and causal
phase/orbit priors. No detector calls, IQ, new nomination or geographic selection.
Both c arms share exactly the same original/refined graph vectors. Native CFO
injection is the previous frozen helper, including its sign/alias checks and
unchanged nonselected data. Operational reference remains the original VI result.

For every case/arm, freeze BOTH noise_precision (including inactive zeros) and
the FULL coefficient_prior_precision exported at each old/refined VI endpoint.
These are physical-coordinate precisions: source-constant scaling is already
included. Do not freeze coefficient means, posterior covariance, phase references
or position. The existing helper expects c0 prior layout and inserts unit slot8
for fitted-c. Adapt a full same-arm packet ONLY by requiring full[8]==1 EXACT,
deleting that slot from helper input and proving exact reinsertion and complete
column-layout equality. Nonunit fitted-c slot8 is a hard failure, never overwrite.
Active noise groups must be positive; preserve every inactive zero unchanged.

Use make_frozen_problem through make_event_problem's explicit basefactory and
attach_event_predictive unchanged. volume_weight=1; predictor sigma*sqrt(2),
shared curved-posterior Gram and300Hz fragment constants unchanged. The objective
is a conditional-Gaussian generalized marginal objective when powers<1, NOT
the old VI ELBO. Legacy field names needed by original fit/summary do not make
these objective numbers interchangeable. Full packets change both noise and
prior precision; do not call their effect only observation weighting.

Pre-execution diagonal controls: each same-CFO/same-packet combination evaluated
at the exact saved last fit INPUT phase_reference and endpoint must reproduce
coefficient means (abs1e-6+relative1e-8 elementwise), conditional residuals and
predictive raw residuals (max abs1e-3Hz), predictive objective (abs<=1e-3 AND
relative<=1e-8). Packet/noise/layout/value/alias and zero-CFO-delta metadata
identity are exact. No conditional-objective equality to old VI is asserted.
Owned fixtures cover mapping/refusal, physical units, normal equations/density,
mean refitting and signed-factorial/missing-cell arithmetic. Failures stop
preparation; no tolerance adjustment in response to values.

Cells00=oldCFO/oldpacket,10=refinedCFO/oldpacket,01=oldCFO/refinedpacket,
11=refinedCFO/refinedpacket. Sixteen actual cold fits: four cells x2cases x2arms.
Every cell starts x=[0,0], phase_reference=0; same25x25km box centered
37.906,-122.545, five outer phase refreshes x48 iterations, original between-fit
phase clipping. Final phase validity uses UNCLIPPED phases. At most30seconds
per fit,600 cumulative numerical worker-seconds INCLUDING preparation, at most
two workers with BLAS1. No warm start, rescue, retry, pruning, backfill or cap
extension. Retain all16slots, raw endpoints, epoch histories and any failures.

Gates and postfit coverage are evaluated on the SAME conditional posterior p
using original retained_metrics, summary and extend_associations. Never call
r.membership or any helper rebuilding a VI parent. Fixed curved/predictive IDs
remain exact; postfit accepted/lost IDs can vary and are reported. Original
residual/owner/phase/retention criteria are diagnostics, not waived. Frozen Gamma
has no Gamma-convergence claim; save phase changes and optimizer history.

Predeclare signed vectors x10-x00 and x11-x01 (CFO),x01-x00 andx11-x10(packet),
interaction x11-x10-x01+x00. Symmetric CFO/packet averages sum to x11-x00 as
vectors; norms need not add and are not causal percentages. The evaluator is
source-frozen before results. Compare position effects primarily within each
packet; packet priors are learned from different VI endpoints, so crosspacket
numbers are conditional mechanism diagnostics. No physical-noise truth claim.

Freeze sources/inputs/packets/evaluator and require exact B preflight plus root
solver_go.json before fits. Live stdout remains outside solver/. RF outputs seal
and independent terminal review passes BEFORE root releases geographic evaluation
of saved final endpoints. Report every completed raw error separately from the
unchanged operational reference. Exposed two-case evidence is not validation.
