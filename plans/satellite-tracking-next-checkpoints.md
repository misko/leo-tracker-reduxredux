# Satellite Tracking: Next Checkpoints

Date: 2026-08-27 UTC

Remote baseline before checkpoint publication: origin/main at
9ff5cd3c8f2fd52f3289a4e3a5b7dc82bfc4d372

Status: **ACTIVE operational roadmap**

Latest opened-development execution:

- [C1/C2/C3 report](../reports/2026_08_27_satellite_tracking_checkpoint_results.md)
- [complete one-attempt receipt](../reports/figures/2026_08_27_satellite_tracking_checkpoints_v1-execution-receipt.json)
- Implementation commit `2a7a793999173f420394a59017a10dc744053b9b`;
  execution-authority commit `c4d3810cf25ed7f259978a2c10b88578eb1917a4`.
- Result publication commit `e4b8f4d8dbd0c20a450ca8d1387ec74f1bdf8f32`.

## Purpose and claim boundary

This is the concise execution dashboard for improving Starlink tracking,
catalogue association, and eventual Doppler positioning. The detailed design
and implementation ledger remains
[satellite-association-and-pnt.md](satellite-association-and-pnt.md). Dated
reports, frozen protocols, and sealed evidence receipts remain authoritative
for experimental results.

The present scientific claim is deliberately narrow:

> Receiver-relative Starlink-format CFO tracking works, including reproducible
> POST-FIX curvature on two registered long arcs. Secure NORAD identity and
> real-data global positioning have not yet been demonstrated.

The north-star question for the next phase is:

> After marginalizing only physically legitimate nuisance states, does one
> satellite hypothesis—or a small calibrated equivalence set—accumulate
> predictive evidence faster than competing catalogue and radio-only
> explanations as time and geometry accumulate?

## Current baseline

| Area | Current evidence | Boundary |
|---|---|---|
| Final POST-FIX holdout | 8/8 evaluable CFO response tracks recovered; temporal-permutation structure on 7/8 | Complete catalogue compatibility 0/8; secure NORAD 0 |
| Short-history forecasting | Fixed 125 ms is descriptively best at 57.754 Hz equal-capture future RMS | Not prospectively promoted; 20/125/500 ms are history horizons, not independent votes |
| Long arc 150802 | 13.825 s, 550 points; conditional 59748; 55.06 Hz future RMS; strong wrong-epoch separation | Earliest rolling origin selects 65438 |
| Long arc 9981 | 30.000 s, 881 points; conditional 67930 stable across rolling origins | A minus-500-second catalogue field predicts better in two of four comparisons |
| Shared nuisance study | All four primary tracks recovered | Shared physical-radio-rate model was 1.48% worse; candidate evidence 0/4 |
| Implementation | Exact K=0,1,2 association, NULL, causal filtering, identity smoothing, known-site calibration, correction contracts, and positioning lanes exist | Most end-to-end qualification remains synthetic or conditional |
| Likelihood calibration | Reproducible paired truth infrastructure exists | Only 3/6 truth arms classified correctly on three independent backgrounds; thresholds are not frozen |

Dataset roles are fixed:

- **Immutable regression evidence:** the final ten-dwell POST-FIX holdout.
- **Opened development evidence:** exact registered 150802 and 9981 spans.
- **Calibration evidence:** known-truth and semi-synthetic injections into
  authorized POST-FIX backgrounds.
- **Confirmation evidence:** a future untouched cohort, only after the method
  and thresholds are frozen and collection is explicitly authorized.

PRE-FIX multi-second slopes never promote a current identity claim.

## Critical path

~~~text
C0 evidence authority
  -> C1 candidate observability + C2 calibrated evidence
  -> C3 real long-arc multi-hypothesis closure
  -> decision: sufficient / measurement-limited / geometry-limited
  -> C4 causal multi-dwell prediction
  -> C5 frozen correction replay
  -> C6 blinded positioning
  -> C7 untouched confirmation
~~~

