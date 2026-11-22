# Share line-of-sight calculations in the collapsed-signed likelihood

The fused projection reduced measured curved geometry CPU by 28% on DS30-0155 and 29% on the public southern simulation. It reproduced both published positions, owner maps, paths and grids exactly. The absolute reductions were 181 ms and 22 ms. Whole-solver comparisons moved in opposite directions and establish no material speed gain.

Every full curved likelihood evaluation projects the nominal orbit states, three physical orbital modes, and two phase-offset states. The nominal and mode projections derive identical observer-relative positions and range. They use different dot products for their rates, which the overlay keeps. The two offset projections consume range rate alone. The overlay computes the observer once, shares the nominal relative positions and range with the mode calculation, calculates elevation only at the nominal phase, and omits azimuth. The original one-meter spatial probes, phase finite difference, reductions, and scaling stay in their original order. The released phase-state cache still validates the orbital buffers, observation labels, times, and current phase reference. This shares work within a position trial and applies at every curved-likelihood call in both calibration arms. [Released phase geometry](../../../src/leo/analysis/localization_v3/marginal.py) · [Original look angles](../../../src/leo/sky/frames.py) · [Overlay](../../../tools/pipeline_eval/variants/algo08_fused_phase_projection.py)

The experiment leaves the robust posterior, observation powers, owner selection, predictive likelihood, far-exterior guard, and publication sampler on the frozen path. Earlier work cached position-independent phase interpolation, changed predictive grid algebra, or compressed the native nuisance updates. The present change targets the curved projection after interpolation. [Earlier predictive layout](solver-predictive-layout.md) · [Earlier grid kernel](solver-grid-kernel.md) · [Earlier robust trials](solver-robust-updates.md)

## Matched saved replays

The control and overlay run the same frozen full-scan `collapsed-signed` specification `99b46f7ffe4d…` and reuse their respective published detections, original archive and regional offer. Its collapsed, causal table, and guard source pins match the subsequent `50d30065095e…` receiver freeze. The physical fixture is DS30-0155. The public simulation uses the southern 100 m inside offer from the matched full-scan pair. Each arm of the comparison runs in a new process on one low-priority pinned Gauss core, with stock first on the physical fixture and fused first on the simulation. The clock starts at consumed detections and stops after the exact numerical evidence packet. The matched instrumentation also records full grid time and the curved projection within and outside the grid. PNG rendering, publication writes, and receiver processing are outside these clocks. [Runner](solver_fused_phase_trial.py) · [Original roof and southern publications](signed-repair-triage.md)

The experiment uses the existing path and grid comparison that drops delivery bindings and elapsed fields and checks every coordinate and numerical value. Both replays matched the previously published arm coordinates, RF RMS, owners, path, and grid. The same-input replays also matched their associated counts and objective-replay digests. Thirteen position and component tests passed, including binary64 comparisons for both complete curved calibration likelihoods and for the four projected arrays at several observer locations. [Tests](../../../tests/pipeline_eval/test_algo08_fused_phase_projection.py) · [Receipts](measurements/solver-fused-phase-projection.json)

| Saved input | Calls / rows projected | Curved geometry CPU, stock → fused | Complete grid CPU, stock → fused | Saved solve and evidence CPU, stock → fused |
| --- | ---: | ---: | ---: | ---: |
| DS30-0155 | 657 / 2,253,510 | 0.636 → 0.456 s | 5.008 → 4.928 s | 20.238 → 21.766 s |
| Public southern near edge | 450 / 119,700 | 0.076 → 0.054 s | 0.403 → 0.385 s | 4.340 → 3.642 s |

DS30-0155 used 356 curved evaluations for its 179 grid locations. Its total projection saving included 100 ms inside the grid and 81 ms outside. South used 272 curved evaluations for its 137 grid locations and saved 12 ms inside and 10 ms outside. The observed whole-solver difference on each input exceeds its entire measured geometry change. The southern control also took 7.304 elapsed seconds versus 3.728 for fused. Even if every curved projection were free, with the rest of the solve fixed, the measured CPU ceilings would be 1.032× on DS30-0155 and 1.018× on the southern simulation.

| Saved input | Calibration | Endpoint latitude, longitude | Associated points | RF RMS (Hz) | Horizontal error (km) |
| --- | --- | --- | ---: | ---: | ---: |
| DS30-0155 | Fixed zero | 37.851044, −122.474970 | 3,498 | 155.420 | 0.972 |
| DS30-0155 | Fitted `c` | 37.851564, −122.472967 | 3,498 | 155.382 | 1.157 |
| Public south | Fixed zero | −32.957782, 21.464976 | 266 | 6.502 | 0.817 |
| Public south | Fitted `c` | −32.960687, 21.465617 | 266 | 6.392 | 1.101 |

The geographic errors come from the original postfit scoring of the matched coordinates. The two saved inputs establish scientific parity at those two offers. [Original matched scores](signed-repair-triage.md)

## Remaining likelihood cost

The DS30-0155 stock robust-bound wrapper consumed 3.576 CPU seconds, including 1.295 seconds inside the grid. Removing the grid's whole curved projection and bound steps would still leave 3.420 of its 5.008 seconds. This trial does not individually attribute that remainder. The event model builds a fresh dense precision Gram from the accepted curved posterior's updated weights, then factors the matrix for predictive integration. The previous dense DS30-0374 experiment separately measured 0.947 seconds on that Gram and 0.632 seconds on the predictive Gaussian. It accelerated predictive geometry and retained those two operations. Passing a checked posterior factor from the curved backend into the predictive model could eliminate duplicate work in complete likelihood evaluations. It would need to preserve the full predictive covariance and prove acceptable arithmetic through both arm gates and the published grid. [Event likelihood](../../../src/leo/analysis/localization_v3/event_position.py) · [Earlier predictive timings](solver-predictive-layout.md)

## Reproduce

Use `solver_fused_phase_trial.py run RECEIPT FROZEN OUTPUT` from the research checkout with `PYTHONPATH=src:.`. The frozen directory is `/tmp/leo-algo08v2-2x-bench/integration-full-float-pgo-signed`. The physical receipt is `/tmp/leo-full-float-pgo-signed-0155-run.json` with `--single-root leo-full-float-pgo-signed-0155`. The southern receipt is `/tmp/leo-algo08v2-2x-bench/paired-full-signed-south-inside/pair.json` with `--fused-first`. Use the shared Gauss lock with CPU 2, low priority and one numerical thread. Each saved solve has an 88-second limit.
