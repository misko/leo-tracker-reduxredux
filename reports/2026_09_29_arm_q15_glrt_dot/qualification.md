# Q15 final-GLRT dot qualification

## Decision

Reject this implementation as a speed optimization for the PLUTO Cortex-A9. It preserves the aggregate host recovery result of the preferred final-reuse baseline, but the measured ARM search and GLRT stages are slower.

## Qualified scope

The candidate is `cohort_final_reuse_f2_rawcondition_arm` from the `arm-q15-glrt-dot-build/v1` receipt. The comparison uses proposal radius 2, proposal top 4, fine frame budget 2, raw conditioned selection, all original final-scoring frames and symbols, and the unchanged FP64 energy, spectra, ceiling, residual-bin, and final-score operations. Timings cover search only; proposal generation and capture are excluded.

Evidence:

- `reports/2026_09_29_arm_subsecond/host704-q15-final-radius2`: 704 dwells and 15,488 windows on the saved all-rate host cohort.
- `reports/2026_09_29_arm_subsecond/arm4-q15-final-radius2`: four dwells and 88 windows on PLUTO+ CPU0.
- Reference runs: the corresponding `host704-final-reuse-radius2` and `arm4-final-reuse-radius2` directories.
- Candidate build receipts: host `f6e83d344be228d20cc1ff22bf43030280e23f44cd3c3f9391c5c6b1824ebaae`; ARM `1b3c691003ac2ecd06b1aac6858d3f9b85b826c957cb65cd4a3516143329449b`.

## Scientific result

The 704-dwell standard-hit audit recovers 19,249 of 19,581 reference-positive hits (`0.9830447883152035`) and reports 21,555 unmatched native-positive hits. These aggregate values exactly match the preferred final-reuse reference audit. The candidate is not bit-identical: all 123,904 ordered candidate rows differ because Q15 matched-filter dots change scores and can change ordering, CFO, or selected candidates. Aggregate recovery parity therefore supports this measured cohort only; it is not an exact-science claim.

## Performance result

On PLUTO+ CPU0, mean search CPU time rises from `1280.099631 ms` to `1371.701184 ms`, an increase of `91.601553 ms` or `7.16%`. Mean GLRT CPU time rises from `302.294217 ms` to `415.1314845 ms`, an increase of `112.837268 ms` or `37.33%`. Cache activity is identical in the ARM comparison: 401 entries and 303 hits. The candidate misses both the speed objective and the subsecond search objective.

The host result does not reverse the ARM decision. Mean host total CPU falls from `83.651417 ms` to `80.153573 ms`, while host GLRT time rises from `13.235159 ms` to `14.718715 ms`. The target hardware result is the controlling measurement.

## Code-based interpretation

The implementation quantizes both CFO-rotated exact and control templates for every executed distinct-GLRT CFO before processing frames. It then performs four widening integer products per complex sample, pairwise promotion to 64-bit lanes, horizontal accumulation, and conversion back to FP64 for the unchanged downstream FFT/scoring path. The stride-4 receiver layout also requires `vld4_s16` deinterleaving.

It is plausible that template quantization, deinterleaving, 64-bit accumulation on Cortex-A9, and conversion back to FP64 outweigh the replaced FP64 dot products. This is an inference from the code and the aggregate GLRT measurement. The instrumentation does not time quantization setup and the packed dot loop separately, so no individual operation is identified as the measured bottleneck.

The component qualification remains valid independently of the performance rejection: host and sanitizer tests cover all rates, stride-2 and stride-4 layouts, saturation, worst-case product accumulation, the analytical quantization-error bound, final-score tolerance, and residual-bin parity; ARM unit tests pass. No further Q15 final-dot variant is recommended from this result.
