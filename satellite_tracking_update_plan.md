# Satellite Tracking Update Plan

Date: 2026-08-26 UTC
Evidence baseline commit: `1a3d72d5b28c44430eb9da682b6996f890a78223`

Status: **living working plan**. This file is not a protocol, evidence receipt,
dataset authorization, production configuration, or permission to collect or
open data. Dated reports and frozen machine-readable protocols remain the
authority for completed experiments.

## Motivation

The receiver now recovers smooth Starlink-format CFO trajectories with useful
future prediction accuracy, but it does not yet attach trustworthy NORAD
identities. The immediate goal is to separate failures of signal tracking from
failures of catalogue discrimination, then improve the latter without giving
each candidate enough nuisance freedom to fit any smooth curve.

## Problem

The final POST-FIX holdout recovered a response trajectory in every evaluable
capture, yet no capture passed the complete historical catalogue-compatibility
gate. The dominant failures were not missing CFO measurements or refill
discontinuities. They were:

1. the training winner often changed on future response data;
2. different reasonable CFO predictors selected different NORADs;
3. rolling-origin candidate identity was unstable;
4. sub-second arcs contained too little curvature to distinguish hundreds of
   geometrically visible Starlinks after a free CFO offset; and
5. receiver, LNB, transmitter, and sample-clock terms remain partly
   confounded with propagation Doppler.

Before any TLE ranking, the physical signal episode itself must also be
constructed without catalogue assistance: canonicalize symbol-rate aliases,
replay selected branches against the same IQ, collapse contained fragments,
preserve genuinely simultaneous incompatible tracks, group same-emitter paths,
and enforce one-to-one assignments when multiple signals coexist. A good TLE
score cannot repair a mistaken episode or alias choice.

Two exact, counter-contiguous POST-FIX development arcs now provide a better
place to study catalogue discrimination: a 30-second `9981` arc and a
13.825-second `150802` arc. Both contain validated receiver-relative
curvature, but both are already opened development data and therefore cannot
serve as untouched confirmation.

## Solution

Use a staged association design:

- retain a lean exact-time TLE model with one free CFO constant per dwell/path;
- use `tau = 0` as the primary orbit-time model;
- treat `tau in [-5,+5] s` as a hard modelling support interval and record its
  stability, without describing the interval as a universal PNT-derived truth
  bound; the measurements from that search remain diagnostic while thresholds
  are calibrated;
- observe two full-catalogue wrong-epoch challenges at `-500 s` and `+500 s`,
  but do not make them a gate or compute a significance p-value from two
  fields;
- compare the TLE model against causal predictor variants and satellite-free
  polynomial models on future blocks;
- use shared physical-radio/LNB rate terms only as regularized diagnostics
  until they show repeatable held-out benefit; and
- require model, future-response, rolling-origin, and eventually independent
  recurrence evidence before promoting a NORAD claim.

## Method

The forward work is divided into four layers:

1. **Track recovery:** establish that the Starlink-format signal supplies a
   supported future CFO trajectory and that its TLE-blind physical episode is
   internally coherent.
2. **Candidate ranking:** rank every eligible Starlink from a causal TLE
   snapshot using training data only.
3. **Candidate persistence:** freeze the winner and nuisance state, then score
   future response bins, runner margins, rolling origins, and model agreement.
4. **Identity authority:** add capture-bound site/antenna authority and
   recurrence on independent observations before making an absolute NORAD
   claim.

No held-out response may alter source selection, masks, candidates, `tau`,
nuisance parameters, or rank order.

## Current decision snapshot

| Question | Current answer |
|---|---|
| Is the waveform/track Starlink-like? | **Supported.** Qin edge-pilot structure justifies a Starlink-only candidate population. |
| Can we recover a future CFO response track? | **Yes conditionally:** 8/8 evaluable final-holdout captures. |
| Is fixed 125 ms currently the best short-history predictor? | **Descriptively yes:** 57.754 Hz equal-capture future-CFO RMS, but it had no frozen promotion gate. |
| Do we have a catalogue-compatible final-holdout candidate? | **No:** 0/8. |
| Do we have a secure NORAD identity? | **No:** 0. |
| Operational orbit-time treatment | Primary `tau=0`; working support `tau in [-5,+5] s`. A boundary hit is reported and never triggers automatic widening. |
| Wrong-epoch treatment | Full-catalogue fields at `delta=-500 s` and `+500 s`, **observe only**. Report scores and identities; no p-value or pass/fail. |
| Forward numeric thresholds | Historical values remain descriptive; new RMS, runner, polynomial-advantage, permutation, and rolling thresholds are unset until a protocol freezes calibrated choices. |
| Priority data | The exact registered POST-FIX `9981` and `150802` long arcs. |
| New or ongoing data | Forbidden until an explicit reviewed policy revision releases it. |

