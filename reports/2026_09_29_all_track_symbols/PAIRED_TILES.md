# Same-frame receiver agreement and known-state conditioning

The two receivers reproduce changing early-region observations. Small tile
shifts do not improve that recovery. Conditioning comparisons on the known
repeating-pattern state reveals substantial cross-frame agreement after symbol
7, with a much weaker association in the first six symbols. No new payload,
satellite ID, timing field, or verified plaintext is established.

## Same-frame test

Use the previously generated, independently calibrated 10 MS/s atlas caches:
S23 (DS7, upper edge, 42 qualified evaluation frames) and DS9-middle (lower
edge, 45 frames). Every included frame passes both receivers' held-pilot
coherence gate of 0.5. Cache SHA256 values are verified against the atlas
receipt. Source excerpt offsets and initial epoch estimates agree within half
a frame, supporting pairing equal frame numbers. This is a software timing
consistency check, not independent absolute time validation.

Tiles start at OFDM symbol 4 and span 8, 16, or 32 symbol times. Eight available
consecutive nonpilot carriers provide six comparison carriers plus margins:
upper 480–487 and lower 536–543. Search ±2 symbol times and ±1 carrier index,
fitting complex phase and the discrete shift only on alternating reference
symbols. Test on the intervening symbols in the same frame. Subtract the complex
mean and normalize within each comparison before correlation.

The unshifted baseline uses the existing pilot/template calibration without a
new tile-phase fit. A second baseline fits only phase on discovery symbols.
Every nonzero cyclic shift of the eligible RX1 frame sequence is a control, with
the entire fitting procedure repeated. These controls preserve per-coordinate
patterns, but are dependent descriptive comparisons, not independent trials.

| Visit | Tile length | Raw held correlation | Phase-only held correlation | Shifted held correlation | Mean raw mismatched correlation | Zero shift selected |
|---|---:|---:|---:|---:|---:|---:|
| S23 | 8 | 0.326 | 0.299 | 0.202 | −0.001 | 59.5% |
| S23 | 16 | 0.358 | 0.350 | 0.314 | 0.007 | 88.1% |
| S23 | 32 | 0.351 | 0.347 | 0.338 | 0.009 | 97.6% |
| DS9-middle | 8 | 0.512 | 0.504 | 0.477 | 0.079 | 93.3% |
| DS9-middle | 16 | 0.515 | 0.510 | 0.510 | 0.044 | 100% |
| DS9-middle | 32 | 0.517 | 0.515 | 0.515 | 0.037 | 100% |

Every raw matched mean exceeds the maximum cyclic-control mean. Searching
small shifts generally reduces held agreement, especially in shorter/noisier
tiles. The current coordinate alignment therefore provides a better starting
point than per-tile shift fitting in these two visits.

For the 32-symbol tile's held half, upper real-sign agreement is 67.56% over
4,032 decisions versus a 50.44% mismatched mean; lower agreement is 74.79% over
4,320 versus 52.78%. These use all six carriers without a confidence filter.
They are not directly comparable to earlier confidence-selected header-only
percentages. Both receivers' sign strings are saved, but agreement does not
establish transmitter bit accuracy or encryption status. Widths overlap and
their counts must not be summed as independent observations.

## Comparison conditional on the known repeating state

Select each frame's state using the existing receiver-checked repeat assay at
symbols 194–225, requiring its known-repeat-compatible label. Compare every
distinct eligible frame pair using all 28 shared nonpilot carriers. For each
pair average the real centered complex correlations RX0(i) versus RX1(j) and
RX0(j) versus RX1(i). No new shifts or phase rotations are fitted here.

There are 14 same-state and 847 different-state pairs in S23; 22 and 968 in
DS9-middle. The regions below are disjoint from the state-selection window.

| Region | S23 same / different state | DS9-middle same / different state |
|---|---:|---:|
| Symbols 2–7 | 0.138 / 0.122 | 0.159 / 0.115 |
| Symbols 8–33 | 0.145 / 0.021 | 0.153 / 0.018 |
| Symbols 34–129 | 0.257 / 0.047 | 0.320 / 0.066 |
| Symbols 130–193 | 0.335 / 0.067 | 0.382 / 0.080 |

![State-conditioned correlation](local/paired-tiles/state-comparison.png)

Descriptive controls shuffle state labels among eligible frames 199 times,
preserving state counts and treating shared pairs together. After symbol 7,
observed same-minus-different gains exceed the controls' 97.5th percentiles
in both visits. For symbols 2–7 the upper gain is within that range; the lower
gain is modestly above it. Frame exchangeability is not established, regions
were examined together, and no multiple-comparison or formal significance
claim is made. The selection window itself is also saved as a consistency check;
its agreement is not independent validation.

This supports a state-dependent component extending earlier than the tail
window. It does not reveal a new state field: the repeating family was already
known. The first six symbols are less explained by that state and remain the
better target for unknown-message analysis. Comparing arbitrary frames or visits
without conditioning on state can obscure the later structure.

## Limits and next step

These are two previously studied visits, not untouched validation recordings or
a satellite-identity experiment. S23 has a prior conditional association with
STARLINK-30257; the DS9 visit has no identity established here. All analysis uses
template-relative soft symbols. A displacement in that space is not a new raw-IQ
timing solution, and shared calibration/model errors remain possible.

Next, estimate the known-state contribution on disjoint late symbols and examine
receiver-correlated residuals near the early header. Any recovered extra bits
must survive that control and a separate visit before receiving field meanings.

## Reproduction

`paired_tiles.py` reads only existing caches. Run with NumPy and Matplotlib.
Ignored `local/paired-tiles/` contains source/method hashes, raw sign strings,
frame lists, pair scores, state labels, control results, and this figure.
The companion synthetic tests check split-symbol shift recovery and rejection
of fitted matches between independent noise streams. The complete folder's
18 tests and Ruff checks pass. No recording, download, commit, or deployment
was performed.
