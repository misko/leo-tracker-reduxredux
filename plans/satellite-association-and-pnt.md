# Satellite Association and PNT Implementation Plan

## Motivation

The project ultimately needs to turn opportunistic Starlink downlink signals
into a defensible global receiver-position estimate. The development receiver
currently has known coordinates, which provides a valuable reference phase for
learning measurement errors, receiver/LNB behavior, satellite ephemeris and
clock corrections, and association uncertainty before receiver position is
released as an unknown.

The immediate scientific opportunity is to combine the repository's recovered
POST-FIX CFO trajectories, including the opened 13.825 s and 30 s long arcs,
with literature-backed multi-hypothesis association and reference-station PNT
methods. The goal is not to make another lowest-residual catalogue label. It is
to determine whether the available radio evidence predicts a stable satellite
identity, ambiguity set, handoff sequence, or abstention on future data, and
then determine whether the resulting correction products support positioning.

## Problem

Current tracking recovers receiver-relative CFO trajectories, but catalogue
identity is unstable across predictor models, training cutoffs, and future
blocks. Short arcs are nearly linear after a free CFO intercept is removed, and
hundreds of visible Starlinks can have similar Doppler rates. Receiver/LNB
drift, transmitter and beam frequency state, satellite clock drift, TLE error,
sample-clock error, aliases, refills, and path-local discontinuities can imitate
parts of the orbital curve.

A single unconstrained fit cannot identify all of those terms. A greedy
rank-one association can lock onto the wrong satellite, while a monolithic EM
fit can converge to a locally consistent but incorrect identity. Conversely,
forcing all fragments or sequential dwells to share one NORAD can hide real
handoffs, activity changes, aliases, and out-of-catalogue observations.

The known development position removes one source of uncertainty, but it does
not itself establish NORAD truth. Using the same observations both to estimate
satellite corrections and to demonstrate positioning would also be circular.
Calibration, association development, correction-product freeze, and blinded
positioning therefore need distinct data and authority boundaries.

## Solution

Implement a catalogue-constrained, Rao-Blackwellized, fixed-lag
multi-hypothesis smoother:

- build physical RF episodes and alias/replica relationships without TLEs;
- preserve short-window likelihood evidence instead of reducing it immediately
  to hard tracks;
- maintain top global hypotheses for satellite identity, active-emitter count,
  handoffs, and unassigned/clutter observations;
- condition on each discrete hypothesis and use an information/Kalman smoother
  plus generalized EM/ECM to estimate only the allowed continuous nuisance
  states;
- select and fit with training data, freeze the state, and score future blocks
  or future dwells exactly once;
- use the known-position phase to publish versioned satellite-side correction
  products with covariance and validity intervals; and
- freeze those products before hiding receiver position and evaluating
  navigation.

This is a living implementation plan, not an experiment protocol, dataset
authorization, evidence receipt, secure-NORAD claim, or RF collection
authorization. Numeric scientific thresholds remain unset until calibrated on
known-truth injections and frozen before untouched confirmation data are
opened.

## Method

This plan synthesizes the repository's seeded alias EM, multi-dwell catalogue
association, raw-Doppler, activity-assignment, and post-refill retrospective
work with the completed 2026-08-26 Doppler/association campaign discussed in
the project review. It also incorporates primary literature on LEO
Mahalanobis data association, MHT/JPDA smoothing, full-frame Starlink
measurement estimation, reference-derived ephemeris corrections,
time-diverse Doppler positioning, and simultaneous tracking and navigation.

Implementation must follow repository contract boundaries: pure analyzers do
not import storage or infrastructure, QNAP access remains read-only, public
contracts remain immutable within a major version, and every component change
includes component-owned tests. Opened development data may refine the method
but cannot become independent confirmation evidence.

The plan was authored from commit
`eca358bc43d82bf672064d184c1c97e49a062cd5` on a dirty development checkout.
Later campaign artifacts discussed in the review are not assumed to be landed
dependencies. WP0 must reconcile the tracked integration state, user-owned
working changes, and exact campaign authorities before scientific execution.

## Goal and current status

**Goal status:** ACTIVE.

**Goal:** implement and test known-position calibration, multi-hypothesis
multi-dwell satellite association with scoped nuisance modeling, predictive
validation, frozen satellite corrections, and blinded-position evaluation.

