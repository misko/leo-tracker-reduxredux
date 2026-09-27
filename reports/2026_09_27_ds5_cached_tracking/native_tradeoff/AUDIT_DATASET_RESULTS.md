# Independent audit of the Stage B dataset assessment

This audit is read-only with respect to the frozen detector, adapter, inputs,
source locks, and results. It evaluates
`results.diagnostic.json` (SHA-256
`ab03caadaa5cdcf0b8617cc365b47168d8645e33e8d2678ada1580aba1ae03f0`)
against `source_lock.diagnostic.json` (SHA-256
`c52473f751ae9c1246bbbc51d2fc45de74a230e9fb2d0eb4152a22eeccd0ab99`).
The receipt is complete: 26 unique development cases, 52 receiver rows per
native method, stable hashes for all 60 locked files, and no validation or
holdout access.

## Independent consistency checks

Every native active result has a pair and every inactive result has no pair.
All active pairs use one receiver, have nonoverlapping probes at least 20 ms
apart, have margins at least 0.025, and differ by at most 8 kHz in tracking
CFO. Every reported truth association independently satisfies both-member
2 us timing, 8 kHz CFO, and at least two detector-profile-supported injected
frames. No receipt or lock invariant failed these checks.

The frozen adapter's scientific separation is sound for this corpus:

- Recorded-comparator agreement and injected physical truth are separate.
- Low-power injected pilots have report-only presence rather than a forced
  positive decision.
- Noise, tones, multitone controls, and the sequence dropout are constructed
  negatives per receiver.
- Baseline early-symbol support and native alternating early/late support are
  assessed separately. A late-only baseline mismatch is not reported as a
  general physical sensitivity miss.
- Pair association requires both observations to match the same trajectory;
  the nearest timing, CFO, and support errors remain visible on a miss.

## Stage B findings

The central counts independently reproduce the main report:

| Rate | Native truth-associated positives | Weak pilots inactive | Constructed true negatives | Native unassociated positives |
|---|---:|---:|---:|---:|
| 2.5 MS/s | 19 | 2 | 5 | 0 |
| 5 MS/s | 19 | 2 | 5 | 0 |
| Total | 38 | 4 | 10 | 0 |

Blind and tracked native modes have identical activity and associated identity
on all 52 receiver rows. The ten negatives comprise four noise receiver rows,
four tone/multitone receiver rows, and two sequence-dropout receiver rows.
The application and both native modes remained inactive on all ten.

The fixed ladder observationally brackets the decision transition:

| Rate | Native | Application full-pair inventory |
|---|---|---|
| 2.5 MS/s | -30/-24 dB inactive; -18 dB and above associated | -30/-24/-18 dB inactive; -12 dB and above associated |
| 5 MS/s | -30/-24 dB inactive; -18 dB and above associated | -30/-24 dB inactive; -18 dB and above associated |

This is a coarse bracket, not a calibrated threshold. Adjacent power levels
use different cases, CFOs, edges, and noise realizations, and there is only one
receiver realization per level and rate. The active native -18 dB pair margins
are already 0.152 or greater at 2.5 MS/s and 0.234 or greater at 5 MS/s, so the
set contains no native positive close to the 0.025 decision margin.

The partial-region controls explain both generic reference-identity losses.
At each rate the early-only receiver has truth-associated application and native
pairs. The late-only receiver has a truth-associated native pair, while the
application produces 8 pairs at 2.5 MS/s and 63 at 5 MS/s with zero associations
to the injected late-only trajectory under its early-symbol contract. Thus the
reported native receiver-level reference loss is a comparator-identity
mismatch on a native physical success. It is not a native false positive or a
physical miss. The application still has a truth-associated early-only result
on the other receiver, so these are not false application visit decisions.

Both full-pilot region/interference receivers associate successfully for both
native modes at both rates. Both multiple-hypothesis cases also produce valid
native pairs: RX0 selects `pilot-b`, while the application full inventory
contains pairs associated with both `pilot-a` and `pilot-b`. The native result
therefore establishes detection of one valid hypothesis, not enumeration or
preservation of both simultaneous signals.

Across the complete application inventories, 618 of 7,845 compatible pairs at
2.5 MS/s and 826 of 10,032 at 5 MS/s are not associated with injected truth.
These are alternative full-response candidate pairs, not 1,444 independent
application decisions. They should be reported as unassociated or mismatched
candidates. Calling each a false alarm would inflate the error count because
the public application decision is one visit-level result and most affected
receivers also contain many truth-associated pairs. The known-negative rows,
where a positive could be called a constructed false detection directly, have
zero pairs.

## Causal sequence result

Among the 16 causal-sequence receiver occurrences, tracked routing has six cold
calls, four guided accepts, and six guided failures followed by blind fallback.
Every pilot result associates with the correct current injected trajectory and
both dropout results remain inactive. Tracked and forced-blind decisions agree
on all 16 rows.

Sequence-only aggregate CPU improves from 70.226 to 53.166 ms at 2.5 MS/s
(1.321x) and from 153.420 to 110.795 ms at 5 MS/s (1.385x), or 1.364x across
both rates. The sequence validates fresh-sample guided acceptance, fallback on
dropout or trajectory change, and state clearing. Its four visits per rate are
too small to estimate field cache-hit coverage or long-run amortized speed.

## Assessment limits

The adapter tests cover fixed membership, split exclusion, hashes and geometry,
counter/key continuity, full reference-pair enumeration, one detector-specific
region case, low-SNR report-only policy, mixed dropout policy, recorded-unknown
semantics, and integer-first source mapping. `load_iq` verifies every file at
runtime, although the component test samples one file from each source cohort.

The truth adapter models the native early/late symbol schedule; the compact
decision output does not carry each frame's actual scored symbol range. The
association therefore validates against the frozen profile model rather than
an independently emitted per-frame native trace. The 2 us/8 kHz association
gate is deliberately much wider than the observed associated errors, which are
sub-sample in timing and below 402 Hz in CFO for the sequence and generally
below 154 Hz elsewhere. Finally, ten constructed negatives cannot measure a
rare field false-alarm probability, and the development set cannot replace the
unopened validation qualification.
