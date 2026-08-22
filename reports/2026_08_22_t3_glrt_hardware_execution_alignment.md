# T3 GLRT hardware-execution alignment

Date: 2026-08-22

Status: implementation qualified for guarded deployment; scientific parameters unchanged

Deployed A/B baseline: `20a1130fce5e295e5fc3029e1ea2da47ff5ba970`. The GLRT
optimization lineage begins at the earlier batched-coarse release
`ace780a8a3db37ac91c4dd699c970b17d362e45c`.

## Executive decision

The second exact-backend release is implemented and qualified. It aligns execution with
the host while leaving every scientific search parameter unchanged.

On a pinned P core, with production services active, the built implementation measured
**1.57× Standard acquisition, 1.48× complete Standard detection, 2.38× Research
acquisition, and 2.27× complete Research detection** against the archived deployed
baseline. Runtime dispatch selected `avx2_fma`. Candidate inventories, epochs, CFO
winners, detector methods, and QAM outputs were unchanged in protected-corpus A/Bs. The
largest detector-score delta was `5.55e-13`.

The central hardware finding is not that the scientific grids should become powers of
two. It is that each existing grid should use the backend and execution shape that fits
the processor:

- Standard keeps its 11 scientific coarse-CFO bins but evaluates 12 internal SIMD lanes,
  discarding the extra lane. It keeps the exact N=5,000 fine FFT.
- Research keeps its 81-bin coarse grid and 201-bin, 100 Hz fine grid. Its coarse kernel
  uses AVX2/FMA without padding, while its fine grid changes from N=25,000 FFT execution
  to exact factored matrix multiplication.
- GLRT-512 and GLRT-4096 keep their grids but use a short-autocorrelation transform that
  replaces 30 large row FFTs with short row transforms and two final transforms.

These are implementation backends of the existing Standard and Research methods. They
create **zero new public GLRT flavors** and require no persisted-contract change.

## Questions this study must answer

1. Which exact backend is fastest for each current Standard and Research geometry?
2. Can runtime AVX2/FMA dispatch preserve a portable fallback and the current numerical
   oracle?
3. Can internal padding improve vector occupancy without adding a scientific CFO bin?
4. How do P cores, E cores, cache residency, and four-path concurrency change the result?
5. Does the combined backend preserve the real-corpus candidate inventory and trajectory
   evidence, not merely a synthetic argmax?
6. After the exact backend is optimized, is any scientifically different power-of-two
   profile still worth qualifying?

## Scientific invariants

The exact lane freezes all of the following:

| Contract or parameter | Standard | Research | T3 exact-backend rule |
|---|---:|---:|---|
| Residual-CFO domain | ±400 kHz | ±400 kHz | Unchanged |
| Coarse step / scientific bins | 80 kHz / 11 | 10 kHz / 81 | Unchanged |
| Fine radius / step / bins | 80 kHz / 500 Hz / 321 | 10 kHz / 100 Hz / 201 | Unchanged |
| Conditioned radius / step / bins | 2 kHz / 100 Hz / 41 | 1 kHz / 25 Hz / 81 | Unchanged |
| Retained candidates | 10 | 32 | Unchanged |
| GLRT size | 512 | 4,096 | Unchanged |
| Pilot, control, and score definitions | Published current definitions | Published current definitions | Unchanged |
| Public products and method names | Current contracts | Current contracts | Unchanged |

Any change to those rows belongs in a named Research parameter study. It cannot be
described as hardware-only alignment.

## Gated analysis plan

The study proceeds as a staircase. A backend advances only after passing the preceding
gate; timings from a rejected backend do not justify later corpus or deployment work.

| Gate | Question | Evidence | Pass condition | State |
|---:|---|---|---|:---:|
| 0 | Is the comparison reproducible? | Fixed 50,000-sample complex128 probe, seed `0xC0A25E`, 2.5 MS/s, one numerical thread, warmup, ten medians | Inputs, affinity, compiler path, and raw timings recorded | Passed |
| 1 | Is each transformation numerically faithful? | Direct/FFT/native oracle comparisons plus edge geometries | Same shapes and argmaxes; existing `1e-12` score tolerance | Passed in built implementation |
| 2 | Do the isolated wins combine? | Complete acquisition and candidate detector, not summed estimates | No candidate/rank/epoch/method changes; material wall-time gain | Passed |
| 3 | Does hybrid-core placement help the real workload? | P-only, E-only, and default-scheduler full-corpus runs | Default scheduler passed; P/E affinity policy remains unchanged and experimental | Passed for release scope |
| 4 | Is real scientific evidence invariant? | T1 50-probe set and protected one-second Trial 132 path | Zero inventory/epoch/winner changes; score/CFO deltas within reviewed tolerances | Passed |
| 5 | Does the full pipeline remain stable? | Two complete concurrent four-path candidate runs plus deployed-release A/B | Exact duplicate output; deployed candidate inventory and trajectory geometry preserved | Passed |
| 6 | Is a parameter variant still useful? | Existing aligned/finer T1 variants rerun only after exact backends land | Must improve science or total cost enough to repay changed geometry | Deferred |

