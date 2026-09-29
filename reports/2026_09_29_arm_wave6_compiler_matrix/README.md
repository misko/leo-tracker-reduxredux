# Wave 6 Cortex-A9 compiler matrix

This bounded matrix uses the byte-identical sealed Wave 5 final v2 source and
changes one semantics-preserving compiler option per optimized build:

* `ipa-pta` adds `-fipa-pta`, enabling interprocedural points-to analysis for
  the existing LTO build.  It may improve alias information in the fused search
  code, at increased link time and memory use.
* `align32` adds `-falign-functions=32`.  Cortex-A9 fetches may benefit when a
  hot function avoids an alignment boundary, but padding can increase text and
  instruction-cache pressure.

Both retain `-fno-fast-math`, the existing finite-complex option, all source
arithmetic, `-mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard`, and final FP64 GLRT.
The sanitizer builds intentionally omit the optimization-under-test and check
the same source for memory and undefined behavior.  Host and ARM optimized
builds contain the recorded option.  These are hardware timing candidates,
not performance claims.

Prior results bound the alternatives.  Strict LTO is already in Wave 5.  A
previous `-funroll-loops` ARM experiment changed mean runtime by only 0.19%
while growing text 1.54%.  Proposal `FFTW_MEASURE` took about 1.06 seconds on
ARM versus about 0.729 seconds for `FFTW_ESTIMATE`; changing the planner is
therefore rejected here.  Fine FFT plans are created per window, so MEASURE
would also put planning work on the timed path without a persistent plan cache.

The installed Linaro GCC 7.3.1 supports `-fprofile-generate`,
`-fprofile-dir`, `-fprofile-use`, and `-fprofile-correction`.  Valid PGO needs
an instrumented ARM build, representative Cortex-A9 training runs, collection
of its `.gcda` files, then a same-source/same-compiler use build.  Timing and
candidate parity must use a disjoint held-out panel and audit coverage-mismatch
warnings.  Host profiles are not transferable across compiler target and
architecture.  Because this task forbids ARM execution, no truthful PGO use
binary can be sealed here.

Rebuild with `python3 build.py`.  ARM binaries use:

```
builds/VARIANT/arm/fused_rate_coarse_gate_arm RATE EXACT CONTROL INPUT_CI16
```

All host and sanitizer component suites passed.  Each host variant was also
compared with the sealed Wave 5 v2 cohort across 704 dwells, 15,488 windows,
and 86,439 candidate entries; both produced zero changed candidates and zero
changed windows.  Host timing is not used to predict Cortex-A9 timing.

The ARM `ipa-pta` text is 1,506,339 bytes, 216 bytes smaller than the sealed
baseline; its binary SHA-256 is
`b969394dd544c73b13a2291641bc8569ca13b9dbd815c2960c3fa86e1401333c`.
The ARM `align32` text is 1,506,755 bytes, 200 bytes larger than baseline; its
binary SHA-256 is
`434faec8e66beefb94c391c112e8aa807fa588b0c93c9c87047363ce6182cd5b`.
The small text deltas prove the target code changed, while also making a large
runtime gain unlikely.  ARM execution remains the required decision gate.
