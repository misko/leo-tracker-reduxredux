# Wave 6 combined exact prototype

Root-owned physical ARM qualification is complete. On the same 152 saved
2.5 MS/s dwells, mean outer CPU time is **814.874 ms**, versus Wave5's
915.434 ms (10.98% lower). All 6,030 candidate objects in 3,344 overlapping
receiver/windows are identical; **4,506/4,573 standard hits** remain recovered.
Nearest-rank p95 is 1,129.109 ms. See `arm152/` for the immutable receipt,
scientific audit, and distribution. This still exceeds the 120 ms real-time
budget and excludes capture. The smaller matched ARM4 result is 863.029 ms
versus 960.455 ms, retaining 119/119 standard hits.

This isolated build begins with the sealed Wave6 dwell-input source.  It adds
the validated shared-base three-lag proposal fold and the exact stable
11/11/10-bit radix ranking change.  The build includes the inherited
`test_dwell_input`, this task's `test_fused_fold`, and the ranking
`test_rank_radix11` units, in addition to the final pipeline units.

Only the source copy in this directory is modified. ARM execution is serialized
by the root agent on PLUTO+ CPU0 at 192.168.1.15, using static files.

All host and sanitizer units passed; the ARM artifact cross-built with warnings
as errors. The host704 evaluator found zero changed
windows and zero changed candidates across 15,488 windows and 86,439 emitted
candidates relative to `arm_wave5_final/host704-v2`.  Its frozen standard audit
is unchanged at 19,217 recovered hits of 19,581 reference-positive hits.

DS8 and DS9 frozen transfer cohorts also have zero changed windows and
candidates against the prior final host cohorts.  Their standard audits are
identical: DS8 recovered 773 of 785 reference-positive hits (3,624 emitted
candidates), and DS9 recovered 886 of 908 (3,689 emitted candidates).  The
hash-bound detail is in `transfer-qualification.json`.

Timing review: `fused_total` starts before `leo_dwell_input_prepare`, then
includes that complete 120 ms dual-receiver conversion plus all 22 proposal and
search calls, and is amortized by 22 before each row is emitted.  It excludes
saved-IQ reading, workspace/template creation, and JSON output.  `stage_sum`
does not include the shared preparation, so it is not an end-to-end substitute
for `fused_total`.  The dwell-input unit covers all four rates, both receivers,
all 11 overlapping windows, CI16 full scale, and a sparse tail; its exact-prefix
bound is `2 * dwell * 2^30 < 2^52` at the largest supported dwell.
