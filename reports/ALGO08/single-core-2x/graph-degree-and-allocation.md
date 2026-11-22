# Track-fitting bounds and whole-solver allocation

An exact stopping rule for polynomial degree search reduced mean Graph preparation CPU by **0.274 s on DS30-0008** and **0.085 s on the southern portable simulation**. A separate whole-solver experiment with jemalloc used more CPU and memory on the Indian simulation. Neither result justifies a larger physical panel. [Track preparation receipts](measurements/graph-degree-reversed.json) · [Allocator receipts](measurements/solver-allocator-india.json)

## The cost of a higher degree

Graph compares polynomial fits on the same observations. Its criterion adds the sum of squared wrapped residuals to a penalty of `(degree + 1) × log(number of observations)`. A higher degree cannot win once its penalty alone reaches the cost of an admissible lower degree. An exact tie belongs to the earlier degree. The experimental selector also computes the maximum degree supported by the number of observations, distinct times, and gaps once per support. It evaluates the original slope test only for a fit whose cost could improve the incumbent. Polynomial fitting, residual arithmetic, alias lifts and the slope limit use the original routines. [Selector](../../../tools/pipeline_eval/variants/experimental/graph_degree_bound.py) · [Degree, support and alias tests](../../../tests/pipeline_eval/test_graph_degree_bound.py)

| Saved detections | Mean original CPU | Mean bounded CPU | Assigned observations | Tracks / curved tracks |
|---|---:|---:|---:|---:|
| DS30-0008 | 1.820 s | 1.546 s | 6,456 | 236 / 111 |
| Southern portable | 0.985 s | 0.900 s | 5,350 | 27 / 25 |

Both orders used the same frozen native graph path. Each case ran original, bounded, bounded, original under the Gauss lock on CPU 2. All four serialized preparation digests agreed at each site, covering the observations, polynomials, owned evidence and curved selections passed to the solver. Each order saved CPU. The first original roof run took 3.46 s elapsed on 1.93 CPU s, so the table uses process CPU. This measurement ends with track preparation. [Runner](graph_degree_trial.py)

## Memory allocation throughout a saved solve

The second comparison applied the system jemalloc library with its default settings to the frozen restored-scout process. Each of four fresh processes solved the same containing Indian offer with the same causal archive and fixed-zero and fitted calibration arms. We reversed the order in the second pair. Both coordinates, frequency residuals, owner maps, path and grid matched across the four runs. [Saved solver runner](solver_allocator_trial.py)

| Mean of two runs per allocator | System | jemalloc |
|---|---:|---:|
| Complete saved-solver CPU | 5.563 s | 5.909 s |
| Complete saved-solver elapsed | 5.658 s | 5.995 s |
| Peak process RSS | 632.5 MiB | 656.2 MiB |

The allocator increased mean solver CPU by 6.2% and peak process memory by 23.7 MiB on this case. The integrated research build keeps the system allocator.

## Reproduction

Use fresh filenames and an unused output directory. Both commands run on the shared low-priority core.

```sh
bench=/tmp/leo-algo08v2-2x-bench
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
trial() {
  flock "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env PYTHONPATH=.:src OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    "$release/venv/bin/python" -BPs -m "reports.ALGO08.single-core-2x.$1" "${@:2}"
}
trial graph_degree_trial "$bench" "$release/assets/tracks.json" "$bench/new-degrees.json"
trial solver_allocator_trial "$bench" "$bench/new-allocator"
```
