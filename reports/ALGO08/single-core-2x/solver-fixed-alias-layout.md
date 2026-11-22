# Skip discarded alias proposals when assembling fixed regional models

The direct layout saved 0.314 constructor CPU seconds on the roof case and 0.045 seconds on the public simulation. The full saved-detection solve and evidence clock showed no material gain. Both calibration arms, owners, paths, and grids matched the published control exactly on both inputs.

`JointMarginal` assembles a `receiver_smooth` layout even when its caller has already assigned a fixed alias to every curved track. The anchored layout proposes aliases twice, first in the base constructor and again at the requested anchor. Once the supplied aliases replace those proposals, the joint model uses the track rows, layout, and sky selections from that object. An earlier DS30-0374 profile attributed 0.61 instrumented seconds to the 220 anchored layouts constructed inside `JointMarginal`. The four independent alias nominations remained relevant to the solve. [Fixed-family constructors](../../../src/leo/analysis/localization_v3/families.py) · [Joint likelihood constructor](../../../src/leo/analysis/localization_v3/marginal.py)

The research overlay builds the original row order, track indices, slices, and private sky arrays directly for explicit-alias `radio_noise` models. It retains the reviewed joint constructor for alias ownership, hardware and receiver design, orbital modes, and priors. Ranking and nomination still generate aliases through the released layout. The direct route requires the original constructor source pins and checks the prepared seed and phase interpolation bounds before taking that route. This operates on every eligible fragment and uses the original regional offer. Matching supplied aliases removes both tentative projections without changing the final likelihood or search schedule. [Overlay](../../../tools/pipeline_eval/variants/algo08_fixed_alias_layout.py) · [Component tests](../../../tests/pipeline_eval/test_algo08_fixed_alias_layout.py)

## Comparison

The trial starts from verified saved candidate detections for one physical roof recording and one public northern near-edge simulation. The control and overlay each ran the frozen `65b664d49a5e…` shared-tables specification in a fresh process with the original scan archive and offer. The replay clock covers causal preparation, solver passes, and the numerical packet, including both calibration arms' objective grids and optimizer paths. Published grid and path checks ignore the delivery binding and elapsed fields, following the existing paired verifier. The replay also compares associated counts, RF RMS, selection, owners, and the objective-replay digest across modes. It ends before figure rendering or publication. [Runner](solver_fixed_alias_layout_trial.py)

| Saved input | Eligible constructors | Stock eligible CPU s | Direct eligible CPU s | Stock solver CPU s | Direct solver CPU s | Stock/direct solver CPU |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS30-0374 physical roof, stock first | 198 / 210 | 0.570 | 0.255 | 22.748 | 23.210 | 0.980× |
| Public northern near-edge simulation, direct first | 109 / 121 | 0.078 | 0.033 | 5.434 | 5.374 | 1.011× |

All eligible calls used the direct layout. Even eliminating all measured eligible constructor CPU with the rest of the roof solve fixed would bound the gain at 1.026×. The one-pair whole-solver timings moved in opposite directions, and the roof solve measured 0.462 CPU seconds slower with the overlay. The local saving supports only the constructor optimization. [Verified receipts](measurements/solver-fixed-alias-layout.json)

| Saved input | Calibration | Endpoint latitude, longitude | RF RMS Hz | Associated points |
| --- | --- | --- | ---: | ---: |
| DS30-0374 | Fixed zero | 37.849914, −122.465943 | 101.232 | 2,900 |
| DS30-0374 | Fitted `c` | 37.851123, −122.464649 | 101.209 | 2,900 |
| Public north | Fixed zero | 47.772561, 16.095479 | 5.406 | 302 |
| Public north | Fitted `c` | 47.771358, 16.095479 | 5.167 | 302 |

The differential tests passed alongside the existing position suite, 11 tests in total. They exercise both calibration arms with a held mask and an explicit alias different from the stock nomination, the real nomination path, and the interpolation-error fallback.

The runner takes `run PAIR FROZEN OUTPUT`, with `--direct-first` for the northern case. `PAIR` is the `pair.json` in `/tmp/ds30-v2-stage-65b664/DS30-0374` or `/tmp/leo-conditional-residual-public-north-first`. `FROZEN` is `/tmp/leo-algo08v2-2x-bench/integration-conditional-residual-reviewed`. Run from the research checkout with `PYTHONPATH=src:.`, one numerical thread, and the shared low-priority CPU 2 lock. Each solve has an 88-second limit.

## Remaining cost

In the earlier roof profile, fine cavity prediction took 1.510 instrumented seconds across 160 candidate calls, including 0.886 seconds in mode assembly, 0.453 seconds in phase-refresh geometry, and 0.136 seconds in Gaussian prediction. This is downstream of the previously shared broad orbital projection. Within one fine candidate the covariance is fixed across all five updates. Its Cholesky factor can be shared, and an identical clipped phase reference could reuse that candidate's deterministic prediction. Across candidates, complete orbital mode banks already share a cache keyed by label set and support. Reusing constituent orbital derivatives across different label sets would require an exact test of row-wise propagation against the original padded group calculation. The roof profile bounds the whole fine-prediction opportunity at 1.510 instrumented seconds, and the constituent figures overlap. The dominant position cost remains the complete likelihood evaluations during nonlinear fitting and grid evaluation. [Previous timing profile summary](solver-cavity-projection.md) · [Fine candidate prediction](../../../src/leo/analysis/localization_v3/family_cavity.py) · [Mode assembly](../../../src/leo/analysis/localization_v3/orbit_modes.py)