The local PNT paper does not publish a scalar `tau` bound. Follow-on work
reports seconds-scale adjustments, so `[-5,+5] s` is a conservative engineering
support interval, not a universal physical claim. Fitted `tau` is an equivalent
along-track/orbit sensitivity, not an estimate of receiver clock error.

## Vocabulary and status labels

Evidence terms:

- **recovered track:** enough future response exists to score a frozen CFO
  trajectory; this says nothing about identity;
- **conditional candidate:** one catalogue object ranks first under a stated
  model, source, site, TLE, nuisance family, and split;
- **catalogue compatible:** a candidate survives all gates of the protocol
  that produced that result;
- **secure NORAD:** an identity with adequate provenance, site authority,
  nuisance control, and independent recurrence.

Forward policy labels:

- **HARD:** required for a result to be considered valid;
- **OBSERVE:** always report, but do not allow the field to pass or fail the
  candidate;
- **DIAGNOSTIC:** sensitivity evidence that cannot silently change identity;
- **SUPERSEDED:** retained as historical evidence but not used prospectively.

Work labels are separate: `NOT STARTED`, `IN PROGRESS`, `DONE`, and `BLOCKED`.

## Exact admissible cohorts

| Cohort | Exact authority | Intended use | Restrictions |
|---|---|---|---|
| Final ten-capture POST-FIX holdout | [`final-doppler-holdout-satellite-protocol-v3.json`](config/analysis/final-doppler-holdout-satellite-protocol-v3.json) | Historical gate audit and method-development sensitivity only | Responses are opened; not a fresh confirmation or tuning holdout; further reuse needs separate experiment authority |
| Two long POST-FIX arcs | [`post-fix-long-arc-research-cohort-v1.json`](config/analysis/post-fix-long-arc-research-cohort-v1.json), parent role `rate_development` | Primary development cohort for long-arc catalogue discrimination | Exact capture/path/span only; opened development; no identity or holdout authority |
| Polynomial-injection hard-null backgrounds | [`doppler-experiment-dataset-policy-v1.json`](config/analysis/doppler-experiment-dataset-policy-v1.json), role `polynomial_injection` | Known-truth synthetic injection after a response-free protocol freeze | Exact 3 authorized hard-null captures; freeze spans, seeds, truth, occupancy, aliases, clock offsets, and scoring first. **Active-background injection requires a separately reviewed policy revision** |
| Opened multi-radio development captures | Same policy, role `multi_radio` | Shared-rate/free-offset diagnostic and repeatability | Diagnostic; no absolute LNB or clock truth |
| Any newer, ongoing, unlisted, PRE-FIX, or CAPTURE_ONLY input | None | None | **Forbidden** until a reviewed policy revision explicitly admits it |

The registered long arcs are:

- `cap-20260824T192252-9981b9c27853`, RX1 upper, samples
  `[0,75,000,000)`, 30.000 seconds;
- `cap-20260825T150802-473cb5bbcbd6`, RX1 upper, samples
  `[93,937,500,128,500,000)`, 13.825 seconds.

Both are committed `RecordingManifestV2` inputs with one counter-authoritative
segment and zero recorded gaps, missing samples, overflows, or enqueue
failures. See the [frozen long-arc cohort report](reports/2026_08_26_post_fix_long_arc_research_cohort.md).

## Gate stack

Not every check is an identity gate. The forward stack is:

