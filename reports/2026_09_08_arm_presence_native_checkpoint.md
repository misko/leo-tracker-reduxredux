# Native single-RX GLRT2: correctness baseline and ARM feasibility checkpoint

Status: implementation in progress; **not qualified for live deployment**.
No new RF, FPGA, flashed firmware, kernel, or production scanner changes.

Latest result: the experimental full-grid FP32/NEON coarse search, with FP64
refinement, takes approximately **1.55/4.40 seconds** at 2.5/5 MS/s on the ARM
smoke probes. This improves the original baseline by about 3.1x/3.6x, but still
misses the 100 ms target by 15.5x/44x. See the final section below.

## Baseline result

A standalone C implementation now performs cold acquisition, two-candidate
refinement, and fractional GLRT scoring using templates supplied at startup.
It has no Python, IIO, storage, or network dependency on the radio. A desktop
development wrapper and saved-IQ replay executable exercise the same library.

The frozen experiment uses RX1 only, chosen from development evidence before
native replay, and the first 20 ms of selected 120 ms visits. Dual-RX recording
is not changed. The baseline retains the full coarse search; GLRT2 does not
mean only two initial correlations.

The [protocol](../config/analysis/arm-presence-native-v1.json) freezes settings,
input selection, and tolerances. Forty saved probes (32 archived RF and eight
synthetic controls) ran three times on desktop. All completely fractionally
refined candidates matched the frozen oracle. This is not yet full raw-candidate
inventory qualification across the archive and is not independent signal truth.

## Measured cost

| Stage | 2.5 MS/s ARM smoke | 5 MS/s ARM smoke |
|---|---:|---:|
| Coarse search | 3,778 ms | 13,347 ms |
| Fine acquisition/refinement | 729 ms | 1,560 ms |
| Fractional GLRT | 300 ms | 730 ms |
| Total process CPU | **4,818 ms** | **15,646 ms** |
| Total wall time | 4,825 ms | 15,649 ms |
| Peak RSS | 6,784 KiB | 11,924 KiB |

These are **one saved-RF probe per rate**, on an identity-attested idle Cortex-A9
radio over its LAN interface. They are not p95/p99 estimates, streaming tests,
or generic ARM/desktop conversion factors. Both ARM outputs matched the frozen
fractional oracle. The executable used one process at nice 19, without affinity;
the two online cores do not imply two otherwise available cores. CPU clock rate
was not established. The CPU clock has coarse apparent stage resolution, so a
reported zero conversion duration does not mean conversion is free.

Native desktop warmed medians were 38.8/122.1 ms at 2.5/5 MS/s; corresponding
p99 values were 43.2/126.5 ms. These describe this baseline implementation, not
the earlier Python/NumPy plus AVX2 path. The original desktop study's hypothetical
5–20x ARM slowdown scenarios were not measurements and must not override these
actual paired-kernel observations.

Evidence: [desktop summary](figures/2026_09_08_arm_presence_native/desktop-results.summary.json),
[ARM smoke receipt](figures/2026_09_08_arm_presence_native/arm-smoke.json), and
[frozen inputs and reference outputs](figures/2026_09_08_arm_presence_native/inputs.json).
Raw IQ and replay binaries are intentionally not included in Git.

## Provenance and qualification limits

The initial replay receipts identify exact binaries and probes by SHA-256.
Those binaries preceded two non-numerical source changes: rejecting a non-nearest
floating-point rounding mode at initialization, and exempting sanitized desktop
builds from the normal 128 MiB address-space cap. Do not claim that a later source
snapshot built those original binaries byte-for-byte.

Build helpers now write sidecar receipts containing source hashes (including the
shared coarse kernel), compiler identity, exact command, and binary digest. They
reject existing output/receipt paths and detect source changes during compilation.
Subsequent optimization measurements must use these digest-bound builds.

Component tests cover coarse-grid parity, fractional GLRT, full GLRT2,
unbracketed acquisition candidates on synthetic cases, CI16 conversion, large
counters, invalid inputs, FFT accuracy, and standalone parsing. A separate
ASan/UBSan replay passed on one 5 MS/s archived probe; it is not a claim of
sanitizer coverage for every frozen input.

The known 5 MS/s tone false positive is retained, not fixed by silently changing
thresholds. Numerical agreement with GLRT cannot establish Starlink specificity.

## Next gate

The 100 ms target fails by approximately 48x/156x. Coarse search consumes 79–85%
of CPU, but even the remaining stages exceed the target. First remove redundant
rotation/interpolation work and optimize FFT/coarse execution with differential
tests. Any precision, search-coverage, or probe-duration change is a separate
experiment requiring new quality qualification. Do not deploy the baseline or
hide this failure by checking only a small unreported fraction of visits.

The remaining checkpoints are optimized ARM feasibility, fresh quality evaluation,
300 s paced streaming replay at each rate, optional versioned iiOD/host integration,
authorized bounded live shadow verification, and an opt-in release with rollback.
See the [implementation plan](../docs/architecture/arm-single-rx-presence-plan.md).

## First equivalent-computation optimization pass

Three changes were tested individually, without shortening the 20 ms probe or
removing any scientific search hypotheses:

1. Cache local CFO rotations across frames. Cache interpolation weights by the
   actual rounded fractional position, including changes across floating-point
   binades, rather than recomputing 16 Lanczos weights at every sample.
2. Specialize radix-2 FFT butterflies and remove division/modulo from inner
   butterfly indexing. A subsequent constant-divisor cleanup also removes the
   remaining variable division at recursive node setup.