**Current cut line:** WP0 is complete. Additive V1 physical-episode,
catalogue-prediction, exact `K=0,1,2` hypothesis, transferable-correction, and
blinded-evaluation contracts now exist, together with the first pure synthetic
Rao-Blackwellized exact solver. The polynomial support-integration helper and a
response-free prediction port exist; a production TLE adapter, covariance-aware
nearest-neighbour baseline, rolling multi-dwell smoother, correction-product
generator/replay, and navigation solver remain pending. No IQ access, catalogue
rerun, new data selection, or RF collection has occurred or is authorized by
this document.

### Implementation checkpoint — 2026-08-27

| Item | State | Evidence |
|---|---|---|
| WP0 collision and reusable-oracle audit | DONE | New work is isolated from the existing TLE-blind `multi_target` tracker and user-owned Research prototypes. |
| Physical observation/episode and response-free candidate bank contracts | DONE, synthetic boundary | Support moments, stable raw-source authority, non-overlap, chronological episode order, causal snapshot, verified element membership, frozen candidate universe, and exact tau-grid policy in [`catalogue_association.py`](../src/leo/contracts/catalogue_association.py) |
| Exact bounded `K=0,1,2` association with normalized feasible-family priors | DONE, synthetic baseline | [`catalogue_association.py`](../src/leo/analysis/catalogue_association.py) |
| Proper Gaussian marginalization of continuity offsets and hardware-epoch drift | DONE, synthetic baseline | Direct covariance-form equality and recovery tests in [`test_catalogue_association.py`](../tests/analysis/test_catalogue_association.py) |
| Solver-safe corrections and blinded truth/estimate/reveal boundary | DONE, contract only | [`satellite_pnt.py`](../src/leo/contracts/satellite_pnt.py) and [`test_satellite_pnt.py`](../tests/contracts/test_satellite_pnt.py) |
| Synthetic mixtures and association poisons | DONE for current exact-solver scope | 29 focused tests cover K=0, 10/0, 8/2, 5/5, ambiguity, unassigned, replica/exclusion, enumeration, work caps, normalized priors, covariance, time-grid boundaries, posterior closure, source re-wrapping/chronology, and tamper cases. |
| Correction/blinded-boundary poisons | DONE for contract scope | 14 focused tests and all 52 repository contract tests cover covariance, chronology, source-span disjointness, freshness/expiry, lane separation, prior breadth, truth commitment, and reveal closure. |
| Current null and evidence scope | RESTRICTED synthetic baseline | Posterior odds are conditional on the complete frozen response-free candidate universe. `K=0` currently uses the declared zero-curve component-offset/hardware-drift Gaussian baseline; the equal-opportunity polynomial/radio-only likelihood required by WP2 is not yet implemented. |
| Real opened long arcs | NOT STARTED | Requires a separate frozen development protocol after this slice is independently audited. |

## North-star milestone

The first end-to-end milestone is complete only when all of the following are
demonstrated:

1. A known-position calibration cohort produces a versioned satellite
   correction product without using future response data.
2. A later untouched observation is processed with the correction product
   frozen.
3. The association layer returns either a stable NORAD, a calibrated ambiguity
   set, a handoff/active-set sequence, or an explicit abstention.
4. With receiver coordinates hidden, the navigation layer produces a
   calibrated position posterior and reports 2-D/3-D error against truth only
   after the estimate is sealed.
5. Oracle-identity, unknown-identity/frozen-correction, and fully joint lanes
   isolate whether any failure came from the measurement, association,
   correction, or positioning layer.

Posterior collapse and optimizer convergence are not success criteria. The
primary criteria are future predictive performance, calibrated uncertainty,
and eventual blinded positioning accuracy.

## System shape

```mermaid
flowchart LR
    A[Digest-bound RF evidence] --> B[TLE-blind physical episodes]
    B --> C[Native short-aperture likelihoods and strict-past predictors]
    C --> D[Response-free catalogue prediction bank]
    D --> E[Top-N identity, active-set, handoff, and clutter hypotheses]
    E --> F[Conditional Kalman/information smoother and ECM]
    F --> G[Future-block and next-dwell prediction]
    G --> H[Known-position satellite correction product]
    H --> I[Position-hidden particle/factor-graph navigation]
    J[DOA, differential receiver, reference tone] -. optional evidence .-> C
    G -->|fixed-lag update after scoring| E
```

