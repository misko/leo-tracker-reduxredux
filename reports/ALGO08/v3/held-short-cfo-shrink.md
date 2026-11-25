# Bounded shrinkage improves tight signed-CFO agreement on two held recordings

On 839 eligible held short measurements with an installed counterpart, the bounded correction raised joint 250 Hz/two-sample agreement from **779 to 803**. It restored **31** originally failing pairs and spoiled **seven** originally passing pairs, with gains on both recordings. The same comparison at 2,250 Hz/six samples remained **819/839**. The correction preserves measured arrival and addresses some nearby frequency misses. [Frozen rule](held-short-cfo-shrink-protocol.md) · [Candidate-only prediction](measurements/held-short-cfo-shrink-prediction.json.gz) · [Scored receipt](measurements/held-short-cfo-shrink-score.json)

| Recording | Held positive short lanes | Forecasts / eligible / installed reference | Strict joint before → after | Restored / spoiled | Absolute CFO p95 before → after |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS30-0049, development | 294 | 45 / 43 / 42 | 36 → 40 | 4 / 0 | 331.1 → 198.4 Hz |
| DS30-0086, development | 1,817 | 214 / 192 / 189 | 176 → 182 | 8 / 2 | 291.4 → 236.8 Hz |
| DS30-0019, held | 2,498 | 406 / 366 / 355 | 322 → 340 | 20 / 2 | 306.9 → 236.3 Hz |
| DS30-0274, held | 3,279 | 544 / 499 / 484 | 457 → 463 | 11 / 5 | 261.3 → 206.7 Hz |
| Held pooled | 5,777 | 950 / 865 / 839 | 779 → 803 | 31 / 7 | 284.9 → 233.3 Hz |

Gates on the 950 held forecasts leave **29 empty targets** and **56 cross-check residuals above one signed bin** untouched. All 865 eligible targets moved. The 26 eligible lanes with no installed winner stay in the eligibility denominator and have no signed error measurement. The 865 changes cover **15.0%** of the 5,777 original held positives. On the scored subset, 46 of the 60 original CFO misses moved closer to installed and 14 farther. Among the 779 original joint passes, 441 moved closer and 338 farther. There were no arrival-only misses in this eligible set at the tight threshold. Both held cases retain the same loose counts, **347/355 and 472/484**. The net gain of 24 tight pairs equals **0.42% of all original held positives**, leaving all abstentions and all other lane opportunities unchanged.

| Eligible scored set | Signed bias before → after | CFO RMS before → after | CFO MAE before → after | Maximum absolute CFO before → after |
| --- | ---: | ---: | ---: | ---: |
| Held 0019 | 2,221.237 → 2,230.626 Hz | 20,022.825 → 20,020.896 Hz | 2,383.487 → 2,370.489 Hz | 249,399.3 → 249,344.5 Hz |
| Held 0274 | 2,016.527 → 2,006.983 Hz | 24,362.638 → 24,362.082 Hz | 3,640.667 → 3,627.112 Hz | 266,469.6 → 266,391.6 Hz |
| Held pooled | 2,103.145 → 2,101.611 Hz | 22,628.174 → 22,627.107 Hz | 3,108.726 → 3,095.406 Hz | 266,469.6 → 266,391.6 Hz |

The improvement in p95 comes with almost unchanged pooled RMS because large signed peak disagreements remain. Signed errors use the original native branch and the installed same-lane maximum-margin winner, without modulo forgiveness. The 20 ms reference overlaps the measured first 8 ms. Close agreement with that reference neither establishes the emitter nor demonstrates improved location.

## Receiver and Graph boundary

The installed verifier’s nominal residual bin is **443.892045 Hz**, from the checked 512-point residual scale and median pilot-symbol separation of 44 ADC samples at 10 MS/s. The halfway correction obeys a **221.946023 Hz** cap. The largest held updates were **220.774 Hz** and **199.476 Hz**. The donor lifts agree in every forecast and the target must be directly within one bin of that signed branch. The scope keeps the complete native measurement, rank, margin, and pilot arrival. The correction was applied only in the agreement readout.

Both radio candidate arrays on every held odd visit were erased before Graph. The 0049 and 0086 forecasts reuse their independently sealed masked plans. Only two new Graph preparations ran, for 0019 and 0274, on CPU3 at nice 15 with one numerical thread. They assigned **1,701** and **2,074** retained observations. The predictor then selected the original held winners for the innovation check, after completing all forecasts. The end-to-end saved forecast process took **2.15 s wall / 2.10 s CPU** and the separate score process took **0.96 s wall / 0.89 s CPU** and ran no Graph. Every measured short and full detector call remains charged. A right-side donor and completed Graph are required, so this readout supplies no online speed or geographic qualification. [Original target exclusion](odd-short-interpolation.md) · [Installed transform audit](selective-carrier-transform.md)

The protocol froze at `a8a5b497d`. Both held forecasts and all applied changes were sealed at `2a7546ddb` before opening any installed attempt outcome. The uncompressed plan SHA-256 is `734c763aa13b45ab39921848cb49886a1acbbe8f28d379c0305b0c48f75bc6f7` and score SHA-256 is `384c22846c7029a5389118459ffb2da1f825f1875cde1474a3816b9f480921a3`. Nine focused and adjacent tests passed. The study opened no IQ, ephemerides or survey references, and ran no localization solver. [Readout source](held_short_cfo_shrink.py) · [Tests](../../../tests/pipeline_eval/test_held_short_cfo_shrink.py)
