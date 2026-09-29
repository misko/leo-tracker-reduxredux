# Wave 3 GCC loop-unrolling experiment

The Wave 3 combined Cortex-A9 build uses `-O3`, but its cross-compiler reports
`-funroll-loops` as disabled.  This isolated experiment adds that one flag to
optimized host and ARM translation units.  GCC may unroll fixed-trip loops and
use the already-enabled register-renaming and loop cleanup passes, which is a
plausible fit for the fixed symbol, feature, frame, and frequency loops in the
proposal and search kernels.  The outcome is uncertain because extra code can
increase Cortex-A9 instruction-cache pressure.

The source snapshot is byte-identical to the sealed Wave 3 combined source.
`-fno-fast-math` remains enabled, and neither the proposal statistic nor the
FP64 final GLRT source changes.  Sanitizer binaries omit loop unrolling and
serve as memory/undefined-behavior checks of the same source.  Host and ARM
optimized binaries include the flag; target timing is intentionally not run by
this build.

Run `python3 build.py` to recreate all builds.  Exact compile commands, source
hashes, binary hashes, and executed host/sanitizer unit output are recorded in
`builds/*/build-receipt.json`.  The ARM timing command uses the existing Wave 3
fused-runner interface:

```
builds/arm/fused_resampled_omit_power_neon_moments_arm RATE EXACT CONTROL INPUT_CI16
```

The serialized ARM runner measured 1.705877 and 1.707014 seconds/dwell, mean
1.706445, versus 1.709724 for the sealed Wave 3 combined binary. This 0.19%
difference is too small to claim a material gain from this four-dwell panel.
All candidate objects match exactly on the 704-dwell mixed-rate host cohort
and both ARM runs. Standard hits recovered remain 19,226/19,581 on the larger
host cohort and 119/119 on ARM. Physical-ARM component tests passed.
The linked ARM text grew from 1,504,779 to 1,527,971 bytes (23,192 bytes,
1.54%), confirming that the flag changed target code and defining the
instruction-cache tradeoff that the timing run must resolve.

## PGO feasibility

PGO was considered but was not tested in this bounded flag experiment.  The
installed Linaro GCC 7.3.1 cross-compiler reports support for
`-fprofile-generate`, `-fprofile-dir`, `-fprofile-use`, and
`-fprofile-correction`, so the toolchain has the required basic mechanism.
PGO is a two-build experiment rather than a standalone compiler flag check: an
instrumented ARM binary must run a representative training cohort on the
Cortex-A9, its matching `.gcda` files must be collected, and the identical
source and cross-compiler must then rebuild with `-fprofile-use`.  Timing and
quality must use a separate held-out cohort, with coverage-mismatch diagnostics
and exact candidate parity checked before any speed claim.  A host-generated
profile is unsuitable because the host compiler and architecture differ and
would describe different branch behavior and optimization costs.  That target
training and held-out pipeline was outside this experiment's bounded,
no-ARM-execution scope; this report therefore contains no PGO result.
