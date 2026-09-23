# Relaxed adaptive coherence: frozen random 30-visit review

The user narrowed review to a seeded random subset after a bounded 301-visit
replay had already completed. This report reads only the 30 IDs frozen in
[`random-30-selection.json`](figures/2026_09_23_relaxed_adaptive_coherence/random-30-selection.json):
`random.Random(20260923).sample(sorted(301 metadata-eligible IDs), 30)`.
The selection code did not read phase results, but this is a retrospective
review subset chosen after the broad computation and is not a new prospective
holdout. The pre-existing five strict two-source visits are reported separately
as references and do not overlap the random 30. No additional IQ was read for
this review.

The random 30 has 16 channel-4, 11 channel-2, and three channel-3 dwells. Of
them, 25 already had one strict archived phase-blind RX pair and five are newly
admitted by the weaker forced-template criterion. All 30 obtained 64 common
training-only raw-offset windows and produced a finite raw RX1-minus-RX0 offset
(-677.382 to -676.333 kHz; median -676.732 kHz). This is a selected FFT branch,
not an independently resolved 750 Hz or 227.27 kHz alias.

Each arm forces a native candidate's epoch/template into the opposite receiver,
then estimates one shared raw receiver offset and per-receiver pilot residuals
using seeded training frames only. A source passes the pilot-support screen
when both receivers' held exact/rolled and exact/wrong-timing power ratios
exceed two. The short-phase screen additionally requires four valid 20 ms
blocks and median block resultant at least 0.8. These are fixed diagnostic
screens, not identity or association decisions.

| Cohort | Arm | Anchors | Pilot supported | Short-phase screen |
|---|---:|---:|---:|---:|
| Frozen random 30 | RX0 anchored | 35 | 32 | 21 |
| Frozen random 30 | RX1 anchored | 37 | 36 | 30 |
| Five strict references | RX0 anchored | 10 | 10 | 10 |
| Five strict references | RX1 anchored | 10 | 10 | 10 |

For the random 30, median held 20 ms resultant is 0.868 in the RX0 arm and
0.921 in the RX1 arm. The median exact/rolled ratios are 23.7 and 15.6 for RX0
and RX1 measurements in the RX0 arm, versus 29.2 and 35.0 in the reciprocal
arm. The corresponding exact/wrong-timing medians are 21.6/16.6 and 26.1/29.7.
Thus forced opposite-receiver template coherence is often measurable under the
fixed model, especially in the RX1-native direction. Its directional asymmetry
is evidence that this is a conditional measurement, not a calibrated common
phase observable.

Two-source DD is a separate and much scarcer measurement. It uses only pairs
of distinct anchors within the same arm, nearest frames, and both-held groups;
it is calculated before separate source-product rate removal. It must not be
inferred from the source-screen counts.

| Cohort | Arm | DD pairs | Both sources pilot supported | DD screen | Median DD R | Median wrong-time R |
|---|---:|---:|---:|---:|---:|---:|
| Frozen random 30 | RX0 anchored | 5 | 2 | 0 | 0.581 | 0.125 |
| Frozen random 30 | RX1 anchored | 7 | 6 | 4 | 0.821 | 0.218 |
| Five strict references | RX0 anchored | 5 | 5 | 5 | 0.953 | 0.190 |
| Five strict references | RX1 anchored | 5 | 5 | 5 | 0.969 | 0.180 |

All random-subset DD pairs had a higher resultant than their fixed
half-sequence wrong-time control, but there are only five and seven pairs in
the two arms. The RX1-arm four-screen result and RX0-arm zero-screen result
cannot be turned into a winner selection or a physical conclusion. They show
that forced-template response can preserve a conditional within-dwell
two-anchor phase pattern in some cases; they do not establish that the anchors
are two satellites, that their inter-receiver phase is calibrated, or that the
pattern is geometric motion. The five reference visits are prior development
evidence and their strong values are not an independent replication.

As a post-fit guard against a forced-template artifact, every one of the 12
random-subset DD pairs and all ten reference arm-pairs was checked using each
source's arm-mapped native CFO plus its already saved train-only within-frame
residual. No pair became closer than 5 kHz modulo the 227.27 kHz symbol alias
in either receiver. The random-pair minima are 24.890 kHz in RX0 and 24.965
kHz in RX1 (an unscreened pair); the four RX1 screened pairs remain separated
by 33.869–45.934 kHz in both receivers. The reference-pair minima are 33.147
kHz and 33.121 kHz. This rules out the narrow explanation that the reported DD
screen simply relocked both anchors to the same effective carrier. It does not
resolve waveform/source identity, pilot aliases, or the receiver phase gauge.

The weaker criterion is useful for a bounded **coherence availability** map:
retain every result, compare both native-anchor directions, and label failure
or weak support. It is unsuitable as a relaxed source-association or position
gate until an experiment has independent source labels and a calibration that
resolves the receiver/alias gauge. The full 301-visit replay completed before
the user narrowed scope; this report intentionally does not aggregate it.