C1 and C2 should run in parallel. A measurement-headroom experiment is a
bounded branch from the C3 decision, not permission to delay calibration or
start a new receiver stack.

## Checkpoint scorecard

| Checkpoint | Status | Required outcome |
|---|---|---|
| C0 — Evidence and physical authority | **DONE for registered arcs; ongoing operational invariant** | Exact inputs, POST-FIX counter authority, causal TLE bytes, response-free candidate populations, and nonduplicated physical observations |
| C1 — Candidate observability atlas | **OPENED RUN EXECUTED; provisional and incomplete** | Final all-tau candidate graph and tau=0 prefix atlas reported; covariance-weighted and prefix-by-prefix all-tau promotion remain open |
| C2 — Common calibrated evidence scale | **EXECUTED; BLOCKED at 3/19 calibration pairs** | Common blocks and abstention work, but covariance and the detector-opportunity inventory are incomplete |
| C3 — Real long-arc hypothesis closure | **EXECUTED; UNRESOLVED on both arcs** | 9981 retains a response-supported four-satellite set; 150802 retains a 571-satellite set; neither promotes identity |
| C4 — Causal multi-dwell prediction | **Synthetic foundation done; real promotion held behind C2/C3** | Better next-dwell prediction from physically scoped shared state without false identity concentration |
| C5 — Frozen known-site correction replay | **Contracts/synthetic lane done; real replay pending C4** | Satellite-only correction predicts a later known-site observation without refitting |
| C6 — Blinded positioning | **Synthetic numerical lanes done/partial; real evaluation pending C5** | Sealed oracle, uncertain-identity, joint, and radio-only comparison with unresolved mass preserved |
| C7 — Untouched confirmation | **Requires frozen method and explicit collection authorization** | Independent recurrence or a quantified, reproducible observability limit |

## Opened-arc checkpoint result — 2026-08-27

The one authorized attempt ran from 18:46:00 to 20:15:29 UTC. It read no IQ,
collected no RF, and completed with a hash-closed report, manifest, two full
compressed results, and ten figures.

| Arc | C1 all-tau 125 ms graph | Response-supported C3 set | Honest outcome |
|---|---|---|---|
| 9981 | 488 candidates; 10 components; largest 466; five singletons | `{54758, 59523, 64746, 67930}`; provisional mass concentrates on 67930 around tau = -1 s | **Unresolved**: opportunity inventory incomplete; covariance and posterior masses uncalibrated |
| 150802 | 573 candidates; 3 components; largest 571; two singletons | 59748 and the early-origin 65438 are in the same 571-candidate component | **Unresolved**: geometry is non-identifying at all three descriptive floors, and C2 remains incomplete |

The 20/125/500 ms all-tau overlays tell the same qualitative story. For 9981,
the largest components contain 469/466/466 candidates; for 150802 they contain
571/571/571. The longer curvature-bearing arc therefore does not by itself
solve catalogue identity after independently allowed tau and receiver drift
are profiled. This is a useful geometry-limit result, not a tracking failure or
permission to widen the nuisance model.

C2 conditionally favors the catalogue family on both opened arcs, and its top
states are 67930 for 9981 and 59748 for 150802. Those values are development
diagnostics only: the opportunity universe is incomplete, only 3 of the
required 19 independent calibration pairs exist, and all posterior-like masses
remain uncalibrated.

## C0 — Evidence and physical authority

**Inputs**

- Registered exact spans for 150802 and 9981.
- Counter-authoritative RecordingManifestV2 continuity.
- Exact site/RF authority and causal TLE snapshot bytes.

**Required invariants**

- Construct physical episodes without TLE ranking.
- Collapse byte-equivalent aliases and contained duplicate fragments.
- Preserve genuinely incompatible simultaneous tracks.
- Count each physical observation once.
- Build complete candidate populations without response ranking.
- Fail closed on stale, incomplete, substituted, or unbound authority.

**Exit evidence**

The existing long-arc manifests, response-free populations, rolling partitions,
and report numbers reproduce from immutable inputs.

## C1 — Candidate observability atlas