The fundamental association unit is a physical RF episode or source group,
not a tracker fragment and not an arbitrary 500 ms fit. A single emission may
have multiple replicas, aliases, paths, or reset-separated fragments. Multiple
simultaneous incompatible canonical tracks imply multiple physical emissions
and must retain exclusion constraints.

## Claim and work status vocabulary

| Term | Meaning |
|---|---|
| `HARD` | Integrity, causality, leakage, or authority requirement; failure causes no-result. |
| `OBSERVE` | Reported sensitivity with no pass/fail or promotion effect. |
| `DIAGNOSTIC` | Model or nuisance comparison that cannot silently change the primary claim. |
| `UNSET` | Concept is required but its numerical threshold awaits calibration and protocol freeze. |
| `SUPERSEDED` | Historical result remains immutable but is not used prospectively. |
| `BLOCKED` | Work cannot start until its explicit authority or dependency exists. |

Evidence terms such as established, supported, candidate, and not established
remain distinct from implementation status.

## Data roles and authority

| Cohort | Intended role | Prohibited interpretation |
|---|---|---|
| Seeded alias and historical multi-dwell artifacts in this checkout | Algorithm regression and failure-case study | Current identity truth or confirmation |
| Opened POST-FIX 30 s `9981` and 13.825 s `150802` long arcs from the completed campaign | Primary development of curvature-aware, multi-hypothesis association | Independent confirmation, secure NORAD, or positioning validation |
| Completed ten-capture response-sealed final holdout from the completed campaign | Immutable historical regression and method sensitivity | Retuning, new promotion, or fresh confirmation |
| Exact authorized HARD-NULL backgrounds | Known-truth synthetic measurement, mixture, and nuisance calibration after a response-free protocol freeze | Real satellite identity evidence |
| Future unopened POST-FIX long arcs or repeated passes | Confirmation only after model, thresholds, and correction schema are frozen | Exploratory tuning |
| New or ongoing RF data | Forbidden until separately authorized by the user and bounded by repository collection policy | Implicit authorization from this plan |

Before an experiment binds the completed campaign inputs, their exact registry,
protocol, reports, and receipts must be present in the active integration branch.
Missing campaign artifacts must cause a blocked/no-result state; implementations
must not substitute similar captures, TLEs, sites, or spans.

## Measurement and estimator contract

For source episode `e`, observation `j`, and candidate identity `z_e`, use a
window-integrated model rather than evaluating a point curve at probe start:

```text
y[e,j] = Dbar[z_e](support[e,j], receiver_position,
                   satellite_correction[z_e])
         + episode_or_path_offset[e]
         + receiver_radio_state[hardware, time]
         + satellite_or_beam_frequency_state[z_e, activity_epoch]
         + robust_error[e,j]
```

`Dbar` is the predicted Doppler averaged with the actual estimator support
kernel. The observation artifact must persist support moments, RF authority,
sample-clock authority, estimator covariance, continuity identity, alias
identity, and response-access chronology.

### Continuous state scope

| State | Share within | Reset or re-prior at | Primary treatment |
|---|---|---|---|
| Receiver/LNB drift | Simultaneous signals on one physical oscillator; sequential dwells only within a declared hardware-continuity epoch | Retune, restart, clock/LO change, or measured change point | Zero-centered bounded random walk or hierarchical shrinkage |
| Path/episode CFO intercept | Verified continuity component or activity epoch | Refill/reset/retune/path discontinuity | Free local intercept under an explicit gauge |
| Satellite identity | Replica-connected paths and fragments assigned to one emitter | Inactivity/handoff; never on a mere tracker reset | Discrete NORAD or unassigned state |
| Equivalent epoch/orbit correction | One NORAD, causal TLE, and validity interval | New TLE or expired correction | `tau=0` primary; `[-5,+5] s` sensitivity; no automatic widening |
| Satellite/beam clock-frequency state | One inferred emitter and beam/FAI activity epoch | One-second/15-second or detected transmitter step | Bounded/random-walk state with explicit jump model |
| Receiver position | Calibration session | Released only for blinded evaluation | Fixed truth in calibration; posterior variable in navigation |

Absolute receiver LO, transmitter CFO, and satellite clock terms have a gauge
ambiguity. The implementation must fix a documented reference or marginalize
the unidentifiable combination. It must not create a separately free slope,
time shift, and intercept for every fragment, because that erases the orbital
information required for identity.

### Discrete state scope

The hypothesis state includes:

