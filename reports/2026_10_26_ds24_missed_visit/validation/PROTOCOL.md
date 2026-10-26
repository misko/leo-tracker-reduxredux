# Missed-visit independent qualification protocol v1

Frozen 2026-10-26 21:29 UTC before new prediction/timing outcomes. This protocol
replaces no prior result and changes none of the previous experiment's gates.
New outcomes can motivate a second, separately frozen round, never a revision
that retroactively makes this round pass.

## Scope and information boundaries

Use the exact split in `../split.json`: twelve development recordings, twelve
held-validation recordings and ten unavailable fast acquisitions. The four
previously examined scans remain development. All recordings have earlier
study exposure: held validation is for this revision, not unseen-site transfer.
Do not open held-validation target outcomes until root freezes the development
handoff. Do not open geographic reference/error outcomes before the relevant
RF/method/inference output seal. No GPS-selected association, threshold, donor,
target, candidate catalogue or hyperparameter is allowed.

The metadata-only development panel has at most 288 paired native windows:
twelve recordings, channels 1/4 controls and 5..8, four fixed time fractions,
both receivers. Missing/ambiguous history and failed raw access remain in the
denominator. Prediction inputs are earlier same-channel/RX/edge actual-RF
measurements, counters, original ranks and a bounded earlier horizon. Full-scan
track predictions and target acquisition winners are forbidden donor inputs.
Target outcomes may be used only in separately labeled development evaluation.

## Practical staged RF screen

1. Freeze method, all proposals, timing domain/spacing, mode cap and budgets
   before target scoring. Compare original persisted winners, sparse point
   prediction and bounded timing search on the same native targets. The point
   and search arms use the same unchanged frequency scorer; any extra search
   computation is disclosed. No uncertainty failure of the abandoned complex
   estimator is automatically attributed to these unchanged measurements.
2. Search on one disjoint target support; seal selected timing/mode before
   opening confirmation support. Confirmation is one frozen proposal per owner
   unless a fixed alternative policy is declared in advance. Re-ranking modes,
   retiming or selecting a confirmation winner requires counting that full
   search in controls. Propagate epoch and CFO reference times explicitly.
   Two target halves are support checks, not independent observations added to
   a localization normal system. Require the worker's frozen unchanged margin
   gate on confirmation and report search/confirmation CFO agreement.
3. Known-truth controls must include both edges, nonzero frequency evolution,
   donor CFO and timing errors of both signs, and weak/absent signal. Freeze
   strong/weak strata before outcomes. For scalar frequency use, the strong
   control must have at least 90% confirmation frequencies within 500 Hz of
   truth and no >1 kHz errors among admitted strong trials. Report the full
   errors and availability, not only gate-passing successes; fewer than 20
   independent strong trials is inconclusive. Weak failures do not get hidden,
   and a weak-only success cannot override a strong-control failure.
4. Repeat the complete proposal/search/confirmation selection on active-donor
   conditional nulls. Count one confirmation per independent target/support
   cluster, not per mode or timing bin. The practical exploratory screen is an
   observed confirmation rate <=5% with its one-sided exact 95% upper bound
   <=10%, using at least 32 independent null target vectors in each relevant
   search-exposure stratum. This is measurable within a bounded experiment.
   Report all proposals and the implied expected false-confirmation range at
   the observed panel exposure. This is not a 288-window family-wise error
   guarantee or a deployment FAR claim. Synthetic nulls only certify their
   model; recorded interference/wrong-donor controls diagnose transfer limits.
5. Natural confirmation must use later native samples distinct from donors.
   Preserve raw target identity, actual RF/sample rate, receiver/band offsets,
   aliases, native counters and exact support. A donor is conditioning, never a
   new independent measurement. Multiple target alternatives/halves share one
   owner. A donor-conditioned posterior is not substituted for a fresh
   likelihood. Unchanged later-sample CFO may be staged with the existing
   baseline noise model for exploratory sensitivity, with selection/timing
   conditioning explicit; this does not assert calibrated new RF uncertainty.
6. Natural RF reliability is a sequence-level question as well as a single
   confirmation gate. Require distinct-time coherent same-lane confirmations,
   residual diagnostics and causal all-catalogue association before claiming
   useful Doppler/curvature. A one-point survivor cannot imply a new satellite
   track. The graph's original minimum support and curvature gates remain the
   authority; any reduced-support graph is exploratory and labeled separately.

The null screen and known-truth frequency screen permit a bounded exploratory
development integration, not automatic promotion. A screen failure triggers a
specific bottleneck diagnosis (opportunity, timing, CFO reliability, aliases,
coherence, association, or geometric information), not indefinite tuning.

## Baseline authority and lean downstream integration

Baseline is ALGO02-v1 + qualified causal signed phase prior + equal-prior family
cavity from `/srv/bulk/leo/research/ds25-20261024`. Existing four-scan endpoint
replay receipts are reusable if their input/source hashes still match. Replaying
saved endpoints is not a new regional localization result.

New native detections and corrections are separate. A correction replaces its
exact existing owner; an originally absent winner receives the existing stable
native observation ID and does not duplicate another support. Stage later-only
CFO values rather than donor predictions, preserve existing aliases for existing
owners, then rerun the original causal graph and catalogue association for
changed observations. A sparse coherent expansion must show how many new
points become curved likelihood versus predictive/postfit-only/unassociated.
Do not merely attach all new marks to a previously recovered satellite.

Matched c0/fitted-c runs use identical complete observations, candidate sets,
aliases, other physical priors, budgets and starts. Region is 25 by 25 km,
center 37.906,-122.545, starts [0,0]. Causal TLEs only. Report in-sample
frequency fit and geographic accuracy separately. GPS is reporting-only after
sealing. A different fitted nuisance coefficient or same-arm empirical
precision is an output, not an input mismatch.

Root approves dependent position execution after an RF/ownership manifest and
ready status exist. Exploratory development position sensitivity may proceed
when the practical RF controls pass and a coherent expansion survives original
graph/causal-association gates. Its limitations remain explicit; no guarantee
of deployment uncertainty or site transfer is implied. If no coherent expansion
survives, compare counts/residual/curvature information and identify that exact
bottleneck instead of forcing an association or manufacturing a position gain.

## Held-validation promotion

Root first freezes method, control/selection policy, follow-up block nomination,
graph/inference budgets and all acceptance rules from development. Held target
outcomes are then opened once under that policy. Preserve every scan and
failure, use the same matched c arms and final GPS-only evaluation seal. The
proposed promotion screen is at least a 10% lower held-validation median
position error with no p90 worsening in each c arm, on matched available cases;
also show unavailable cases against all twelve, association changes, tails,
and frequency-fit effects. This is a development-screen criterion, not a
statistical confidence statement, unseen-location result or 500 m guarantee.
Qualified promotion also requires the frozen practical RF controls and ownership
audit to pass; a geographic improvement cannot rescue invalid RF provenance.

## Bounds and delivery

Own/write only `validation/`. No old artifact changes, production/runtime
contract changes, new RF, QNAP writes, git mutations/push or new agents. Use
apply_patch for handwritten files. Numerical shards <=600 seconds, BLAS1,
<=2 workers in this branch. Deliver source/hash receipts, owned tests, audits,
figures, compact summary and exact next bottleneck or qualified handoff.
