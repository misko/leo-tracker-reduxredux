# T2 batched coarse-acquisition prototype

Date: 2026-08-22

Status: implemented and qualified on an isolated branch; not deployed

## Decision

The folded-anchor coarse CFO search should use the new batched native kernel for both
Standard and Research. It is a mathematically equivalent implementation backend, not a
new scientific GLRT flavor, and it requires no search-parameter or persisted-contract
change. The legacy per-CFO native path remains available as the numerical oracle and as
the runtime fallback when the batched extension is unavailable.

## What changed

The previous implementation constructed a complete derotated probe for every CFO bin and
then rescanned that probe independently. The batched implementation factors out the
position-dependent common phase, precomputes the small CFO-rotated reference bank, and
evaluates all CFO bins while each received sample is resident in the inner loop. Power
normalization and epoch support are computed once because they are CFO invariant.

The CFO dimension is contiguous in the native accumulator so the compiler can vectorize
it with the repository's portable build flags. Correlation magnitude uses the cheaper
square-root form only when an input-derived bound proves it cannot overflow; otherwise it
falls back to `hypot`.

## Portable-kernel benchmark

The benchmark used deterministic complex Gaussian input: 50,000 complex128 samples at
2.5 MS/s, the 12 production anchor symbols, seed `0xC0A25E`, one numerical thread, a warmup,
and 10 measured repetitions. Times are medians on this x86-64 host. No machine-specific
compiler flags were enabled.

| Lane | CFO bins | Legacy coarse | Batched coarse | Coarse speed-up | Max score delta | Argmax changes |
|---|---:|---:|---:|---:|---:|---:|
| Standard | 11 | 91.071 ms | 30.098 ms | 3.03× | 2.33e-13 | 0/11 |
| Research | 81 | 672.570 ms | 167.627 ms | 4.01× | 2.48e-13 | 0/81 |

The larger Research grid benefits more because sample loads and normalization are shared
across 81 bins rather than 11. This is the speed-up that the earlier GLRT-only release
could not expose: that release accelerated downstream transforms while leaving coarse
acquisition as the dominant cost.

## Whole-acquisition effect

These measurements include coarse search, basin selection, fine CFO, conditioned scoring,
and candidate construction for the current Standard and Research study profiles.

| Lane | Legacy acquisition | Batched acquisition | Speed-up | Candidate/epoch changes | CFO delta | Margin delta |
|---|---:|---:|---:|---:|---:|---:|
| Standard | 119.117 ms | 57.865 ms | 2.06× | 0/10 | 0 Hz | 0 |
| Research | 882.399 ms | 376.389 ms | 2.34× | 0/32 | 0 Hz | 0 |

The end-to-end speed-ups are smaller than the isolated coarse-kernel gains because fine
CFO and conditioned scoring remain unchanged work. They are nevertheless materially
larger than the previous exact-FFT-only improvement.

## Parameter and flavor consequences

- Standard remains the current 80 kHz coarse grid with its existing fine and conditioned
  grids.
- Research remains the current 10 kHz coarse grid with its existing fine and conditioned
  grids.
- Power-of-two parameter variants remain named Research experiments. This kernel removes
  the need to alter scientifically meaningful CFO geometry merely to obtain the main
  hardware gain.
- There is still one public GLRT64 method per lane. Legacy direct, exact FFT, and batched
  coarse paths are internal numerical backends.

## Qualification

- The batched grid was compared against the legacy per-CFO native oracle at 2.5 and
  2.4 MS/s, with production, arbitrary fractional-CFO, short-probe, and non-frame-aligned
  tail geometries. The tolerance is `1e-12`, and every tested CFO-row argmax matched.
- The missing-extension fallback was exercised explicitly.
- Focused Standard, Research, acquisition, and DSP tests passed: 67 tests.
- On implementation base `39bbfd2`, the full repository plan passed all 159 jobs,
  including mypy, Ruff, all ordinary pytest shards, PostgreSQL tests, web build, and web
  tests. Receipt:
  `.leo/test-receipts/d84045616c27f77e31ec5e29eabec6498950d1e757bc1469efe32794d80cadf0.json`.
- After rebasing onto `e1aa01c`, every test, type-check, lint, and build job passed; the
  repository-wide format check alone reports two files introduced or modified by that
  upstream commit: `tools/report_carrier_continuity_case.py` and
  `tools/rerun_dense_independent_glrt.py`. Neither file is in this prototype's diff.
  Receipt:
  `.leo/test-receipts/409cb8152002aea8bf3039cee2b7dd83f17f2ac80813c988faf2b3da1ba86f4d.json`.
- The protected one-second Trial 132 real-corpus path passed its frozen-equivalence smoke
  test in 12.25 s. The corpus remained read-only and no RF was collected.

Machine-readable benchmark: [benchmark.json](figures/2026_08_22_t2_coarse_acquisition_batch/benchmark.json).