- active emitter count `K`, beginning with `K=0,1,2`;
- NORAD or explicit unassigned/clutter identity for each emitter;
- fragment-to-emitter assignment;
- activity, birth, death, and handoff sequence;
- bounded alias integer and replica/exclusion constraints; and
- optional missed detections on scheduled usable observations.

Birth/death refers to RF activity in the receiver, not physical satellite
existence. A candidate may own multiple non-overlapping fragments. Simultaneous
exclusion-connected fragments may not own the same candidate unless an
explicit multi-beam same-satellite model is separately frozen and tested.

## Prospective time policy

- Exact UTC and `tau=0` remain the primary physical model.
- Candidate-specific `tau in [-5,+5] s` is a bounded sensitivity informed by
  seconds-scale recent-TLE corrections in the PNT literature; it is not a
  universally proven prior.
- A tau solution at either boundary causes an association abstention or
  boundary diagnostic; it never causes the search to widen automatically.
- Full-catalogue fields at `delta=-500 s` and `delta=+500 s` are `OBSERVE`
  challenges only. Each gets the same local tau support and nuisance freedom as
  the true-time field, with training-only selection and one future score.
- The two wrong-epoch fields do not form a null distribution, p-value, hard
  gate, or secure-identity criterion.
- The historical 40-field, +/-15 minute to +/-5 hour empirical-rank control is
  `SUPERSEDED` prospectively but remains immutable historical evidence.

## Window and observable policy

- Preserve native per-probe likelihood/ambiguity evidence for association,
  including the exact 20 ms GLRT aperture where that measurement contract is
  used.
- Keep measurement-aperture duration distinct from strict-past predictor
  history. Fixed20, fixed125, and fixed500 denote history windows; they are not
  automatically 20, 125, and 500 ms RF integration apertures.
- Treat fixed125 as the leading current immediate-CFO predictor, not a promoted
  production winner.
- Retain fixed500 and lean quadratic models on identical masks as model
  sensitivity lanes.
- Treat a 500 ms trajectory as a summary or continuous-state update interval,
  not the fundamental identity unit.
- On long arcs, compare line, quadratic, and bounded cubic descriptions with
  block-weighted validation; curvature is evidence, while jerk remains
  secondary until independently confirmed.
- Add full-frame/predictable-symbol CFO and TOA likelihoods when supported by
  the existing corpus. Qin/pilot detection establishes Starlink-format signal,
  not NORAD identity.
- Add DOA, a disciplined reference, or differential-receiver evidence through
  optional narrow ports; absence of those measurements must remain explicit.

## Work packages

### WP0 — Integration and authority closure

**Purpose:** establish exact inputs and prevent silent use of stale or similar
artifacts.

**Deliverables:**

- active-branch inventory of the completed campaign protocols, reports,
  registries, TLE authorities, site/RF authorities, and artifact hashes;
- one versioned experiment protocol for each data-opening boundary; and
- a deny-by-default dataset resolver that authorizes exact capture/span/path
  identities.

**Tests:** missing, altered, newer, extra, or substituted inputs fail before IQ,
response, propagation, or ranking access.

**Exit:** every development and future-confirmation row resolves to immutable
authority, or the work remains `BLOCKED`.

### WP1 — Measurement-kernel and physical-episode foundation

**Purpose:** ensure association consumes faithful physical observations rather
than biased timestamps or duplicated tracker fragments.

**Deliverables:**

- support-centred/window-integrated CFO observation contract;
- persisted support moments and calibrated/frozen uncertainty inputs;
- TLE-blind source groups, fragments, replica edges, exclusion edges, and
  unassigned state; and
- exact sample-clock, continuity, alias, and RF lineage.

**Tests:** support-centre regression; alias lift/replay; refill and continuity
poisoning; nested-fragment weight caps; simultaneous-incompatible-track
preservation; no TLE import in episode construction.

**Exit:** the long-arc rows reproduce under the new timestamp contract and no
tracker fragmentation can create extra association votes.

### WP2 — Candidate likelihood bank and baselines

**Purpose:** produce complete, uncertainty-aware candidate evidence before
global association.

**Deliverables:**

- causal TLE propagation integrated over observation support;
- response-free candidate geometry/visibility population;
- robust per-fragment and per-episode candidate likelihood/cost matrices;
- explicit radio-only/polynomial and unassigned likelihoods; and
- covariance-aware nearest-neighbor/EKF baseline.

**Tests:** finite-difference propagation; candidate completeness and stable
ordering; TLE/site/RF poison tests; equal-mask scoring; analytic synthetic
curves; invariance under harmless row duplication and ordering.

