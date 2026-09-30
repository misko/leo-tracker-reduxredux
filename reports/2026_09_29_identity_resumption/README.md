# Starlink identity and header structure: resumed controlled investigation

**Status:** the new app-level goal is active. This report records executed
experiments on existing DS7/DS8/DS9/DS10, rather than declaring semantic decoding
complete. No new RF was collected. No golden fixtures or production components
were changed. Generated data are ignored by Git.

## Main finding

There is a **short-term early-sign similarity lead**, but no validated satellite
identifier. Same-candidate visits on the same channel have a modest excess of
real-sign similarity after instrument, time, quality and T-state matching.
Almost all supporting comparisons are under two minutes apart. The evidence
does not separate satellite identity from continuity of a beam, service cell,
transmission episode or correlated association error. Cross-session matching
does not survive controls preserving session and trajectory structure.

Stable signs transfer within the three longer cached DS10 excerpts, but many
also match other candidate satellites. Apparent simple counter bits do not pass
familywise circular-shift controls. No SATAddr, NORAD ID, RFNum, time, beam ID,
position or verified message bytes were recovered.

## Ranked approaches and what was executed

The initial ranking, exclusions and later coverage-driven amendments are in
[PLAN.md](PLAN.md). All six justified work packages were pursued:

| Rank | Approach | Outcome |
|---|---|---|
| 1 | Frame-disjoint early-feature transfer across candidate identities | Short-term sign lead; insufficient evidence of unique satellite identity |
| 2 | Relative-phase features insensitive to common phase/polarity | No robust cross-session identity evidence |
| 3 | Discovery-stable signs, receiver consensus and specificity to a candidate | Stability observed; specificity not established |
| 4 | Physical-frame-index counter harmonics | No familywise-supported counter candidate |
| 5 | T-state, channel, receiver/rate, quality, time, CFO and episode confounds | Essential: session/trajectory controls remove apparent long-term evidence |
| 6 | Firmware and literature constraints | Constrain interpretation; no verified OFDM-to-message mapping supplied |

Previously failed unconstrained CRC, byte-offset, convolutional-code, parity and
alignment scans were not repeated. These new tests add cross-frame transfer,
explicit nuisance matching, phase-invariant features, identity-specificity tests
and grouped null controls to the earlier descriptive correlations.

## Corpus and identity authority

The frozen qualified analysis set supplies 1,394 track entries. After removing
one duplicate visit/RX entry by pilot quality, 1,393 remain: DS7 242, DS8 154,
DS9 342, DS10 655. These are the existing >=5 MS/s, >3-second track-selected
caches; they do not represent all recordings or continuous long captures.
There are 315 candidate-labelled entries, including only 26 in the strongest
`control_supported_candidate` tier. None is an identity read from RF.

Each track cache contains four recovered frames with two reserved evaluation
frames. The earlier evaluation frame supplies feature-normalization statistics;
the later frame supplies a separate observation. Population normalization uses
no identity labels. Pair scores symmetrize first-frame/second-frame transfer.
Source NPZ SHA-256 values are verified against the existing metadata before use.

Four common nonpilot carriers per edge give comparable coordinates across rates:
upper 486/487/496/497, lower 526/527/536/537. Only symbols 2–7 enter identity
features: 24 complex samples per observation, or 24 real signs. This small
intersection sacrifices information to avoid comparing different spectral
coverage. Pilots and the late T-code region are excluded from these features.

The four feature families are absolute unit phase, within-symbol adjacent-carrier
phase products, between-symbol phase products (3→4 and 5→6), and real signs.
Relative products cancel a common phase rotation/polarity, but not arbitrary
frequency-dependent channel errors. No per-pair alignment or phase search occurs.
Instrument-stratum centering/scaling is learned on first-frame observations only.
Scores are cosine similarities after normalization, not percentages of equal bits.

All observations were inspected in prior research. These fits use computational
holdouts; this is exploratory analysis, not pristine prospective confirmation.

## Between-candidate and revisit comparisons

Exact matching requires common edge, channel, receiver and sample rate, pilot
coherence difference <=0.05, and controls in the same separation bin, same/different
session category and known-tail-state overlap category. Pilot coherence is a
quality proxy, not a calibrated SNR measurement. T-state overlap is derived from
accepted tail words, not a claim that entire frames have identical state.

