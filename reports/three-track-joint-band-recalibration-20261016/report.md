# Joint receiver-band recalibration after timing reassignment

Recording: `fast8-auto-20261016-161535-99008d35-1-lower`.

The previous [all-candidate timing search](../three-track-coordinate-timing-20261016/report.md) escapes poor timing basins but leaves the inherited receiver-band contrast fixed. This control exposes those two existing offsets to joint optimization while preserving the same model at initialization. It improves training score, but changes fitted-c coherent held matches only from **31 to 32 of 129**. It does not solve the three-trajectory recovery goal or establish position accuracy.

## Controlled change

The old correction contains receiver intercept `a[r]` and an uncentered high-minus-low offset `delta[r]`. For a training high-channel fraction `p[r]`, the identical joint representation uses intercept `a[r] + p[r] * delta[r]` and contrast `(high - p[r]) * delta[r]`. Common clocks, RF coefficient, satellite timings, candidate order and detectability remain unchanged during transport. The contrast retains the original 50,000 Hz Gaussian prior, counted once.

For each fold and c arm, the frozen control and joint model start from the same accepted timing-search endpoint and receive the same original observation inventory, candidate bank, priors, spatial domain and 60-second solver/65-second overall allowance. The frozen control converges in about 1–2 seconds; the same cap is available to both. Target memberships and held carrier values do not enter either fit. Original held values are loaded only after both fits finish.

## Numerical and held results

| Fold | c arm | Frozen objective | Joint objective | Joint stationarity | Joint accepted |
| --- | --- | ---: | ---: | ---: | --- |
| Forward | fitted | 54,977.660 | 54,819.771 | 0.000501 | Yes |
| Forward | zero | 55,548.981 | 55,103.192 | 4.372147 | No |
| Reverse | fitted | 55,339.331 | 55,287.075 | 0.000139 | Yes |
| Reverse | zero | 55,749.469 | 55,353.669 | 0.000442 | Yes |

The lower forward zero-c objective does not override its numerical rejection. The fitted-c likelihood NLL decreases by 142 forward and 76 reverse; those are training frequency-score improvements, not geographic error reductions.

![Training objective controls](02_training_objective.png)

| Fold | Variant, fitted c | Early CH2 held matches | CH4 held matches | Late CH2 held matches |
| --- | --- | ---: | ---: | ---: |
| Forward | Frozen | 0/14 | 27/36 | 0/13 |
| Forward | Joint | 0/14 | 28/36 | 0/13 |
| Reverse | Frozen | 3/15 | 1/37 | 0/14 |
| Reverse | Joint | 3/15 | 1/37 | 0/14 |

These are actual classifier coherence counts: the held point must select the training-selected satellite with posterior above clutter. They are not independently verified satellite identity accuracy. Missing groups stay in the denominator. The original cold pipeline had 75/129 coherence on these folds; this prototype remains worse.

![Actual held coherence](01_held_coherence.png)

The forward CH4 reporting label remains 62052. Its held RMS worsens from 258 to 283 Hz even though one more point is associated. Reverse early CH2 improves from 531 to 504 Hz and CH4 from 1,128 to 1,109 Hz, still with poor transfer. Late CH2 remains unsupported. More associated points and lower training score therefore do not establish recovery.

The learned RX1/RX2 offsets move from −18,124/+32,169 Hz to −18,054/+31,508 Hz forward, and from −16,410/+41,177 Hz to −16,384/+40,944 Hz reverse. These are fitted receiver contrasts, not identified physical LNB states or per-satellite corrections.

## Verification and consequence

Four component tests cover both RF arms, unchanged physical predictions/priors/shared gradients at initialization, exact detector-tail transport after contrast changes, analytic offset gradients, and incompatible-frame rejection. On actual data, initial frequency transport differs by at most 7.28e−12 Hz and objective by at most 7.28e−12. Refreezing trained offsets for prediction preserves frequency, objective and posteriors within the declared gates.

`fit.py` reconstructs and verifies its original cold donor and timing-search parent before fitting. `band_transport.py` contains the numerical transport without storage or CLI imports. Results preserve numerical failures. This experiment does not show that freezing the band offset is the sole cause of rejection; ordinary local optimization can still stay in a poor multimodal solution.

The saved capture also labels RF mappings as hypotheses rather than physically qualified LNB state. A separate [RF-mapping control](../three-track-rf-mapping-20261016/report.md) compares declared interpretations of the same recorded IF/CFO observations. No RF collection or production change is involved. Full recovery remains unproven.