No new RF collection is needed. Gates 3–5 use deterministic data and the existing
read-only corpus.

## Host geometry

The deployment host is an Intel Core Ultra 9 285K with 24 physical cores and no SMT:
8 P cores (up to 5.5–5.7 GHz) and 16 E cores (up to 4.7 GHz). It exposes AVX2, FMA, and
AVX-VNNI, but not AVX-512. The host reports 36 MiB shared L3 and 40 MiB total L2.

NumPy 2.5.2 uses dynamic-architecture OpenBLAS. The service already fixes OpenBLAS,
OpenMP, and MKL to one thread, which is correct: parallelism belongs at the bounded probe
level. The deployed baseline C extension is compiled with portable
`-O3 -fno-math-errno`. The candidate wheel contains that portable kernel plus a narrowly
targeted AVX2/FMA function selected at runtime. It does not compile the whole package
with `-march=native`; disassembly and the forced-backend tests verify the packed `ymm`/FMA
path and portable fallback independently.

## Implemented combined result

The comparison below uses the archived deployed implementation as the baseline and the
built runtime-dispatch implementation as the alternative. The candidate contains vector
peak extraction, factored matrix scoring, geometry-aware fine dispatch,
summed-autocorrelation GLRT, factored workspace phases, a runtime AVX2/FMA target with a
portable fallback, and Standard-only 12-lane execution padding.

Production services remained active during the run. The benchmark ran at nice 0 while
production workers run at nice 10. This intentionally provides useful contention
evidence. The default-scheduler four-path corpus gate passed; no core-affinity change is
part of this release.

| Core | Lane | Boundary | Deployed baseline | Built implementation | Speed-up |
|---|---|---|---:|---:|---:|
| P, CPU 1 | Standard | Acquisition | 62.396 ms | 39.817 ms | **1.57×** |
| P, CPU 1 | Standard | Complete detector | 80.482 ms | 54.429 ms | **1.48×** |
| P, CPU 1 | Research | Acquisition | 488.315 ms | 204.834 ms | **2.38×** |
| P, CPU 1 | Research | Complete detector | 553.807 ms | 244.246 ms | **2.27×** |
| E, CPU 8 | Standard | Acquisition | 85.861 ms | 67.965 ms | 1.26× |
| E, CPU 8 | Standard | Complete detector | 110.161 ms | 88.748 ms | 1.24× |
| E, CPU 8 | Research | Acquisition | 600.476 ms | 446.092 ms | 1.35× |
| E, CPU 8 | Research | Complete detector | 693.041 ms | 502.213 ms | 1.38× |

P cores are especially valuable after vectorization: the earlier complete prototype was 1.50×
faster on P than E for Standard and 1.84× faster for Research. This does not yet justify
P-only worker pinning. Eight P cores cannot host the current maximum of sixteen
simultaneous path threads, so aggregate throughput and tail latency must be measured
before changing affinity.

## Numerical and protected-corpus result

| Lane | Candidate count | Rank/epoch changes | Max acquired-CFO delta | Max tracking-CFO delta | Max detector-score delta | Method changes |
|---|---:|---:|---:|---:|---:|---:|
| Standard | 10 | 0 | 0 Hz | 0 Hz | 9.03e-14 | 0 |
| Research | 32 | 0 | 2.91e-11 Hz | 2.91e-11 Hz | 2.34e-13 | 0 |

The larger maximum margin delta across the Research detector inventory was `4.38e-13`.
The deterministic probe result is now supplemented by three read-only protected-corpus
gates:

| Gate | Inventory checked | Result |
|---|---:|---|
| T1 immutable windows | 500 Standard + 1,600 Research candidates | Zero rank/epoch changes; Standard CFO exact; Research CFO delta at most `5.82e-11 Hz`; score delta at most `4.23e-13` |
| Trial 132 one-second frozen path | 40 probes | Passed reviewed frozen equivalence in 11.63 s; production eight-candidate bound returned all 40 probes with zero truncation |
| Trial 132 full deployed-release A/B | 9,600 probe certificates, 38,400 returned candidates, 115,200 method scores | Zero certificate/rank/epoch/method/CFO/QAM changes; score delta at most `5.55e-13` |

