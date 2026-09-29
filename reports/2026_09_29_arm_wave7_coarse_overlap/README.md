# Wave7 coarse-overlap reuse feasibility

This bounded study evaluates an exact per-dwell cache before allocating or
building one.  The proposed key is `(receiver, symbol, absolute sample
position)`; the fixed workspace template and dwell identity are implicit in a
cache lifetime of one fused invocation.  Its value would be the 12 normalized
FP32 CFO magnitudes produced before they are added, in the unchanged
frame/symbol order, to an epoch accumulator.

`analyze_reuse.py` reconstructs every valid `coarse_fp32_add` request from the
sealed Wave6 proposal centers and native geometry.  It expands each top-four
center by the existing radius two, uses all 12 symbols and all 16 coarse
frames, applies the native tail condition, adds the 10 ms window origin, and
counts a hit only when the complete key has already occurred earlier in the
same receiver/dwell cache.  The set is recreated for every dwell, so the
measurement cannot count stale cross-dwell reuse or hash collisions.

The representative regional32 panel issues 2,451,559 coarse cell requests;
382,692 repeat, a **15.61%** hit fraction.  All four rate cells are between
14.98% and 16.41%.  The full 704-dwell panel issues 53,971,369 requests;
8,031,223 repeat, a **14.88%** hit fraction.  Per-rate fractions range from
14.03% to 15.32%, and some dwells have zero reuse.

This is insufficient for the current goal.  Even treating a hit as free, the
measured ceiling is 14.88% of coarse correlation work.  Applied to Wave6's
134.47 ms ARM coarse stage, that is at most about 20.0 ms, or 2.46% of its
814.87 ms outer runtime.  A real implementation would also hash and probe all
53.97 million requests, and insert values for the 85.12% misses.

The minimum sparse payload is 56 bytes per unique cell: an eight-byte key and
12 FP32 magnitudes.  The full panel averages 65,256 unique cells and 3.65 MB
of payload per dwell.  A practical open-addressed table near 50% load would
need roughly 7.3 MB before allocator and alignment overhead.  A dense table
over symbols and absolute dwell positions is substantially larger.

No runtime cache, source fork, binaries, or ARM jobs were created.  That is the
intended outcome of the requested evidence gate: the maximum possible saving
is too small to justify cache complexity, memory traffic, collision tests, or
hardware qualification.  The existing sealed Wave6 sources and receipts are
unchanged.

Reproduce with:

```sh
python3 reports/2026_09_29_arm_wave7_coarse_overlap/analyze_reuse.py \
  --features reports/2026_09_29_arm_proposal_features/host704-omit-power-v1/rows.jsonl \
  --manifest reports/2026_09_29_arm_wave6_combined/host704/manifest.json \
  --output reports/2026_09_29_arm_wave7_coarse_overlap/reuse-host704.json
```
