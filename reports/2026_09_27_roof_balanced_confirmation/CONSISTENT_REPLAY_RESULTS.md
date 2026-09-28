# Calibration consistency replay: no added geographic benefit

All four paired runs completed successfully in 734–823 seconds. Each prior evaluated exactly its own saved 289 coordinates. The whole-cohort reporter passed all input/model/code/grid bindings before computing reference errors. Across all 2,312 points, the old calibration reproduced saved scores exactly, and changing reception calibration left every Doppler score exactly unchanged. Thus the differences below are reception-calibration ranking effects, not different search coverage or frequency fits.

Distances are kilometers to the operator-supplied roof reference, not surveyed ground truth. All selected locations are interior to their local grid and prior disk.

| Scan | Prior | Doppler-only | Previous geometry | Consistent calibration |
|---|---|---:|---:|---:|
| 339af | Sacramento | 2.4237 | 1.9585 | 1.9585 |
| 339af | Reno | 2.4662 | 1.6095 | 2.2357 |
| 53ce | Sacramento | 5.5377 | 5.5132 | 6.0323 |
| 53ce | Reno | 5.7088 | 5.7013 | 5.7013 |
| e76c | Sacramento | 3.0003 | 3.0003 | 3.0003 |
| e76c | Reno | 3.0138 | 3.0138 | 3.0138 |
| c9db | Sacramento | 5.4166 | 5.4166 | 5.4166 |
| c9db | Reno | 5.4218 | 5.4218 | 5.4218 |

| Prior | Mean Doppler-only | Mean previous geometry | Mean consistent calibration |
|---|---:|---:|---:|
| Sacramento | 4.094565 | 3.972148 | 4.101923 |
| Reno | 4.152652 | 3.936606 | 4.093171 |
| Combined | 4.123608 | 3.954377 | 4.097547 |

Compared with previous geometry, the correction improves zero cases, worsens two, and leaves six unchanged. Sacramento 53ce worsens by 0.5191 km; Reno 339af worsens by 0.6263 km. The two prior means worsen by 3.27% and 3.98%, respectively.

Compared with Doppler-only on the same grids, consistent geometry improves three cases, worsens one, and leaves four unchanged. Sacramento mean worsens by 0.18%; Reno mean improves by 1.43%. Overall mean improvement is only 0.63%, versus 4.10% for the previous geometry calibration. The roughly 7 m radial-error difference on 53ce Reno is not evidence of metre-scale resolution on a 0.5 km grid.

## Interpretation and decision

Fixing the measured association-feature mismatch is scientifically coherent, but this isolated correction does not improve geographic results. The earlier gain is sensitive to reception calibration. These results do not prove that RX geometry lacks information, nor do they establish reliable improvement in both priors. Do not promote this correction as an accuracy improvement or silently select the old calibration based on these evaluation outcomes.

These are already-unblinded development recordings; the two priors per recording are correlated. This replay is not a new prospective confirmation, a production-baseline comparison, a confidence-interval validation, or proof of improved tracking resolution. No production configuration changed.

A remaining concrete modeling mismatch is mean-direction reception calibration versus candidate-likelihood marginalization at scoring time. `CANDIDATE_MIXTURE_CALIBRATION_DESIGN.md` specifies a calibration-only investigation and a same-objective mean-direction control. Its advancement criteria are declared without accessing these geographic outcomes. It is not implemented or validated yet. A failure of those calibration gates should stop that iteration rather than trigger tuning against these locations.

Artifacts: `consistent-replay-distances.json`, four `consistent-replay-scan-fw-*.json` files, `CONSISTENT_REPLAY_PROTOCOL.md`, and `CONSISTENT_REPLAY_VALIDATION.md`. The experiment-directory suite passed 42 tests; software checks alone are not performance evidence.
