# Server runtime review: 2.5 and 10 MS/s

Measured 2026-10-06 around 00:58–01:09 UTC (October 5 Pacific), on the
deployed Python 3.14 / AVX2 code, after the CFO tiling deployment. The server is
an Intel Core Ultra 9 285K with 24 logical CPUs. Production limits stayed at
13 analysis leases and 6 tracking leases. No RF collection, queue interruption,
scientific configuration change, or production deployment was performed.

## Findings

The next improvements should address **nested CPU concurrency**, **tracking
contract construction/validation**, and **rate-specific GLRT kernels**. Disk
reading is a small part of the sampled GLRT work. More queue workers would add
contention before addressing these costs.

### GLRT: different bottlenecks at the two rates

Four saved visits (0, 71, 503, 1701) per rate were replayed serially through the
deployed detector with its 120 ms probe stride. Profile totals include reading
IQ and building the complete visit result.

| Profile | 2.5 MS/s | 10 MS/s |
| --- | ---: | ---: |
| Session | `scan-fw-c4a9c707b55aa15e` | `scan-fw-aadec7177d989684` |
| Profiled time, four visits | 1.072 s | 10.276 s |
| Probe evaluations | 11 | 9 |
| Native coarse CFO search | 13.6% | 63.0% |
| Fractional refinement, inclusive | 39.7% | 13.0% |
| Fractional interpolation, nested within refinement | 17.2% | 7.8% |
| Coarse peak sorting | 9.3% | 5.3% |
| IQ read | 4.2% | 1.4% |

These are **profile shares on these visits**, not fleet averages or full-scan
runtime estimates. Different probe counts, signal content, host load and CPU
placement prevent treating their ratio as a controlled sample-rate experiment.
cProfile also adds overhead, especially to Python-heavy paths.

The earlier exact CFO tiling change already reduced CPU time by 31.7% across
24 paired 10 MS/s visits, with identical published visit products. See
[the earlier benchmark](../2026_10_06_glrt_10m_profile/README.md). That is an
existing deployed improvement, not an additional saving measured here.

### Tracking: contract work matters

A 20-second, 49 Hz py-spy sample of a live core-tracking process yielded 978
stack samples. Its session, `scan-fw-ac7255886b4a00d3`, was 2.5 MS/s.

- 630/978 samples were under prediction-field bank construction.
- 250/978 were under `_roundtrip_revalidate_inputs` (25.6%).
- 238/978 were under final prediction-bank creation (24.3%).
- JSON encoding, Pydantic dumping/validation, and finite-value validation were
  prominent leaf frames; SGP4 was only one part of the work.

These inclusive counts overlap and must not be summed. The sample covers a
particular phase, not the entire tracking job. All six live tracking sessions
checked at sampling time were 2.5 MS/s; there is **no live 10 MS/s core-tracking
measurement** in this review.

An elegant optimization is to reduce repeated construction of the same
validated numerical data *within the owning component*, keeping the public
contract and boundary validation intact. Simply disabling round-trip validation
would remove deliberate protection against mutated or bypass-constructed input
and is not an acceptable speedup. A follow-up must preserve the mutation-rejection
tests, output digests, candidate inventory, tau grid, and scoring decisions.

### Position: geometry and repeated work

A separate 20-second sample of a live position child yielded 452 samples;
427 were under point evaluation. Array reductions, vector norms, visibility
interpolation, and gathering mapped position/velocity arrays dominated the
sample. Four position children were running for that one tracking lease.
Summed child RSS would double-count shared mapped pages; it is not a memory
usage estimate.

Bounded read-only replays also exercised both rates through input preparation,
two tracks capped at 128 observations, the first 1,024 catalogue candidates,
bank construction, and three fixed receiver points:

| cProfile phase | 2.5 MS/s | 10 MS/s |
| --- | ---: | ---: |
| Session | `scan-fw-cc609ed603589e6e` | `scan-fw-aadec7177d989684` |
| Total including imports | 30.26 s | 41.62 s |
| Input preparation | 24.88 s | 36.99 s |
| Trajectory reconstruction, nested | 11.92 s | 16.72 s |
| Support geometry, nested | 6.68 s | 13.51 s |
| Hough extraction, nested | 10.56 s | 14.26 s |
| Process peak RSS | 399 MiB | 449 MiB |

The deliberately small bank/search makes preparation dominate this replay. It
does **not** imply preparation dominates a full regional search. cProfile's
large Python-call overhead also makes these unsuitable as normal runtime
estimates. Neither replay fits the learned RF coefficient `c` or compares
localization accuracy; any later scientific localization comparison needs the
matched fitted-`c` versus `c=0` ablation.

### CPU admission needs to account for child workers

The second 10-second `/proc` delta sample found 13 GLRT processes consuming
12.56 CPU cores and 18 tracking processes (parents plus children) consuming
7.92 cores: **20.48 cores total**, excluding unrelated workloads and the replay
process. CPU pressure `some avg10` was 26.23%. This measures wall time with at
least one task waiting for CPU, not a percentage slowdown.

