# Narrow native GLRT preparation

Decoding one probe at a time and releasing the private detector document after tracking lowered the measured high-water through native preparation from **589,428 to 553,072 KiB** on DS26-0036 and from **632,148 to 606,236 KiB** on DS29-0082. The stock and candidate had identical prepared observations, graph tracks, and metadata in both recordings. Narrow decoding added about 0.3 CPU seconds at the read boundary. [Protocol](PROTOCOL.md) · [Receipts](receipt.json)

The candidate verifies the complete native archive digest and uses the standard JSON decoder for individual probes. It stores only the six fields the tracker reads from each recognized fractional candidate and leaves every candidate in its original list and order. The two unused score fields remain in the source archive. Other metadata and unrecognized records retain their original representation. The original graph fitter, receiver clocks, candidate gates, RF lanes and geometry receive the same values. The reader holds the decoded JSON text in memory while preparing probes. A fresh private document is released when the graph returns, before causal sky and phase-history preparation. [Worker](../../../tools/pipeline_eval/variants/v5_stream_prepare.py) · [Parser tests](../../../tests/pipeline_eval/test_v5_stream_prepare.py)

## Preparation measurements

The detector input audit compared every probe and candidate. Python container measurements exclude scalar values, the JSON text, and other allocations. The stage RSS counters cover the complete numerical process up to that boundary.

| Recording | Native JSON bytes | Probes | Candidates | Stock → candidate container bytes |
|---|---:|---:|---:|---:|
| DS26-0036 | 22,647,323 | 13,530 | 59,973 | 16,312,656 → 5,277,624 |
| DS29-0082 | 16,526,343 | 9,736 | 42,162 | 11,468,064 → 3,710,256 |

| Boundary | DS26 stock → candidate | DS29 stock → candidate |
|---|---:|---:|
| Native reader CPU (s) | 0.166 → 0.489 | 0.121 → 0.424 |
| Reader and native preparation CPU (s) | 17.51 → 17.27 | 20.02 → 20.50 |
| Resident RSS after graph (KiB) | 311,984 → 305,784 | 289,640 → 285,580 |
| Peak RSS through native preparation (KiB) | 589,428 → 553,072 | 632,148 → 606,236 |

Both workers used one pinned host core for each capture, with the same instrumentation and the numerical libraries limited to one thread. Parsing accounts for a small part of native preparation. The larger phase includes the original causal sky, phase history and related operations. The stock and candidate exposed the same graph digest before that phase, with 3,395 observations and 94 tracks on DS26, and 1,868 observations and 61 tracks on DS29. [Input audit](input-shape.json) · [Stage timings and process memory](receipt.json)

The end-to-end measurements were mixed. Each row represents one paired replay on the same shared host. Complete CPU and wall times include worker launch and kernel compilation. Peak RSS is the numerical process high-water.

| Recording | Stock → candidate peak RSS (KiB) | Stock → candidate CPU (s) | Stock → candidate wall (s) |
|---|---:|---:|---:|
| DS26-0036 | 1,416,864 → 1,486,696 | 175.40 → 177.29 | 180.29 → 184.97 |
| DS29-0082 | 1,310,704 → 1,281,552 | 133.53 → 133.05 | 139.62 → 137.12 |

## Geographic and frequency results

Each pair gives `c = 0` followed by fitted `c`. Geographic error uses the known receiver position for scoring after inference. Conditional RMS measures the matched selected RF fit. The two methods used matched observations, causal snapshots, region, priors and fit budgets.

| Recording | Geographic error (km) | Conditional Doppler RMS (Hz) |
|---|---:|---:|
| DS26-0036 | 1.278 / 1.208 | 74.761 / 74.682 |
| DS29-0082 | 0.567 / 0.517 | 97.004 / 96.684 |

Both arms matched the paired stock and independent frozen v5 endpoints, RF objectives, conditional RMS, associated counts, and recovery decisions exactly. [Candidate positions](positions.jsonl.gz) · [Stock positions](stock-positions.jsonl.gz)

## Reproduce

```sh
taskset -c 20 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python -m tools.pipeline_eval.qualification.stream_prepare_eval \
  --case DS26-0036 --out /tmp/stream-prepare
taskset -c 21 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python -m tools.pipeline_eval.qualification.stream_prepare_eval \
  --case DS29-0082 --out /tmp/stream-prepare
.venv/bin/python -m tools.pipeline_eval.qualification.stream_prepare_eval \
  --package /tmp/stream-prepare --out /tmp/stream-prepare-report
```