**Exit:** every candidate and null model is scored with equal evidence and
nuisance opportunity, without looking at future response.

### WP3 — `K=0,1,2` multi-hypothesis association

**Purpose:** preserve one-emitter, two-emitter, handoff, and ambiguity
explanations instead of majority voting fragments.

**Deliverables:**

- exact or top-N active-set enumeration after response-free gating;
- chronological assignment with replica/exclusion constraints;
- unassigned/clutter and handoff states;
- deterministic tie handling, pruning receipts, and complete runner sets; and
- posterior/marginal likelihood that includes covariance and complexity rather
  than minimized RMS alone.

**Tests:** 10/0, 8/2, and 5/5 mixtures; false split/merge; sequential and
simultaneous emitters; close-rate pairs; label swapping; clutter; missed
detections; enumeration versus brute force on small banks.

**Exit:** known-truth mixtures return calibrated active-count and assignment
posteriors or explicit ambiguity without candidate truncation.

### WP4 — Conditional nuisance smoother and ECM

**Purpose:** jointly estimate legitimate shared state without absorbing
identity-specific curvature.

**Deliverables:**

- information/Kalman smoother for conditionally linear nuisance states;
- bounded nonlinear tau/orbit profile;
- generalized EM/ECM updates inside each retained discrete hypothesis;
- deterministic multi-start and two-cycle/local-mode diagnostics; and
- fixed-lag backward smoothing after, never before, future scoring.

**Tests:** monotonic penalized objective/ELBO; gauge invariance; bound hits;
random-walk/reset behavior; multi-start disagreement; comparison with direct
optimization on small synthetic cases; no per-fragment hidden slope/tau.

**Exit:** nuisance recovery and uncertainty are calibrated on known truth, and
different near-optimal identity modes remain separate.

### WP5 — Calibration and model-selection suite

**Purpose:** learn measurement floors, structural penalties, and reporting
thresholds without using real candidate outcomes as truth.

**Deliverables:**

- response-free injection protocol covering rate, acceleration, jerk,
  sample-clock ppm, RF-scale error, SNR, occupancy, steps, aliases, drift,
  retunes, TLE error, and emitter mixtures;
- comparison of radio-only, current independent fit, NNDA/EKF, `K=1`, `K=2`,
  and oracle-label lanes with equal nuisance flexibility; and
- frozen thresholds or formal abstention where the number of independent
  calibration groups is insufficient.

**Tests:** exact truth and seed reproduction; scenario-equal aggregation;
identical evaluable-ID gates; block/group uncertainty; no invalid finite-sample
coverage claim.

**Exit:** any future numeric identity or margin threshold is frozen before an
untouched confirmation cohort is opened.

### WP6 — Opened long-arc development

**Purpose:** determine whether the current best real arcs contain useful
catalogue information under the new model.

**Deliverables:**

- `K=0,1,2` reports for `9981` and `150802`;
- candidate and active-set posterior timelines;
- tau profiles, nuisance profiles, candidate-switch points, and polynomial-null
  comparisons;
- causal future-block and rolling-origin predictions; and
- top-k/equivalence-set and abstention outputs.

**Tests:** results reproduce from sealed inputs; every no-result persists;
training selections are frozen before future scoring; block/episode units, not
raw row counts, control uncertainty.

**Exit:** each arc is honestly classified as stable candidate, ambiguity set,
handoff/multi-emitter sequence, radio-only, or unresolved. No confirmation or
secure-NORAD claim is made.

### WP7 — Sequential multi-dwell prediction

**Purpose:** test whether later geometry resolves earlier ambiguity and whether
shared satellite corrections transfer over time.

**Deliverables:**

- rolling experiment: fit dwells `1..d`, predict `d+1`, seal score, then
  assimilate and optionally smooth backward;
- identity, active-count, nuisance, and correction-state trajectories; and
- leave-one-session-out analysis where enough sessions exist.

**Tests:** future-dwell poison fields; state reset and validity expiry;
permutation of dwell order where chronology should matter; offline reduced-bank
Rao-Blackwellized particle audit of top-N pruning.

**Exit:** improvement is demonstrated in future predictive log score and
calibrated identity sets, not merely full-data residual or apparent convergence.

### WP8 — Satellite correction product

**Purpose:** create the transferable boundary between the known-position
reference and an unknown-position receiver.