For every close candidate pair and every causal prefix, compute the separation
remaining after the allowed nuisance basis is projected away:

\[
d_{jk}^{2}(T)=
\min_{\beta}
\left\|
D_j(0{:}T)-D_k(0{:}T)-B\beta
\right\|_{\Sigma^{-1}}^{2}.
\]

Here, B contains only declared physical nuisance terms such as a path offset or
a verified receiver-drift state. It must not contain a hidden candidate-specific
slope, acceleration, or per-fragment time shift.

The calibrated target is the covariance-weighted expression above. The first
opened-development atlas deliberately reports a separately labeled
`homoscedastic-identity-rms-v1` lane because the C2 covariance has not passed
calibration. Its 20/125/500 ms RMS floors are detached descriptive overlays,
not a substitute for Sigma and not a gate. A covariance-weighted C1 promotion
must wait for C2 covariance calibration so that geometry and evidence use the
same frozen noise authority.

**Deliverables**

- Response-free tau=0 threshold-graph connected neighborhoods by prefix
  duration, plus the exact all-tau profile at final duration. Prefix-by-prefix
  all-tau profiling remains a C1 completion item rather than being inferred
  from the tau=0 curves.
- The C3 identity handoff uses the 125 ms connected neighborhoods from the
  offset-plus-ridge-drift lane, matching the receiver offset/drift nuisance
  basis marginalized by C2 without implying covariance-metric identity. The
  offset-only atlas remains a reported sensitivity view and is never
  substituted for that handoff. Candidate-identity edges are profiled over the
  complete cross-product of independently allowed tau states: an edge exists
  when any allowed tau pair falls below the floor, and the resulting candidate
  component label is then carried by every tau state for that candidate. A
  tau=0-only atlas remains a labeled sensitivity view and cannot authorize the
  C3 handoff.
  These are single-linkage components, not pairwise-equivalent cliques; chained
  endpoints remain explicitly marked.
- Effective candidate count rather than only rank one.
- Candidate-pair time-to-separation curves.
- The displayed close-pair inventory is the response-free union of nearest
  pairs selected independently under offset-only and offset-plus-ridge-drift;
  neither lane is allowed to hide the other lane's nearest competitors.
- Sensitivity to 20, 125, and 500 ms measurement histories.
- Separate same-NORAD tau sensitivity from full-catalogue delta = ±500 s
  specificity. The first wrong-field lane is explicitly fixed at tau = 0 in
  both fields; it is not operational-tau-profiled and is not a null test.

**Exit decision**

- **Observable:** at least one candidate class separates at the calibrated
  measurement floor; proceed to C3.
- **Measurement-limited:** separation appears after a realistic noise
  reduction; run the bounded measurement-headroom branch, then repeat C1.
- **Geometry-limited:** large classes remain equivalent even with a materially
  lower noise floor; stop adding Doppler-fit freedom and plan a new observable
  or geometry for later authorization.

## C2 — Common calibrated evidence scale

Catalogue orbits and line/quadratic/cubic radio-only explanations must share:

- identical calendar blocks and masks;
- one declared covariance treatment;
- normalized hypothesis-family priors;
- equal handling of missing data and work limits; and
- proper future/prequential scoring.

Known-truth scenarios must cover orbit, line, quadratic, cubic, close-orbit
decoys, K=0/1/2 activity, aliases, receiver resets, slow drift, sparse
transmitter steps, missing data, and one-/two-emitter mixtures.

**Exit evidence**

- Innovation covariance and independent-block coverage are calibrated.
- The truth remains in the reported singleton or ambiguity set at the
  predeclared rate.
- Active-emitter count and null behavior are calibrated.
- Numerical thresholds are frozen before another observational cohort is
  interpreted.

The current three independent background groups are insufficient for the
predeclared 19-pair empirical-rank floor. Until that floor is met, likelihoods
remain development evidence and no posterior probability becomes an identity
claim.

If modest covariance or prior variants continue to reverse orbit-versus-radio
preference, the correct output is **unresolved model family**.

