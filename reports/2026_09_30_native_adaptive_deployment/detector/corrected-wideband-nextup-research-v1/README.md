# Corrected wideband next-up research v1

This isolated experiment changes one hot call in the frozen corrected-wideband
source: positive, finite, normal binary64 interval contributions below
`DBL_MAX` advance one representable value by incrementing their copied
`uint64_t` representation. Zero, subnormal, maximum finite, infinity, NaN,
negative/nonpositive, unsupported-size, non-IEC-559, and mixed integer/float
word-order cases retain libc `nextafter`.

The fast path requires matching integer and floating word order. Both the host
and Cortex-A9 detector builds declare IEC-559 binary64 and matching little
endian word order under the detector's complete floating-point compiler flags.
`activation-check.txt` also shows the bit classification and increment in the
linked host DSO. The implementation uses `memcpy`, so it does not violate
aliasing rules.

`test_next_up_positive.c` compares result bits and all floating exception flags
with libc under nearest, downward, upward, and toward-zero rounding. It covers
positive and negative zero, subnormal/normal boundaries, adjacent powers,
maximum finite, infinities, quiet NaN, explicit positive and negative signaling
NaNs, pre-existing exception flags, and 250,000 deterministic finite/nonfinite
bit patterns. Normal and ASAN/UBSAN host tests and QEMU ARM each pass 250,160
checks.

The rebuilt host detector reproduces every visit-301 field after removing only
timing and RSS diagnostics. The independently bound corrected-32 harness also
passes 32 visits, 64 receiver windows, 512 retained candidates, all 318
rank-level native/current-server gates, and 88 passing gates. Its summary binds
detector SHA-256 `44237fcc0e3cbfaa8c8e0a9b4d3bec1e34f4bd3ddadbf87dc3177b88e375dba7`
and task digest `891288fe06418ec5b6143764fc55e64e4aaee8b4be4097a4ed429e3026f2ea3e`.
No golden or prior replay output was changed.

The candidate has no host performance claim: one diagnostic visit is too noisy
for that purpose. The physical ARM experiment should run the focused test and
then exactly one visit-301 candidate replay against the retained 55.300-second
control. Repeat timing only if that first A/B result is material.

Frozen ARM artifacts are under `artifacts/arm/`:

- `test-next-up-positive` SHA-256
  `ffbbf12bc39f6f073073ce74ce96915f60e11061b2dca9f7c1b99536930756dd`;
- `leo-native-adaptive-replay` SHA-256
  `f8783b06ad8df876e249ebc1ec741f67d8334b8f5e046ec088c63d0686f2a8b3`;
- `libleo-adaptive-detector.so` SHA-256
  `30c82b55c1847291246f62901ffec9cc589927813848643d063d244649826c3a`.

Physical ARM execution passes. The focused test reproduced all 250,160
result-bit and exception-flag checks in 0.076225249 seconds wall. Two serial
control/candidate visit-301 pairs preserved every non-timing row field and raw
numeric lexeme. Mean detector-call wall time fell from 55.290824823 to
50.286970763 seconds, a 9.05006% reduction. Unrelated serial CPU-only work ran
between the first control and first candidate; the repeated pair was
consecutive. `physical-comparison.json` binds the runs and this provenance.
The candidate remains about 419 times slower than the 120 ms dwell, so this is
not real-time qualification.

This is research only. Production source, installed applications, detector
capability flags, device state, and RF state are unchanged.
