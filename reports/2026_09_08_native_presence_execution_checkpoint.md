# Native GLRT execution: smaller setup, exact reuse, bounded arithmetic experiment

2026-09-08. **Offline implementation checkpoint, not deployed or qualified
realtime classification.** Implementation: `eea714de`. No new RF, FPGA/kernel/
flashed-firmware changes, production deployment or remote-main changes.

## Outcome

The RX1 detector now reuses exact geometry and GLRT rotation calculations and
allocates frequency tables for the configured search width. In the current
200 Hz-radius worker configuration this saves **7,464,560 bytes (7.12 MiB)**
across the two 5 MS/s edge workspaces. Desktop C workspace creation takes about
**79% less CPU time**; median recurring detection improves by approximately
**2–3%**. These are separate measurements, not a 79% detector speedup.

An optional magnitude shortcut gives about **6–7% lower desktop median CPU**
relative to the original detector. It remains **off by default** and retains
the original math in the final GLRT statistic after a numerical stress test
exposed an amplified rounding difference there. No ARM timing improvement or
unchanged live duty is claimed.

The [receipt](evidence/2026_09_08_native_presence_execution/receipt.json) binds
builds, source hashes, commands, tests, retained rejected runs and compressed
raw numerical evidence. No IQ or executable binary is included.

## Implementation and invariants

`LEO_PRESENCE_PRECOMPUTE=1` is the development-source default. Setting it to zero
retains an uncached comparison path.

- Precompute the existing rounded symbol and frame boundaries once. Execution
  now explicitly rejects a changed floating-point rounding mode rather than
  mixing setup and runtime geometry. The required mode remains `FE_TONEAREST`.
- Reuse the same rotation vector across GLRT epoch evaluations sharing exactly
  the same CFO and fractional offset. It has its own workspace rather than
  sharing scratch that other stages overwrite. This caches a mathematical
  function, not IQ, a previous-dwell estimate or transmitter phase.
- Replace 42 unconditional conditioned-frequency tables with the configured
  bound: six tables for the worker's 200 Hz radius, including room for a clipped
  off-grid endpoint. The full 2,000 Hz-radius configuration still has 42 tables.
  Clipped searches retain their nonregular calculation path.

`LEO_PRESENCE_BOUNDED_MAGNITUDE=1` is a separate, default-off experiment. It
uses `sqrt(re²+im²)` for ordinary finite magnitudes in proposal/frequency scoring,
with libc fallback for underflow, overflow and nonfinite inputs. The final
GLRT normalization and tone-nuisance magnitude remain on the original libc
path. This option is not universally bit-exact and needs ARM and broader
qualification before promotion.

Both variants preserve RX1 selection, all six 20 ms screening intervals in
each 120 ms dwell, the blind single-confirmation budget, search grids,
templates, thresholds and public result layouts. Device counters remain
separate from fractional offsets. Neither variant changes capture buffers,
retuning, IQ recording, the second receiver or detector delivery policy.

## Paired saved-IQ results

The source is **96 previously opened development dwells**, 48 at each rate,
assembled from hash-checked complete six-window inventories. The directory's
historical “holdout” name does not make it untouched qualification data.

Each dwell ran five times through the original pre-change FFTW artifact,
exact-cache artifact and cache-plus-magnitude artifact. Forward/reverse
execution order alternates; all variants receive the same immutable CI16 data.
The original baseline's source hashes were checked against `fa467153`, and
new build hashes were checked against the current implementation.

| Numerical result, excluding execution timings | Exact cache | Cache + optional magnitude |
| --- | ---: | ---: |
| Optimized-versus-original comparisons | 480 | 480 |
| Exactly equal serialized numerical payloads | 480 | 400 |
| Differences outside existing rtol 1e-9 / atol 1e-10 | 0 | 0 |

The benchmark summary also counts 480 baseline self-comparisons. Thus its
1,440 executions represent **960 optimized comparisons, not 1,440 independent
comparisons or detection trials**. Numerical parity is not detection accuracy.

| Whole-dwell desktop CPU | Original | Exact cache | Cache + optional magnitude |
| --- | ---: | ---: | ---: |
| 2.5 MS/s median | 0.900 ms | 0.881 ms | 0.843 ms |
| 2.5 MS/s p99 | 1.104 ms | 1.087 ms | 0.999 ms |
| 5 MS/s median | 1.708 ms | 1.658 ms | 1.589 ms |
| 5 MS/s p99 | 2.159 ms | 2.080 ms | 2.016 ms |