3. Accumulate four coarse-search frequency lanes in scalar registers rather
   than repeatedly updating twelve complex array entries per tap. The existing
   scientific kernel's default path is unchanged; an optional compile-time
   correlation hook selects this layout only for the standalone native port.

| 5 MS/s smoke build | Coarse CPU | Fine CPU | Fractional CPU | Total CPU |
|---|---:|---:|---:|---:|
| Fresh digest-bound baseline | 13,321 ms | 1,569 ms | 729 ms | 15,639 ms |
| Cache rotations/weights | 13,342 ms | 1,580 ms | 170 ms | 15,102 ms |
| Also optimize FFT butterflies/indexing | 13,346 ms | 1,149 ms | 110 ms | 14,625 ms |
| Also register-block coarse search | 7,517 ms | 1,159 ms | 120 ms | **8,806 ms** |

The register-block build's 2.5 MS/s smoke took **2,979 ms** total, including
2,369 ms coarse, 540 ms fine, and 70 ms fractional. All five listed ARM
executions matched the original frozen fractional oracle. These remain smoke
observations, not distributions. The final recursive constant-divisor cleanup
was made after this table's binaries; its cost is not separately measured here.

Both cached and register-block desktop replays passed all 40 frozen probes,
three executions each. The latter explicitly forced the portable path rather
than using AVX2, so its desktop runtime must not be compared as though the
execution backend were unchanged. Tests exercise both default and forced
portable builds and FFT sizes spanning mixed radix-2/5 geometries.

The [stage receipt](figures/2026_09_08_arm_presence_optimization/arm-stages.json),
build sidecars, and desktop replay outputs preserve evidence for each variant.
The baseline is now a local Git checkpoint (`5404dd95`); none of this is merged
into remote main or deployed to production.

The optimizations help, but the latest measured cost is still about **30x/88x**
the 100 ms target. The next experiment is a separately labelled single-precision
coarse search using ARM NEON; fractional refinement remains double precision.
Its grid errors and candidate decisions must be tested, not presumed equivalent.

## Separately qualified FP32/NEON coarse-search experiment

The [precision protocol](../config/analysis/arm-presence-fp32-experiment-v1.json)
was frozen before its results. It permits a coarse-grid absolute error of 2e-6
and relative error of 2e-5, while retaining the original tight tolerances for
final candidate inventory/order, epochs, fractional offsets, CFOs, scores, and
decisions. It changes no search hypotheses or probe duration. Original IQ and
all fine/fractional refinement remain double precision.

The coarse input is normalized by its maximum absolute I/Q component, then
correlated and accumulated in FP32. Energy prefixes remain FP64. On ARM, NEON
handles twelve frequency lanes, including reciprocal-square-root refinement
for magnitudes; the compiler output was inspected to confirm the SIMD path.
This is an opt-in compile-time experiment, **not the default numerical oracle**.

An initial SIMD build took 1.83/5.52 seconds. Disassembly showed substantial
loop expansion and spills. Disabling loop unrolling, peeling, and automatic
prefetch reduced the smoke totals to 1.56/4.38 seconds. A final rebuild with
explicit unsupported-input error handling was replayed on both edges:

| Rate / edge | Coarse CPU | Fine CPU | Fractional CPU | Total CPU |
|---|---:|---:|---:|---:|
| 2.5 MS/s lower | 900 ms | 570 ms | 70 ms | **1,550 ms** |
| 2.5 MS/s upper | 910 ms | 570 ms | 70 ms | **1,550 ms** |
| 5 MS/s lower | 3,048 ms | 1,217 ms | 120 ms | **4,394 ms** |
| 5 MS/s upper | 3,053 ms | 1,200 ms | 130 ms | **4,399 ms** |

Every ARM candidate in these four final smoke executions matched the frozen
fractional oracle. Peak RSS was approximately 7/12.6 MiB. This is still only
one invocation per rate/edge: no ARM distribution, RF streaming claim, or
independent sensitivity estimate follows from these results.

Both initial and final FP32 desktop builds passed all 40 frozen probes, three
iterations each. Four rate/edge Gaussian grids passed the separately frozen
coarse precision bound in component tests. The combined focused regression
suite passed **152 tests**. ASan/UBSan passed four archived probes (both rates
and edges) for the optimized FP64 build and four for the FP32 desktop build;
that sanitizer result does not instrument the ARM NEON instructions.

Malformed template amplitudes and unsupported CFO ranges are rejected. An
unrepresentable FP32 normalization returns an error, not a successful negative
detection. Tests also check scale invariance and preserve the known tone
counterexample. None of the previously seen data is presented as a fresh holdout.

The [final ARM receipt](figures/2026_09_08_arm_presence_optimization/arm-fp32-final.json)
and adjacent build sidecars identify exact sources, flags, binaries, and inputs.
The spare's IIO buffers were disabled before and after replay; production
`leo-acquisition.service` remained active. Temporary userspace replay artifacts
were staged only under the spare's owned `/tmp` experiment directories.

### Next implementation decision

The full blind search remains too expensive. The next bounded experiments need
to profile fine refinement separately and reduce acquisition work: fewer
acquisition frames, bounded coarse candidate proposals, or a reduced-rate scout,
followed by fractional confirmation on retained original IQ. Each variant must
be explicitly configured and tested for lost evidence and interference response.
The historical cache and periodicity scouts are not presumed effective.

Checking every Nth revisit remains a labelled coverage tradeoff, not completion
of the every-visit target. No live collector, IIO result extension, production
enablement, merge into remote main, or deployment has occurred. The full plan
remains active, with runtime feasibility still the blocking release gate.
