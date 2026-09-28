# Forty-percent headroom optimization

**Achieved in two recorded-cadence contention runs: 44.05% and 42.66% CPU0
headroom.** Selected candidate: `goal40mag`. This is a qualified benchmark
build, not a deployed live-IQ feedback pipeline.

| Recorded-cadence run | CPU0 busy | CPU0 headroom | CPU1 busy | Mean GLRT CPU | Published response p95 |
|---|---:|---:|---:|---:|---:|
| First | 55.95% | 44.05% | 32.13% | 70.86 ms | 161.41 ms |
| Repeat | 57.34% | 42.66% | 34.13% | 72.21 ms | 170.39 ms |

Each run delivered 330/330 live capture visits and completed 330/330 GLRT
jobs. All 660 receiver outputs per run matched the qualified candidate.
Each overlap measurement includes 38 complete one-second CPU intervals and
288 fully completed GLRT jobs. Capture and IRQ settings were restored.
These are short measured runs, not a guarantee for every signal or load.
Queue delay for the first/last 50 jobs was 45.12/41.22 ms in the first run
and 45.14/45.69 ms in the repeat; final queue delays were 0.085/0.091 ms.
Bursty arrivals still produced 101/288 and 152/288 responses above 120 ms
during overlap, despite adequate average throughput.

## Continuous 120-ms stress result

The fixed-period run completed 500/500 jobs, with 1,000/1,000 matching
receiver results, and delivered 330/330 live capture visits. During overlap,
373 jobs completed with **zero published responses above 120 ms**: p95
101.66 ms, maximum 113.95 ms. Mean GLRT CPU was 75.68 ms, CPU0 busy 66.07%
and CPU1 busy 38.00%, over 43 complete CPU intervals. CPU0 headroom was
**33.93%**: the 40% goal is met for recorded adaptive arrivals, not continuous
120-ms arrivals. These finite observations do not establish a hard real-time
guarantee. Evidence: `persistent/runs/opt-goal40mag-fixed120/qualification.json`.

## Selected implementation

The selected build adds bounded block phase-rotation generation, an FP32
coarse differential dot product, and a bounded magnitude fast path to
`goal40a` below. The magnitude path retains robust libc fallback. Both
receivers, all six ranking windows, confirmation work, frame support and
the original recorded arrival schedule remain intact.

## All-rate saved-file results

Mean of each real case's five-repetition CPU median; both receivers run
serially on CPU0. All 104 ARM cases and 104 host sanitizer cases passed the
existing scientific gates against original D.

| Sample rate | Real cases | Original D | Selected build | Speedup |
|---|---:|---:|---:|---:|
| 2.5 MS/s | 32 | 108.06 ms | 67.06 ms | 1.61x |
| 5 MS/s | 32 | 202.10 ms | 124.81 ms | 1.62x |
| 7.5 MS/s | 8 | 310.34 ms | 199.79 ms | 1.55x |
| 10 MS/s | 8 | 389.36 ms | 239.94 ms | 1.62x |

There are also six noise/pilot/tone controls per rate. Decisions and CFO
estimates are unchanged; floating diagnostics are scientifically qualified,
not all bitwise identical to original D. See
[the detailed numerical audit](GOAL40MAG_SCIENCE_AUDIT.md).
The 10-MS/s real cohort has no positives; planted controls cover positives.
Higher-rate saved-file support does not establish live real-time throughput.
The current live firmware advertises 2.5/10 MS/s; live 5/7.5 MS/s remains
unqualified. Existing [four-rate examples](../EXAMPLES.md) retain input and
template conventions; use `goal40mag` as the optimized implementation.

## Headroom definition

Target: 192.168.1.15, 2.5 MS/s dual-RX adaptive scan. The completion criterion
is CPU0 busy at most 60% over complete one-second intervals in the common
live-capture/GLRT window, using the recorded adaptive arrival schedule. GLRT
remains one thread on CPU0; capture and Ethernet IRQ work use CPU1. This is not
a claim that the entire pipeline uses only one physical core. Continuous
120-ms input pacing is retained as a separate stress test.

The scientific workload remains six ranking windows and one confirmation per
receiver, with unchanged frame and known-symbol support. All four sample rates
remain in qualification. No input-result caching, window removal, receiver
removal or slower arrival schedule is used to manufacture CPU headroom.

## Initial combined candidate: goal40a

Compared with the earlier `rankunroll` candidate, this combines:

- Exact register-resident coarse folding and widening NEON rank arithmetic.
- Exact integer CI16 energy; floating/tone-subtracted IQ retains the original
  floating path. Unneeded tone-fit energy is deferred until the tone screen.