| Layer | Checks | Forward disposition |
|---|---|---|
| Dataset integrity | Exact authorized capture/path/span/digests; POST-FIX counters; one segment; no loss/gaps/overflow; causal TLE bytes | **HARD** |
| Analysis integrity | Frozen source and response masks; chronological split; training-only candidate/nuisance selection; identical held-out masks; complete failure ledger | **HARD** |
| Physical-episode construction | TLE-blind alias canonicalization and same-IQ replay; exact-Qin versus rolled/control specificity; fragment collapse; source-bound joins/breaks; preservation of simultaneous incompatible tracks; cross-path same-emitter grouping and one-to-one assignment | **HARD** before catalogue ranking |
| Track support | Minimum training and future bins; future response fraction; no silent missing-response exclusion | **HARD** |
| Forecast quality | Identical-mask future CFO scoring, completion, and block-wise fixed125/fixed500/quadratic comparison | **HARD reporting concept**; numerical RMS threshold remains **UNSET** pending calibration, and no method may be selected after seeing its response |
| Candidate separation | Training winner remains best on future data; runner separation is reported | Persistence is a **HARD concept**; numerical runner threshold remains **UNSET** pending calibration |
| Model stability | Candidate agreement across predeclared predictor models and rolling origins | **HARD concept** for a catalogue claim; forward counts/thresholds must be frozen in a protocol |
| Satellite-free comparison | TLE model versus the appropriate line/quadratic/cubic radio-only null on future blocks | **HARD concept**; numerical advantage threshold remains **UNSET** pending calibration |
| Physical time sensitivity | `tau=0` primary; common `[-5,+5] s` support; report optimum, boundary, early/late, and rolling stability | **HARD** search support and no automatic widening; resulting scores are **DIAGNOSTIC** until calibrated |
| Two wrong-epoch fields | Re-rank the full Starlink catalogue at `-500 s` and `+500 s` with the same local `tau` support and training-only selection | **OBSERVE** only; no p-value, threshold, or veto |
| Permutation control | Preserve masks and splits while breaking temporal ordering | **HARD reporting concept** for trajectory structure; count/rank threshold remains **UNSET** and is not identity-specific |
| Receiver/LNB nuisance | Per-dwell/path CFO constants; shared regularized physical-chain rate sensitivity | Constants are primary; shared rate is **DIAGNOSTIC** until validated |
| Provenance sensitivities | Exact UTC bounds, observer site, predecessor/latest causal TLE, RF and path identity | **HARD** provenance evidence |
| Absolute identity authority | Capture-bound site/antenna authority and independent recurrence | **HARD** before `secure NORAD` language |

### Computing the observational `+/-500 s` fields

For each field centre `delta in {0,-500,+500} s`, candidate `j`, and
`tau in [-5,+5] s`, use

```text
predicted_cfo_i = TLE_Doppler_j(t_i + delta + tau) + fitted_CFO_constant
```

For each `delta`, freeze a response-free geometric Starlink population using
that field's shifted measurement times, the same causal snapshot, observer,
RF metadata, and predeclared horizon rule. Geometry determines membership;
response data does not. The training prefix alone then selects the NORAD,
`tau`, and CFO constant. Each field receives identical nuisance flexibility.
The training-selected winner and nuisance values are frozen and scored exactly
once on the identical future mask; held-out response never reranks or refits.
Record, for all three fields:

- winning NORAD and runner;
- selected `tau` and whether it is on the support boundary;
- training and future RMS;
- `R_-500 - R_0`, `R_+500 - R_0`, and the corresponding RMS ratios; and
- candidate-fixed scores for the true-time winner as a secondary diagnostic.

With only two wrong-epoch fields, the old empirical rank expression can take
only `1/3`, `2/3`, or `1`. It cannot support a `p <= 0.05` claim. These fields
must therefore remain observations, even when both are worse than true time.

## Historical frozen final-holdout audit

The following table describes the completed v3 experiment. Its frozen verdict
is not rewritten by this plan. Eight of ten captures were association-evaluable;
`cap-20260825T034929-bc0480bdb4a8` lacked total/training support and
`cap-20260825T035201-d0abaead734c` lacked training support.
Association evaluability required both primary and fixed500 predictions plus
`>=10` total bins, `>=6` training bins, and `>=4` evaluation bins. The lower
recovered-track floor then required `>=4` finite evaluation bins, `>=50%`
future response availability, `>=2` visible candidates, and finite held-out scores for every
candidate. The separate claim condition below required `>=8` future bins.

