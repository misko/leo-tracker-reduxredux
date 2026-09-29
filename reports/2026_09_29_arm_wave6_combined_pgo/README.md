# Wave 6 combined Cortex-A9 PGO

Target qualification is complete on the disjoint 32-dwell panel: **776.473
ms/dwell**, versus **816.561 ms** for the exact Wave6 combination and
**917.633 ms** for Wave5 on the same contexts. This is a 4.91% incremental
saving and 15.38% overall. All 1,201 candidate objects and **904/921 standard
hits** are identical. All nine component units pass on ARM. See
`heldout-comparison.json`, `arm-heldout32/`, `arm-units-use.json`, and the
recorded `profile-data.tar.gz`. This is a 32-dwell qualification, not a claim
of full 152-dwell or DS8/DS9 target coverage.

This isolated workflow applies real target PGO to the sealed Wave 6 combined
source, which already combines exact dwell-owned input views, shared-base
three-lag proposal folding, and stable 11/11/10-bit proposal ranking.  It keeps
the existing `-fno-fast-math` policy and unchanged final FP64 GLRT arithmetic.

Build the instrumented binary with `python3 build_pgo.py generate`.  It uses
the stable compilation directory `work/arm`, the target profile directory
`/var/tmp/leo-wave6-combined-pgo-profile`, and relative proposal source/object
names.  `builds/generate` is evaluator-compatible and contains exact commands,
thresholds, binary and source hashes, and copied source snapshots.

Train on the same four recorded `arm4-v2` metadata contexts used by the first
PGO experiment:

1. Clear and create `/var/tmp/leo-wave6-combined-pgo-profile` on ARM.
2. Run `builds/generate/fused_wave6_combined_arm RATE EXACT CONTROL INPUT_CI16`
   once per training context.  Reuse the same binary so counters accumulate.
3. Retrieve the complete profile directory to the identical absolute host path.
   It must contain nonempty `proposal_core.gcda`, `conditioned_czt.gcda`,
   `fft_full.gcda`, and `fused_probe.gcda`.
4. Run `python3 build_pgo.py use`.  The script checks all four files before
   compiling, reuses exact source/object paths, makes coverage mismatch fatal,
   and freezes `builds/use` separately.
5. Run the nine ARM component binaries, then evaluate against the existing
   disjoint 32-dwell reference in `../2026_09_29_arm_wave6_pgo/heldout32-reference`.
   Require exact candidate parity and compare per-dwell outer CPU totals.

The first Wave 5 PGO experiment saved 4.71% on that held-out panel.  This build
does not assume the gain composes with Wave 6 source changes; target training
and held-out timing are required.
