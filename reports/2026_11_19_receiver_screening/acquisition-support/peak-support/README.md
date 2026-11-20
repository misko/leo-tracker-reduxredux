# Physical peak agreement and shared observation support

Against capture-era gated winners, the wide detector misses primarily at the exported epoch boundary. Wide recovered the same winning family on 20,274 of 22,755 positive capture-era probes. Of the remaining 2,481 probes, 2,092 had no nearby exported wide epoch and 362 contained the matched gated family below another winner. Against narrow ordinary gated winners, wide agreed on 22,638 of 23,439 probes. The most frequent disagreement on that comparison was a gated family losing the winning rank. [Six-recording census](peak-census.json) · [Frozen physical rule](PROTOCOL.md)

## Six authentic native inputs per detector

The census covers every valid dual-RX visit on the six released sessions. Capture-era, narrow and wide shared identical clocks, sample counters, complete probe metadata and acquisition exclusions. The comparison has 38,641 dual visits and 77,282 RX probes. For all positive probes the counting unit is one receiver's admitted, highest-margin candidate. The aliased physical families use integer-plus-fractional epoch at 750 Hz and CFO modulo 1/(4.4 µs). [Parent replay and input receipts](../../detector-origins/whole-band/README.md) · [Native digest and shared history authority](plan.json)

| Reference → target | Reference positive | Same winner | No target epoch | Epoch without joint CFO | Joint without reciprocal | Reciprocal gate failed | Matched gated nonwinner |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Capture-era → wide | 22,755 | 20,274 | 2,092 | 26 | 0 | 1 | 362 |
| Capture-era → narrow | 22,755 | 19,633 | 2,223 | 146 | 1 | 93 | 659 |
| Narrow → wide | 23,439 | 22,638 | 127 | 57 | 147 | 14 | 456 |
| Wide → narrow | 23,837 | 22,638 | 290 | 252 | 156 | 119 | 382 |

The narrow and wide pair had 23,273 probes positive in both. Capture-era and wide had 21,008. There were 26,506 reciprocal family links between capture-era and wide over the full inventory, and 146,454 between narrow and wide. A family can be present without either detector selecting it. Of the narrow winners that found a reciprocal wide family, 614 required an alias lift for the matched member pair, versus 375 capture-era winners matching wide. Folded CFO tolerances therefore matter to apparent identity.

At 10 MS/s, the strict tolerances were 2 samples and 1 kHz. Widening them to 6 samples and 3 kHz changed capture-era → wide epoch misses from 2,092 to 2,085 and left same winners at 20,274. Narrow → wide same winners changed by one to 22,639. The circular half-turn within the same RX/channel/RF/edge lanes produced zero same-winning families under strict in all directed comparisons and at most one per direction under broad. The two sensitivity levels use the same within-probe strict families. [Exact strict and broad counts, including the circular control](peak-census.json)

The capture-era → wide epoch misses included 1,925 of 22,579 high-margin winners, 101 of 106 middle-margin winners, and 66 of 70 low-margin winners. Narrow → wide missed the epoch on 107 of 22,956 high-margin, 12 of 348 middle-margin, and 8 of 135 low-margin winners. Strong capture-era winners account for most absolute epoch misses, while weaker capture-era strata have higher miss rates. With two or more competing eligible target families for a narrow winner, the winner agreed on 300/383 probes; with one eligible target it agreed on 22,338/22,872. Margins and ambiguity defined these strata before any geographic join.

These are exported-factor events. A missing epoch may originate in scout proposals, regional restriction, retained candidate capacity, refinement or export. The complete files show neither a full scout rank nor the pre-export stage that rejected a missing family.

## Shared whole probe ablation

A probe enters common support when three independently matched, reciprocal pair links form one triangle with a passing family in all three sources. Every input then uses the same selected probe indices and keeps its own complete original candidate rows and ordering. The equal-size comparator takes the lowest fixed SHA-256 ranks in each RX/channel/RF/edge lane and 30 second block. The shared set is a retrospective diagnostic that has access to all three detector outputs.

| Recording | Total RX probes | Common and hash-thinned size | Common/random overlap | Position role |
| --- | ---: | ---: | ---: | --- |
| DS26-0036 | 13,530 | 3,032 | 1,175 | Development |
| DS29-0082 | 9,736 | 1,544 | 595 | Development |
| DS26-0237 | 13,532 | 3,282 | 1,215 | Held reserve |
| DS29-0174 | 13,408 | 3,635 | 1,455 | Held reserve |
| DS26-0122 | 13,542 | 4,041 | 1,600 | Census |
| DS29-0247 | 13,534 | 4,668 | 2,014 | Census |