**Required fields:**

- NORAD or explicit ambiguity set;
- causal TLE hash, element epoch/age, and propagation model;
- equivalent epoch/orbit correction and covariance;
- satellite/beam clock-frequency state and covariance;
- correction validity start/end and expiry reason;
- association probability/evidence class;
- calibration site/time and measurement provenance; and
- explicit exclusion of local receiver/LNB/path states.

**Tests:** canonical digest, immutable versioning, covariance validity,
expiry/rejection, gauge separation, and no receiver-local state leakage.

**Exit:** a correction product can be loaded without opening calibration IQ and
predicts a later known-site observation within its frozen uncertainty.

### WP9 — Position-hidden navigation

**Purpose:** measure whether associated/corrected signals actually determine
receiver position.

**Lanes:**

1. oracle identity and oracle/frozen correction;
2. unknown identity with frozen reference-derived correction;
3. unknown identity with jointly refined correction; and
4. radio-only/no-correction control.

**Initialization ladder:** declared position priors of approximately 100 m,
10 km, 100 km, and continental/global scope. Broad priors require particles or
geographic modes; identity uncertainty remains a mixture in the position
posterior. An Earth-surface/altitude constraint must be declared rather than
silently assumed.

**Tests:** synthetic position recovery; numerical Jacobians; posterior
multimodality; prior-radius sweep; wrong-identity poisoning; correction expiry;
leave-session-out and frozen-output truth reveal.

**Exit:** a sealed position posterior is produced before truth is read, and the
result reports 2-D/3-D error, covariance/credible-region coverage, convergence
mode, and failure attribution by lane.

### WP10 — Untouched confirmation and operational scaling

**Purpose:** confirm the method independently and decide whether a correction
network, STAN, or additional observable is required.

**Deliverables:**

- versioned protocol and thresholds committed before opening new response;
- at least one untouched long arc and preferably repeated, separated geometry;
- independent receiver/pass recurrence where feasible; and
- decision on reference-network corrections, STAN/radio-SLAM, DOA, wideband,
  disciplined oscillator, or differential-receiver investment.

**Exit:** the full milestone passes on untouched data, or the result identifies
the measured observability limitation and the next required observable. Any
new RF collection requires explicit user authorization and remains bounded by
repository policy.

## Parallel execution and dependencies

| Lane | Can start after | Work | Joins at |
|---|---|---|---|
| A — Measurement | WP0 | WP1 support kernels, likelihoods, uncertainty, full-frame feasibility | WP2 |
| B — Association | WP0 contracts plus synthetic adapters | WP2 candidate bank, WP3 active sets | WP4/WP6 |
| C — Nuisance/calibration | WP0 | WP4 kernels on synthetic data, WP5 injections | WP6/WP7 |
| D — Navigation | WP0 plus correction schema draft | Oracle-identity WP9 solver on synthetic data | WP8/WP9 |

WP6 may use opened development data only after WP1-WP5 code and experiment
authority are frozen. WP7 follows the first stable WP6 artifact. WP9 can build
its synthetic/oracle lane in parallel but cannot consume real correction
products until WP8 passes.

## Validation ladder and required metrics

### Test ladder

1. Pure unit/property tests for contracts, propagation, likelihoods, gauges,
   assignments, and smoothers.
2. Analytic and simulation tests with exact truth.
3. Known-truth RF-background injections after protocol freeze.
4. Opened real-data development on exact registered cohorts.
5. Rolling future-block and next-dwell prediction.
6. Immutable correction-product replay.
7. Position-hidden retrospective evaluation.
8. Untouched confirmation under a precommitted protocol.

### Measurement metrics

- future CFO/TOA/DOA log score and RMS in correct units;
- completion/no-result fraction and exact common masks;
- normalized residuals, calibration/coverage, and block-weighted uncertainty;
- absolute versus differential Doppler information retained; and
- support-centre and estimator-model sensitivities.

### Association metrics

- top-1 accuracy where truth exists and top-k credible-set coverage;
- posterior entropy/effective candidate count and runner set;
- active-count confusion and minority-emitter recall;
- false split, false merge, handoff, assignment, and identity-switch rates;
- future winner persistence and fixed-lag revision history; and
- radio-only/unassigned probability and abstention reason.

### Nuisance metrics

- recovery error and covariance for shared/local states;
- boundary-hit and reset counts;
- sensitivity to tau, TLE, site, RF, sample clock, and estimator lane; and
- whether added nuisance freedom improves future prediction rather than only
  training residual.