At 5 MS/s the fractional-stage median falls from 0.394 to 0.363 ms with exact
caching. The optional arithmetic variant mainly reduces coarse/fine work.
Pooled timings include first execution of each geometry; they are not a
separately qualified warm-tail distribution. The cache variant's observed
maximum is slightly worse than baseline at both rates, so the data do not
support an every-run speedup or a hard deadline guarantee.

## Setup and memory

The separate setup experiment prepares templates and ctypes signatures before
timing, alternates variant order over 25 trials per rate/edge, and measures the
C creation call. Destruction is outside the interval. This is a warm desktop
process/allocator experiment, not cold ARM process launch, template loading or
first-dwell execution.

| C workspace creation CPU median | Original | Exact cache |
| --- | ---: | ---: |
| 2.5 MS/s | 1.120 ms | 0.237 ms |
| 5 MS/s | 2.204 ms | 0.466 ms |

Earlier wrapper-initialization measurements included Python/template caching
and must not substitute for this C-only comparison. Direct allocation checks
include the private workspace structure and changed tables: savings are
1,865,240 bytes per 2.5 MS/s edge and 3,732,280 bytes per 5 MS/s edge. These are
requested allocation differences, not measured RSS or total worker memory.

## Tests and findings that changed the implementation

- **475 component regressions passed**, including 51 execution-specific cases,
  fractional rotation-cache invalidation, changed samples, clipped search
  endpoints, both rates/edges, numerical extremes, rounding-mode rejection,
  worker IPC and frame-result binding. No test marker, tolerance or golden
  scientific fixture was relaxed.
- **32 ASan/UBSan/leak-instrumented processes passed**: 64 full dwells and
  384 confirmations, using saved IQ, fractional pilot-plus-tone, zero and
  full-scale alternating inputs. Every process exited zero with empty stderr.
  All serialized outputs match the uncached, uninstrumented **same builtin FFT
  backend** within existing tolerances. External FFTW itself is not instrumented.
- Both variants **cross-compile for Cortex-A9/NEON** with the existing userspace
  toolchain/sysroot. This reads the firmware repository's compiler assets; it
  does not change firmware or establish ARM execution.
- Changed Python Ruff and whitespace checks pass.

The first optional shortcut also changed magnitudes in the final GLRT ceiling.
It passed the saved-IQ comparison but failed a new full-scale alternating-input
test: tiny ceiling rounding differences were amplified by fractional peak
interpolation. The final implementation restores libc magnitude at that point;
the new test now passes without changing its expected tolerance.

The stress control also exposes a **pre-existing cross-backend difference**:
builtin FFT versus FFTW produces fractional offsets differing by roughly
7e-9 to 1.1e-8 samples in three geometries even with the uncached baseline.
This is a deliberately non-pilot waveform, not an RF timing truth fixture.
The failed cross-backend run remains retained; universal backend equivalence
is not claimed. The independent final audit requires both optimized variants
to match their own baseline backend on all four stress geometries.

Two harness mistakes are retained as rejected evidence: an initially omitted
pytest parameter caused a collection error, and the first sanitizer comparison
treated the fixed-capacity ctypes candidate array as the variable-length active
candidate list serialized by C. Its incremental writer also attempted to reuse
an exclusive output filename. The corrected harness trims only inactive slots,
checks candidate counts, and writes distinct per-process records. These were
harness failures, not sanitizer diagnostics or reasons to weaken comparisons.

## Remaining gates toward realtime classification without duty loss

1. Verify the spare radio's changed SSH identity through a trusted source, then
   run bounded **saved-IQ** ARM startup and recurring-work benchmarks. The
   previous connection attempt to `192.168.1.15` failed strict host-key checking
   before authentication. No trust entry was replaced and no remote command
   ran. Do not extrapolate desktop ratios into a new ARM timing claim.
2. Qualify Starlink detection on frozen untouched scans and interference/short-
   burst controls. The [decision checkpoint](2026_09_08_arm_presence_decision_checkpoint.md)
   remains authoritative for known sensitivity/association limitations.
3. Replay original arrival/counter/hop sequences with competing capture load,
   finish userspace release packaging and rollback verification, then obtain
   explicit authorization for bounded live disabled/enabled comparisons.

The last measured 5 MS/s ARM numbers remain **113.47 ms CPU p99** and
**126.62 ms copy-to-result p99**, plus an unresolved initial-execution tail.
This checkpoint does not close those gates. The
[runtime publication/UI checkpoint](2026_09_08_scanner_glrt_runtime_checkpoint.md)
remains opt-in and undeployed; unknown or unqualified evidence must not become
a no-Starlink label. The full requested goal remains unfinished.
