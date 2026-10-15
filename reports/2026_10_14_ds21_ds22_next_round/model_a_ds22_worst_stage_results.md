# Original DS22-A059/A105 stage-path diagnosis

All 36 saved low/high/final fits across the twelve original A paths replay strict stationarity, objective, likelihood and physical-domain checks. Neither case is an unavailable-optimizer outcome or an active 25 km final-disk boundary. The original configured-reference errors remain A059 312.411 km and A105 223.158 km, from the sealed complete-development cohort. Station continuity for DS22 remains unconfirmed.

The selected paths expose a substantial handoff change despite the high stage holding geography fixed:

| Original case / selected start | High timing change from low RMS s | Low→final geography movement km | Final radius from original center km | Low-stage low NLL | Final low NLL | Low-stage / final low signal mass |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS22-059 / 1 | 2.636776 | 4.715229 | 10.347 | 26265.076 | 26438.535 | 965.69 / 944.42 |
| DS22-105 / 5 | 4.111634 | 6.920204 | 8.400 | 24814.657 | 26204.150 | 1144.84 / 801.22 |

The final low-band NLL worsens in **all six paths in both cases**, with frequent changes in associations. This is exact replay on the original observations and likelihood, not a refit or evidence that a particular hardware coefficient is wrong. At the selected paths, high NLL also worsens slightly relative to its own high-stage optimum: +55.560 (059) and +8.530 (105). Both separately optimized stages can prefer different timing/calibration/association states.

| Case | Start | Low J | High J | Final J | Final low NLL minus own low-stage NLL | Low→high timing RMS s | Final radius km |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 059 | 0 | 27292.572 | 20879.899 | 49165.648 | +1623.218 | 2.783 | 10.067 |
| 059 | 1 | 26871.722 | 20804.987 | 47345.853 | +173.459 | 2.637 | 10.347 |
| 059 | 2 | 27793.109 | 20560.023 | 48121.818 | +794.152 | 3.598 | 6.163 |
| 059 | 3 | 26905.770 | 21417.074 | 48383.334 | +1297.419 | 2.035 | 4.126 |
| 059 | 4 | 28067.710 | 21582.766 | 49769.433 | +884.285 | 3.350 | 4.632 |
| 059 | 5 | 27633.167 | 21259.081 | 48569.277 | +311.940 | 1.902 | 12.271 |
| 105 | 0 | 25695.830 | 15879.681 | 42209.790 | +1525.286 | 3.287 | 5.987 |
| 105 | 1 | 26976.030 | 15524.313 | 42607.512 | +877.946 | 3.094 | 11.932 |
| 105 | 2 | 26850.187 | 16009.486 | 44163.938 | +1918.594 | 2.272 | 0.720 |
| 105 | 3 | 26492.573 | 16131.557 | 42891.469 | +927.438 | 2.560 | 13.811 |
| 105 | 4 | 26592.571 | 15724.778 | 42594.734 | +935.045 | 2.457 | 16.808 |
| 105 | 5 | 25415.871 | 15684.707 | 41835.862 | +1389.493 | 4.112 | 8.400 |

Low, high and final J use different observations/learned contrasts and are **not** comparable model-selection scores. The table records path transitions, while original selection remains the minimum accepted final training objective. At selected 059, 161 of 716 windows supported in both low and final change dominant satellite; selected 105 has 221 of 711. No omitted-transmitter conclusion follows from these association changes.

Prior work matters: `DS22_059_DISCOVERY_DOMAIN_RESULTS.md` already proves the configured station is outside every original 25 km disk, by at least 112.281 km beyond the nearest disk radius. Interior fitted endpoints do not rule out discovery exclusion. The subsequent B-only nine-start/61-satellite quadrant experiment is a separate architecture and bank, not a new A result. Its full winner remained far despite improved half selectors. Therefore preserving low timing alone cannot overcome all established 059 search restrictions. The 105 audit likewise does not prove the discovered geography is sufficient.

Next causal options are training-only discovery/seed coverage and the previously tested conditional-high calibration port. Neither has been fitted here. A higher-priority measured issue now exists in A053: hard visibility can change conditional-density normalization even for exactly zero-posterior satellites. Smooth visibility with consistent derivatives will be qualified separately; ordinary small KKT in these DS22 receipts alone does not establish smoothness or a global optimum.

Source `cbb7ae568`, three component tests and Ruff pass. Separate frozen outputs `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-a-ds22-{059,105}-stage-audit-v1`. Each used 18 objective evaluations, 18 explicit orbit predictions, 24 band-likelihood evaluations and **zero fits**, in 32.149 / 30.153 seconds under 120/135/140 second limits. Scientific seals: 059 `e07346a3abfdaf95d80c88a50eb11678786c30f12f40eac8bc25d52273f475b4`; 105 `e89a3fe36d76fa2372fcddbe5bcf6dfacf3b2a9ccbdb6cddc86544125b827585`. Audits read neither held observations nor reference coordinates, preserve all original fits and leave the original selectors unchanged. The companion JSON contains complete stage timing/calibration/nuisance vectors, candidate masses and exact receipt bindings.
