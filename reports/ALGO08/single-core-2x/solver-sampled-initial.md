# Time-spread proposals with full-data regional fitting

On DS30-0374, sampled proposals reduced initial CPU from **6.71 to 3.94 seconds** and complete solve and grid CPU from **28.94 to 26.70 seconds**. Both horizontal errors fell, both conditional frequency RMS values rose, and the final packet retained 65 fewer observation owners per calibration arm. The northern containing simulation reproduced both stock results and showed little change in the measured initial stage.

This experiment gives each curved track at most 16 observations during initial discovery and its first two numerical updates. The full curved-track test decides which fragments enter discovery. The stock centre and corner proposals search every candidate supplied by the causal sky. The sampling rule uses the original track timestamps. It keeps both endpoints, then repeatedly chooses the sample farthest from its nearest retained sample, breaking exact ties in chronological order. It uses the same observation budget as the existing coarse residual-salvage nomination. [Prototype](../../../tools/pipeline_eval/variants/algo08_sampled_initial.py) · [Existing salvage screen](../../../src/leo/analysis/localization_v3/residual_screen.py)

The up to three best sampled hypotheses each get two ordinary initial phase refreshes. Their nominal owner labels, aliases, fitted position and clipped phase references seed three additional refreshes on the original tracks with their full observations. The full-data objective chooses among those branches, and the incumbent gate uses all of its original curved observations. An empty full-data gate triggers the stock initial selection. Conservative recovery, historical orbit priors, signed inference, cavity, both calibration arms, and the standard full objective grid run through the original solver schedule using the original tracks and observations. [Runner](solver_sampled_trial.py) · [Component tests](../../../tests/pipeline_eval/test_algo08_sampled_initial.py)

Both comparisons use verified saved detections, identical regional offers and causal archives, one low-priority CPU, and the exact causal parser and coarse salvage optimizations in each arm. The timed boundary starts at saved detections and ends after packet and grid construction. We score the estimated positions against existing references after the solve. [Physical scoring reference](../location-audit/README.md) · [Simulation scoring baseline](../regional-release/blind-scores.csv)

| Saved input | Early / full curved observations | Initial CPU, stock → sampled (s) | Solve and grid CPU, stock → sampled (s) | Final owners per arm, stock → sampled |
|---|---:|---:|---:|---:|
| DS30-0374 | 1,052 / 2,918 | 6.710 → 3.944 | 28.939 → 26.704 | 2,905 → 2,840 |
| North containing | 240 / 285 | 0.588 → 0.578 | 8.170 → 7.462 | 302 → 302 |

The physical trial ran candidate first, and the simulation ran stock first. Each trial measured one pair. All runs returned both fixes and completed the 179-point full-data grid. DS30 kept all 1,407 sky candidates in discovery and northern kept all 1,569. When discovery used 1,052 of the 2,918 physical curved observations, its sampled score after two updates placed the winning full-data branch last among the three finalists. Evaluating only the lowest sampled-score branch would have discarded the full-data winner. The stock gate initially accepted 2,467 observations and the sampled variant accepted 2,389, after fitting on all 2,918 each time.

| Saved input and arm | Sampled estimate | Horizontal error, stock → sampled (km) | Solver RF RMS, stock → sampled (Hz) |
|---|---|---:|---:|
| DS30-0374, `c = 0` | 37.849246, −122.465760 | 1.855 → 1.755 | 101.536 → 102.115 |
| DS30-0374, fitted `c` | 37.849777, −122.466218 | 1.935 → 1.717 | 101.520 → 102.074 |
| North containing, `c = 0` | 47.771519, 16.086911 | 0.745 → 0.745 | 5.380 → 5.380 |
| North containing, fitted `c` | 47.770427, 16.087693 | 0.711 → 0.711 | 5.173 → 5.173 |

The physical winner assigned a different satellite to four initial tracks and kept their discrete aliases. In each final packet, 68 baseline observations lost ownership, three gained it, and every jointly owned observation retained its original satellite. The northern winners, positions, final owner maps and numerical grid points matched exactly. Its measured initial saving was 10 ms. Most of the 0.71-second whole-run difference occurred outside the changed stage.

The measured 1.70× initial acceleration on the physical recording was a 1.08× solve and grid acceleration. This comparison covers a physical recording and a distinct containing simulation. The earlier profile identified substantially more initial work in DS30-0008. Its response to sampling remains unmeasured. [Cost breakdown](cost-checks.md)

## Short recording and another region

The frozen sampler reproduced both fixes, the final owner maps, and the grid scores on the short two-family DS30-0016 case and on the southern containing simulation. The short case used all three sampled finalists. Its initial stage ran 95 ms faster while its full solve used 27 ms more CPU. The south used two distinct sampled finalists. Its initial stage ran 247 ms faster and the full solve used 118 ms less CPU.

| Saved input | Early / full curved observations | Initial CPU, stock → sampled (s) | Solve and grid CPU, stock → sampled (s) | Final owners per arm |
|---|---:|---:|---:|---:|
| DS30-0016 | 48 / 127 | 0.337 → 0.241 | 4.452 → 4.479 | 109 |
| South containing | 224 / 266 | 0.815 → 0.568 | 6.543 → 6.425 | 266 |

| Saved input and arm | Horizontal error, both runs (km) | Solver RF RMS, both runs (Hz) |
|---|---:|---:|
| DS30-0016, `c = 0` | 1.644 | 109.375 |
| DS30-0016, fitted `c` | 1.662 | 109.479 |
| South containing, `c = 0` | 0.826 | 6.503 |
| South containing, fitted `c` | 1.109 | 6.392 |

## Offer that excludes the receiver

The northern far offer used the same saved detections as north containing and a region that excludes the simulated receiver. The frozen sampler and the previously saved combined control both published false fixes in both calibration arms. The sampler's full evidence assigned 140 observations per arm, down from 228, and each trial offered a cavity replacement. The candidate's lower frequency RMS accompanied worse geographic error. Both grids completed, with 137 evaluations in the earlier control and 158 in the candidate.

| Calibration arm | Horizontal error, stock → sampled (km) | Solver RF RMS, stock → sampled (Hz) |
|---|---:|---:|
| `c = 0` | 52.455 → 55.232 | 37.951 → 9.263 |
| Fitted `c` | 52.491 → 55.464 | 37.533 → 9.106 |

The earlier control used 12.145 CPU seconds and the candidate used 7.668. The separate timing sessions and changed ownership limit attribution of that difference to initial sampling. Both methods published both arms on all five saved offers, including the four containing offers and the one far error. Taken together, the changes in physical ownership and in the false fixes leave this candidate unqualified for substitution. [Published wrong-region baseline](../regional-release/blind-scores.csv)
