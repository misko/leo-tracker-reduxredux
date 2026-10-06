# 10 MS/s GLRT profile and register-sized CFO tiles

## Result

On 24 saved visits from three 10 MS/s adaptive captures, register-sized CFO
tiles reduce total visit-analysis CPU from **42.473 s to 28.989 s**: **31.75%
less CPU / 1.465× throughput**. All 48 receiver/probes and all 384 candidate
entries remain; complete persisted visit products compare exactly equal.
Eight 2.5 MS/s control visits also retain identical products (16 probes, 128
candidates), measuring 1.557 s versus 1.519 s, effectively unchanged at this
small duration. This is a bounded saved-IQ replay, not a full-scan deployment
or end-to-end queue throughput measurement. No RF collection was performed.

The CPU benchmark alternates baseline/candidate execution order per visit,
uses one BLAS/OMP thread, and includes source reads and full visit analysis.
Both variants run in the same production Python process and share normal warm
caches. The baseline is the deployed acquisition module at
`/opt/leo-adaptive-memory/9181d637d/src/leo/analysis/starlink/acquisition.py`.
The candidate changes only the coarse-grid wrapper. Visits are
0, 71, 203, 503, 901, 1201, 1701, and 2101, using production 120 ms probe stride.

| Capture | Rate |
|---|---:|
| `scan-fw-aadec7177d989684` | 10 MS/s |
| `scan-fw-1d4684501207703c` | 10 MS/s |
| `scan-fw-3563f54ed3c91ff3` | 10 MS/s |
| `scan-fw-c4a9c707b55aa15e` | 2.5 MS/s control |

## Profile and selected change

A four-visit production-backend cProfile run took 7.253 seconds. Native coarse
timing/CFO search consumed 5.230 s (72.1%); fractional refinement consumed
0.867 s (12.0%). Fine CFO search and conditioned search each consumed about
0.21 s. Reading the saved source accounted for under 0.1 s. The first checkout
profile inadvertently used the Python fallback; it was discarded as a
production estimate after verifying production already loads AVX2/FMA.

The 21-lane coarse CFO bank takes the generic AVX2 path. The existing 12-lane
native implementation keeps its accumulators in registers. The new wrapper
partitions wider banks into 12-lane tiles, shares geometry and the received
energy prefix, and fills the final tile with duplicate discarded frequencies.
Every original CFO and epoch is retained in its original order. Templates,
precision, candidate limits, gates, fractional refinement, and persisted
configuration remain unchanged. Portable and explicitly forced backends keep
their previous dispatch.

This is numerical equivalence, not a universal bit-exact intermediate-grid
claim: explicit register FMA can differ from the generic compiled loop by a
few ulps. Random all-rate grid tests require the established 1e-12 tolerance
and identical winning epochs. Final saved-visit product parity is separately
checked exactly; no golden scientific fixture was changed.

## ARM report review and rejected alternatives

The existing ARM work is useful, but most reports use 11 overlapping windows
per receiver per 120 ms dwell, versus one window at the production stride for
a 120 ms visit. Many also predate production fractional refinement. Their
headline speedups cannot be applied directly to current server jobs.

- ARM register/packing experiments motivate testing execution geometry while
  preserving the searched hypotheses. The server change reuses an existing
  AVX2 register kernel; it does not port NEON instructions.
- ARM shared-input FFT integration reported a 1.638× 10 MS/s probe speedup,
  with no benefit at 2.5 MS/s. A local FP64 overlap-save prototype on the four
  current server visits took 7.367 s versus the native baseline's 7.253 s;
  final products matched, but this prototype showed no speed benefit.
- Simply padding 21 lanes to 24 took 7.443 s on that panel and was rejected.
  Register-sized tiles measured 4.814 s on the same profiled panel.
- Exact refinement reuse is compatible in principle, but is a smaller target
  than the measured coarse bottleneck. Fine FFT and conditioned CZT changes
  also target small fractions of current server runtime.
- Reduced proposals, higher rejection gates, fewer frames, or cross-window
  reuse can lose detections. ARM Wave8's 51% saving retained only 92.08% of its
  frozen original hits. Those tradeoffs are not part of this implementation.

Reviewed local evidence in the reference workspace:
`docs/research/arm-glrt-performance.md`, `docs/research/arm-glrt-comparison.md`,
`reports/2026_09_28_arm_coarse_tiles/README.md`,
`reports/2026_09_28_arm_fft_integration/ARM_RESULTS.md`,
`reports/2026_09_28_arm_conditioned_czt/PERFORMANCE_REPORT.md`, and
`reports/2026_09_28_arm_refinement_cache/README.md`.

## Validation and limits

82 acquisition/performance tests pass, including 16 all-rate native grid
comparisons across 13, 21, 24 and 25 frequencies, partial support and zero-energy
cells. The wider scanner run has 49 passes and four pre-existing failures:
`test_native_analysis_preserves_actual_target_counter_precision_and_physical_rx`
uses a detector mock that rejects `search_geometry`. All four failures reproduce
against the unchanged deployed overlay. Ruff and diff checks pass.

At an unchanged CPU allocation, the measured 0.683 runtime ratio would turn
the earlier 59-minute median 10 MS/s GLRT phase into about **40 minutes**.
That is an extrapolation, not an observed full-scan completion time. Queue
waiting, overview/phase products, tracking/position, I/O contention, and the
eight-tracker concurrency setting can change elapsed time independently.

Reproduce with `tools/benchmark_coarse_cfo_tiles.py` and its required baseline,
bulk-root, session, and output arguments. The runner is read-only and capped
at 48 visits. Paired raw timings are in `paired-visits.json`. Additional
profile receipts and experimental scripts are retained in
`/home/mouse9911/release-evidence/glrt-10m-20261006/`.

## Deployment

PR #62 merged into main as `9a46a442d6b04e10e6d027801f05481f7df8413a`.
At 00:33:11 UTC on October 6, the worker overlay's acquisition module was
atomically linked to `/opt/leo-glrt-cfo-tiles/1507272de/acquisition.py`.
The other overlay modules and native binary are unchanged. The original module
is retained at `/opt/leo-glrt-cfo-tiles/1507272de/acquisition.before.py`; use that
path as the benchmark baseline after deployment, or restore it atomically to
roll back the module.

All 26 worker PIDs remained unchanged. Queue workers launch a fresh interpreter
for each analysis slice, so existing subprocesses finish with their loaded code
and new subprocesses import the optimized module. Queue child PID 2228303 for
`scan-fw-200bdf2228366f36` started after deployment with the updated overlay
path. A four-visit replay through that production path retained exact final
product parity. Admission remains 18 analysis / 8 tracking; there were zero
expired active leases at verification. This verifies deployment and adoption,
not a full-scan runtime reduction under live contention.
