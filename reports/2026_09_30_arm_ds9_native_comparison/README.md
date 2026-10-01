# DS9 native ARM control / ordinary / PGO comparison

The two optimized builds preserve **all native candidate fields and counters**
on this DS9 panel, with no differences in any repeated call. Both fit the
**120 ms detector budget**, but **neither passes the preferred 100 ms maximum**:
one dwell exceeds 100 ms in all ten repetitions for both optimized builds.

This is a new physical ARM saved-IQ run, not a reuse of DS7 timings. No RF was
collected, no detector parameters or compiler profiles were trained on DS9,
and no capture worker or live service was changed.

## Frozen inputs and execution

- All 80 existing 2.5 MS/s DS9 dwells in
  `/var/tmp/leo-lag-discovery-ds9-v1/inputs.json`: 20 scans, 44 lower-edge and
  36 upper-edge dwells. This is a saved subset, not the complete DS9 dataset.
- Each input is dual-RX CI16, 120 ms long. Explicit 120 ms stride processes
  the first 20 ms per receiver: 160 unique receiver-windows across the panel.
- Ten shuffled repetitions per dwell, 800 calls per build, 2,400 calls total.
  These repetitions are timing observations, not independent science samples.
- Seed `2026093001`; maximum eight unique dwells per persistent batch;
  build order rotates between batches. All three builds use identical inputs,
  templates, schedules, and within-batch call order. First calls are included.
- PLUTO+ `192.168.1.15`, Cortex-A9 CPU0, with the maintained persistent RAM
  benchmark client and a 220,000 KiB process memory cap. The target was idle
  before execution. No simultaneous-capture qualification is implied.
- The three binary and receipt hashes match the original published headroom
  experiment, and the device FP64 FFTW hash also matches. The original PGO
  binary is reused without retraining.

[panel.json](panel.json) records the complete source contexts, source/raw IQ
hashes, templates, binaries, receipts, seed, and per-call mappings. The raw IQ
staging archive is ignored by Git; original saved inputs remain unchanged.

## Physical timing

Wall time surrounds the public RAM detector call. Input preparation,
allocation, proposals, search, scoring and per-call cleanup are included.
File preload, context creation, serialization, capture, transport, queueing,
and downstream analysis are excluded. These are detector timings, not
capture-to-result latency. Percentile 95 uses nearest rank; p50 is the median.

| Build | Mean wall ms | P50 | P95 | Maximum | Calls >100 ms | Calls >=120 ms |
|---|---:|---:|---:|---:|---:|---:|
| Native control | 119.50 | 116.84 | 153.40 | 181.45 | 624/800 | 362/800 |
| Optimized ordinary | **51.36** | 48.60 | **79.31** | **101.90** | **10/800** | **0/800** |
| Optimized PGO | **50.04** | 47.20 | **78.32** | **100.25** | **10/800** | **0/800** |

| Build | Mean CPU ms | P95 CPU ms | Maximum CPU ms | Mean wall speedup vs control |
|---|---:|---:|---:|---:|
| Native control | 119.46 | 153.40 | 181.28 | 1.00x |
| Optimized ordinary | 51.35 | 79.18 | 101.90 | **2.33x** |
| Optimized PGO | 50.03 | 78.31 | 100.25 | **2.39x** |

The optimized means are close to the DS7 report's 49.64/48.45 ms ordinary/PGO
results, but their DS9 maxima exceed the former 96.05/93.93 ms maxima.
Different input panels need not have identical latency distributions.
The native control mean is likewise close to the prior 117.95 ms result.

Both optimized >100 ms tails are entirely from
`scan-fw-b34e380766e24b3b`, visit **277**, all ten repetitions. CPU time also
exceeds 100 ms, so this is not explained by wall-only scheduling delay.
Worst observed detector headroom against 120 ms is **18.10 ms** for ordinary
and **19.75 ms** for PGO. The 120 ms gate passes on this panel; the preferred
20 ms reserved headroom does not. Finite maxima do not establish a universal
hard-real-time guarantee. No additional optimization or retuning was performed.

Peak observed XADC temperatures were 72.84 C control, 72.59 C ordinary and
72.96 C PGO. Device frequency/throttling was not independently measured.
Peak process RSS was 47,676 / 32,080 / 32,076 KiB respectively, including
preloaded inputs and client state. This is not detector-only memory usage.

## Exact native-control comparison

Across the 80 unique dwells, the native control emits:

| Quantity | Native control | Ordinary | PGO |
|---|---:|---:|---:|
| Receiver-windows searched | 160 | 160 | 160 |
| All candidate entries | 298 | 298 identical | 298 identical |
| Positive candidates, margin >=0.025 | 286 | 286 identical | 286 identical |
| Windows with a positive candidate | 90 | 90 identical | 90 identical |
| Repeated calls differing from native control | 0/800 | 0/800 | 0/800 |

Comparison removes only each numerical row's `timings_ms`. It retains ordered
candidate objects, every score and coordinate, flags, candidate counts and
all non-timing row counters. Every control repetition is also compared with
the first control result for that dwell. No tolerance-based score comparison
or positive-only filter is used.

This establishes **100% preservation relative to the native control** on this
panel. It does not measure recovery against the frozen original detector or
the currently deployed fractional pipeline, and does not qualify phase,
timestamp authority, trajectories, satellite associations or positions.

## Evidence and reproduction

- [run.py](run.py): staging, hash checks, bounded execution, comparison and
  summary generation. Run from the repository with `.venv/bin/python`; it
  requires NumPy, the recorded saved corpus/builds and existing device access.
  It refuses to replace an existing panel. Use a fresh report directory for
  another run. The existing password file is referenced, never copied.
- [summary.json](summary.json): timing distributions, unique scientific counts,
  mismatches, execution order and SHA-256 of all 33 raw JSONL result files.
- [tail-audit.json](tail-audit.json): every >100 ms call, temperatures and
  speedups, from an independent pass over the saved raw results.
- [device-before.txt](device-before.txt), [device-after.txt](device-after.txt):
  device snapshots and shared-library hashes.
- `local/{control,ordinary,pgo}-{lower,upper}-*.jsonl`: complete raw benchmark
  outputs, including setup, call and summary records.
- `*-build-receipt.json`: the exact original build receipts.

Execution completed successfully in about 277 seconds including staging.
An independent readback verified every raw-result hash and recomputed the
reported wall-time means. No numerical component source changed and no new
hardware unit suite was run; this experiment directly exercises the three
previously qualified binaries on DS9.