The full A/B initially exposed a downstream alias-boundary tie: four trajectories on one
path were represented one exact pilot-alias spacing (`227,272.727 Hz`) away after tiny
score-rounding changes altered content IDs. The release fix canonicalizes fitted global
Hough intercepts to `[0, alias_spacing)` before persistence. A targeted 2,400-probe
full-path replay then restored the deployed geometry: maximum trajectory coefficient
delta `4.66e-10 Hz`, zero structural changes, and no alias jump. Content-derived IDs
still evolve with the new implementation digest, as intended.

Two concurrent new full four-path runs produced byte-identical 90,798,566-byte outputs
before that canonicalization fix. The targeted correction is covered by an exact
alias-translation component regression and the affected full-path rerun.

## Isolated backend findings

The following pinned P-core measurements explain why one universal backend is not the
right design.

| Stage | Standard result | Research result | Backend decision |
|---|---:|---:|---|
| Local-peak extraction, 1,000 grids | 404.236 → 65.674 ms, 6.15× | Same geometry | Replace the Python loop with the exact vector rule |
| Fine CFO | FFT 0.486 ms; GEMM 1.269 ms | FFT 1.842 ms; GEMM 0.776 ms, 2.38× | Standard FFT; Research factored GEMM |
| Conditioned CFO | 1.267 → 0.511 ms, 2.48× | 2.576 → 0.760 ms, 3.39× | Factored GEMM in both lanes |
| GLRT exact/control pair | 0.128 → 0.099 ms, 1.29× | 0.639 → 0.136 ms, 4.70× | Summed-autocorrelation backend; Research benefits most |
| Conditioned correlation workspace | 0.912 → 0.811 ms, 1.13× | Same selected-symbol geometry | Safe but low priority |
| Coarse native ISA, unpadded | 30.806 → 30.111 ms, 1.02× | 171.108 → 115.243 ms, 1.48× | Native dispatch matters directly for Research |
| Coarse native ISA plus execution shape | 11 lanes 30.199 → 12 lanes 22.319 ms, 1.35× | 81 lanes beat padded 84/88 | Pad Standard to 12; do not pad Research |

### Why 12 internal lanes are not a parameter change

Standard still returns exactly the existing 11 CFO rows. The native kernel computes one
extra finite dummy row so its inner CFO loop has a more favorable vector shape, then the
wrapper discards that row before peak extraction. Against the portable 11-row oracle,
the retained score surface differed by at most `1.67e-16` with zero argmax changes.

Padding to 16 was slower than padding to 12. Padding Research from 81 to 84 or 88 was
also slower. “More power-of-two-like” is therefore not a useful rule by itself; the
measured vector width and loop body decide the execution shape.

## Cache and working-set interpretation

| Object | Standard | Research | Interpretation |
|---|---:|---:|---|
| One complex128 probe | 0.76 MiB | 0.76 MiB | Fits comfortably in shared cache |
| Fine direct rotation bank | 8.08 MiB | 5.06 MiB | Standard bank is too costly versus N=5,000 FFT; Research bank is effective with GEMM |
| Conditioned rotation bank | 2.09 MiB | 4.12 MiB | Factoring avoids materializing the base-frequency copy for every candidate |
| Fine FFT scratch, 15 frames | 1.14 MiB | 5.72 MiB | Standard FFT remains compact; Research FFT repeats a larger transform for only 201 requested bins |

With four paths and up to four threads per path, these per-probe objects can multiply into
shared-L3 and memory-bandwidth pressure. The default scheduler completed the duplicate
four-path corpus gate deterministically, but RSS, cache misses, completed probes/s, and
p50/p95 latency remain required before any future concurrency or affinity change.

## Implementation bundles

### Bundle A: exact portable Python/NumPy backends — implemented

1. Vectorize the plateau-aware local-peak rule.
2. Factor the first CFO phase and use matrix multiplication for conditioned grids.
3. Dispatch Standard fine search to its exact N=5,000 FFT and Research fine search to
   factored direct GEMM.
4. Evaluate GLRT through summed short autocorrelations and two final transforms.
5. Factor frame-common phase in the conditioned workspace, retaining it only if the
   corpus result justifies its modest isolated gain.

This bundle keeps the portable native extension and is the simplest fallback-capable
release unit.

