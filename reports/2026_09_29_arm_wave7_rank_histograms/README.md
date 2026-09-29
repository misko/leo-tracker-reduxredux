# Wave7 exact radix histogram reuse

Wave6's proposal rank sort made three stable digit passes, counting each digit
again after the previous permutation. A permutation cannot change its digit
histogram. This prototype builds all three histograms in one input scan, then
executes the same stable 11/11/10-bit LSD scatters. It needs 20 KB of histogram
storage rather than reusing an 8 KB table. Scientific arithmetic is unchanged.

The second sealed variant also canonicalizes signed zero using integer bits
rather than a floating-point comparison. Its reference still uses the old key
function, so the owned test verifies equivalence rather than comparing the new
function against itself. Tests cover random finite IEEE bit patterns, positive
and negative values, signed zeros, subnormals, ties, flat and reversed inputs,
and all proposal FFT sizes. Host/sanitizer suites and both physical ARM units
pass. The input remains the finite-score workload of the existing ranker.

On the same four saved 2.5 MS/s ARM dwells:

| Variant | Mean outer CPU ms/dwell | Rank phase ms/dwell | Candidate parity |
|---|---:|---:|---|
| Wave6 combined control | 863.029 | 98.047 | Reference |
| One histogram scan | 840.302 | 74.527 | All 182 identical |
| Above plus integer-only keys | 831.795 | 68.267 | All 182 identical |

The second variant saves 3.62% of the outer CPU time on this small panel.
These are non-PGO builds; their savings must not be added to PGO results
without measuring a combined build. Both Host704 variants preserve all 86,439
emitted candidate objects in 15,488 windows; v2 is recorded in `host704-v2`,
and its ARM4 result is in `arm4-v2`.

`prepare.py` and `prepare_integer_keys.py` construct separate snapshots.
`build.py` and `build_v2.py` produce hash-bound host, sanitizer, and Cortex-A9
artifacts. All timing includes shared dwell preparation and every proposal and
search; file loading, initial workspace setup, JSON formatting, and radio
capture are excluded. This does not reach the additional 50% runtime goal.
