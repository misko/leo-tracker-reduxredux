# Wave6 proposal arithmetic SIMD

This isolated Wave5 final v2 variant uses explicit four-bin NEON operations
for proposal FFT complex products and scaled squared magnitudes. Each lane
preserves its multiply/add sequence; no reductions or normalization sums are
reassociated. Cortex-A9 NEON subnormal behavior means full IEEE-range bitwise
equivalence is not claimed.

Host and sanitizer units cover zero, signed normal-range samples, all FFT
grid sizes, and vector tails. The owned unit also passes on the physical ARM.
Host704 preserves all 86,439 candidate entries exactly; this host uses the
scalar conditional path and does not substitute for target validation.
Physical ARM4 preserves every candidate and all 119/119 standard hits.
Its mean CPU time is 954.435 ms against 960.455 ms for Wave5 v2, only 0.63%
lower. This small difference is provisional and not included in the initial
exact combined prototype.

`prepare.py` constructs the isolated source snapshot; `build.py` builds host,
sanitizer, and Cortex-A9 artifacts. `arm-unit.json` and `arm4/` hold physical
evidence. The larger target corpus has not yet qualified this SIMD variant.
