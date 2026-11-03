# Frozen discovery calibration and acquisition-clutter diagnostics

Recording: `fast8-auto-20261016-161535-99008d35-1-lower`.
These are local research results using existing observations. They do not change production.

The reverse cold-start failure remains unresolved. Keeping the missing candidate and grouping coherent observations helped one trajectory, but did not recover all three. Two further bounded diagnostics are negative: choosing among the existing discovery calibrations is insufficient, and learning one acquisition-margin clutter slope does not solve the failure. Frequency residuals below are not position errors or independently verified satellite identities.

## Finite discovery-calibration audit

For each temporal fold, all 24 numerically accepted lower-band discovery fits were reconstructed and their objectives and stationarity rechecked. Each calibration and geographic position remained frozen. The search considered all 1,035 regional satellites, a common timing grid from −5 to +5 seconds in 0.05-second increments, 125 Hz Gaussian errors and a 2-second timing prior.

The three user-inspected coherent groups have supplied membership but no supplied satellite labels. Candidate identities, timing and calibration-family selection use their training observations only. If two groups choose the same satellite, they must share one timing correction and pay its prior once. The exact search enumerates the five partitions of three groups and assigns distinct satellites to the partition blocks. Held-out carrier values are evaluated only after all 24 training fits have been compared.

Across the 24 fitted-c calibration families, **zero families fit all three training groups within 200 Hz RMS**, in either fold. The lowest achievable worst-group training RMS is 269 Hz forward and 275 Hz reverse. Three forward families and one reverse family fit all three within 375 Hz; those descriptive training references do not establish reliable extrapolation.

![All frozen calibration families, training scores only](01_frozen_family_training.png)

The minimum-total-training-score winners give:

| Fold | Selected discovery point, km in prior chart | Early CH2 test RMS | CH4 test RMS | Late CH2 test RMS |
| --- | --- | ---: | ---: | ---: |
| Forward | (50, −150) | 480 Hz | 992 Hz | 5,244 Hz |
| Reverse | (−50, 50) | 134 Hz | 640 Hz | 570 Hz |

The reverse result improves two individual residuals compared with the original reverse fit, but this is a conditional three-track diagnostic, not a replacement fit of the full scan. Its selected identities are 51117, 52845 and 58952; the forward winner chooses 67654, 63469 and 51112. These differ from the hypotheses supported by the accepted forward joint model. There is no independent identity truth to adjudicate them here.

![Training-selected calibration families on held-out observations](02_frozen_family_test.png)

The coefficient-zero arm in this particular frozen-calibration diagnostic **deletes c without refitting the intercepts, clocks or position**. It holds observations, candidates, priors and search budget fixed, but is not an independently optimized c = 0 localization model. It selects the same discovery point in each fold and yields 448/953/5,213 Hz forward and 90/635/598 Hz reverse. The separately optimized c = 0 experiment below is the matched fitted-model ablation.

The initial scalar implementation exceeded its explicit 240-second computation budget before completing all families and published no winner. Batching timing-shifted orbit queries reduced the completed audits to approximately 23 seconds per fold. Every batch's first and last timing prediction was checked against the original orbit port on the actual observations: maximum prediction difference was exactly 0 Hz and visibility masks agreed. The batched calculation preserves calibration at the original observation times. The timing-batch test and three exact-search tests pass, including exhaustive small-bank comparisons and shared-timing/prior accounting.

## Learned acquisition-margin clutter slope

This experiment adds one scalar slope to the point-mixture model. The covariate is selected acquisition log-margin, standardized using only the cold training observations. The row clutter rate is multiplied by exp(beta × standardized log-margin), with beta bounded to ±2 and a unit Gaussian prior. The conditional density includes the corresponding row normalizer; margin is not interpreted as a calibrated probability of detection. Beta = 0 reproduces the original density.

Candidate retention, training timing proposals, free receiver band offsets, clock priors, spatial prior and fit budgets are matched between fitted-c and independently refitted c = 0 arms. Each receives a 60-second fit with a 65-second overall allowance. The original stationarity gate of 0.001 is unchanged. Forward uses 4,734 training observations and reverse 4,731; entire held probe groups remain absent.

| Fold | c arm | Learned beta | Stationarity | Accepted | Early CH2 / CH4 / late CH2 test RMS |
| --- | --- | ---: | ---: | --- | --- |
| Forward | fitted | −0.390 | 0.007151 | No | 132 / 164 / 113 Hz |
| Forward | refitted zero | −0.282 | 0.002103 | No | 148 / 127 / 109 Hz |
| Reverse | fitted | −0.365 | 0.000844 | Yes | 1,979 / 310 / 4,119 Hz |
| Reverse | refitted zero | −0.407 | 0.000269 | Yes | 1,440 / 319 / 6,565 Hz |

![Acquisition-margin model with matched c ablation](03_acquisition_clutter_test.png)

The slope has the expected sign: higher selected margin decreases modeled clutter odds. This does not establish better associations. The accepted reverse fits still fail two trajectories, and the apparently good forward residuals do not override their numerical rejection. Six component tests cover original-model closure, density normalization, analytic frequency/clutter/visibility/detectability gradients, training-only margin normalization and invalid inputs. Actual-data finite-difference checks are included in each result receipt. This tests only the selected-margin covariate, not a likelihood over all acquisition branches or the full native-acquisition framework.

## Controls on alternative calibration anchors

Four earlier production sessions were inspected read-only as potential external calibration sources. They supply no independently verified geographic or satellite labels. Their inferred receiver-band contrasts vary by several kHz and their inferred positions vary, so they cannot be treated as independent calibration truth. More directly, the target's good forward and bad reverse initial fits have almost identical band contrasts: approximately −18.12/−18.20 kHz for RX1 and +40.53/+40.53 kHz for RX2. A rule using those two offsets alone cannot distinguish the basins. The shortlist is retained in the result files; no historical prior was fitted or applied.

A second control fits fixed polynomial degrees 1, 2 and 3 to each raw training carrier trajectory, with phase unwrapping and coefficients computed from training data only. All 18 cases are reported, without selecting a degree by held-out error. Quadratic test RMS is 752/9,728/658 Hz forward and 479/11,692/1,050 Hz reverse for early CH2/CH4/late CH2. Cubics do not repair this generally. A low local polynomial training residual therefore does not justify long extrapolation or satellite identity. Short polynomial segments may still help propose clean observations; the final association must use orbit physics and temporal validation.

## Implication and reproducibility

The next model should address which clean, informative trajectories enter calibration and how the common clock/position ambiguity is resolved. Selecting another existing frozen discovery fit or adding one margin-based clutter weight is insufficient. No additional per-satellite correction or relaxed acceptance threshold is justified by these results. Automatic extraction of short coherent segments, with balanced channel/time coverage and orbit-based continuation, is a candidate next experiment; it has not yet been implemented or qualified here.

`evaluate.py` and `polynomial_control.py` use the adjacent [verified replay capsule](../three-track-recovery-replay-20261016/report.md) and require its pinned deployed Python environment, original observation export and local TLE archive. `shared_identity_search.py` and `timing_batches.py` contain the tested search kernels. The acquisition implementation and its tests are in [the grouped-fit component](../three-track-grouped-fit-20261016/report.md). Result JSONs retain training rows' provenance, numerical audits, candidate identities, timing corrections and individual held residuals. `manifest.json` pins this report, figures, source and packaged results. The three-trajectory recovery goal remains incomplete because both temporal folds have not passed.
