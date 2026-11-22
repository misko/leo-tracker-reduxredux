# Row-parallel robust likelihood in the guarded solver

Packing sparse design rows for the native robust likelihood preserved both fixes and all checked numerical evidence on DS30-0374 and the India containing simulation. The physical saved solve used **0.605 fewer CPU seconds and 1.578 more elapsed seconds** than the archived Graph control. India used **0.152 more CPU seconds**. These two single observations leave the experiment well short of the 2.6-second target. The frozen candidate stays unchanged. [Timings and parity](measurements/guarded-packed-residual.json)

## Profile

The profile ran the frozen guarded and Graph solver `e279026b…` on the sealed physical detections and assigned causal archive. It reproduced the archived fixed-zero and fitted solutions. The profiled solve took 28.891 CPU seconds. The earlier unprofiled solve took 21.955. Individual profile times therefore locate work and bound priorities, with the instrumentation overhead included. [Profile runner](guarded_solver_profile.py) · [Frozen Graph control](measurements/screened-tiled-graph-freeze.json)

| Boundary | Profiled CPU |
|---|---:|
| Saved detections through native and causal preparation | 5.731 s |
| Full-sky ranking and initial phase fits | 6.016 s |
| Conservative recovery | 5.155 s |
| Family history | 3.788 s |
| Complete-family cavity nomination | 3.470 s |
| Selected evidence packet and grid | 3.940 s |
| Native C likelihood, across the preceding stages | 3.904 s |

Track preparation accounts for 1.763 profiled seconds inside preparation. The stock and exported posterior C entries account for 2.655 and 1.247 seconds within the native boundary. This boundary spans both arms and multiple stages. It still performs the original ordered row residual calculation on every variational iteration. The earlier group-moment experiment replaced some row calculations with a quadratic and had small floating-point differences. [Earlier group moments](solver-statistics.md)

## Independent observation lanes

The overlay packs eight consecutive rows sharing the same support group. Each SIMD lane accumulates one row dot product with the same coefficient order, binary64 multiplies and additions as before. The code visits the residual and group-energy rows in the original order. It preserves the original design, Gamma updates, condition checks and stopping rules. The packed design values are bounded to 8 MiB. The original scalar arithmetic handles short runs, unavailable AVX2 on x86 and allocation failures. The experiment compiled separate ordinary and posterior-export libraries and retained the frozen Python likelihood, proposal policies, gates and full grid. [Native calculation](../../../tools/pipeline_eval/variants/algo08_packed_residual.h) · [Research adapter](../../../tools/pipeline_eval/variants/algo08_packed_residual.py)

| Saved input | CPU, Graph → packed | Elapsed, Graph → packed | Identical observation owners per arm | RMS, fixed-zero / fitted |
|---|---:|---:|---:|---:|
| DS30-0374 | 21.955 → 21.350 s | 22.383 → 23.961 s | 2,905 | 101.535913 / 101.519803 Hz |
| India containing | 5.566 → 5.718 s | 5.665 → 6.074 s | 517 | 15.536351 / 15.305842 Hz |

Both candidates matched the archived status and nullable reason, both arm endpoints and RMS, orbit policy, owners, observation counts, full numerical grid, optimizer path and objective replay. Both kept 356 checked posterior grid handoffs. The India horizontal errors stayed 1.017 and 0.751 km. The physical and India controls are the previous unprofiled Graph saved solves and were compared with one new packed solve each. There was no paired retiming of either control. The earlier India and physical timings cannot separate scheduling variation from the observed changes. No raw acquisition, figure publication or geographic qualification was measured. [Original Graph checks](screened-tiled-graph.md) · [Packed receipts](measurements/guarded-packed-residual.json)

The initial search remains the largest inference stage in the physical profile. Full-sky ranking alone used 4.110 profiled seconds, including about 1.018 seconds constructing the original discovery and phase statistics. Assignment calls across the solve used 1.389 seconds. Reaching the remaining elapsed target through this boundary would require addressing more than one kernel while preserving every branch. The observed row-parallel effect does not support another raw run.

## Reproduction

Use the same saved DS30-0374 detector and offer verified by `screened_tiled_graph_trial.py`, or the saved India containing detector, offer and archive from the earlier guarded salvage experiment. This command profiles and times a single saved input. Omit the positional profile path for an unprofiled control. Use a fresh output for each invocation. The previously profiled control and the measured packed trials used separate invocations on the shared Gauss core.

```sh
bench=/tmp/leo-algo08v2-2x-bench
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
frozen="$bench/integration-screened-tiled-graph"
trial=reports/ALGO08/single-core-2x/guarded_solver_profile.py
lock() {
  flock -x "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 "$@"
}
lock env PYTHONPATH="$PWD:$release/src:$release" "$release/venv/bin/python" -BPs -c \
  'from pathlib import Path; from sys import argv; from tools.pipeline_eval.variants.algo08_packed_residual import build; build(Path(argv[1]))' \
  "$new_binaries"
lock env PYTHONPATH="$frozen:$release/src:$release" "$release/venv/bin/python" -BPs \
  "$trial" "$saved_detections" "$frozen/spec.json" "$causal_archive" "$offer" \
  "$profiled_result" "$profile"
lock env PYTHONPATH="$frozen:$release/src:$release" "$release/venv/bin/python" -BPs \
  "$trial" "$saved_detections" "$frozen/spec.json" "$causal_archive" "$offer" \
  "$packed_result" --packed "$new_binaries"
```
