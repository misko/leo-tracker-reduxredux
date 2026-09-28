# Post-SSS recovery: calibrated soft symbols, hard decisions unresolved

**Subsequent result:** [DATA_RECOVERY.md](DATA_RECOVERY.md) records successful
repetition-assisted raw-bit recovery from stronger visits. The limitations
below describe this earlier visit and individual header decisions.

## Motivation

Recover the 6–9 OFDM symbols immediately after SSS in DS7 at 10 MS/s.
This continues the initial negative header assay in [README.md](README.md).

## Problem

The initial demodulator divided each subcarrier by one noisy SSS observation.
It also transferred a fixed frame cadence from cached pilot acquisition. Those
assumptions obscured real header structure. A subsequent constant phase-slope
model failed when extended from 20 ms to a whole 120 ms visit.

## Solution

**Eight consecutive post-SSS symbols now have reproducible template evidence
and calibrated complex soft outputs on 24 captured non-pilot subcarriers.
Reliable hard symbol/bit recovery remains incomplete.** This supersedes the
initial report's negative finding for these windows, but does not establish
decoded metadata or error-free header contents.

Source: DS7 `scan-fw-a40658642d9ade6a`, visit 2022, both receivers, 10 MS/s,
120 ms of existing IQ. The verified public reader exported the same sealed
visit used in the first investigation; there was no new RF collection.
The analysis covers 89 complete frames and symbols **2–9**, with SSS numbered
1. Each frame contributes 24 × 8 = 192 complex carrier symbols. Subcarrier
indices are 476–487 and 496–507; the known pilots at 488–495 are excluded.
These are the captured in-band portions, not all 1024 subcarriers of each OFDM
symbol or a reconstructed 240 MHz channel.

The main improvement was a pilot-measured timing-rate mismatch of **3.527 ppm
on RX0 and 3.566 ppm on RX1**. This is an effective received timing mismatch;
it is not a measurement isolating the receiver clock from propagation or
transmitter effects. Correcting frame epochs removed more than 99.8% of the
measured phase-slope drift. The final correction is about four native samples
over the visit, enough to matter for a 133 ns cyclic prefix.

| Evidence | RX0 | RX1 | Combined |
|---|---:|---:|---:|
| Even-frame fixed-axis template statistic | 0.1476 | 0.1170 | 0.2305 |
| Largest of 1,000 wrong-template controls, even frames | 0.0516 | 0.0333 | 0.0466 |
| Odd-frame fixed-axis template statistic | 0.1477 | 0.1043 | 0.2270 |
| Largest of 1,000 wrong-template controls, odd frames | 0.0441 | 0.0327 | 0.0640 |

The desired template exceeds all controls in both receiver streams and both
frame splits. The test does not fit header phase to make the desired template
match. Combined frame-bootstrap 95% intervals are approximately 0.216–0.246
and 0.213–0.240. These exploratory control comparisons are not calibrated
false-alarm probabilities; the splits share pilot/SSS-only nuisance estimates.

The serious remaining limitation is **64.7% agreement between independent
receiver sign decisions** on these carrier symbols. This is consistent with
substantial noise and cannot support error-free decoded bytes. Receiver errors
may also be correlated. The exported signs are provisional, not verified bits.

## Method

1. Verify source manifest binding and excerpt digests. Use cached pilot timing
   and CFO only as acquisition anchors.
2. Demodulate each frame's known pilots. Estimate residual phase rate and
   spectral phase slope using pilot symbols 22–301. Reserve pilot symbols
   2–21 for validation, leaving all requested header samples out of the fit.
3. Fit the spectral phase-slope drift versus frame number and convert it to
   fractional native-sample epoch corrections. Demodulate again at those
   corrected epochs; fit the small residual trend using pilots.
4. Correct phase and channel response using those pilots. Estimate a smooth
   complex-linear response across the 24 non-pilot bins from SSS observations
   in other frames. Each target frame's own SSS is excluded from its pooled
   channel estimate; post-SSS unknown data never enters that estimate.
5. Retain the corrected complex observations and remove the published template
   separately to expose its BPSK deviations. Combine the two calibrated
   receiver streams with weights based on reserved-pilot residual variance.
   The near-real cross-receiver correlation supports their phase alignment;
   no header-based phase rotation or sign alignment is applied.
6. Compare the fixed SSS-referenced BPSK axis against 1,000 wrong templates
   using independent random temporal shifts per subcarrier, seed 20260927.
   Report even/odd frame groups separately and bootstrap whole frames.

Four later 10 MS/s sessions were also inspected, at chronological indices
4, 9, 14, and 18. Two supplied qualifying upper-edge candidates, contributing
four additional 20 ms excerpts. Earlier pilot-aided tests of those excerpts
also showed early-symbol template excess, including six prominent post-SSS
symbols in visit 701 of `scan-fw-90329b2d033fac49`. They are exploratory support,
not included in the table above or substituted for the verified dual-receiver
result. The initial expanded outputs predate the final drift correction and
are kept separately under `local/expanded/`.

## Artifacts and verification

All data below are git-ignored under `local/dual/`:

- `post-sss-eight-symbols.npz`: `rx0`, `rx1`, and `combined` complex arrays of
  shape **(89, 8, 24)**, `template_removed`, provisional ±1 signs, OFDM symbol
  numbers, subcarrier indices, corrected frame epochs, and combination weights.
- `post-sss-eight-symbols.csv`: 17,088 rows of combined I/Q, template-removed
  I/Q, and provisional signs, indexed by frame, OFDM symbol, and subcarrier.
- `inventory.json`: sealed source provenance and hashes of the two original
  120 ms IQ excerpts. Epochs refer to samples in these excerpts.
- `recovery.json`: pilot validation, timing corrections, residual drift, and
  per-symbol statistics. `recovery-soft-symbols.npz` also preserves diagnostic
  SSS and pilot-calibrated outputs.
- `validation.json` and `recovered-eight-symbols.png`: split-frame validation
  and the visible eight-symbol signature.
- `RECOVERY-SHA256SUMS`: source and result fingerprints.

`recover.py --out reports/2026_09_27_ds7_header/local/dual` runs the recovery;
`validate_recovery.py` exports and validates the eight requested symbols. Use
the NumPy/SciPy/Matplotlib environment shown in the parent report. Source export
uses `export_dual.py` with the pinned DS7 reader release and a 60-second bound.
The pure numerical work uses one BLAS thread and existing local excerpts.

Four synthetic tests pass: restricted-band OFDM/header discrimination, noise
null, exact recovery of withheld synthetic symbols with a known channel/CFO,
and invariance of calibration when all reserved header samples are changed.
No production component or golden fixture was changed.

Remaining work is to improve or bound the hard-decision error rate. The soft
symbol artifact and repeatable structural finding are real progress toward
the requested recovery; they are not a substitute for verified decoded header
symbols, FEC/CRC validation, or satellite/time/orbit fields.
