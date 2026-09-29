# Conditioned-moment NEON qualification

The `LEO_NEON_CONDITIONED_MOMENTS` build changes the regular-grid approximate
conditioned screen only. It evaluates four adjacent 100 Hz frequencies in
parallel and uses FP32 complex block accumulators. It retains all 16 frames,
all 41 frequency bins, and all fifth-order moments. The exact FP64 recheck and
final GLRT paths are unchanged.

The component comparison directly invokes both the original moment function
(FP64 total accumulation) and the new four-frequency path over four
deterministic weighted-input patterns at 2.5, 5, 7.5, and 10 MS/s. It measured
a maximum magnitude error of `0.000854492188` and a screen-normalized maximum
of `0.00126164407`, where normalization uses `max(abs(reference), 0.1)` to
avoid treating an approximately zero magnitude as a meaningful relative-error
denominator. The raw maximum relative value was `27.4401264`, occurring at a
near-zero reference magnitude; it is recorded rather than hidden by an
equality assertion. The enforced component bounds are absolute error at most
`0.001` and screen-normalized error at most `0.01`.

Host and ASan/UBSan builds passed both this component test and the existing
all-rate final-reuse cache/invariant test. The Cortex-A9 build is cross-built
only. Its disassembly contains `vld1.32`, `vmul.f32`, `vadd.f32`, and
`vsub.f32` instructions in the new loop, confirming the four-frequency path
was emitted as NEON FP32 code.

The ready ARM artifact is
`builds/arm/cohort_final_reuse_f2_rawcondition_arm`; its build receipt and the
host/sanitizer test outputs are in `build-manifest.json` and each target's
`build-receipt.json`.

## Physical ARM follow-up

The CPU0 saved-IQ physical panel preserved every candidate object from the v1
moment implementation and the full 704-dwell host audit preserved its standard
recovery and extra-positive counts. V1 measured 1.323542 s/dwell total with a
347.789 ms conditioned stage. V2's rate-precomputed powers and block-major
phase layout measured 1.228289 s/dwell total with a 256.259 ms conditioned
stage: 95.253 ms (7.20%) less total CPU and 91.530 ms (26.32%) less conditioned
CPU on that same small ARM panel. These remain stage timings, not an outer
fused dwell measurement.