### Navigation metrics

- sealed 2-D/3-D position and timing error;
- credible-region coverage and consistency diagnostics;
- convergence rate, mode count, and dependence on the declared initial prior;
- oracle-to-unknown-identity and frozen-to-joint-correction degradation; and
- time-to-first-position and observation/satellite support.

## Checkpoints

| Checkpoint | Required outcome |
|---|---|
| C0 — Authority | Exact inputs, protocols, source hashes, and deny-by-default resolver pass before data access. |
| C1 — Measurement | Support-centred observations and TLE-blind episodes pass truth and regression tests. |
| C2 — Association | `K=0,1,2` synthetic mixtures recover calibrated active sets or ambiguity without forced labels. |
| C3 — Nuisance | Shared/local state recovery is identifiable under declared gauges and improves heldout prediction. |
| C4 — Long arcs | Both opened arcs produce complete predictive reports with stable candidates, ambiguity sets, or abstention. |
| C5 — Multi-dwell | Later dwells improve calibrated predictive evidence without forcing inappropriate common identity. |
| C6 — Correction | A receiver-local-state-free correction product predicts a later observation. |
| C7 — Blinded PNT | Position is sealed before truth reveal and all four diagnostic lanes attribute error. |
| C8 — Confirmation | Precommitted untouched data confirms or falsifies the milestone. |

## Failure semantics and non-goals

The system must abstain rather than manufacture an identity when:

- radio-only or unassigned evidence is competitive;
- important catalogue candidates were truncated or propagation is incomplete;
- top modes are restart-dependent or within the calibrated ambiguity margin;
- identity changes under predeclared estimator, TLE, or nuisance variants;
- a critical nuisance hits its bound;
- future likelihood degrades despite better training residual;
- physical episode/alias authority fails;
- support, duration, recurrence, or position/antenna authority is insufficient;
  or
- the position posterior remains materially multimodal.

This plan does not seek to:

- infer secure NORAD identity from Qin/PSS/SSS alone;
- declare hundreds of correlated rows to be independent evidence;
- make the old far-time empirical rank a future hard gate;
- treat `[-5,+5] s` as universally proven or widen it after a boundary result;
- enforce one satellite across all sequential dwells;
- equate receiver-relative CFO with physical orbital Doppler;
- export receiver/LNB state as a satellite correction;
- use opened development data as untouched confirmation; or
- launch an unbounded RF collection campaign.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Flexible nuisance absorbs identity curvature | Restrict state scope, use priors/gauges, compare equal-flexibility radio-only models, and score future data. |
| Greedy or EM lock-in | Retain top global modes, deterministic multi-starts, fixed-lag smoothing, and offline particle audit. |
| Fragment duplication creates false votes | TLE-blind physical grouping, replica/exclusion graph, and source-group weight caps. |
| Similar Starlink shells remain inseparable | Return ambiguity sets; prioritize longer curvature, simultaneous differences, DOA, wideband, or reference receivers. |
| Known-position leakage inflates navigation | Freeze correction products on separate calibration data before releasing position on untouched data. |
| Receiver drift assumed stable too long | Random-walk/hierarchical state with measured resets and validity intervals, not hard equality across hours. |
| TLE snapshot is recent but element is stale | Persist both retrieval age and selected element epoch/age; expire corrections explicitly. |
| Added rows manufacture precision | Use block/episode/session analysis units and grouped uncertainty. |
| Point estimate hides multimodality | Persist full top-mode/credible-region summaries and calibration diagnostics. |

## First implementation slice

The first bounded implementation should stop after a synthetic and contract
demonstration; it should not immediately reopen real IQ:

1. Define versioned observation, physical-episode graph, candidate-likelihood,
   active-set hypothesis, and correction-product contracts.
2. Implement window-integrated catalogue prediction and a covariance-aware
   nearest-neighbor baseline using synthetic adapters.
3. Implement exact/brute-force `K=0,1,2` assignment on small candidate banks,
   with unassigned state and equal nuisance opportunity.
4. Implement the conditional linear nuisance solver under an explicit gauge.
5. Verify 10/0, 8/2, 5/5, handoff, alias, drift, and close-rate cases.
6. Freeze the long-arc development protocol only after the synthetic and poison
   tests pass and an independent audit verifies data authority and leakage
   boundaries.

This slice answers whether the architecture is sound before optimization,
large-catalogue execution, or navigation code expands the scope.