The 19 queue leases are not a 19-core ceiling. Each GLRT job permits two visit
threads, while each position phase creates a four-process pool. The theoretical
requested compute concurrency can reach 13×2 + 6×4 = 50 on a 24-CPU host, though
the observed usage is much lower because phases, the GIL, and memory traffic
limit simultaneous execution.

## Tested exact prototype

`tools/benchmark_hough_peak_selection.py` replaces full sorting of each Hough
accumulator with partition-based top-k selection. It preserves the original
stable tie ordering, including the selected side of a boundary tie. It runs only
inside the benchmark process; production code is unchanged.

The benchmark checks 48 ordering cases (ties, all-zero arrays, random values,
small and full selections), then compares complete input-preparation evidence
digests for both saved sessions, twice with reversed execution order. All 48
ordering checks and all four complete evidence-digest comparisons passed.

| Preparation CPU time, sum of two runs | Baseline | Prototype | Reduction |
| --- | ---: | ---: | ---: |
| 2.5 MS/s | 24.867 s | 24.009 s | 3.45% |
| 10 MS/s | 43.838 s | 28.484 s | 35.02% |

These timings were collected without cProfile. Both execution orders improved,
but this is only one session per rate on a busy heterogeneous CPU. Results
are in `hough-top-k-results.json`. This is a preparation-stage saving, not a
demonstrated full-tracking or queue-throughput gain. Promote it with
component-owned tests and a broader saved-session parity check before deployment;
it is a small, concrete implementation candidate alongside the larger work below.

## Recommended implementation order

1. **Budget CPU across the whole job tree.** Start with an explicit per-job
   inner-worker setting and benchmark 1 versus 2 GLRT threads and 1 versus 2/4
   position children at a fixed total host budget. Measure completed visits and
   point evaluations per CPU-second, queue completions, UI latency and CPU
   pressure. Then use the existing PostgreSQL admission mechanism to account
   for requested CPU slots, including position children. Avoid adding another
   queueing system. Do not change persisted scientific configuration digests
   merely for an execution-resource setting.
2. **Reduce repeated tracking contract work.** Profile a bounded saved track,
   retain immutable numerical intermediates within the component, and avoid
   redundant serialization inside hot loops. Preserve full validation at public
   boundaries and test rejection of mutated nested inputs. The live 25.6%
   round-trip-validation share identifies a target, not a promised saving.
3. **Optimize 2.5 MS/s fractional refinement.** Prototype reusable interpolation
   geometry/weights or a fused FP64 kernel. Cache only with exact keys covering
   all position bits and interpolation parameters. Preserve edge support,
   normalization, candidate order and thresholds. Halving the measured 39.7%
   refinement cost would save roughly 20% of this GLRT workload; this is an
   Amdahl estimate, not a benchmark result.
4. **Optimize the remaining 10 MS/s coarse kernel.** Keep the deployed tiling;
   investigate input/template reuse across tiles and native register-block
   choices. A further 20% kernel reduction would save about 13% of this GLRT
   workload. The previously tested generic FFT replacement did not win on this
   server, so do not port ARM FFT results without server measurements.
5. **Fuse position geometry after measuring fixed-work throughput.** Reduce
   temporary arrays and repeated fixed interpolation metadata while keeping
   FP64, catalogue membership, observations, visibility decisions, search
   budgets and priors identical. Compare points/CPU-second, numerical results,
   and proportional memory usage. Fewer position children can reduce contention
   but is not automatically faster overall.

## Evidence and reproduction

- `profiles.json`: top cumulative functions and replay timings.
- `source-hashes.json`: exact deployed source hashes, including the tiled module.
- `core-tracking-live.raw`, `position-live.raw`, `tracking-live.raw`: raw py-spy
  stack counts. The last file spans a parent switching from bank building into
  waiting for children and is not used to attribute core-tracking cost.
- `server-cpu-sample.json`: process CPU deltas, PIDs and pressure.
- `profile-glrt-10m.py`, `benchmark-tracking-memory.py`: exact replay script
  snapshots; their names predate this review. The first supports multiple local
  experiments; this review used `GLRT_VARIANT=current` only.

Run these scripts with the production interpreter and
`PYTHONPATH=/opt/leo-adaptive-memory/9181d637d/src`, with
`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1`. The interpreter is
`/opt/leo-tracker/releases/47e2705e437722daa5e6d6bb1c252d54b7a21dbc/.venv/bin/python`.
Raw cProfile binaries are retained under `/var/tmp/position-{2m5,10m}.prof` and
`/var/tmp/glrt-profile-<session>-current.prof`; the portable summaries are saved
here. Runtime modifications in the prototype apply only to its own process.

At the queue check during this review there were 13 analysis and 6 tracking
leases, 18 analysis and 70 tracking jobs pending, and zero expired active leases.
That snapshot is not a throughput measurement.
