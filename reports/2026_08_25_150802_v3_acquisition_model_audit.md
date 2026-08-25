# V3 acquisition-model audit: `cap-20260825T150802-473cb5bbcbd6`

Date: 2026-08-25

## Decision

V3 is not losing the Qin pilot in the 50 robust missing windows.  It is
discarding a stable, trajectory-consistent acquisition mode before the Kalman
filter can use it.  The primary cause is a model-definition error in the
full-frame acquisition gate:

1. the supplied trajectory epoch is treated only as a diagnostic reference and
   is not protected during sparse-anchor candidate retention;
2. the exact template and a 17-symbol rolled template independently maximize
   over the complete epoch/CFO domain;
3. the global rolled-template maximum is subtracted from every exact candidate;
   and
4. a negative specificity margin is reported as `NO_RESULT`, which makes a
   code/epoch ambiguity look like signal absence.

At 2.5 MS/s, 17 OFDM symbols are exactly 187 samples.  Searching the rolled
control at an epoch approximately 187 samples earlier therefore reacquires the
same Qin sequence.  It is a close reparameterization of the expected waveform,
not an independent signal-absence null.  CFO curvature, a physical frame reset,
and the early second CFO family are not the general cause.

The best bounded counterfactual is seed-aware short-block acquisition:

- always evaluate the supplied trajectory epoch/CFO mode;
- measure repeated held-out evidence in four approximately 20 ms blocks;
- evaluate controls at the candidate's same epoch/CFO and on the same absolute
  verification samples;
- preserve distinct CFO families as separate modes; and
- keep numerical acquisition, pilot presence, code specificity, uniqueness,
  tracking, and phase-lock qualification as separate decisions.

On this frozen development capture, that model surfaced all 50 robust missing
modes and the phase-safe core tracked all 50.  Only one became phase-qualified,
and that case is just 0.000875 rad below the existing RMS threshold.  This is
therefore an acquisition recovery, not evidence for 50 new navigation-quality
locks.  The thresholds remain in-sample and uncalibrated, so the model is not a
Standard-pipeline promotion result.

## Frozen population

The source is the complete 537-window, trajectory-conditioned 75 ms replay.  It
contains 57 V2-complete/V3-`NO_RESULT` rows:

- 50 robust rows with 18--56 V2 frequency updates;
- seven one-update rows that have a same-time peer exactly one OFDM CFO alias
  (`227,272.727273 Hz`) away;
- zero Standard-V1-qualified rows; and
- zero V2 phase-lock-qualified rows.

V3 preserved every V2 phase-lock-qualified row and every Standard-qualified
row through acquisition.  The apparent loss is therefore restricted to weak
or already-unqualified V2 state estimates.

Among the 57 missing rows, 48 fail the V3 full-frame exact-minus-control gate.
The other nine pass acquisition but the selected epoch/CFO has no supported
frame.  Running the unchanged phase-safe V3 core directly at the persisted
nominal V2 epoch/CFO completes 57/57 with the same frame support as V2, while
qualifying phase lock on 0/57.

## Why the rolled control is not a null

`CONTROL_SYMBOL_ROLL` is 17.  The sampled displacement is

\[
17\times4.4\ \mu\mathrm{s}\times2.5\ \mathrm{MS/s}=187\ \mathrm{samples}.
\]

For every one of the 18 strongest real-data vetoes, the independently searched
control winner is at nominal epoch minus 187 +/- 1 samples and within 250 Hz of
the nominal CFO seed.  The shifted template overlap is approximately 0.96.
Exhaustive 300-roll checks rank roll 0 first at the nominal epoch and roll 17
first at the shifted epoch; all other rolls are near the noise floor.  The
control is therefore seeing structured Qin energy from the same sequence.

A noiseless 20-frame synthetic exact injection makes the same point.  The
exact hypothesis scores 1.000, while the independently searched roll-17
control scores 0.915 at epoch minus 187.  Injecting roll 17 reverses that finite
window preference.  Because the roll is odd, the shifted search also swaps the
received even/odd symbol parity: exact and control verification no longer use
the same physical held-out samples.