## Definition of done

The goal is complete when:

- WP0-WP10 artifacts, tests, and protocols are versioned and linked;
- every data opening follows committed authority and chronology;
- the association posterior is calibrated on known truth and predicts future
  observations on untouched data;
- a frozen correction product cleanly separates satellite and receiver-local
  state;
- a position-hidden evaluation seals its posterior before truth reveal;
- the oracle, association, correction, and full-system lanes attribute any
  remaining error;
- the result either meets a precommitted PNT milestone or records a precise,
  evidence-backed observability blocker; and
- no required work remains under the active goal.

## Literature basis

- [Nearest Neighbor Data Association for LEO Satellite Identification](https://people.engineering.osu.edu/media/document/2025-05-19/kassas_nearest_neighbor_data_association_for_leo_satellite_identification.pdf)
- [Multiple Hypothesis Tracking](https://doi.org/10.1109/TAC.1979.1102177)
- [Joint probabilistic data association and smoothing for space objects](https://doi.org/10.2514/1.G002230)
- [Maximum Likelihood TOA and Doppler Estimation for Precise Starlink-Based PNT](https://radionavlab.ae.utexas.edu/wp-content/uploads/qin_ML_Precise_TOA_PLANS.pdf)
- [Modeling and Compensation of Timing and Spatial Ephemeris Errors](https://people.engineering.osu.edu/media/document/2025-07-23/kassas_modeling_and_compensation_of_timing_and_spatial_ephemeris_errors_of_non_cooperative_leo_satellites_with_application_to_pnt.pdf)
- [First Results of Differential Doppler Positioning with Unknown Starlink Signals](https://people.engineering.osu.edu/sites/default/files/2022-10/Kassas_First_results_of_differential_Doppler_positioning_with_unknown_Starlink_satellite_signals.pdf)
- [Time-Diverse Doppler-Only LEO PNT](https://rosap.ntl.bts.gov/view/dot/80647)
- [Ad Astra: Simultaneous Tracking and Navigation](https://people.engineering.osu.edu/media/document/2023-11-14/kassas_ad_astra_simultaneous_tracking_and_navigation_with_megaconstellation_leo_satellites.pdf)
- [Direction-of-Arrival and Doppler-Based Positioning with Starlink and OneWeb](https://www.ion.org/publications/abstract.cfm?articleID=20327)

## Repository evidence and reusable building blocks

- [Seeded alias EM](../reports/2026_08_21_seeded_alias_em_d6a.md)
- [Historical multi-dwell Starlink association](../reports/2026_08_22_multi_dwell_starlink_association.md)
- [Fresh thirteen-dwell association](../reports/2026_08_23_thirteen_dwell_starlink_association_fresh.md)
- [Ten-dwell raw Doppler pipeline](../reports/2026_08_24_ten_dwell_raw_doppler_pipeline.md)
- [Post-refill retrospective synthesis](../reports/2026_08_25_post_refill_24h_retrospective/README.md)
- [`satellite_assignment` research implementation](../src/leo/analysis/research/satellite_assignment.py)
- [`cross_dwell_shared_norad` reducer](../src/leo/analysis/research/cross_dwell_shared_norad.py)
- [Evidence ledger](../docs/research/evidence-ledger.md)

These existing implementations and reports are references, regressions, or
component starting points. They are not automatically promoted into the new
public contracts or accepted as current identity evidence.

## Decision log and update rules

- **2026-08-26:** goal activated and this living implementation plan recorded.
- **2026-08-27:** first synthetic checkpoint implemented. It freezes a
  TLE-blind physical-episode contract, a response-free and
  membership-authorized candidate universe, exact `K=0,1,2` Gaussian
  hypothesis enumeration with explicit ambiguity/abstention, and the
  correction/blinded-position artifact boundary. This checkpoint is
  model-conditional and synthetic; it neither opens real data nor completes
  WP2, WP4, WP7, WP8, or WP9.
- Prospective changes to data, masks, state scope, tau support, candidate
  population, scoring, or thresholds require a versioned protocol/config and a
  decision-log entry before affected response is opened.
- Dated reports and receipts are never rewritten to match this plan; corrections
  are additive.
- Completed work packages must link their exact code, config, tests, report,
  commit, and artifact hashes.
- This plan becomes stale when the estimator architecture, data policy,
  reference-to-user correction boundary, or target PNT milestone changes.
