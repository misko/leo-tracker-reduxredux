# Native single-RX GLRT2: correctness baseline and ARM feasibility checkpoint

Status: implementation in progress; **not qualified for live deployment**.
No new RF, FPGA, flashed firmware, kernel, or production scanner changes.

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
