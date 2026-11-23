# Exact input preparation for fixed-timing CFO refinement

Gathering only the original CI16 samples used by the fractional verifier saved **113.9 µs per positive**, a paired median **5.126 ms** over the 45 short positives on the staged DS30-0169 member. All eight native diagnostic doubles, emitted tuples and update decisions were bitwise equal to the frozen refinement. The measured saving projects to **0.727 CPU s** at 6,380 dense positives if this per-positive cost transfers. Exact rotation preparation remains the largest stage. [Frozen frequency experiment](short-cfo-refine.md) · [Paired and component clocks](measurements/short-cfo-exact-cost.json.gz)

## What the original helper spends

The frozen binary fills the verifier's lane buffer with all 200,000 complex samples, then evaluates 14 or 15 pilot frames at the existing short timing and signed CFO. A separate instrumented build kept the original operations and reproduced all eight diagnostics. Its per-thread CPU clocks bracket frame geometry, full gather, exact rotation and Lanczos preparation, the original correlation call, and the final score. The packed correlation was already dispatched through the released AVX2/FMA kernel on this host. [Pinned build and stage brackets](short_cfo_exact_cost.py) · [Released exact fractional path](../../../tools/pipeline_eval/variants/experimental/receiver_fractional_exact.inc)

| Original native stage | CPU over 45 positives | Mean CPU per positive |
|---|---:|---:|
| Frame geometry | 0.008 ms | 0.17 µs |
| Full CI16 lane load and conversion | 6.710 ms | 149.1 µs |
| Exact rotation and Lanczos tap preparation | 14.966 ms | 332.6 µs |
| Released packed correlation | 7.430 ms | 165.1 µs |
| Delay products and scores | 0.344 ms | 7.6 µs |
| Total bracketed | 29.457 ms | 654.6 µs |

Rotation and tap preparation account for **50.8%** of the bracketed CPU. The original helper evaluates a scalar `sincos` at each absolute pilot tap and keeps the original Float64 angle multiplication and division. Deriving rotations from a per-frame phase or an oscillator recurrence would change those floating-point values. This trial kept their original scalar evaluations. [Exact angle and load helper](short_cfo_exact_cost.inc)

## Paired exact implementations

The new loader writes only each frame's contiguous literal correlation support into the existing workspace. Fractional positions load from the same floored first sample through the last sample, with the original seven-left and eight-right interpolation support. Integer positions use the original rounded integer start. Unexpected range geometry uses the original full load. The candidate keeps the same CI16 conversion, correlations, accumulation order, workspace layout, timing, original acceptance margins and signed CFO rule. The staged positives used 14 frames ten times and 15 frames 35 times, requiring **41,836 complex samples on average** or **20.9%** of the old lane conversion. The second variation separates exact angle arithmetic into a vectorized AVX2 multiply/divide pass, then calls the unchanged scalar trig routine. [Native implementation](short_cfo_exact_cost.inc)

| Arm | Refinement plus rule, median CPU / elapsed | Full signed lane batch, median CPU / elapsed |
|---|---:|---:|
| Frozen | 29.956 / 29.970 ms | 170.979 / 170.987 ms |
| Frame-support gather | 24.833 / 24.836 ms | 165.141 / 165.164 ms |
| Gather and AVX2 angle preparation | 24.689 / 24.695 ms | 164.119 / 164.141 ms |

Six repeats ran three forward and three reverse batches under the shared low-priority Gauss CPU2 lock. The full lane clock includes all 102 signed lane calls, original full anchors, short successes and nulls, refinement, rule evaluation and the benchmark's result materialization. The separate refinement clock includes the native call, diagnostic marshaling and frozen Python rule. The gather saved **4.585–5.593 ms** of refinement CPU across the six individual pairs and **5.143 ms** on median at the complete signed-lane boundary. The angle variant's additional paired refinement saving over gather was **0.052 ms** over 45 positives, with two small regressions. Its full-lane clocks also include variation in the unchanged upstream detection, so they do not establish an independent angle gain. [Individual clocks](measurements/short-cfo-exact-cost.json.gz)

The gather leaves **0.552 ms CPU per positive** on this repeat series. At 6,380 positives, the median added cost on these paired clocks projects from **4.25 to 3.52 CPU s**. The prior separate frozen trial measured **4.62 s** on its extrapolation. Setup was charged separately. Building the measurement DSO took **0.441 s wall** and the observer's compiler-launch CPU excludes the compiler subprocess. Signed tmpfs intake took **0.264 CPU / wall s**. The six benchmark receiver contexts and initial imports took **0.463 CPU / wall s** combined. The gather reuses the original allocated buffer and introduces no additional context initialization. [Earlier complete refinement charge](short-cfo-refine.md) · [Setup and exact clocks](measurements/short-cfo-exact-cost.json.gz)

All staged comparisons rechecked original signed probes and held I/Q digests. Both variants retained the 45 short positives, with **35** bitwise identical CFO updates and **10** identical tail-support fallbacks. All eight diagnostic doubles matched the frozen held receipt byte for byte. Both pilot edges, both CFO polarities, extreme and near-integer offsets, and integer/fractional support were also exercised through 12 native boundary controls. The test used only the existing staged waveform and synthetic boundaries. No original waveform read, new detector policy, solve or position measurement was performed. [Native boundary and component tests](../../../tests/pipeline_eval/test_short_cfo_exact_cost.py)

## Reproduction

The compact receipt SHA-256 is `724bea19f4efba018efc1931f54312dea04231e9c9fdb7b330c464d8bb704360`. The pinned original DSO was used for performance comparison and rebuilt byte for byte from its archived flags. Fifteen component and adjacent tests passed. The driver reads the existing DS30-0169 tmpfs stage and takes a new tmpfs output directory. [Runner](short_cfo_exact_cost.py)

```bash
install_root=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
gauss() {
  flock -w 60 -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
    sudo -n -u leo ionice -c2 -n7 nice -n15 taskset -c 2 env \
    TMPDIR=/dev/shm PYTHONPATH="$install_root/src:$PWD:$PWD/src:$install_root" \
    OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$@"
}
gauss "$install_root/venv/bin/python" -BP -m reports.ALGO08.v3.short_cfo_exact_cost \
  /dev/shm/leo-short-cfo-exact-cost-rebuild
gauss "$install_root/venv/bin/python" -BP -m pytest -q -p no:cacheprovider \
  --basetemp=/dev/shm/leo-short-cfo-exact-cost-rebuild-tests \
  tests/pipeline_eval/test_short_cfo_exact_cost.py tests/pipeline_eval/test_short_cfo_refine.py
```
