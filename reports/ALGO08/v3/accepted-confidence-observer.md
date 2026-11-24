# Where lean confidence spent its time on DS30-0049

The two scored confidence calls spent **914.706 ms wall / 914.344 ms CPU** on the original saved DS30-0049 successor packet. The first causal phase-width call alone spent **787.776 ms wall**. The second confidence call repeated all five projections and fifteen likelihood profiles with exact operands and bit-identical results. Their second executions took **17.605 ms** and **8.762 ms wall**, respectively. The prototype reuses only the projections, and the original solver earns zero measured runtime credit. [Frozen protocol](accepted-confidence-protocol.md) · [Verified machine receipt](measurements/accepted-confidence-0049.json.gz)

| Inside the two confidence calls | Calls | Wall ms | CPU ms |
| --- | ---: | ---: | ---: |
| Sensitive support selection | 2 | 0.042 | 0.042 |
| Conditional problem construction | 2 | 0.976 | 0.975 |
| Conditional state | 2 | 2.786 | 2.784 |
| Causal phase widths | 2 | 792.436 | 792.119 |
| Orbit preparation | 2 | 8.456 | 8.455 |
| Five anchor projections per call | 10 | 35.219 | 35.191 |
| Ordered RF likelihood profile | 30 | 17.383 | 17.375 |
| Competitor conversion | 30 | 0.822 | 0.821 |
| Operand and output fingerprints | 92 | 46.979 | 46.961 |
| Original assembly and remaining observer overhead | — | 9.606 | 9.621 |
| **Inclusive confidence total** | **2** | **914.706** | **914.344** |

Each row is a disjoint leaf of the inclusive confidence stopwatch. Preparation and projection clock the original callable, and the fingerprint clock encompasses its own allocations and hashing. Argument setup, slice gathering, timing dispatch and bookkeeping still contribute to the remainder. The score returned to the normal solver carries its original values and order. The original archived same-packet child ran in **6.36 s wall / 6.31 s CPU** in a different session. The observed child took **6.990 s wall / 6.396 s CPU** through exit. That difference supplies no matched estimate of instrumentation overhead. [Trace implementation](accepted_confidence_trace.py) · [Archived saved diagonal](ds30-0049-saved-crossover.md)

## What actually repeated

The two calls shared all 133 ordered sample epochs, including the capture time origin, and the same ordered causal catalogue and exact prepared geometry. They also matched the mask, reference, location and the conditional `beta` and `smooth` nuisance used to correct observed CFO. Each prepared projection fingerprint includes every stencil or geometry array, the exact mapped coordinate and the original altitude and reference RF constants. Every RF profile hashes its ordered observed and predicted arrays, phase derivative, elevation, noise, widths and candidate identity. Every paired projection and profile returned identical array bits. The cold and warm causal-width calls took **787.776 ms** and **4.661 ms wall**. The width source caches the constructed earlier orbit view for the same ordered labels and still checks the prior digest and assembles the per-family widths on a cache hit. The large first call is a separate paid scope, and these receipts do not split it further into authentication, orbit preparation and prior arithmetic. [Original confidence caller](lighter_joint_estimator.py) · [Installed earlier-view cache](/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/src/leo/analysis/localization_v3/orbit_modes.py)

The observer-only replay reproduced the archived detector and terminal hashes, both calibrated numerical arms, all 268 ordered owners per arm, the normalized 179-point grid, the path and eight PNGs including their independent decoded RGBA digests. The offline reader initially compared differently tagged RGBA digest strings. Normalizing that representation reproduced all eight exact hashes from the retained outputs. The paid child was unchanged. [Independent readback](accepted_confidence_readout.py)

The reuse prototype keeps one exact geometry generation under the normal confidence binding and at most 32 MiB of private projection arrays. The five observed projections occupy **24.562 MB**. The key includes the evaluator identity, exact source and prepared geometry, ordered epochs and coordinate bits. Profile calculations run in original order with the current receiver nuisance even when projection hits. Tests on a saved 33-observation slice with a controlled sky showed 20→10 actual projector calls with byte-identical confidence. Changing nuisance preserved projection hits and recomputed distinct profiles. Changing epochs forced fresh projections. A zero-capacity test made all 20 original calls. Nine tests passed across the observer and earlier accepted lean component. The prototype received no additional timed solver invocation. [Guarded prototype](accepted_confidence_projection_reuse.py) · [Tests](../../../tests/pipeline_eval/test_accepted_confidence_trace.py)

## Scope and custody

The sealed charted build `30cc3b0440…` ran from the existing resident stage. Its preflight checked 48 signed original catalogue bodies and the existing portable index, with all 49 files resident and zero solver calls. One numerical child started **94.7 ms** after the official DS30-0281 storage deferral under the shared nonblocking CPU 2, nice 15, idle-I/O lease. It exited successfully before the next official deferral, which was again for storage. The worker used one authenticated saved handoff and denied backing and waveform reads. Two untimed setup checks exposed a portable-producer digest representation and a source-relative tool dependency. Both were corrected before the sealed positive-port preflight and the single paid child.

The earlier first-30 panel measured **47.767 s wall / 47.437 s CPU** inside confidence. The new partition applies to DS30-0049. On this case the exact projection repeats sit inside the previously proved 44.9 ms duplicate seed gate, so the two ceilings overlap. The larger causal-width clock and dense cases with changing masks remain outside the demonstrated reuse budget. [First-30 duplicate accounting](accepted-lean-duplicate-bound.md)

As-run source commit `c996d7438`. Positive preflight SHA-256 `baf9d6a1747098b4c900746f45bdfc423183849271cb6c15165676304f359dab`. Raw clock and trace digests are `4714b8feecf6abd6ffa2cc52d2e4eeed9250fc3af2d0bac2ecb1bff9acc78e4f` and `4401cfaded55a8c45e83c39983b1979eec5ece2ddc4953595bfb21af4a2e080f`.