The implementation says that symmetric maximization prevents a control from
winning by shifting epoch, but the opposite is true for a cyclic roll.  The
exact and rolled searches are at
`src/leo/analysis/starlink/acquisition.py:350-413`; the global scalar control is
used for every exact candidate at lines 393--413, and a negative margin becomes
`NO_RESULT` at lines 442--478.

The synthetic tests that require symmetric exact/roll rejection are useful V3
replay tests, but they cannot define signal-absence semantics for a successor.
Without an external absolute frame marker, a pilot roll plus a compensating
epoch shift is code-phase ambiguous.

## Why the correct exact mode is sometimes absent

V3 first scores only 12 sparse anchor symbols, retains eight separated basins,
and only then evaluates the full even/odd partitions.  The nominal trajectory
mode is not injected into this retained set.  In the 50 robust losses:

- 25 V3 winners remain within two epoch samples of nominal and are rejected by
  the shifted rolled-control maximum;
- 25 jump 35--1,557 samples to diffuse weak basins, with a median absolute jump
  of 612 samples; and
- a direct nominal-epoch CFO sweep recovers exact Qin scores of 0.041--0.190 in
  all 50, never at the +/-2 kHz CFO boundary.

Increasing retention from eight to 16 recovers 19/48 rejected alignments;
increasing it to 32 recovers 25/48.  This diagnoses sparse-anchor truncation,
but it is an inefficient incomplete remedy.  Explicitly proposing the nominal
mode is both cheaper and faithful to the fact that these windows are
trajectory-conditioned reacquisitions rather than blind detections.

Candidate ordering also matters after controls become candidate-conditional.
A maximum-margin rule can prefer a weak basin merely because its control score
is unusually small.  Among candidates that pass a predeclared specificity
gate, the exact held-out score should lead ordering; the trajectory prior and
margin should be explicit conditioning evidence rather than an accidental
tie-break.

## Full-537 conditional-control counterfactual

A read-only replay evaluated the same IQ, edge, epoch/CFO seed, and phase-safe
tracker for all 537 rows.  All 14 consumed compressed chunks were verified
against the manifest hashes.  The three-roll variants used the repository's
already declared `(17, 53, 101)` surrogate bank at each exact candidate's same
coordinates, with an exact floor of 0.02 and a descriptive margin of 0.03.

| Acquisition policy | acquired | tracked | phase lock | recovered 57 missing |
|---|---:|---:|---:|---:|
| Current V3: independently searched roll 17 | 383 | 266 | 54 | 0 |
| Same-coordinate roll 17, zero margin | 531 | 291 | 54 | not selective |
| Three same-coordinate rolls, no protected prior | 267 | 267 | 54 | 14 |
| Three same-coordinate rolls plus nominal proposal | 319 | 311 | 54 | 49 |

The zero-margin conditional variant admits 209/214 rows where neither V2 nor
V3 tracks, although none of those 209 survives the downstream tracker.  This
shows why simply moving the existing control is not enough.  The conservative
three-roll prior variant preserves 53/53 Standard-qualified tracks and 55/55
V2 phase-qualified tracks, recovers 49 missing numerical tracks, and creates no
additional phase lock.  Eight of 214 both-no rows enter acquisition but zero
track; the acquisition decision must therefore remain distinct from signal
presence and track qualification.

An opposite-edge code transplanted to the same carrier tones has maximum
cyclic correlation about 0.049, compared with the shifted roll control's 1.0
code equivalence.  It behaved similarly to the three same-coordinate rolls on
this capture.  That is useful confirmation, but neither control bank has a
search-wide calibrated threshold.

## Short-block conditioned reacquisition

The deeper prototype used four 20 ms blocks starting at approximately 0,
18.333, 36.667, and 55 ms inside each 75 ms window.  In each block it searched
only nominal epoch +/-2 samples and CFO +/-500 Hz in 50 Hz steps, evaluated
exact odd-Qin evidence and same-coordinate controls, and required consistent
epoch and CFO across at least three of four blocks.

The descriptive development-capture gate was:

- exact score at least 0.08 and same-coordinate margin at least 0.02 in at
  least three blocks;
- median exact score and margin at least the same thresholds;
- capture-relative epoch span at most three samples; and
- CFO median absolute deviation at most 100 Hz.

