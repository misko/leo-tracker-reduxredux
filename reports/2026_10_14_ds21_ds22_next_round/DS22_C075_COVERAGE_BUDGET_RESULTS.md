# DS22-075 coverage: matched fresh 20/60-second budget probe

Increasing the fit budget restored strict stationarity for three of four prespecified starts. It did not establish good localization. The training-selected 60-second results are 78.429728 km without the common receiver clock and 80.766346 km with it, measured against the configured, unconfirmed station reference. Neither 20-second arm has an eligible result.

All eight new calls began from the original qualified initializers, not the failed endpoints. Four starts were selected before this experiment by minimum returned training objective within each model × original/coarse source group. Each received matched fresh 20- and 60-second runs with 600 iterations and unchanged strict KKT threshold 0.001. Original controls retained their own 25 km disks; coarse starts retained their grid-derived 141.421356 km disks. The 87-candidate union, receiver lifts, physical timings, priors, and calibration frames remained fixed. These are fitted-c experiments.

| Model | Source ordinal | Budget s | Strict accepted | Objective | KKT | Evaluations | Fit seconds |
|---|---:|---:|---|---:|---:|---:|---:|
| No clock | original 2 | 20 | no | 40412.946250 | 471.863 | 207 | 20.156 |
| No clock | original 2 | 60 | yes | 39905.834144 | 0.000185558 | 396 | 51.060 |
| No clock | coarse 7 | 20 | no | 43034.979759 | 8161.563 | 234 | 20.150 |
| No clock | coarse 7 | 60 | no | 42208.611371 | 81.098 | 513 | 60.106 |
| Common clock | original 2 | 20 | no | 39721.746448 | 2052.386 | 205 | 20.157 |
| Common clock | original 2 | 60 | yes | 39447.108044 | 0.000736603 | 443 | 57.781 |
| Common clock | coarse 7 | 20 | no | 40793.603294 | 2498.269 | 250 | 20.154 |
| Common clock | coarse 7 | 60 | yes | 40208.591540 | 0.000601760 | 515 | 58.896 |

Every rejected call reached its wall-time deadline with solver success false; all three accepted calls reported solver success. Process CPU time closely matched wall time. This experiment demonstrates a budget effect for these starts, not a measured contention explanation for earlier runs. Four parallel paired units completed in 129.458 seconds. The original 44-call, 20-second coverage experiment remains entirely unavailable and unchanged.

Only after all eight calls were sealed did the evaluator join the configured reference. The accepted coarse-clock result is 74.321462 km away but loses by 761.483495 training-objective units to original-clock start 2; it is not selected. Lower objective and improved frequency fit are not evidence of better position accuracy.

Historical original C full/low/high distances are approximately 77.5869/23.4284/51.1464 km. Those used the original bank and shared-discovery initialization, and are not matched half controls for this union-bank coverage experiment. No independent-half or accuracy-target claim follows. All six original 25 km disks miss the configured reference; the complete coarse-grid domains cover the declared prior square, but this probe optimized only one coarse start per model. It cannot resolve the full coverage question.

The next proposed finite completion would preserve all four existing 60-second outcomes, including the failed no-clock coarse result, and execute only the remaining 40 never-attempted 60-second calls. No failed call is to be retried automatically. This is additional search cost, not an original-cohort correction or promotion.

## Authority

- Driver source: `7ef008b39`; evaluator: `4850e1418`; three driver and two evaluator tests passed, with Ruff clean.
- Four-objective, zero-fit actual qualification passed in 43.071 seconds; all original initializer deltas were zero.
- Scientific namespace: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c075-coverage-budget-v1`.
- Protocol SHA256: `1993bc0365b849f2f0d5bd5d6ff6e5a3b8c2d0ff45ad95a8567d7782d27f6e1f`.
- Terminal SHA256: `1039fb745792c019ff7119208b1c4dc393680e1ce046fd3d6cbee4727570a51d`.
- Seal SHA256: `36b77984dfc3cc63058239144844f9990cf44e01dd935000561e07c6f384222e`.
- Post-seal comparison: adjacent `ds22-c075-budget-comparison-v1/report.json`, SHA256 `7486ebaae724773d3b9150e8a67ffcd9849b8ad7ad70b359eb26ad4752581548`.
- No held or locked data were used. DS22 station continuity remains unconfirmed; reported distances are not verified ground-truth accuracy.
