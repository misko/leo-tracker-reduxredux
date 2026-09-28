# Exact integer rank-fold candidate

This isolated candidate changes only V5's integer folding traversal. For the
full-fold production flags, it visits each group of four timing cells first and
keeps four complex `int64` accumulators in NEON registers across all 15 frames.
The frozen implementation visits frames first and reloads/stores those eight
sums for every frame. The correlation FFT and all six-window ranking logic are
unchanged.

Each real or imaginary term is a sum/difference of two signed 16-bit products.
Across 15 frames its magnitude is below `15 * 2 * 2^30`, so the reordered exact
integer additions cannot overflow `int64`. The scalar tail and scalar host path
use the same terms and support limits.

Run the host equivalence, sanitizer, cross-build, and static NEON checks with:

```sh
python3 reports/2026_09_27_plutoplus_static_arm/optimize/rank/test_rank_candidate.py
```

The script requires the frozen `/tmp/leo-static-arm15-20260927-v3` snapshot and
refuses a baseline source hash mismatch. It writes all binaries under `build/`
and records commands and hashes in `test_receipt.json`. It does not contact or
execute on target hardware.