| Historical v3 condition | Requirement | Passed | What it says |
|---|---:|---:|---|
| Association-evaluable captures | both predictors and `>=10` total / `>=6` training / `>=4` evaluation bins | 8/10 | Two captures were retained but could not enter catalogue scoring |
| Recovered track | `>=4` finite evaluation bins, `>=50%`, `>=2` candidates, all candidate scores finite | 8/8 | Tracking worked on every evaluable capture |
| Minimum future bins | at least 8 | 8/8 | Basic response count was adequate |
| Future-bin availability | at least 50% | 8/8 | Basic response fraction was adequate |
| Rank-one future RMS | at most 100 Hz | 6/8 | Most, but not all, selected curves predicted to tens of Hz |
| Primary/baseline rank-one agreement | same NORAD | 2/8 | Identity was highly predictor-dependent |
| Training runner ratio | at least 1.10 | 6/8 | Two winners were poorly separated at selection time |
| Training winner remains best held out | required | 2/8 | Six candidates did not persist into future response |
| Future runner ratio | at least 1.10 | 6/8 | Two future winners were poorly separated |
| Historical wrong-time fields scored | at least 38 of 40 | 8/8 | Historical control execution was complete |
| All 20 permutations scored | required | 8/8 | Control execution was complete |
| Permutation empirical rank | at most 0.05 | 7/8 | Smooth temporal ordering was usually real |
| At least two stable rolling origins | required | 1/8 | Causal identity stability was the rarest positive result |
| UTC/site/predecessor controls | complete and same ID | 8/8 | Those bounded provenance sensitivities were not the immediate failure |
| Forty-field far-time empirical rank | at most 0.05 | 0/8 | Historical global catalogue-time specificity failed; 6--36 of 40 shifted fields were no worse per capture |
| Complete catalogue compatibility | every frozen condition | 0/8 | No final-holdout candidate passed |
| Absolute secure NORAD | permitted and supported | 0 | Site/boresight authority independently remained insufficient |

The exact capture-level matrix is in the
[detailed final result](reports/2026_08_26_final_doppler_holdout_and_starlink_association_v2.md).

Removing the historical far-time condition would not create a match. Every
one of the eight evaluable captures failed at least one other condition,
usually model agreement, future winner persistence, or rolling stability.

| Capture suffix | Other historical failures after ignoring far-time rank |
|---|---|
| `022235` | predictor-model agreement; future winner persistence; rolling stability |
| `030000` | absolute RMS; predictor-model agreement; training and future runner margins; future winner persistence; permutation rank; rolling stability |
| `031521` | predictor-model agreement; future runner margin; rolling stability |
| `033028` | future winner persistence; rolling stability |
| `033302` | predictor-model agreement; training runner margin; future winner persistence |
| `041207` | predictor-model agreement; rolling stability |
| `043656` | absolute RMS; predictor-model agreement; future winner persistence; rolling stability |
| `050946` | future winner persistence; rolling stability |

### Forecast-method promotion gate, not an identity gate

The final experiment also froze a separate decision about replacing the
fixed-500 predictor with the strict-past 500 ms quadratic. It must not be
confused with catalogue compatibility.

| Predictor condition | Requirement | Observed | Result |
|---|---:|---:|---|
| Equal-capture RMS ratio | quadratic/fixed500 at most 0.95 | 0.964863 | fail |
| Per-capture wins | at least 8/10 | 9/10 | pass |
| Complete capture comparisons | exactly 10 | 10 | pass |
| Worst capture ratio | at most 1.10 | 1.006281 | pass |
| Completion difference | at most 1 percentage point | 0.222 pp | pass |
| Response/common availability per capture | at least 50% | `034929`: 10/112 | fail |

Formal historical result: do not promote the quadratic. Fixed 125 ms was the
best descriptive future-CFO predictor, but it had no frozen promotion test.

### Retrospective bounded-nuisance gate audit

The separate four-capture opened-development experiment used three short
frame-CFO tracks and the long `150802` direct-CFO arc. It tested a bounded
physical-radio rate hierarchy against a fixed-time/free-offset baseline.