The strict design has 847 pairs: 3 same-candidate and 844 different-candidate.
Only one same-candidate pair has a different-candidate control in its stratum.
There is no strict cross-session/channel positive pair. This is a coverage limit,
not evidence that no identity exists.

A separate mixed-instrument sensitivity matches receiver/rate **pairs**, exact
channel pairs and the other strata, with pilot gap <=0.1. It gives 6,743 same-channel
pairs (68 same-candidate, 6,675 different-candidate), with 30 matched positive
pairs. Cross-session, different-channel comparisons give 7 matched positive
pairs and 15,942 negative pairs. All seven positives involve just three candidate
IDs: 63779 (four pairs), 63854 (two), 63791 (one). They are not seven independent
satellite confirmations. Strong-tier-only analyses have no matched positive
comparison and must abstain.

![Feature effects](local/identity-effects.png)

| Design | Matched positive pairs | Absolute phase excess | Within-symbol phase excess | Between-symbol phase excess | Real-sign excess |
|---|---:|---:|---:|---:|---:|
| Strict same instrument/channel | 1 | −0.018 | +0.180 | −0.119 | −0.112 |
| Mixed instruments, same channel | 30 | +0.046 | +0.018 | −0.002 | **+0.103** |
| Different sessions/channels | 7 | +0.062 | +0.104 | +0.099 | +0.037 |

Excess means same-candidate score minus the mean matched different-candidate
score, averaged over positive pairs. Overlapping pairs remain dependent.

### Controls change the interpretation

499 seeded label permutations first preserve instrument strata. A maximum over
four feature families and Bonferroni over eight scope/tier comparisons accounts
for the primary search family. A stronger permutation also preserves sessions.
An additional whole-trajectory permutation renames candidate IDs consistently
across all their visits/receivers within each session. This last control preserves
episode continuity and has little power for within-session identity equality.
Its purpose is to test whether cross-session names add information beyond episodes.

The same-channel real-sign excess has session-preserving family-adjusted
exploratory p=0.048, but trajectory-preserving maximum-statistic p=0.356 even
before the additional scope correction. The cross-session/channel feature
advantages lose support under session-preserving and trajectory-preserving
controls. Instrument-only shuffles had made them appear compelling; they broke
the session structure and are not sufficient evidence.

The short-term sign effect remains +0.100 after requiring >=15-second separation,
but only one matched positive pair remains at >=120 seconds (also >=2 hours).
Only one of the 30 matched positives crosses sessions. Excluding symbol 2 gives
+0.119; adding coarse CFO-difference strata gives +0.102. Leaving one candidate
out gives +0.087 to +0.119. These descriptive checks make a single universal
symbol, a single candidate or coarse CFO difference less persuasive explanations,
but do not isolate satellite identity from beam/episode state or receiver effects.
They were follow-ups to the lead, not new prospective significance tests.

The per-pair lookup, including IDs, separations and feature scores, is exported
as [matched-revisits.csv](local/matched-revisits.csv).

## Within a visit: stable signs and counter hypotheses

The existing longer paired excerpts are DS10-F010 visits 1085, 1150 and 1162,
each 120 ms with 89 recovered frames per receiver. They have 45/18/21 jointly
qualified frames. These are longer than the four-frame census excerpts, but
**not multi-second continuous observations**. Candidate 63400 is conditional.

Early RX0 selects coordinates with >=90% identical signs. The consensus version
also requires early RX1 stability and the same majority sign. Later RX1 tests
these frozen values. Consensus retains 12/7/9 coordinates; within-visit held-out
agreement is 88.4/95.2/84.8%. The first mask contains nine symbol-2 positions.

![Stable transfer](local/stable-transfer.png)

Cross-visit agreement alone is not specificity. `stable_specificity.py` applies
these frozen masks to second-frame observations in the wider candidate-labelled
corpus, with at least three shared coordinates and exact coordinate footprints
in controls. Coverage ranges from 119 to 181 candidate-labelled observations
depending on mask and symbol-2 exclusion. Many different-candidate controls
score 70–88%; same-candidate targets do not consistently exceed them. Strict
same-session/time controls are generally absent or singletons. Removing symbol 2
does not yield a consistent candidate-specific pattern. No stable address bits
have been established.