The 223-row tracker follow-up was deliberately stratified:

| group | rows | selected | tracked | phase-qualified |
|---|---:|---:|---:|---:|
| Robust V3 drops | 50 | 50 | 50 | 1 |
| Standard-qualified controls | 53 | 53 | 53 | 42 |
| Matched unqualified successful controls | 53 | 53 | 53 | 5 |
| One-update missing aliases | 7 | 0 | 0 | 0 |
| Matched alias/null peers | 57 | 0 | 0 | 0 |
| Weak V3-only rows | 3 | 0 | 0 | 0 |

The held-out evidence distributions explain the clean separation in this
capture:

| group | median exact | median same-coordinate margin |
|---|---:|---:|
| Robust V3 drops | 0.1667 | 0.1436 |
| Standard-qualified controls | 0.2145 | 0.1935 |
| Matched unqualified successful controls | 0.1993 | 0.1751 |
| Matched alias/null peers | 0.0430 | 0.0217 |
| One-update missing aliases | 0.0522 | 0.0311 |

All 50 robust drops exceeded 0.05 in all four blocks.  The one new phase lock is
`stream-1/rx1` at 4.15 s.  Refining nominal epoch 303 to 302 changes phase RMS
from 0.561238 to 0.499125 against a 0.50 threshold.  It is a borderline,
in-sample research result and must not be promoted as new scientific lock
evidence.

The non-integral frame lattice must be handled exactly.  At 2.5 MS/s the period
is 3333.333... samples, so raw block-local epochs have deterministic 0, +/-1/3,
and +/-2/3 sample residues.  Consensus must compare each candidate to
`e0 + round(k * period) - block_start`, not cluster naively rounded modulo-frame
coordinates.  After block consensus, the small common base-epoch/CFO grid can
be re-scored jointly on the whole 75 ms window.

## Rate, reset, alias, and overlap tests

### CFO rate

The 50 hard rows have trajectory rates of roughly -3.55 to -2.22 kHz/s, only a
44--71 Hz change over 20 ms.  Optional quadratic rate dechirping changes their
median score by 0.000156, with maximum gain 0.00049, and does not change median
CFO dispersion.  Rate centering is sensible for longer blocks, but it is not
the missing-signal fix.

### Physical reset

Five representative missing windows were split into twelve sliding 20 ms
slices.  All 60/60 slices retained exact score above 0.1, capture-relative
epoch stayed within 1.67 samples, and CFO stayed within 150 Hz of the model.
The signal is not confined to the first 20 ms and does not reset inside these
windows.  Across a broader block search, no far-epoch basin with score at least
0.03 recurred in three blocks in any tested row.

### CFO alias

The seven one-update losses are ordinary representatives one OFDM alias away
from a same-time peer.  They should be canonicalized modulo
`1 / 4.4 us = 227,272.727273 Hz` upstream and not counted as independent
components or recovered tracks.

### Concurrent CFO family

The early `stream-1/rx1` interval has two non-alias Qin candidate families
separated by approximately 85 kHz.  Both independently pass protected
short-block evidence near scores 0.20--0.22.  This supports simultaneous Qin
modes, but it does not identify two satellites.  Only 10/57 V3 losses occur in
that overlap, so it is not the general failure cause.  A successor should carry
the two trajectory-conditioned components separately instead of widening one
local Gaussian state or forcing one winner.

## Calibration boundary

The current acquisition status is not a detection verdict.  On 64 deterministic
30-frame complex-Gaussian windows, the alignment stage returned `COMPLETE` in
42/64 cases (65.6%, Wilson 95% interval 53.4--76.1%).  Search-selected exact
scores were 0.02268--0.02949, so the default 0.02 floor rejected none; the sign
of the near-exchangeable control margin decided admission.  The downstream
fixed-epoch per-frame gate nevertheless rejected all 64, giving zero complete
V3 tracks and zero phase locks.