The full recipient controls come from the previously sealed five-refresh compact replay for capture-era and full-band replay for narrow and wide. The subset services start at authenticated stored factors and use the 78-source compact worker. Clocks, exclusions, offered tile, track configuration and causal TLE histories are shared. Each worker fits matching observations and solver settings for zero and fitted calibration. [Exact support indices](support.jsonl.gz) · [Protocol](PROTOCOL.md)

## Development position results

All 12 services completed. The common support beat hash thinning in five of six detector/recording pairs in both arms. It beat the corresponding full factors in three of six. [Checked scores](scores.csv)

| Recording | Detector | Full error, zero / fitted (km) | Shared error, zero / fitted (km) | Random-thin error, zero / fitted (km) | Observations, shared / random |
| --- | --- | ---: | ---: | ---: | ---: |
| DS26-0036 | Capture-era | 1.260 / 1.196 | 1.134 / 1.051 | 0.680 / 0.568 | 3,032 / 1,246 |
| DS26-0036 | Narrow | 0.218 / 0.180 | 0.664 / 0.623 | 1.347 / 1.168 | 3,032 / 1,268 |
| DS26-0036 | Wide | 1.003 / 0.935 | 0.749 / 0.656 | 0.785 / 0.682 | 3,032 / 1,275 |
| DS29-0082 | Capture-era | 0.568 / 0.516 | 1.470 / 1.688 | 2.936 / 2.780 | 1,544 / 653 |
| DS29-0082 | Narrow | 2.789 / 2.654 | 2.230 / 2.099 | 6.056 / 5.863 | 1,544 / 706 |
| DS29-0082 | Wide | 2.489 / 2.346 | 3.019 / 3.011 | 5.497 / 5.418 | 1,544 / 708 |

The shared set guarantees a positive on each selected probe. The equal-size random controls therefore hold probe budgets fixed while varying positive counts. On DS26-0036, capture-era shared support had lower fitted conditional RMS than random thinning, 74.392 versus 77.864 Hz, while random thinning gave lower position error. On DS29-0082, narrow shared support beat its full error with fitted conditional RMS 104.839 versus 106.588 Hz. [Both calibration arms and all conditional RMS values](scores.csv)

## Held position results

All 12 held services completed. DS26-0237 improved under shared support for both capture-era and narrow. On DS29-0174 all three shared-support fits had larger errors than their full recipient. [Both calibration arms and all conditional RMS values](scores.csv)

| Recording | Detector | Full error, zero / fitted (km) | Shared error, zero / fitted (km) | Random-thin error, zero / fitted (km) | Observations, shared / random |
| --- | --- | ---: | ---: | ---: | ---: |
| DS26-0237 | Capture-era | 0.353 / 0.262 | 0.140 / 0.058 | 1.255 / 1.142 | 3,282 / 1,313 |
| DS26-0237 | Narrow | 0.889 / 0.814 | 0.658 / 0.519 | 0.732 / 0.588 | 3,282 / 1,347 |
| DS26-0237 | Wide | 0.382 / 0.323 | 0.482 / 0.340 | 0.702 / 0.538 | 3,282 / 1,357 |
| DS29-0174 | Capture-era | 0.886 / 0.918 | 0.894 / 0.966 | 1.004 / 0.816 | 3,635 / 1,549 |
| DS29-0174 | Narrow | 1.161 / 1.224 | 1.442 / 1.486 | 1.409 / 1.220 | 3,635 / 1,566 |
| DS29-0174 | Wide | 0.793 / 0.806 | 1.305 / 1.383 | 1.195 / 1.069 | 3,635 / 1,577 |

Across development and held data, shared support beat equal-probe thinning in 9/12 detector/recording pairs with `c = 0` and 8/12 with fitted `c`. It beat full factors in 5/12 in each arm. Shared support came within 10% of each full error in 6/12 and 7/12 pairs, versus 3/12 and 5/12 for random thinning. The common rule changes which probes are retained and their positive density. These results cannot separate corroboration from that density. The four recorded position cases come from one roof. [Both-arm standard charts](plots/index.html) · [Summary](summary.json)

All 24 numerical services used CPU 8 or 9 with the enforced 512 MiB cap and zero swap. Measured systemd lifetimes were 21.169–57.327 s and peak cgroup charges were 253,509,632–385,675,264 bytes. One controller interval reached 191.083 s during bulk-filesystem contention. Its measured service lifetime was 40.602 s. These intervals start at stored native factors. [Runtime and position receipts](results.jsonl.gz) · [Prediction seal](prediction-lock.json)
