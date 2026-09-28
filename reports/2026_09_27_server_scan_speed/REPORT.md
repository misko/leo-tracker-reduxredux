# Portable server Standard analysis optimization

Date: 2026-09-27. This is a saved-file experiment and a local source change;
no RF, production service, published product or persisted contract was changed.

**Measured outcome: 4.31% less CPU for full Standard numerical analysis at
2.5 MS/s**, averaged over five real visits using each visit's median of three
timed repetitions. Baseline/candidate order alternates after one warmup each.
Mean per-visit CPU fell from **1.2799 s to 1.2247 s** (1.045x throughput).
All five full numerical outputs matched exactly after excluding elapsed time.
This is a useful small portable gain, not the ARM experiment's speedup.

| Saved visit | Baseline median CPU | Candidate median CPU | CPU reduction |
|---|---:|---:|---:|
| Main 1678 | 1.3095 s | 1.2449 s | 4.93% |
| Main 1679 | 1.3759 s | 1.2766 s | 7.21% |
| Main 1681 | 1.2685 s | 1.2165 s | 4.10% |
| Newdev 1077 | 1.2466 s | 1.2213 s | 2.03% |
| Newdev 1078 | 1.1990 s | 1.1644 s | 2.88% |

The change preserves candidate/decision histories, timing, CFO, scores,
waterfalls, IQ digests and pilot-Doppler products. `paired-full.json` records
all 30 timed analyses and their complete common scientific outputs;
`paired-summary.json` contains the aggregate calculation. These numerical
latencies are not live real-time performance: the full Standard workload
still needs substantially more than 120 ms on one pinned server core.

## Workload and scope

The published scanner path is `run_published_standard_scanner_analysis` ->
`analyze_standard_scanner` -> `analyze_glrt64_dwell`. We preserve the default
120-ms dwell, 11 overlapping 20-ms probes at 10-ms strides, both receivers,
eight retained acquisition candidates, all 22 acquisition calls and all 176
GLRT candidate evaluations per tested visit. This workload differs from the
PLUTO experiment's six ranked windows and one confirmation per receiver.

The capture scheduling tool `run_adaptive_capture_cycle.py` instead uses the
external `Ci16EnergyDetector` during collection. These changes benefit the
server Standard scientific analysis and other consumers of its shared
acquisition/correlation functions; they do not modify that capture detector.

Inputs are the already extracted, SHA256-verified DS5 CI16 visits used by
the PLUTO experiment. Four-rate screening selects manifest indices 24, 56,
88 and 96, one real visit per rate, without selecting by detector outcome.
The 2.5-MS/s repeat cohort uses indices 24, 25, 27, 40 and 41. The fixtures
and original modules remain unchanged. These are bounded cohorts, not
whole-corpus recall or production-throughput qualification.

The host is an Intel Core Ultra 9 285K, Python 3.12.14, NumPy 2.5.2,
AVX2/FMA acquisition backend. Timed scanner runs pin CPU0 and set
`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1`. Each run warms the implementation
before measuring. CPU frequency is not locked; timing differences of a few
percent cannot be treated as established gains.

## What was changed

1. Acquisition now heapifies all discovered coarse peaks and removes only as
   many strongest peaks as needed to retain the requested separated candidates.
   It preserves the old full-sort order: score, absolute CFO, epoch and stable
   discovery order. Every coarse score is still calculated; no search cell,
   candidate budget or scientific support was removed. Synthetic selector
   timing improved from about 4.0 to 2.0 ms for an 11-by-3333 grid.
2. Correlation caches immutable geometry, exact/control reference samples and
   reference energies per sample rate and edge, with at most 16 entries.
   Received IQ, CFO, candidates and results are never cached. Correlation
   arithmetic remains unchanged. The isolated workspace gain is small;
   see `cache-audit.md` rather than attributing the complete gain to this cache.

The ARM-specific NEON code, integer-to-double conversion trick and IRQ
placement were not copied into the server path. The server already uses
AVX2/FMA acquisition and FFT/autocorrelation GLRT dispatch.