## C3 — Real long-arc multi-hypothesis closure

Run a Rao-Blackwellized, multiple-hypothesis model on the registered arcs:

- H0: radio-only or unassigned;
- H1: one persistent NORAD;
- H1-switch: at most one physical handoff or declared change point; and
- K=2: only where the TLE-blind physical graph contains two incompatible
  simultaneous sources.

Discrete identity, H0 radio-only/unassigned, handoff, and emitter-count branches
remain separate.
Continuous receiver, satellite-frequency, and bounded equivalent-epoch states
are marginalized within each branch. An EM/ECM update may refine those
continuous states, but it may not erase competing identity branches or use
future response to rewrite causal receipts.

**Deliverables**

- Cumulative prequential evidence versus duration.
- Posterior mass and entropy over equivalence classes.
- Main and rolling-origin future scores.
- Nuisance-state and change-point diagnostics.
- Complete accounting of pruned, null, and unresolved mass.

**Healthy expected behavior**

- 150802 may retain {65438, 59748} early and concentrate later if curvature
  warrants it.
- 9981 should retain ambiguity or null mass unless calibrated evidence truly
  resolves its wrong-epoch catalogue decoys.

A method that confidently labels both arcs merely because an optimizer
converged has failed this checkpoint.

## Decision after C3

| Finding | Action |
|---|---|
| Candidate geometry is separable and likelihood is calibrated | Proceed to C4 |
| Geometry is separable but the measurement floor is too high | Run the measurement-headroom branch and repeat C1–C3 |
| Candidates remain Doppler-equivalent after credible noise reduction | Preserve the equivalence set; prioritize DOA, disciplined frequency, differential reception, or new geometry |
| Radio-only remains competitive or evidence calibration is unstable | Report unresolved; improve C2 rather than widening nuisance freedom |

### Bounded measurement-headroom branch

Use only already authorized/opened IQ and identical evaluation masks. Where the
corpus supports it, compare:

- current direct-GLRT or pilot CFO;
- predictable-symbol/edge-pilot evidence;
- minimal full-frame or template-frame maximum-likelihood CFO;
- joint carrier CFO and symbol/frame-rate evidence; and
- sparse change-point diagnostics on one-second and 15-second grids.

A provisional engineering promotion target is at least a twofold reduction in
independent-block residual scale, no material support loss, and a corresponding
increase in the C1 projected catalogue separation. Better training residual
alone is not sufficient. If the target is missed, stop this branch and retain
the current estimator.

## C4 — Causal multi-dwell prediction

Extend the real-data adapter to changing visibility, candidate birth/death,
multiple physical episodes, and bounded persistent tau while retaining NULL
and handoff modes.

Compare, prospectively:

1. per-dwell offsets only;
2. one drift inside a verified hardware-continuity epoch;
3. dwell-local drift states coupled by a calibrated random walk; and
4. the same models with sparse transmitter-frequency changes.

Score dwell d+1 before assimilating it. Learn random-walk or change-point
hyperparameters on earlier sessions or known truth, never on the target future
dwell. Do not hard-share a deterministic drift between 9981 and 150802 merely
because the named receive chain matches; the observations are separated by
many hours.

**Promotion criterion**

Shared state improves next-dwell proper score and calibrated identity-set
concentration over the independent-dwell baseline.

If richer state lowers training residual but does not improve the future
score, retain the simpler model.

## C5 — Frozen known-site correction replay

Only after C3/C4 supports an identity mode or calibrated equivalence set:

1. fit satellite frequency and equivalent-epoch states at the known site;
2. marginalize and exclude every receiver/LNB/path state;
3. freeze covariance, validity interval, TLE digest, and identity-mixture mass;
4. predict a later known-position observation before assimilation; and
5. forbid identity or satellite-state refitting during replay.

**Promotion criterion**

The frozen correction improves later normalized residuals over causal
TLE-only prediction and its uncertainty has valid coverage.

