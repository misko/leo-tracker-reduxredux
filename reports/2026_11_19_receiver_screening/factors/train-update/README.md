# Freeze the training assignments and update the position once

Keeping the satellites and Doppler aliases fixed after the training fit increased coverage from **119 to 133 of 135** roof recordings. Both receivers withheld all nine offers that excluded the roof. The additional fixes included an **11.217 km** fitted-calibration error. The original v5 no-repair error on that recording was **0.758 km**. [Every decision and error](scores.csv) · [Fitted roof chart](../../../2026_11_19_position_atlas/screening/fitted_c/native_train_update-roof.png) · [Wrong offers](../../../2026_11_19_position_atlas/screening/fitted_c/native_train_update-omitted.png)

| Calibration and cohort | Fixes | Median / P95 / worst published error (km) | Same-input joint fixes | Joint median / P95 (km) | Original no-repair median / P95 (km) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Zero, all roof recordings | 133/135 | 1.853 / 4.559 / 11.439 | 119/135 | 1.759 / 4.695 | 0.982 / 2.941 |
| Fitted, all roof recordings | 133/135 | 1.638 / 4.656 / 11.217 | 119/135 | 1.584 / 4.723 | 0.988 / 2.819 |
| Fitted, DS26 | 125/127 | 1.638 / 4.706 / 11.217 | 112/127 | 1.590 / 4.806 | 0.999 / 3.126 |
| Fitted, DS29 | 8/8 | 1.539 / 3.249 / 3.495 | 7/8 | 1.285 / 1.959 | 0.742 / 1.312 |

With fitted calibration, 34, 85 and 128 of all 135 attempts returned a position within 1, 2 and 5 km respectively. The joint control returned 36, 80 and 114. Original no-repair v5 returned 69, 115 and 133. The fixed-assignment receiver was within 10% of each recording's no-repair error or better in 37/135 fitted and 35/135 zero-calibration attempts. The summary includes all four v5 options in both settings. [Coverage and paired comparisons](summary.json) · [Zero-calibration roof chart](../../../2026_11_19_position_atlas/screening/c0/native_train_update-roof.png)

The three previously inspected refusals were disclosed before running. Their fitted errors were 1.798 km on DS26-0197, 11.217 km on DS26-0223 and 3.495 km on DS29-0316. On the other 132 recordings the receiver published 130 with fitted median and P95 of 1.569 and 4.555 km. The joint control returned 119 with median and P95 of 1.584 and 4.723 km. The new receiver withheld its two remaining roof fixes at the boundary of the supplied tile. On the nine omitted tiles the median forced error was 29.117 km with fitted calibration. The published fix count there was zero. [Prespecified cases and criteria](PROTOCOL.md) · [Omitted offers and distance to the tile](omitted-queries.json)

## What the change tested

The control assigns satellites on the training observations and repeats that search on the pooled observations. The candidate makes three joint assignment calls on training observations, down from seven total in the control. It predicts held tracks at the exact training solution, appends those that pass the existing threshold and fits once more with all assignments fixed. Median training-to-final displacement was 0.467 km. Even the 11.217 km error passed the original 4 km displacement gate with a displacement of 2.017 km. A position can be stable across two fits with the same incorrect assignment. [Algorithm](../../../../tools/pipeline_eval/variants/train_update.py) · [Association evidence for this recording](../association-evidence/association_summary.csv)

Estimating the RF-dependent coefficient lowered conditional Doppler RMS on 132/135 roof inputs by a paired median of 23.29 Hz. It reduced position error on 83 of 133 published pairs and increased it on 50. The two calibration arms used the same observations, assignments, aliases and search budget. [Calibration ablation](summary.json)

The 144 fresh single-threaded workers authenticated the recorded GLRT factors and causal catalogues and rebuilt the exact same anonymous tracks as the control. Each had a 512 MiB address-space cap. Roof worker CPU was 5.47 s median and 7.10 s P95. Wall time was 5.96 s median and 7.73 s P95. The largest roof resident footprint was 150.1 MiB. The joint control in its separate host run measured 5.00 s median CPU and 5.36 s median elapsed. Exact held-track predictions added enough work that the smaller number of assignment passes did not produce a measured speedup here. The recordings already had GLRT outputs when the timer started. [Sealed predictions and roster](prediction-lock.json) · [Rebuild the position figures](figures.json)
