# A held Doppler gate for replacing full discovery with one spatial start

The frozen route deferred to complete discovery on **both saved inputs**. The dense positive had bilateral held support, but its held CFO forecasts missed badly and the two radios disagreed on nearby spatial challengers. The translated weak offer supplied held support on one radio only, and both provisional fits landed on a face. The dense proposal also cost more than the complete current cold stage even if training preparation were free. No downstream solver replay met the frozen admission criteria. [Protocol](held-spatial-start-protocol.md) · [Post-seal score](measurements/held-spatial-start-score.json)

## Keep measurements out of nomination

The trial masked one in five original stereo visits in each signed RF lane before Graph. The training curves nominated one position from a nine-point mesh, using the stock full-curve Doppler contrast over all screened causal orbits. A single nominal winner per track supplied the training aliases and one bounded normal-prior fit in each calibration arm. This directly replaced repeated phase nomination and finalist racing in the shadow call. The earlier six-knot scout tested a much smaller differential feature, the previous mixture paid a new full-data assignment without independent fallback, and the recent coreset kept the original rank payable. [Earlier differential scout](arc-doppler-start.md) · [Full-data mixture](mixture-joint-start.md) · [Whole-visit warm start](visit-information-warm-start.md)

The held native CFO values entered only the forecast residuals after training nomination and fitting. Matches used a unique receiver, RF and channel interval from the trained curves, with a nearby training epoch. This can join the wrong emitter where temporal support alone is uninformative. Held-visit detection presence and time define which training fragments can supply a forecast. The fitted coefficients never see held CFO. The modulo residual removes fixed-period alias offsets and provides no absolute alias certification. The bilateral threshold also demands that the proposed point beat four axis challengers 2 km away using the same held rows, after fitting nuisance coefficients to training again at each alternative. [Implementation](held_spatial_start.py)

## Sealed results

| Saved input | Held matches | Provisional error, fixed / fitted `c` (km) | Current repaired solver error, fixed / fitted `c` (km) | Gate |
|---|---:|---:|---:|---|
| Dense DS30-0008, containing | 789 / 1,504 | 1.260 / 1.276 | 0.915 / 0.854 | Full discovery |
| Weak DS30-0016, translated offer | 37 / 103 | 177.775 / 177.541 | 181.829 / 181.688 | Full discovery |

The dense paired training fit used 79 nominated tracks. Its holdout matched 414 observations across 24 predicted orbits on radio 1 and 375 across 22 on radio 2. Both arms gave about **41.8 / 28.4 kHz** held RF RMS across the two radios, well above the two-sigma threshold of 282 Hz. Some challengers improved held score in both arms. The provisional geographic errors exceeded the current control by 345 / 422 m. The current full-data fitted RF RMS was **140.961 / 140.949 Hz** in the fixed-zero and fitted arms. Those are full-data reference values. The candidate's reported holdout errors use different support. [Dense shadow receipt](measurements/held-spatial-start-dense.json) · [Current dense control](mixed-named-finish-0008.md)

The translated weak case had all 37 usable held rows on radio 1 across two predicted orbits and zero on radio 2. Each arm had **41.5 kHz** held RMS on radio 1 and terminated its provisional horizontal fit at the offer face. The repaired full-data control still falsely fixed at **131.122 / 132.619 Hz** RF RMS in the original calibration order. Deferral protects the original solver route and makes no new withholding decision. Neither candidate was admitted, so accepted-case positioning accuracy is unmeasured. [Translated shadow receipt](measurements/held-spatial-start-omitted.json) · [Repaired translated control](portable-omitted-region.md)

## Paid boundary

| CPU seconds | Dense | Translated weak |
|---|---:|---:|
| Training-only Graph, causal sky and forecast preparation | 3.213 | 1.569 |
| Full regional scan build and nine-point nomination | 6.199 | 0.248 |
| Paired fit and held score | 1.131 | 0.060 |
| Entire attempted shortcut including stereo split | 10.562 | 1.881 |
| Archived original cold discovery | 5.808 | 0.217 |
| Archived complete numerical solve | 25.954 | 2.328 |
| Charged attempt plus archived full fallback, additive budget | 36.515 | 4.209 |

Even granting the training preparation for free would leave the dense candidate **1.541 CPU s slower** than the original cold stage. The translated case also has a negative optimistic margin of **0.095 CPU s**. These are measured stage costs and additive budget comparisons. There was no newly timed full fallback or publish-through-exit. The measured 2/2 fallback fraction covers these two fixtures only.

The experiment was frozen on `b4edfe7bc` and both timed proposal processes ran on `0fa9a156c`. After both proposals sealed, the score-only command corrected an audit digest transcription and confirmed the translated input matched the repaired proof-equivalent archive. Neither correction involved a new fit or altered inputs to the gate. The archived result reports the exact proposal receipts. Seven component and adjacent tests passed. [Saved runner](held_spatial_start_trial.py) · [Tests](../../../tests/pipeline_eval/test_held_spatial_start.py)
