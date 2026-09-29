# Factor-five NEON fine-frequency FIR gate

This is a standalone component gate for the earlier scalar factor-five fine FFT
prototype.  It does not alter Wave 4 or run a cohort.  The candidate keeps the
full-frame 500 Hz grid (`rate/500` samples become one fifth as many FFT cells),
the 24-tap Hamming-windowed low-pass response, aligned band-center mixing, and
the existing magnitude correction for FIR response and factor-five amplitude.
An eventual integration must retain both endpoint frames and the requested
plus-or-minus 80 kHz score interval exactly as the scalar prototype did.

The NEON kernel calculates only every fifth FIR output.  It processes four
adjacent taps per vector and leaves the first wraparound outputs scalar.  Every
vector load is therefore inside the explicit `n`-sample input.  Nonmultiple and
29-sample partial inputs are included in the test specifically to prevent the
known full-frame overread pattern from reappearing.

The component test covers all four rates, zero input, full-scale alternating
input, impulses, an in-band tone pair, an out-of-band alias, response-corrected
magnitudes, and partial bounds.  Host and ASan/UBSan use the scalar fallback;
the ARM test compares the NEON result against the scalar kernel with a bounded
FP32 reassociation tolerance.  The ARM binary is cross-built only.

Run the target gates in this order:

```
builds/arm/test_decimated_fir_arm
builds/arm/bench_decimated_fir_arm
```

The benchmark prints JSON for each rate with 200 repetitions of the full FFT,
scalar FIR plus small FFT, and NEON FIR plus small FFT.  Setup and FFT planning
are outside the timers.  If NEON plus the small FFT does not beat the full FFT
on Cortex-A9, stop this experiment before integration or cohort work.  Host
SIMD performance is not evidence for the ARM decision.