This does not mean V3 has a measured 65.6% end-to-end false-lock rate.  It means
`alignment COMPLETE` is only numerical admission.  Even 0/64 end-to-end events
only gives a one-sided 95% upper bound of 4.57% for this one synthetic geometry.
Showing a rate no larger than 0.001 with zero events requires at least 2,995
genuinely independent null units.  The repository does not currently contain
an authoritative labeled real-IQ signal-absence corpus, so a successor must
remain candidate-only until that calibration gap is closed.

## Recommended additive model

The Qin and Kassas workflows acquire a discrete delay/Doppler mode before local
continuous tracking.  The appropriate local observation model is a bounded
mixture:

\[
Y_{m,s,k}=\sum_{j=1}^{K} h_{j,m,k}q_{s,k}
\exp\{i2\pi(f_{0j}+\dot f_j t_m)t_s\}+\epsilon_{m,s,k},
\]

where epoch and CFO-alias class are discrete; CFO, rate, fractional timing, and
timing rate are local continuous states; frame/tone channel and carrier phase
are nuisance variables; and `K` is a bounded component count.

An additive research V4 should implement the following policy without changing
V3 or published contracts:

1. Accept a provenance-bound seed containing epoch, CFO, rate, uncertainties,
   trajectory/branch identity, and canonical CFO-alias identity.
2. Use a mixture prior: concentrated continuity mass near the nominal mode plus
   bounded diffuse mass for genuine reset/reacquisition.
3. Always evaluate the nominal proposal.  Use short-block predictive evidence
   before a blind global fallback, and retain alternatives rather than silently
   replacing a valid seeded trajectory with a different component.
4. Fit geometry on anchor/even symbols and validate on odd symbols.  Score all
   controls at each exact candidate's same nuisance coordinates and on the same
   absolute samples.  Include predeclared non-cyclic/wrong-edge controls for
   later search-wide calibration.
5. Rank passing candidates primarily by held-out exact evidence.  Report
   proposal origin, truncation, prior distance, all control scores, and block
   consistency.
6. Canonicalize +/-227.273 kHz aliases before component counting.  Preserve
   resolvable approximately 85 kHz modes as separate candidate components,
   without assigning satellite identity.
7. Expose separate decisions for numerical completion, pilot presence,
   code/epoch specificity, alias resolution, component uniqueness, tracker
   completion, and modulo-pi phase lock.  A globally searched roll may report
   `code_phase_ambiguous`; it must not report `no_signal`.
8. Reacquire independently at caller-qualified change points.  Do not widen a
   Gaussian timing covariance across a full-frame jump.

The change should be additive (`KnownPilotFrameAcquisitionResultV2` and
`PilotPntKalmanV4Result`, or equivalent).  V3 is exported and source-hash-bound
in existing replay artifacts, and its tests deliberately encode the present
rolled-family behavior.  Mutating V3 would silently redefine persisted
research evidence.

Before any Standard consideration, freeze the configuration, calibrate the
complete search on preregistered Gaussian/colored/impulsive/tone/wrong-edge and
real-IQ null units, retain a protected retro numerical canary, and evaluate at
least ten untouched same-release estimable dwells against the same-mask causal
20 ms line with complete control and truncation accounting.

## Evidence and scope

- [Full 537-window replay results](figures/2026_08_25_150802_v3_full_dwell/full-dwell-results.json)
- [Full-dwell coverage and method](2026_08_25_150802_v3_full_dwell.md)
- [Initial missing-signal diagnosis](2026_08_25_150802_v3_missing_signal_investigation.md)
- [V3 implementation review](2026_08_25_pnt_kalman_v3_comprehensive_review.md)
- [Additive implementation and validation plan](2026_08_25_pnt_kalman_v4_correction_plan.md)
- Qin et al., [*Pilots and Other Predictable Elements of the Starlink Ku-Band
  Downlink*](https://arxiv.org/abs/2602.02627), demodulation Eq. 21 onward.
- Kozhaya, Saroufim, and Kassas, [*Unveiling Starlink for
  PNT*](https://navi.ion.org/content/72/1/navi.685), acquisition/tracking
  discussion beginning on PDF page 17.

All replays were bounded and read-only.  No QNAP path, Standard artifact,
published contract, golden fixture, or RF collection was changed.  The
counterfactual thresholds are descriptive and were evaluated on the same
capture used to diagnose the defect; they are not false-alarm calibration.