## Initial four-rate detector comparison

Median process CPU seconds per complete dual-RX visit. Baseline has two timed
repetitions and candidate three, each following warmup. These separate runs
are screening evidence; repeated alternating 2.5-MS/s full-analysis runs are
the primary performance check.

| Rate | Baseline CPU | Candidate CPU | Observed speedup |
|---|---:|---:|---:|
| 2.5 MS/s | 1.189 s | 1.072 s | 1.110x |
| 5 MS/s | 3.333 s | 3.024 s | 1.102x |
| 7.5 MS/s | 6.577 s | 6.670 s | 0.986x |
| 10 MS/s | 11.338 s | 11.203 s | 1.012x |

All four full detector outputs are exactly equal, including selected
candidates, scores, timing, CFO, decisions and probe history. This is stronger
than the comparison script's permitted 1e-12 absolute floating tolerance.
No high-rate throughput gain is established. In particular, the 7.5-MS/s
screening run was slightly slower and is retained here.

Before optimization, acquisition accounted for 82% of the detector's CPU at
2.5 MS/s and 93%, 96%, 98% at the higher rates. A separate cProfile run
identified the native coarse grid as the largest acquisition cost; peak
sorting and correlation setup are secondary. Further substantial gains need
profiling and optimization of that native coarse grid, not wholesale FP32
conversion of final GLRT. Profile timings include instrumentation overhead.

## Reproduction and evidence

`benchmark.py` performs the four-rate detector experiment and can include
the full numerical analyzer with `--full-analysis`. It verifies raw hashes,
checks repetition identity and records configurations, backend and source
hashes. `paired.py` alternates baseline/candidate order over five real
2.5-MS/s visits and includes waterfalls, IQ digests and pilot-Doppler products.
It compares all numerical products after removing only report elapsed time.
Archive reading/decompression, PNG rendering, publication and production
queueing are outside both timing claims.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python reports/2026_09_27_server_scan_speed/benchmark.py --output /tmp/server-scan-new-run --repeats 3
```

Original acquisition is retained in `acquisition_peak/original/acquisition.py`
and original pilot scoring in `pilot_methods_baseline.py`. Pass these with
`--baseline-acquisition` and `--baseline-module` to reproduce the baseline.
Input files live under `/tmp/leo-static-arm15-20260927-v3/data`, with their
manifest beside that directory. The report does not copy or alter golden IQ.

`baseline-v2/`, `cache-only/`, `combined/` and their comparison JSON retain
the raw detector measurements. `full-baseline-v2/` is the initial one-frame
full-analyzer baseline. `profile-baseline/` is instrumented and excluded
from performance claims. Empty `baseline/` and `full-baseline/` directories
are failed harness setup attempts, not numerical failures.

The combined four-rate run used acquisition hash `b5f41d1...ef811`;
the final source differs only in import ordering (`ef87f40f...39d6`). Both
exact files and hashes are retained in `acquisition_peak/SOURCE_LOCK.json`.
The alternating full-analysis run uses the final source. Pilot hash is
`7486c61084e02b6fb61b6e1c913aaa48df487a93c235ccf4771a9ca7cc32e451`.

The final pilot module is also frozen as `pilot_methods_candidate.py`.
Validation: **164 tests passed**, including acquisition evidence and stable
tie ordering, workspace scalar-oracle comparisons at all four rates/both
edges, partial-frame geometry, full-symbol support, and scanner decision
semantics. Ruff and `git diff --check` passed. `validation.json` binds the
tested source hashes. Reproduce the focused suite with:

```sh
.venv/bin/python -m pytest -q tests/analysis/test_standard_performance_equivalence.py tests/analysis/test_pilot_methods_workspace_cache.py tests/scanner/test_glrt64_only.py tests/dsp/test_starlink_acquisition.py reports/2026_09_27_server_scan_speed/acquisition_peak/test_peak_selection.py reports/2026_09_27_server_scan_speed/test_compare.py
```
