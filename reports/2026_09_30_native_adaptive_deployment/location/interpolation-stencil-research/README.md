# Exact interpolation-stencil scoring experiment

The baseline profile used the complete native E2 scoring fixture: 11,129
satellites, 64 tracks, 3,372 observations, two published locations and the
unchanged integer tau grid from -5 through +5 seconds. The optimized production
build scored both locations in 0.88 seconds with one worker and 0.56 seconds
with two workers on this host. Fixture parsing alone completed in less than
0.01 seconds.

The sampled optimized profile attributed 40.58% of CPU time to 39,693,390 calls
to `leo_orbit_interpolate`; scorer and interpolation together accounted for
98.6%. The unchanged conservative horizon gate rejected 678,797 of 712,256
satellite-track pairs at the first location and 677,868 at the second. The
remaining pairs still performed about 19.85 million interpolations per
location.

The research candidate computes a 72-byte stencil for each observation/tau
pair after the first eligible satellite for a track. The largest track in this
fixture needs 96 × 11 stencils, or 76,032 bytes per worker. It stores the exact
Hermite coefficients while retaining the state-load and floating-point
expression order. The generic interpolator remains the numerical oracle.

Eight final host runs per implementation were interleaved ABBA/BAAB. Control
median wall time was 927.064 ms and candidate median was 523.586 ms, a 1.771×
speedup. All 16 one-worker results, plus both two-worker results, had identical
SHA-256 `7b52641ee5961180615d980a2cd3d241e97df8bdd2a397225df3d4da41706216`.
The measured commands consumed 11.706 seconds in total, below the 60-second
profiling bound.

Host and ASAN/UBSAN component suites passed. A full sanitizer fixture comparison
also produced the same result digest. ARM EABI5 control and candidate binaries
were cross-built with identical production flags, and both research and
standard component tests passed under qemu-arm. Physical ARM timing is recorded
separately after root-owned execution; no hardware or radio was accessed while
creating this experiment.

The physical 96-knot orbit cache build remains a separate measured 9.9-second
stage and is not included in these prebuilt-fixture score timings. The latest
57.12-second application snapshot-to-result duration minus 29.84 seconds of
tracking and one 9.9-second orbit build leaves roughly 17.38 seconds for scoring
and application work, but that subtraction is an inferred residual rather than
an isolated ARM score measurement.

The initial receipt is research evidence only. At that point production
`score.cpp`, its C ABI, scientific policy and fixtures were unchanged. The
subsequent production integration retained exact full-fixture output and added
generic-interpolator fallback for allocation failure and over-limit scratch.

The subsequently integrated production implementation is bound by
`production-receipt.json`. The pre-integration generic scorer is preserved
verbatim as `native/adaptive/location/research/score_baseline_20260930.cpp`
(SHA-256 `5694b36379e50fd86971f0a4c88cf4925a6d14ebf3109bca37d9bc87eba1e17c`).
The research candidate now includes that frozen file, so rebuilding research
control/candidate binaries cannot silently consume the promoted scorer. This
changes the research wrapper source digest while leaving the frozen physical
receipt and its binaries as historical evidence.