| Retrospective condition | Passed | Interpretation |
|---|---:|---|
| Primary support | 4/4 | Single-frame bundles had `>=3` paths, `>=2` physical radios, and every path had `>=30` training bins and `>=20` evaluation bins; the long arc had `>=300` total bins |
| Recovered baseline and hierarchy catalogue banks | 4/4 | All four tracks were rankable with finite candidate banks |
| Hierarchy future RMS at most 100 Hz | 3/4 | `130425` failed at 136.44 Hz |
| TLE beats quadratic radio null by at least 20 Hz | 2/4 | Orbit shape was not consistently better than local curvature |
| Training runner gap at least 100 Hz | 0/4 | Universal separation failure; gaps were 0.30--39.04 Hz |
| Future runner gap at least 50 Hz | 3/4 | `130425` failed with a 4.98 Hz gap |
| Baseline/hierarchy winner agreement | 4/4 | Added rate freedom did not change those four winners |
| All three rolling origins preserve the winner | 3/4 | One track changed winner |
| Old `+/-0.25 s` sensitivity keeps the winner and is interior | 0/4 | Every optimum reached a boundary; this old range is superseded |
| Historical 40-field wrong-time rank | 1/4 | Historical only; superseded prospectively |
| Twenty-permutation temporal-order control | 4/4 | Smooth temporal order was real |
| Complete candidate-evidence gate | 0/4 | No identity passed |
| Secure provenance | 4/4 | Causal TLE, observer, RF, path/radio identity, and nuisance-bound checks passed |
| Secure capture | 0/4 | No capture combined recovery, candidate evidence, and provenance |
| Independent recurrence | 0 | Required the same passing NORAD in at least 2 independent capture IDs; none existed |
| Secure NORAD | 0 | No evidence pass or recurrence |

The hierarchy's equal-capture future RMS was 79.18 Hz versus 78.02 Hz for the
baseline, 1.48% worse. This is why shared radio-rate freedom remains a
diagnostic rather than a default identity model.

### Long-arc one-off gate status

The long-arc registry itself is only an input authority; it runs no identity
gate. Existing one-off analyses remain useful but are not a common operational
scorecard:

- `9981`: candidate 67930 forecast the tail better than a train-only cubic,
  but the training runner gap was only 23.86 Hz, the old time search reached a
  boundary, and no complete calibrated catalogue-control family existed.
- `150802` RX1-only: fixed-time candidate 59748 produced a strong conditional
  score, but fitted time worsened future RMS and early/late folds selected
  inconsistent shifts.
- the older `150802` dual-channel common-orbit audit passed 9 of 19 checks and
  failed 10, including time interiority, radio-polynomial advantage, runner
  separation, future alternative separation, time stability, and matched-time
  specificity. Both channels shared one Pluto clock and LO.

These one-off checks motivate the unified long-arc protocol; they are not
silently promoted into new gates by this plan.

### Forward disposition of historical gates

| Historical field | Forward treatment |
|---|---|
| Dataset, response-sealing, support, identical-mask future scoring, winner persistence, model/rolling stability, satellite-free comparison, permutation execution, and provenance concepts | Retain as required concepts |
| Historical numerical cutoffs (`100 Hz`, `1.10`, `100/50 Hz` runner gaps, and `20/100 Hz` polynomial advantages) | **UNSET prospectively**; report descriptively, but none transfers automatically to a long-arc protocol before appropriate calibration |
| `tau=0` only | Replace with `tau=0` primary plus the common `[-5,+5] s` diagnostic support |
| Forty fields from `+/-15 min` through `+/-5 h` and `p<=0.05` | **SUPERSEDED prospectively**; historical result remains immutable |
| `-500 s` and `+500 s` full-catalogue comparisons | Add as **OBSERVE-only** fields; never silently turn them into a p-value or hard gate |
| Shared physical-radio rate | Keep diagnostic and unable to silently change identity |
| Absolute secure identity | Continue to require stronger site/antenna authority and recurrence |

## Where satellite tracking currently fails

### 1. Identity discrimination, not signal recovery

The strongest result is also the clearest diagnosis: 8/8 response tracks were
recovered, but the training winner survived future data in only 2/8 and at
least two rolling origins were stable in only 1/8. We can follow a moving
signal without yet knowing which Starlink produced it.

