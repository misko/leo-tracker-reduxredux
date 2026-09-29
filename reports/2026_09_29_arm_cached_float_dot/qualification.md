# Cached FP32 final-dot qualification

## Decision

Reject the cached FP32 final-GLRT dot as a PLUTO Cortex-A9 speed optimization. The sealed NEON-moments-v2 candidate preserves aggregate recovery on the saved host cohort but increases both target search time and GLRT time.

## Sealed evidence used for the decision

- Candidate build receipts: host `24cb5923368c1f8e54eb7d96493a59a7f38f521ce867e42443be747aac9d4f5c`; ARM `c00a8f488919b7e759c0ebafca284a5dcf9f8e85b1b526c4f497a2ab217ab67b`.
- Host science: `host704-v2`, 704 dwells and 15,488 windows, compared with `arm_subsecond/host704-neon-moments-v2-radius2`.
- ARM timing: `arm4`, four dwells and 88 windows on PLUTO+ CPU0, compared with `arm_subsecond/arm4-neon-moments-v2-radius2`.
- ARM component execution: `arm-units-v2.json`, with all four unit binaries passing.
- Configuration: proposal radius 2, proposal top 4, fine frame budget 2, raw conditioned selection, all 16 final-scoring frames, 64 symbols, and both exact/control references. Timings cover search only.

The earlier `host704` receipt `b7197221…` and `arm-units.json` receipt `04e540da…` belong to the pre-rebase final-reuse build. Their exact 56-file source snapshot has been recovered under `historical/old-b719-sources/` and verified in `historical/old-b719-source-verification.json`. They are retained for provenance and are not used to attribute the final NEON-moments-v2 timing result.

## Scientific result

The sealed `host704-v2` audit recovers 19,249 of 19,581 reference-positive hits (`0.9830447883152035`) and reports 21,555 unmatched native-positive hits. These aggregate values match the NEON-moments-v2 reference. Candidate results are not bit-identical: 123,857 ordered candidate rows differ, so this is measured cohort recovery parity rather than an exact-science result.

## Performance result

Mean ARM search CPU time rises from `1228.2892185 ms` to `1276.8611895 ms`, an increase of `48.571971 ms` or `3.95%`. Mean GLRT CPU time rises from `303.7583355 ms` to `354.5445810 ms`, an increase of `50.786246 ms` or `16.72%`. Both runs report 401 GLRT-cache entries and 303 hits. The candidate therefore misses the speed objective and remains above one second for search alone.

The implementation successfully removes the earlier FP32 scorer's per-call allocation, full-length conversion, and unused-template conversion. The target result still shows that FP32 template generation, stride-4 deinterleaving and CI16-to-FP32 conversion, FP32 partial accumulation, and reduction back into the FP64 downstream path do not outperform the baseline FP64 dot implementation as a whole. The timing instrumentation does not separate those operations, so assigning the slowdown to any one of them would be inference rather than measurement.

No further cached FP32 final-dot variant is recommended from this result.