For counters, each discovery-variable early coordinate fits power-of-two square
waves with periods 2/4/8/16/32/64 **physical frames**, phase and inversion selected
on early RX0. Later RX1 evaluates each chosen rule against a frozen constant
predictor. Controls circularly shift the whole RX1 frame sequence and take the
maximum over every searched coordinate. All three visit-level results have
across-visit corrected p=1.0. Large-looking individual accuracies are therefore
not counter evidence. These excerpts cannot test 1-second or 15-second header
evolution, arbitrary scrambling or a general counter serialization.

## Literature and firmware interpretation

The public pilot study reports common edge pilots and extensive predictable
tessellation. It supports treating these as nuisance structure rather than unique
satellite IDs. It does not provide the missing verified header field mapping.
[Qin et al., 2026](https://www.nature.com/articles/s44459-026-00075-6).

The timing study reports 15-second fixed beam-assignment intervals and timing
behavior that can differ among beams of one satellite. Thus a repeatable short
signal episode need not be a stable satellite identifier. Its observations
motivate the separation sensitivity, but we have not established GPS-aligned
assignment boundaries in these recordings.
[Humphreys et al., Timing Properties](https://arxiv.org/html/2501.05302v1).

The existing [firmware timing/identity investigation](../../docs/research/starlink-literature/firmware-timing-identity.md)
identifies software SYSINFO SATAddr, channel, RFNum and ephemeris fields, plus
PNT flags/variance. The [header investigation](../../docs/research/starlink-literature/firmware-header-analysis.md)
associates a two-bit software prefix with PDU-sequence handling. These are
software-level constraints. SATAddr has no established mapping to NORAD IDs,
and the bit-reader's order does not establish OFDM serialization. Without the
PHY coding/interleaving/scrambling bridge, assigning those names to recovered
coordinates would exceed the evidence. These constraints informed which
hypotheses were tested and which blind scans were excluded.

## Reproduction and remaining work

Run from the repository root in an environment with NumPy, Matplotlib and pytest:

```sh
python reports/2026_09_29_identity_resumption/corpus_identity.py
python reports/2026_09_29_identity_resumption/within_visit.py
python reports/2026_09_29_identity_resumption/stable_specificity.py
python reports/2026_09_29_identity_resumption/illustrate.py
python -m pytest -q reports/2026_09_29_identity_resumption/test_experiments.py
```

The separately bounded `paired_extension.py` reuses the unchanged stored-IQ
recovery script for two preselected, stronger-tier different candidates. It
requires the documented read-only storage/runtime privileges, imposes a
240-second timeout per visit, reuses completed outputs, and never starts RF.
Its selection/receipts are in `local/paired-extension.json`; it does not alter
the frozen dataset membership or prior summaries. Both replays completed:

| Existing visit | Conditional candidate | Selection tier | Jointly qualified frames |
|---|---:|---|---:|
| DS10-F004-v535 | 58097 | control-supported | 2 |
| DS10-F009-v238 | 67055 | control-supported | 1 |

These were the top two lower-edge 10 MS/s stronger-tier candidates with distinct
IDs other than 63400, selected on the original single-receiver pilot metric.
The longer paired replay did not produce enough jointly qualified frames for
the >=12-frame header assay. This is a coverage/quality failure, not negative
evidence about their identities. It also shows why strong single-receiver
selection cannot guarantee a useful paired long excerpt. The existing corpus
has six same-visit dual-RX qualified track pairs, but none carries an accepted
candidate label in that table, so those cannot close the identity-validation gap.

The three passing synthetic tests cover phase/polarity invariance, rejecting unmatched identity
contrasts, and correct counter handling across missing physical frames. Tests do
not validate orbit labels or message meaning. Outputs, figures, feature matrices
and lookup tables remain under ignored `local/`; scripts and prose are reviewable.

The highest-value remaining lead is separating short-term beam/episode similarity
from independent satellite revisits with validated receiver consensus and enough
matched controls. The present results do not justify publishing an identity decoder
or interpreting candidate signs as a satellite address. The active goal remains
open; the original scope has not been replaced with passing statistical tests.
