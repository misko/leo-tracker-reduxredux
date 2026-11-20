# Bounded catalogue memory in v5

On two stored-GLRT recordings, batching full-catalogue propagation and retaining the residual screen's freshly owned orbit arrays reduced the numerical worker's measured peak RSS by **8.36% on DS26-0036** and **16.79% on DS29-0082**. All four geographic endpoints, conditional Doppler RMS values, RF objectives, association counts, and recovery decisions matched the frozen controls exactly. [Protocol](PROTOCOL.md) · [Measured receipt](receipt.json)

## What changed

Residual screening and final admission each propagate the causal catalogue on 381 knots. DS26's 11,137 satellites produce 203,673,456 bytes of ECEF position and velocity arrays. DS29's 11,186 produce 204,569,568 bytes. During the stock propagation, SGP4 retains the TEME position and velocity, and the ECEF conversion adds rotated and Earth-rate arrays. The candidate propagates 256 adjacent catalogue rows at a time using the original kernel and places the results into the full ordered float64 arrays. The separate reassociation propagation audit remains unchanged. A 517-satellite archived snapshot gave exact ECEF positions, velocities, and usability bits across the batch boundary. [Numerical check](numeric-check.json)

The stock residual screen also holds the full ECEF arrays, boolean-indexed eligible arrays, and an immutable byte snapshot of those eligible arrays. The candidate retains the freshly created eligible arrays through read-only buffers. The hook is bound to the frozen residual screen, which immediately replaces the local dictionary that constructed those arrays. It checks each array's exclusive reference, native float64 type, ownership, and contiguous layout. Aliases or views use the original copying constructor. The time grid remains independently copied, and the original shape and finite-state validation still runs. Each measured final candidate retained exactly one bank without entering the fallback. [Implementation](../../../tools/pipeline_eval/variants/v5_catalogue_memory.py) · [Ownership and validation tests](../../../tests/pipeline_eval/test_v5_catalogue_memory.py)

## Peak RSS and time

Each recording's workers used the same pinned x86 core, single-threaded numerical libraries, and the same instrumentation. RSS is the Linux high-water of the numerical worker. Wall and total CPU cover compilation and the complete invocation from archived detections through the final paired positions.

| Recording | CPU core | Stock → candidate peak RSS (KiB) | Stock → candidate CPU (s) | Stock → candidate wall (s) |
|---|---:|---:|---:|---:|
| DS26-0036 | 20 | 1,420,016 → 1,301,324 | 154.54 → 132.64 | 155.83 → 133.37 |
| DS29-0082 | 21 | 1,298,192 → 1,080,176 | 117.54 → 94.71 | 118.32 → 96.13 |

Batching alone lowered the observed ECEF-stage pressure and gave mixed worker peaks. The first candidate reached 1,515,812 KiB on DS26 and 1,280,424 KiB on DS29 while the residual screen still made the byte snapshot. With the retained bank, residual-screen CPU fell from 10.83 to 6.36 seconds on DS26 and from 25.76 to 21.68 seconds on DS29. These are single executions in each order. The later candidate also entered residual screening with a different cumulative high-water, especially on DS26. The total CPU and RSS differences describe the measured runs on this host. [DS26 stock trace](DS26-0036-compact_finish-stages.jsonl.gz) · [DS26 first attempt](DS26-0036-propagation-only-stages.jsonl.gz) · [DS26 final trace](DS26-0036-v5_catalogue_memory-stages.jsonl.gz) · [DS29 stock trace](DS29-0082-compact_finish-stages.jsonl.gz) · [DS29 first attempt](DS29-0082-propagation-only-stages.jsonl.gz) · [DS29 final trace](DS29-0082-v5_catalogue_memory-stages.jsonl.gz)

## Calibration and positions

Each pair below gives `c = 0` followed by fitted `c`. The two methods used identical stored detections, causal TLEs, the original receiver region, candidate sets, priors and fit budgets. The candidate and stock also matched both arms of the independent frozen full-v5 replay exactly.

| Recording | Geographic error (km) | Conditional Doppler RMS (Hz) |
|---|---:|---:|
| DS26-0036 | 1.278 / 1.208 | 74.761 / 74.682 |
| DS29-0082 | 0.567 / 0.517 | 97.004 / 96.684 |

The RF metric measures the selected fit and the geographic column is scored independently against the receiver location. [Retained-bank predictions](positions.jsonl.gz) · [Stock predictions](stock-positions.jsonl.gz)

The first experiment and refinement can be reproduced with the same case-specific affinity. Run the two commands for each recording in sequence. Both recordings can run in parallel on distinct cores.

```sh
taskset -c 20 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python -m tools.pipeline_eval.qualification.catalogue_memory_eval \
  --case DS26-0036 --out /tmp/catalogue-pairs
taskset -c 20 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python -m tools.pipeline_eval.qualification.catalogue_memory_eval \
  --case DS26-0036 --retain --out /tmp/catalogue-retained
taskset -c 21 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python -m tools.pipeline_eval.qualification.catalogue_memory_eval \
  --case DS29-0082 --out /tmp/catalogue-pairs
taskset -c 21 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python -m tools.pipeline_eval.qualification.catalogue_memory_eval \
  --case DS29-0082 --retain --out /tmp/catalogue-retained
.venv/bin/python -m tools.pipeline_eval.qualification.catalogue_memory_eval \
  --package /tmp/catalogue-pairs --retained /tmp/catalogue-retained --out /tmp/catalogue-report
```
