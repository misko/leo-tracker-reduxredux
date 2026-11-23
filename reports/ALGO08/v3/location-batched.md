# Four-location likelihood batches on the saved grid

Four-location AVX2 batches increased the checked native posterior cost by **2.00% on dense DS30-0008** and **6.96% on weak DS30-0016** after paying for the batch. Every sampled score, native posterior byte, Gamma update count and sampled winner matched. The measured row pass misses the **0.5 CPU second** full-grid saving that would justify integration. [Frozen protocol](location-batched-protocol.md) · [Dense receipt](measurements/location-batched-dense.json) · [Weak receipt](measurements/location-batched-weak.json)

| Five paired repetitions, 16 original arm-and-location calls per panel | Dense DS30-0008 | Weak DS30-0016 |
| --- | ---: | ---: |
| Ordinary native export, median CPU | 73.859 ms | 2.519 ms |
| Batched native export and prepass, median CPU | 75.296 ms | 2.684 ms |
| Four prepasses, including allocation and layout scatter, median CPU | 5.230 ms | 0.295 ms |
| Paired increase, median | 1.477 ms / 2.00% | 0.175 ms / 6.96% |
| Pairs in which the candidate used more CPU | 4 / 5 | 5 / 5 |
| Original Gamma updates, both arms | 9–19 | 6–26 |

The dense control had one **161.081 ms** repetition among four others at **73.449–74.011 ms**. It is retained in the receipt and median. Excluding the preparation charge entirely gives a median paired saving of **5.31%** of the dense strip's native export CPU. Transferring that fraction to the entire measured 1.931-second native grid for scale gives **0.103 s**. The actual paid strip result went in the opposite direction. The scale calculation assumes the measured strip fraction transfers to all locations. [Per-repetition clocks](measurements/location-batched-dense.json)

## Exactly what was batched

One SIMD lane represents one grid position. A batch streams the shared group, active-column locations and original row scales once. Its four responses and four design values remain independent. Each lane accumulates the Gram and right-hand-side products in original row order with binary64 multiplication and addition. The upper/lower copies use the symmetry of each ordered Gram accumulation. The paid prepass includes the matrix and RHS scatter into the original per-location representation. The checked posterior copies those arrays and runs the same private and shared factorization, prior initialization, per-position conditioning, log-rate stopping and budget, including the final factor. The grid's ordinary predictive objective consumes that factor unchanged. The original packed-residual study vectorized multiple observations at one location. This trial vectorized a shared row walk across locations and left its iterative residual calculation alone. [SIMD pass](location_batched_gram.inc) · [Comparison driver](location_batched_trial.py) · [Earlier row-parallel study](../single-core-2x/guarded-packed-residual.md)

Both strips per arm contain four original coordinates, one near the selected endpoint and one on the southern coarse boundary. The driver reconstructs the archived selected models from saved data, compares every sampled stock score with its archived binary64 value, then checks exact exported means, residuals, precisions, rates, scalar convergence, ordered factors and scores for both treatments. The same sampled minima remain in the local strip in both arms. Both returned endpoints, RF values, owner and role rows, and endpoint replays match the archived originals. The dense reconstruction also matches the archived optimizer path. The reported CPU clocks include the checked native export and the candidate's prepass. Building geometry and collecting comparison copies occur outside these kernel clocks for both methods. The publication sampler, position fits and its per-point deadline remain on the original path. [Dense selected reconstruction](grid-neighbor-gamma.md) · [Weak saved control](weak-combined-raw.md)

## Remaining budget and reuse

The disjoint breakdown of the **4.220 CPU seconds** in the archived 356 fully checked curved callbacks is **1.931 native export**, **0.185 argument validation**, **0.213 remaining adapter**, and **1.892 remaining curved callback**. The native number contains the other per-point robust work as well as the row pass. Achieving the 0.5-second integration gate through only this native boundary would require a **25.9%** reduction. The 4.220-second clock comes from nested instrumentation on the same genuine short detector, grid, and selected outputs as the unfiltered publication. Its components cannot be added to the same-run 6.022-second complete evidence ceiling. [Nested timing and archive binding](measurements/location-batched-budget.json) · [Original posterior audit](grid-cross-arm-posterior.md)

| Same-run saving grant | Total | Credited stage | Remaining | Target |
| --- | ---: | ---: | ---: | ---: |
| Unfiltered dense solver, all numerical evidence free | 26.105 CPU s | 6.022 s | 20.083 s | 14.067 s, first four |
| Unfiltered dense solver, all numerical evidence free | 26.105 CPU s | 6.022 s | 20.083 s | 15.956 s, first sixteen |
| Protected dense solver, all numerical evidence free | 21.781 CPU s | 4.464 s | 17.316 s | 16.000 s |
| Weak raw-to-exit, entire numerical solve free | 8.901 elapsed s | 2.605 s | 6.295 s | 5.415 s |

The dense first-four and first-sixteen targets assume the optimistic 231.52 MB/s archive-reader rate. The protected dense route already misses the independent position screen. The weak removal grants even the solve work outside the grid. These optimistic reductions apply separately to their observed parent routes. [Dense same-input comparison](regional-dense-pair.md) · [Protected route](dense-protected-cost.md) · [Weak paired raw launch](weak-combined-raw.md)

The current curved callback already caches phase-interpolated states, reuses its symbolic native layout, forms Gram/RHS once before the Gamma loop, and supplies its checked factor to the predictive stage. All of those savings are present in the comparison. A broader design that evaluates full Gamma fits in adjacent batches would see independent stop counts. Grouping the original 178 fresh calls per arm in fours, including each final factor pass, gives **63.8% / 65.6%** lane occupancy and **21 of 45** unequal-stop batches per arm. Observed stop counts ranged from 9 to 119 with fixed-zero calibration and from 9 to 89 with fitted calibration. In eights the occupancies would be **55.4% / 58.4%**. These are work counts for fixed-width masking, with unused tail slots included. Broader Gamma batching would also need separate covariance and conditioning work per position, and active stop-point enforcement. The experiment measures only the four-location Gram/RHS candidate. [Original phase reuse](grid-phase-state-reuse.md) · [Original symbolic layout reuse](incremental-layout.md) · [Recomputed occupancy](measurements/location-batched-budget.json)

## Reproduce

Run the receipt audit directly with `python reports/ALGO08/v3/location_batched_budget.py NEW_BUDGET.json`. Run the two strips in fresh local bulk directories from the research checkout using the existing release interpreter. Gauss CPU 2 requires AVX2, one numerical thread and the shared lock. The launcher authenticates the archived dense control and the weak installed-graph packet. Two failed preflights imported native solver modules before lazy startup and stopped before sampling a grid. Moving imports after the existing configuration hook resolved those attempts. The checked-in dense receipt binds the driver at `87a0da171`. The weak import correction leaves the same dense candidate and code path.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
here="$PWD/reports/ALGO08/v3"
gauss() {
  flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
    env PYTHONPATH="$here:$payload:$PWD:$release/src:$release" OMP_NUM_THREADS=1 \
    OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 "$@"
}
gauss "$release/venv/bin/python" -BPs "$here/location_batched_trial.py" dense "$new_dense"
gauss "$release/venv/bin/python" -BPs "$here/location_batched_trial.py" weak "$new_weak"
```

Three focused tests passed, including a bit-exact comparison of all four SIMD Gram/RHS outputs against scalar ordered accumulation. [Tests](../../../tests/pipeline_eval/test_location_batched_gram.py)