### 2. The short arcs do not contain enough distinctive geometry

The final association arcs contain roughly 0.33--1.01 seconds of binned
response. After fitting a free CFO constant, many of the roughly 508--551
visible Starlinks supply nearly affine local curves. More frames reduce noise,
but they do not manufacture orbital curvature.

### 3. Candidate identity depends on the CFO predictor

The strict-past quadratic and fixed-500 baseline selected the same NORAD in
only 2/8 captures. Fixed 125 ms was the best descriptive short-history
forecaster, but it was not part of a frozen identity-promotion comparison.
Future association must compare predeclared predictors on identical masks and
must not choose the winner after response access.

### 4. Catalogue runner separation is inconsistent

Two of eight training runner ratios and two future runner ratios failed the
historical 1.10 threshold. The four-capture retrospective nuisance experiment
was even clearer: all four training winners missed its 100 Hz runner-margin
gate. A low absolute RMS is therefore not enough. This is not the universal or
dominant final-holdout failure: model agreement, future persistence, and
rolling stability failed more often.

### 5. Nuisance freedom has not solved identity

The bounded multi-radio hierarchy recovered 4/4 finite rankings but was 1.48%
worse in equal-capture future RMS and produced 0/4 complete candidate-evidence
passes. The final shared-rate diagnostic found small receiver-chain departures,
including `-4.0188 Hz/s` for the only chain pooled across several evaluable
captures, but it was forbidden from changing identity and supplied no
held-out promotion result. More unconstrained per-candidate slope or curvature
would risk fitting away the orbital signature. Bench evidence also shows that
LNB drift can wander over minutes, so the forward hierarchy is a soft,
time-local shrinkage model with free path/dwell offsets—not one stable slope
assumed across hours.

### 6. Some captures remain support-limited

Two of ten final captures were not association-evaluable. Long histories also
have lower completion when uninterrupted support is absent. Every failure must
remain in the denominator rather than being silently dropped.

### 7. Upstream acquisition is not yet end-to-end withheld

Source, alias, trajectory, and epoch selection may use all-Qin evidence over a
complete span. The final result is genuinely future-response-withheld
downstream of that conditioning, but it is not a blind causal acquisition
test. Long-arc rolling claims must either rebuild association from each
training prefix or state this conditioning explicitly.

### 8. Secure-identity authority is incomplete

The reviewed observer location is a preset with stated uncertainty, not a
capture-bound survey; antenna boresight/gain authority is absent. Those facts
do not explain all candidate instability, but they independently prevent an
absolute secure-NORAD claim.

## Why the long arcs matter

The registered arcs directly target the largest failure: lack of curvature.

| Arc | Empirical shape evidence | Present candidate status | Development question |
|---|---|---|---|
| `9981`, 30.000 s | Cubic is the minimum adequate long-arc CFO description | NORAD 67930 conditional only | Does a physics-based TLE curve beat the cubic radio-only null on future blocks and remain stable under bounded `tau`? |
| `150802`, 13.825 s | Quadratic CFO/timing curvature is clear; jerk is not robustly required | NORAD 59748 conditional only | Does 59748 remain best across future blocks, predictors, bounded `tau`, and catalogue runners? |

These arcs are development evidence. They can falsify models and refine a
protocol, but they cannot provide independent confirmation because they have
already been examined.

## Intended forward work plan

