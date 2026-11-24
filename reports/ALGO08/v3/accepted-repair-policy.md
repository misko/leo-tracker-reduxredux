# Rerun the released solver after an accepted lean repair

The frozen rule would invoke the released installed solver on the same already-acquired mixed packet in **11 of 27 verified pairs (40.7%)**. It reaches **five of 13** field fixes with more than 250 m of deterioration in either calibration and misses the other eight. Its two measured invocations improve one material regression without clearing both arms’ 250 m limit, and charge a separate saved solve on one fix that already improved. The remaining nine triggered cases have no measured installed/mixed outcome. [Frozen condition](accepted-repair-policy-protocol.md) · [Complete receipt](measurements/accepted-repair-policy.json).

## Coverage

- **Reached above 250 m in either arm.** DS30-0452, 0124, 0220, 0244 and 0010.
- **Missed above 250 m in either arm.** DS30-0274, 0105, 0183, 0407, 0189, 0444, 0073 and 0049.
- **Other invocations.** DS30-0330, 0086, 0170, 0087 and 0354 have two comparable fixes below the material-deterioration threshold. DS30-0397 completed under charted, but the installed/full attempt failed in the solver. Released installed/mixed behavior on 0397 is unmeasured.
- **Other outcomes.** Three recordings withheld under both paths and had no accepted repair. The 23 comparable fixes include 18 with some positive deterioration. The rule reaches eight of those 18.

The condition reads the charted branch decision and accepted repair status with its positive integer refit count, before joining the survey. All 27 triggers were resolved from their own as-run witnesses and verified dispositions. The archived `0147` and `0073` repairs failed and their charted ordinary fallback ran. Those charted fallbacks are a distinct path from the released installed/mixed crossover. [Field study artifact contract](ds30-paired-evaluation.md).

## Actual effects on the three measured mixed packets

Values are **fixed `c = 0` / fitted `c`** in metres. An error delta below zero moves closer to the surveyed reference. Endpoint displacement is the actual distance between solver outputs on the same mixed packet.

| Recording | Rule fires | Charted mixed error | Released mixed error | Error change from switch | Endpoint displacement | Released mixed error minus installed/full |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| DS30-0049 | No | 4,471.9 / 4,040.2 | 4,471.9 / 4,040.2 | 0 / 0 | 0 / 0 | +2,646.2 / +2,619.8 |
| DS30-0086 | Yes | 370.6 / 381.6 | 399.4 / 378.1 | +28.8 / −3.5 | 173.8 / 151.6 | −2.9 / −31.8 |
| DS30-0220 | Yes | 1,411.7 / 1,371.3 | 592.9 / 546.4 | −818.8 / −824.8 | 1,657.8 / 1,624.6 | +274.8 / +177.6 |

Both solvers used the same byte-identified mixed packet for each comparison and produced independently verified publications. DS30-0049 reproduced the mixed terminal, positions, RF and owners exactly. Both DS30-0086 switched errors are still lower than their installed/full controls. DS30-0220 improved by more than 0.8 km in both arms. Its fixed-zero arm remained 274.8 m worse than installed/full. Of the measured switches, zero bring a case from over 250 m in either arm to within 250 m in both. [0049 factorial](ds30-0049-saved-crossover.md) · [0086 factorial](field-receiver-solver-cross-0086.md) · [0220 factorial](field-receiver-solver-cross-0220.md).

## Costs and timing boundary

| Recording | Existing charted verified raw wall / CPU s | Separate released saved child wall / CPU s |
| --- | ---: | ---: |
| DS30-0049 | 13.600 / 12.840 | 7.840 / 7.740 |
| DS30-0086 | 58.836 / 51.713 | 21.557 / 21.071 |
| DS30-0220 | 56.418 / 51.322 | 31.829 / 31.078 |

The saved clocks run through child exit with re-entry on the already acquired packet. The original through-verification clocks include raw acquisition and a separate common verifier. The two scopes are shown separately. DS30-0049 also has a charted child at the matched saved boundary, **6.360 s wall / 6.310 CPU s**, so paying the released child from that same boundary adds **1.480 s wall / 1.430 CPU s**. The trigger does not pay that rerun. DS30-0086 and 0220 give representative retry charges on the two measured invocations. Their measurements do not establish a reused-state cost, or a 27-case median or total under the new rule.

The accepted-repair condition becomes final after the charted lean route makes its evidence decision. The original 11 reached cases spent a total of **7.590 s wall / 7.484 CPU s** just on repair preparation and paired refitting, a median of **0.657 / 0.656 s**. A separate direct switch at the first failed **paired** gate would reach 13 cases. It adds DS30-0073, a 336.4/392.9 m regression, and DS30-0147, whose charted named fallback already improves both errors. It could skip the original repair work, including the measured **0.543 / 0.514 s** on 0086 and **0.405 / 0.405 s** on 0220. It would still owe the released solve, and neither those two skips nor the timings of a shared live handoff were measured. The earlier initial curved-track screen is a separate stage.

The [read-only evaluator](accepted_repair_policy.py) takes the campaign result root, the sealed cohort directory, the sealed 0220 crossover receipt and `reports/2026_11_21_ds30_full/reference-audit.json`. The committed receipt used the durable `field-receiver-solver-cross-0220.json.gz` from `3258963eb`. Eight component tests and all 27 archived source and result bindings passed. No solver or additional acquisition ran for this policy audit.
