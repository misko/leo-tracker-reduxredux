# Wave 7 certified histogram rank

This exact prototype tries to avoid three complete radix sorts by deriving a
stable-rank interval for every feature score from a 4,096-bin ordered-float-key
histogram.  It adds the interval endpoints in the same FP32 feature order as
the exact combined score.  It accepts a top-four result only when interval
bounds force every local-maximum predicate, score/index tie decision, and
mapped-distance NMS exclusion.  Any ambiguity runs the existing exact
11/11/10-bit radix implementation.

The adversarial component test covers random finite scores, dense ties, signed
zero/flat inputs, wraparound peaks, index ties and NMS geometry.  Every accepted
result is compared with exact stable radix output; only 1/2,000 adversarial
arrays certified, which demonstrates that ambiguous cases fall back.

On Host704, 778/15,488 receiver-windows certified (5.02%) and 14,710 fell back.
All 86,439 candidate objects and all 15,488 windows are exactly identical to
the Wave 7 integer-key histogram control.  Mean host proposal rank time rose to
16.92 ms/dwell from the control's 7.66 ms rather than falling, because the
interval scan and conservative proof are paid before radix in 94.98% of
windows.  This is a bounded negative result.  No ARM timing was run and the
candidate should not advance to hardware.

V2 replaces fixed key buckets with per-feature linear bins over `[0,max]`.
Mapping uses a monotone double-precision scale, clamps the maximum into bin
4095, and refuses certification for negative, nonfinite, or invalid-scale
inputs.  Tests cover bin monotonicity across adjacent floats, subnormals and
linear-bin boundaries, plus explicit negative/NaN/infinity fallback.

Linear bins raise Host704 certification to 12,843/15,488 windows (82.92%), with
2,645 exact fallbacks.  All 86,439 candidates remain exactly identical.
Nevertheless, rank time is 13.69 ms/dwell versus 7.66 ms for the exact
integer-key histogram control, and fused time is 96.70 ms versus 82.24 ms.
The proof's interval construction and repeated peak/NMS scans cost more than
the radix scatters they usually replace.  Cortex-A9 FP64 bin scaling is also an
unfavorable target operation.  V2 therefore remains a negative host result and
was not run on ARM.

Rebuild with `python3 build.py`; receipts contain exact commands, source hashes,
unit output and binary hashes.