| Stage | Work | Inputs | Parallelism | Expected artifacts | Status |
|---|---|---|---|---|---|
| 0 | Record the current semantics and gate inventory | Committed reports and protocols only | Serial | This plan | **DONE** once merged |
| 1A | Freeze one long-arc association protocol, TLE-blind episode rules, support-centred measurement kernel, and block analysis units before evaluating new candidate outcomes | Exact two-arc registry and causal TLE bytes | Serial prerequisite | Versioned protocol, masks, splits, model hierarchy, failure ledger | NOT STARTED |
| 1B | Design known-truth calibration for estimator error, nuisance stress, candidate margins, and bounded-`tau` power | TLE-derived synthetic signals on the exact three authorized hard-null backgrounds | Parallel after model/truth freeze | Calibration protocol with known NORAD/time shift and catalogue rerun; descriptive mechanics report until enough independent groups exist | NOT STARTED |
| 2A | Run the exact `9981` long-arc development comparison | Registered 30-second span only | Parallel | Full candidate table, `tau` profile, future/rolling scores, polynomial comparison, figures | NOT STARTED |
| 2B | Run the exact `150802` long-arc development comparison | Registered 13.825-second span only | Parallel | Same outputs; explicit 59748 adjudication | NOT STARTED |
| 2C | Evaluate a soft, time-local receiver/LNB nuisance sensitivity after 2A/2B training winners are sealed | Authorized multi-radio data plus only the exact registered RX1 long-arc spans | Sequenced after candidate freezing; can run alongside later scoring/audit | Shared-rate, separate-radio, and hierarchical common-plus-regularized-deviation comparisons with free path/dwell offsets | NOT STARTED |
| 3 | Independent scientific and provenance audit | Sealed outputs from stages 1--2 | After runs | Gate reconstruction, leakage audit, artifact manifest | NOT STARTED |
| 4 | Freeze a confirmation protocol | Successful development design only | Serial | Immutable protocol and acceptance rules | NOT STARTED |
| 5 | Evaluate a genuinely unopened long-arc cohort | Only after explicit dataset release/review | Later | Confirmation report; no post-hoc threshold changes | BLOCKED pending authorized data |

Stages 2A and 2B may run in parallel once stage 1A has frozen the common model,
masks, scoring, and claim language. Stage 2C starts only after their
training-selected identities are sealed; it must not estimate one constant
radio/LNB slope across hours or silently access unregistered receivers. Stage
1B may proceed in parallel after a response-free model/truth protocol freezes
the exact authorized hard-null spans, seeds, truth, occupancy, aliases, clock
offsets, and scoring. It becomes **BLOCKED** if it needs an active real
background, a new span, or a new capture. Existing generic polynomial
injections can assess estimator rate/RMS and stress behavior, but they cannot
calibrate catalogue runner margins or `tau` identity power unless the injected
signal is a known TLE-derived trajectory and the catalogue search is rerun.
Three reused backgrounds and twelve groups also cannot supply a finite formal
95% rank quantile; that requires at least nineteen suitable exchangeable
calibration groups. This plan does not launch any stage.

Any authorized Stage 1B design must separately sweep SNR/occupancy, smooth
rate/acceleration/jerk, abrupt steps, sample-clock ppm/time-scale, RF scale,
and alias changes. It must preserve their meanings: an injected rate error in
Hz/s is not a future-CFO error in Hz, a receiver-chain disagreement is not
truth error, and fitted `tau` is not a receiver-clock measurement.

## Expected per-arc output

Every long-arc result should preserve:

- exact input, TLE, site, path, source, and mask digests;
- TLE snapshot retrieval age and each winner/runner element epoch and age as
  separate fields;
- a versioned support-centred observation-time rule or full aperture-kernel
  moments for multi-frame GLRT measurements, rather than treating probe start
  as the CFO observation time; retain older probe-start results only as a
  labelled sensitivity;
- the TLE-blind physical-episode/alias construction ledger, including
  simultaneous-signal and cross-path assignments;
- complete candidate and failure inventories;
- `tau=0` and bounded-`tau` candidate identities and profiles;
- training, future, and rolling-origin RMS by candidate and model;
- true-time runner identities and margins;
- line/quadratic/cubic radio-only comparisons on identical future blocks;
- fixed125, fixed500, and quadratic predictor identity agreement where the
  required measurements exist;
- `-500 s` and `+500 s` observational winners, scores, differences, and ratios;
- shared-rate/free-offset sensitivity that cannot silently rerank candidates;
- block/episode-level paired uncertainty, effective analysis-unit counts, and
  an explicit warning that dense frames and overlapping rolling origins are
  correlated rather than independent;
- unit-explicit metrics: future CFO error in Hz, known-truth rate error in
  Hz/s, and receiver-chain disagreement labelled as neither of those nor as
  physical Doppler truth;
- Matplotlib figures, machine-readable evidence, and an artifact manifest; and
- an explicit disposition for every capture and every gate.

## Non-goals and claim boundary

- Do not reinterpret the historical final-holdout `0/8` result under the new
  prospective semantics.