### Bundle B: runtime native execution — implemented

1. Keep the current portable C kernel as the baseline function.
2. Add a narrowly scoped `avx2,fma` target function and select it with runtime CPU-feature
   detection; do not compile the entire package with `-march=native`.
3. Pad only Standard's internal coarse bank from 11 to 12 lanes and slice back to the 11
   scientific rows.
4. Leave Research at 81 execution lanes.
5. Exercise both the feature-selected path and forced portable fallback in tests.

Bundle B is not an AVX-only package. Runtime feature detection keeps the portable kernel
available and recovery independent of one host generation.

## Hybrid-core follow-up

The release keeps the scheduler-default policy, which passed the complete corpus run.
The remaining affinity-only Research experiment uses the same corpus and current
production concurrency rather than another isolated probe loop:

| Run | Process/core policy | Path workers | Purpose |
|---|---|---:|---|
| A | Scheduler default, all 24 cores | 4 per path | Control matching production |
| B | Eight P cores only | 4 per path | Lowest possible per-probe latency; likely oversubscribed |
| C | Sixteen E cores only | 4 per path | Maximum core capacity but slower probes |
| D | P cores reserved for foreground; workers may use E plus remaining P capacity | 4 per path | Candidate operational policy |

Each run processes the same bounded four-path input twice. Report wall time, process CPU,
probes/s, p50/p95 probe latency, maximum RSS, API latency, and acquisition-loop lateness.
No worker-count increase is included: the existing two 2×2 trials already found that six
threads/path did not improve the whole system.

## Relationship to power-of-two parameter variants

The earlier T1 parameter report remains valid. Standard's radix-2 fine profile was 1.8%
slower and changed one winner epoch; Research's aligned profile saved 3.9% but changed its
CFO lattice. Those profiles remain named Research experiments.

T3 changes the expected value of rerunning them. Once current Research uses the much
faster 201-bin GEMM backend, reducing its fine grid to 133 radix-2-aligned bins can affect
only a smaller fraction of total runtime. Power-of-two parameters should therefore be
reevaluated for scientific resolution or hardware implementation constraints, not as the
default performance fix.

## Qualification and rollback gates

Release qualification completed the following:

1. Component tests cover randomized, zero, nonfinite, short-tail, fractional-CFO,
   2.4 MS/s fallback, and frame-boundary geometries.
2. Portable and AVX paths are forced in the same test process and their complete score
   surfaces.
3. The protected one-second Trial 132 frozen-equivalence test passed.
4. The immutable 50-probe T1 set preserved candidate counts, ranks, epochs, winner
   identities, and hit inventory.
5. Two concurrent scheduler-default four-path runs were deterministic, and a full
   deployed-release A/B preserved candidate and trajectory geometry.
6. Deployment uses runtime CPU-feature selection with a portable kernel and the guarded
   exact-release rollback path.

No golden scientific fixture was modified. The historical full-run golden describes the
older 1,200-probe-per-path schedule, while both current Main and this candidate emit
2,400 probes per path; its count assertion is therefore already stale against the
deployed baseline. Qualification used the reviewed one-second frozen gate plus a direct
deployed-release/candidate full-corpus A/B. The old golden remains immutable pending a
separate explicit scientific review.

## Reproduction

The study benchmark is `tools/benchmark_glrt_hardware_execution.py`. The P/E result files
record every repetition, environment variable, affinity, configuration, working-set size,
and numerical delta:

- [P-core portable-versus-native prototype](figures/2026_08_22_t3_glrt_hardware_execution_alignment/p-core-native-prototype.json)
- [E-core portable-versus-native prototype](figures/2026_08_22_t3_glrt_hardware_execution_alignment/e-core-native-prototype.json)
- [P-core portable prototype detail](figures/2026_08_22_t3_glrt_hardware_execution_alignment/p-core.json)
- [E-core portable prototype detail](figures/2026_08_22_t3_glrt_hardware_execution_alignment/e-core.json)
- [SIMD and execution-padding study](figures/2026_08_22_t3_glrt_hardware_execution_alignment/simd-execution-study.json)
- [Built P-core implementation](figures/2026_08_22_t3_glrt_hardware_execution_alignment/p-core-implemented.json)
- [Protected-corpus qualification summary](figures/2026_08_22_t3_glrt_hardware_execution_alignment/qualification-summary.json)

The implementation is component-tested, wheel-built, and protected-corpus qualified.
Public contracts, scientific search parameters, golden fixtures, and QNAP paths remain
unchanged. Deployment and its post-cutover receipt are the final operational gate.
