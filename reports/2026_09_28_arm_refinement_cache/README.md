# Exact per-window refinement cache

This isolated experiment starts from verification-fusion V1. Each full-search
call owns two count-initialized arrays bounded to eight entries; entries beyond
the current count are never read. No cache state
crosses a window or workspace call, and duplicate candidates remain separate
entries in the final inventory.

After fine search, the refinement cache key is the exact bit pattern of
`(refined_epoch, conditioned_grid_lower_frequency, conditioned_bin_count,
conditioned_grid_last_frequency)`.
A hit copies only the conditioned winner, conditioned score, and fused
acquire/verify/control scalar results. The current candidate retains its own
coarse and fine fields. After candidate sorting, the final cache uses exact
`(refined_epoch, acquired_cfo)` bits and copies the three final GLRT scalars.
Workspace scratch is never cached. Signed zeros and adjacent representable
floating-point values do not alias.

The final-frequency component is required because `grid()` appends a
nonregular stop. Two lower-clipped grids can have identical starts and counts
while ending at different frequencies within the same 100 Hz bucket. V1
omitted this component and is rejected; all qualification must use V2.

The host704 opportunity measurement found 7,782 repeated epoch/final-CFO keys
among 123,904 candidates (6.28%) in the full baseline. At 2.5 MS/s the rate is
7.70%; sparse 8/12 with 128 centers raises it to 8.93%. This suggests only a
roughly 2–3% whole-search opportunity and is not a speedup claim.

`test_refinement_cache.c` covers cold hits, exact hits, nearby unequal doubles,
signed zero, epoch and bin-count differences, scalar copies, cache reset across
two simulated windows, and all-rate partial/full zero searches. Normal host,
ASAN/UBSAN, and ARM cross-builds are source-receipted. Hardware execution is
owned by root.

Combining fine-FFT requested bins by epoch may offer additional reuse, but it
is intentionally not implemented here. Any such work must preserve each
candidate's original fine range, winner, interpolation, and addition order.

Measured V2 ARM full-dwell CPU time is 33.166615 s versus 33.728123 s for
verification fusion (1.01693x), with every candidate object identical and
119/119 hits in 88 windows. V1 remains rejected regardless of its passing
small cohort. See REPORT.md for cache counts and the remaining real-time gap.