- One peak enumeration per coarse grid, persistent initialization of unused
  CFO rows, and reuse of the already evaluated retained center score.
- FFTW FP32 rank FFTs, precomputed support reciprocals, and an FP32 NEON
  conditioned-frequency dot product. Final GLRT statistics remain FP64.
- Cached rotated GLRT templates, bounded sample indexing, and reduced
  fine-FFT copy/conversion traffic without changing FFT inputs or sizes.

`goal40a` passes 104/104 host ASAN/UBSAN scientific cases and the initial
14-case ARM gate. Host timing/CFO decisions are unchanged; maximum final
score difference from original D is 2.0e-15. This is scientific equivalence
under the existing gates, not bitwise identity of every diagnostic float.

The first 45-second capture run delivered 330/330 visits and completed all
330 scheduled GLRT jobs. All 660 receiver results exactly matched the
candidate's already qualified static outputs. Original-D scientific checks
and candidate repeatability checks are recorded separately.

During overlap, CPU0 busy was **63.47%**, giving **36.53% headroom**: below
the requested goal. Mean GLRT CPU was 82.87 ms; p95 published response was
201.66 ms. Radio, kernel-buffer and IRQ settings were restored. Evidence:
`persistent/runs/opt-goal40a-recorded-cadence/qualification.json`.

## Qualification details

`test_coarse_fold_v2.c` executed 220 ARM NEON fold comparisons and 220 energy
comparisons, including CI16 extrema, partial windows and all rates, with zero
exact mismatches. `test_fine_io.c` passed 36 wrapped FFT-output range checks
under host ASAN/UBSAN, including input allocations only as long as the used
prefix. GLRT rounded-endpoint tests cover all rates and near-integer offsets.

`prepare_worker_reference.py` creates repeatability receipts only after the
original-D scientific gates pass and binary hashes match. Legacy `-D.json`
filenames are retained solely for compatibility with the receipt reader;
the manifest and stored method explicitly identify the candidate. The
`summarize_candidate_phase.py` wrapper records that distinction and the CPU
headroom calculation in each phase's `qualification.json`.

Excluded experiments include `FFTW_MEASURE` (approximately 7 ms slower),
full FP32 GLRT (slower despite passing science gates), and prefix-sum rank
projection (no worthwhile gain). Separate sources and raw receipts are kept
so a discarded result cannot be mistaken for the selected implementation.

As before, live RF provides real capture/network/memory contention while GLRT
processes resident historical IQ. An integrated pipeline consuming each new
live visit and applying GLRT feedback is still separate work. Burst-arrival
latency and a hard 120-ms deadline are distinct from average CPU headroom.

## Reproduction and retained evidence

Selected ARM probe SHA256:
`2f3d90978343b7e51bfe039e5a20fa9090b35ebccb26992d132f6a9c4d82f249`.
The source snapshot and compiler command are in `work/goal40mag/`;
`arm-all/` contains the full physical ARM qualification and `host-check/`
the sanitizer qualification. Persistent worker build receipts separately
identify the paced and recorded-arrival executables and identical kernels.

From the repository root, rerun saved-file qualification into a fresh output
directory (no RF), or run a bounded concurrent phase:

```sh
.venv/bin/python reports/2026_09_27_plutoplus_static_arm/optimize/arm_check.py goal40mag --all --output-name arm-recheck
.venv/bin/python reports/2026_09_27_plutoplus_static_arm/optimize/persistent/run_phase.py recheck --candidate goal40mag --recorded-arrivals --jobs 330 --seconds 60 --capture --irq1
.venv/bin/python reports/2026_09_27_plutoplus_static_arm/optimize/summarize_candidate_phase.py reports/2026_09_27_plutoplus_static_arm/optimize/persistent/runs/opt-goal40mag-recorded-recheck --candidate goal40mag
```

The latter starts 45 seconds of receive-only capture. Do not overlap hardware
benchmarks or SD transfers. Four-rate standalone target examples are in
`../EXAMPLES.md`. The target executable is `opt-goal40mag` in
`/mnt/glrtbench/leo-static-glrt.4jwvdm`.

This goal used four 45-second RX-only capture runs: the initial goal40a,
two selected recorded-arrival runs, and selected fixed120 stress, totaling
180 seconds. All restored radio/kernel-buffer/IRQ settings. No production
firmware or capture service was replaced. Continuous full-rate dual-RX raw
SD recording remains limited by the previously measured SD write rate.

The report tree, sources, tests, build receipts and raw results are retained
on the SD as `goal40-20260927.tar.gz` and extracted under
`goal40-reproduction` in the same target directory. Archive hash verification
is recorded locally in `goal40-sd-copy.json`. Discarded candidates remain
experimental artifacts; only `goal40mag` is selected by this report.