- Do not promote either opened long-arc candidate to a secure identity.
- Do not treat `[-5,+5] s` as universally proven by PNT literature.
- Do not treat two wrong-epoch fields as a null distribution or p-value.
- Do not add candidate-specific free slope, acceleration, jerk, or scale to the
  primary orbit model merely to lower residual RMS.
- Do not apply the current LNB/radio drift observations as an absolute Doppler
  correction.
- Do not open ongoing, newer, or unlisted experimental data.
- Do not collect new RF under authority of this plan.

## Provenance

Current primary sources:

- [Detailed final holdout and association result](reports/2026_08_26_final_doppler_holdout_and_starlink_association_v2.md)
- [Immutable final score](reports/figures/2026_08_26_final_doppler_holdout_attempt2-score.json)
- [Retrospective receiver-nuisance result](reports/2026_08_26_retrospective_satellite_nuisance_results.md)
- [Fixed500 and strict-past curvature calibration](reports/2026_08_26_fixed500_calibration_results.md)
- [Multi-radio common-rate result](reports/2026_08_26_multi_radio_common_rate_results.md)
- [Frozen POST-FIX long-arc cohort](reports/2026_08_26_post_fix_long_arc_research_cohort.md)
- [`9981` cubic-CFO/TLE comparison](reports/2026_08_24_9981b9c27853_cubic_cfo_tle_comparison.md)
- [`150802` visible-Starlink fit](reports/2026_08_25_150802_visible_starlink_tle_fit.md)
- [Satellite identity recovery review](reports/2026_08_25_satellite_identity_recovery_v2.md)
- [`150802` alias-aware common-orbit audit](reports/2026_08_25_150802_alias_aware_common_orbit.md)
- [Dual-LNB drift reference](reports/2026_08_22_dual_lnb_drift_reference.md)
- [Wrong-time and orbital-time interpretation](reports/2026_08_26_wrong_time_specificity_and_orbital_time_shift.md)
- [Doppler-rate campaign synthesis](reports/2026_08_26_doppler_rate_experiment_campaign.md)
- [Research evidence ledger](docs/research/evidence-ledger.md)

Lower-priority campaign lanes remain intentionally deferred: V4 improved a
numerical acquisition inventory but its downstream rate comparison was
under-supported and slightly adverse; the causal acceleration surrogate was
adverse on real short arcs; phase/PSS-SSS rate estimates remain unvalidated as
identity inputs; and no frozen real weak-frame full-likelihood comparison is
available. See the [V3/V4 benchmark](reports/2026_08_25_v3_v4_downstream_rate_benchmark.md),
[causal acceleration result](reports/2026_08_25_causal_cfo_acceleration_development.md),
and [multi-dwell PSS/SSS result](reports/2026_08_25_multi_dwell_pss_sss_doppler.md).

## Decision log

| Date | Decision |
|---|---|
| 2026-08-26 | Register exact `9981` and `150802` POST-FIX long arcs as opened development inputs. |
| 2026-08-26 | Keep `tau=0` as primary and use `[-5,+5] s` as the operational sensitivity support. |
| 2026-08-26 | Replace the historical broad far-time family prospectively with observations at `-500 s` and `+500 s`. |
| 2026-08-26 | The two wrong-epoch fields are observational only: no empirical p-value, threshold, veto, or promotion effect. |
| 2026-08-26 | Prioritize long-arc discrimination, future persistence, model agreement, runners, and rolling stability over adding unconstrained nuisance terms. |

## Update rules

1. Never rewrite dated result reports to match this evolving plan.
2. A prospective gate change requires a versioned protocol/config and a new
   decision-log entry before outcome evaluation.
3. Every completed work item must link its code, config, tests, report, commit,
   and machine evidence.
4. Counts in this plan must come from sealed artifacts, not recollection.
5. `[-5,+5] s` must remain labelled a working support interval unless a
   calibration campaign establishes a different claim.
6. The `+/-500 s` fields must remain observations unless a future, separately
   calibrated protocol explicitly promotes them.
7. This plan never authorizes data access, data collection, dataset discovery,
   or substitutions.
8. Re-review this plan whenever the long-arc protocol freezes, a work stage
   completes, dataset policy changes, or identity claim language changes.