No suitable independent same-NORAD recurrence currently exists. An expired
validity interval, unresolved frequency gauge, receiver-state leakage, or
material identity mass outside the corrected set blocks real positioning.

## C6 — Blinded positioning

Run the existing diagnostic lanes in order:

1. oracle identity and correction;
2. unknown identity with frozen reference correction;
3. joint identity/correction mixture; and
4. radio-only no-position control.

Advance from a local prior toward broader/global particles only when numerical
rank, condition/D-GDOP, evaluated identity mass, and geographic modality are
reported. Seal the estimate before truth is accessible.

Interpret failures diagnostically:

- oracle failure means measurement, correction, or geometry is not ready;
- oracle success plus unknown-identity failure means association is limiting;
- local success plus global failure means initialization or geographic
  multimodality is limiting; and
- null, pruned, or unevaluable identity mass remains unresolved.

## C7 — Untouched confirmation

No new RF collection is authorized by this plan. If C1–C6 reach an
existing-corpus observability ceiling, first freeze the method, thresholds,
candidate policy, correction schema, and evaluation protocol. Then request
explicit authorization for one bounded campaign of at most 30 minutes.

The confirmation capture should bind:

- exact UTC and causal TLE bytes;
- receiver position and antenna/boresight;
- RF path, oscillator, counter, and reset authority;
- several long sequential arcs or separated recurrence geometry;
- simultaneous signals on one oscillator where possible; and
- preferably one orthogonal observable: DOA, wideband TOA/frame timing, a
  disciplined reference, or a synchronized second receiver.

Confirmation succeeds if it yields either a secure recurring identity or a
well-calibrated abstention that quantifies the Doppler-only observability limit.

## Standing model policy

- Primary orbit time remains tau = 0.
- Tau in [-5,+5] s is a bounded persistent equivalent epoch/along-track
  sensitivity, not a literal receiver-clock correction.
- Full-catalogue delta = -500 s and +500 s fields are always reported and
  remain observe-only.
- Fixed 125 ms is the principal descriptive short-history lane; 20 ms is a
  change-detection lane and 500 ms is a rate/sensitivity lane.
- No response may select the candidate universe, physical episode, mask,
  nuisance family, or threshold.
- Low RMS, optimizer convergence, or posterior collapse alone never promotes
  identity.
- Same-emitter continuity, orbital curvature, conditional NORAD, secure NORAD,
  transferable correction, and navigation-ready are separate claims.

## Immediate execution queue

1. Expand C2 known-truth calibration from 3 to at least 19 independent pairs,
   freeze a covariance authority, and construct a complete detector-opportunity
   inventory. Reconcile the current RMS/NLL family reversal before interpreting
   another posterior-like mass.
2. Promote C1 from detached homoscedastic floors to the same calibrated
   covariance metric used by C2. Add prefix-by-prefix all-tau profiling only if
   it changes a decision; the final exact profile already establishes severe
   150802 Doppler equivalence.
3. Implement genuinely distinct rolling-origin refits and future scores. The
   current cumulative prefixes of one fixed partition are not that experiment.
4. Inventory the existing corpus for causal multi-dwell recurrence and an
   orthogonal observable—frame/symbol rate, disciplined frequency, DOA, or a
   synchronized second receiver—before considering any new collection.
5. Run C4 on real sequential dwells only after steps 1–3 are frozen. Advance to
   C5 no-refit correction replay only if next-dwell score improves without false
   identity concentration.

These tasks use the existing corpus and require no new RF campaign.

## Source-of-truth hierarchy and update rules

1. Frozen protocols, dated reports, and sealed evidence receipts are result
   authority.
2. [satellite-association-and-pnt.md](satellite-association-and-pnt.md) is the
   detailed design and implementation ledger.
3. This file is the current priority and checkpoint dashboard.
4. [satellite_tracking_update_plan.md](../satellite_tracking_update_plan.md) is
   retained as superseded historical context.

A checkpoint status changes only when a dated receipt or report and its commit
are linked here. A development result may refine a method, but it never becomes
independent confirmation retroactively.
