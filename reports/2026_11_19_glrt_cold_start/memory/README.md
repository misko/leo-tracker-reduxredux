# Memory during the compact v5 fit

Batching the existing conservative salvage score reduced peak RSS through that stage from **1,356,620 to 981,736 KiB** on DS26-0036. Peak for the complete numerical worker fell from **1,472,540 to 1,414,540 KiB**, a 3.94% reduction. Both final positions, conditional frequency metrics and recovery decisions matched the frozen compact finish exactly. The worker still exceeds the previously measured Pluto+ RAM capacity. [Worker receipts](receipt.json) · [Archived physical-memory measurement](../../2026_11_19_receiver_frontend/embedded/README.md)

## Where memory peaks

One stock worker ran from the original stored GLRT detections through both final positions. The profiler recorded `ru_maxrss` at stage entry and exit, which captures peaks even when a stage releases its arrays before returning. Stage figures below are cumulative process high-water marks. Each complete run used one pinned x86 logical CPU and one numerical thread. [Stock stage trace](control-stages.jsonl.gz) · [Candidate stage trace](candidate-stages.jsonl.gz)

| Stage completed | Stock high-water (KiB) | Batched high-water (KiB) |
|---|---:|---:|
| Native input preparation | 590,428 | 590,364 |
| Initial discovery and selection | 970,976 | 967,348 |
| Conservative recovery | 1,356,620 | 981,736 |
| Residual screening | 1,472,172 | 1,406,084 |
| Reassociation catalogue preparation | 1,472,540 | 1,414,540 |

Conservative salvage evaluates 81 orbital-phase cells per satellite. Its largest logged input was a 123,444 × 80 float64 prediction matrix, **79,004,160 bytes**. The original Gaussian likelihood also builds raw residual, whitened, innovation and related temporary arrays. The candidate invokes that same profile on contiguous blocks of candidate rows, capped at 1 MiB of prediction values per block for the recorded geometry. It writes the returned fields into preallocated arrays in the original order, preserving the original shortlist and position policies. The full prediction and result arrays remain resident where the caller needs them. [Variant implementation](../../../tools/pipeline_eval/variants/v5_batched_salvage.py)

The remaining global high-water occurs in the residual and reassociation catalogue work. Residual screening propagates the full causal catalogue on a 381-knot grid, converts TEME to ECEF, copies eligible rows, and takes a further immutable-byte snapshot of the ECEF state bank for repeated trials. Reassociation separately prepares and audits its catalogue. A confirmation through the delivered CLI measured **1,269,864 KiB** at the end of residual ECEF propagation alone, up from 971,524 KiB. Its process high of **1,369,440 KiB** occurred later in the catalogue work. The two batched runs bracket observed process-memory variation. Both reproduced the same science. [Confirmation stage trace](cli-confirmation-stages.jsonl.gz) · [All worker receipts](receipt.json)

## Matched position and time

Both arms used the original observations, causal catalogue, region, candidate inventory and fit budgets. `c = 0` gave a **1.278 km** error and **74.761 Hz** conditional RMS. Fitted `c` gave **1.208 km** and **74.682 Hz**. Each arm retains 2,690 associated observations. Both methods produced the same endpoint and objective for each arm. A shape-matched synthetic likelihood also preserved every alias and the ordered top 30 candidates. The largest per-candidate score rounding difference was 3.64e-12 when BLAS operated on smaller batches. [Stock positioning row](stock-positions.jsonl.gz) · [Batched positioning row](positions.jsonl.gz) · [Synthetic check](profile-numeric-smoke.json)

| Measurement | Stock | Batched |
|---|---:|---:|
| Conservative recovery CPU (s) | 18.80 | 19.04 |
| Complete worker wall (s) | 157.81 | 166.89 |
| Complete worker CPU (s) | 157.41 | 162.09 |

The timing is one run per method on adjacent pinned logical CPUs. The measured boundary runs from archived detections through the position fit on x86 for this recording.

Reproduce from the repository root with the existing corpus bindings, a fresh output path and one available logical core per run. The fixture verifier checks the frozen input digest, exact coordinates, conditional metrics, associated counts, and both adoption decisions after each run.

```sh
taskset -c 15 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  /usr/bin/time -v timeout 260s .venv/bin/python -m \
  tools.pipeline_eval.qualification.batched_salvage_eval --mode control --out /tmp/v5-memory-stock
taskset -c 16 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  /usr/bin/time -v timeout 260s .venv/bin/python -m \
  tools.pipeline_eval.qualification.batched_salvage_eval --mode batched --out /tmp/v5-memory-batched
taskset -c 15 env OPENBLAS_NUM_THREADS=1 .venv/bin/pytest -q \
  tests/pipeline_eval/test_v5_batched_salvage.py tests/pipeline_eval/test_compact_finish.py
```
