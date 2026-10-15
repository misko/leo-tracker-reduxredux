# A053 crossed half-geography/full-calibration profiles

The full CH1–8 training selector improves from **1.343357 to 1.148233 km** (14.5% lower error). The new objective is 19299.950146 versus 19314.770184, with independent KKT 0.000632238. It comes from the current high-half geography combined with the old full complete non-geographic state, first fitted at fixed XY and then released. All four fixed profiles and all four free continuations passed strict acceptance. The original full incumbent remained eligible throughout.

The current accepted full/low/high incumbent errors are **1.148233 / 1.659857 / 1.444907 km**. All are from the same fitted-c, propensity observation model, 59-satellite bank, frozen learned calibration frame and original 50 km disk. These are conditional half views rather than independent discovery pipelines. Full now beats both half incumbents, but remains above 1 km and does not establish the full-dataset 0.5 km median target.

| Fixed geography | Initial non-geographic state | Fixed objective | Free objective | Free KKT | Free error km |
| --- | --- | ---: | ---: | ---: | ---: |
| Accepted low | Full incumbent | 19315.193142 | 19313.715083 | 0.000470518 | 1.349659 |
| Accepted low | Complete low incumbent | 19314.278736 | 19312.888465 | 0.000012977 | 1.318361 |
| Accepted high | Full incumbent | 19313.715630 | **19299.950146** | 0.000632238 | **1.148233** |
| Accepted high | Complete high incumbent | 19604.437377 | 19601.498244 | 0.000097879 | 1.046912 |

The geographically closest trial is not selected: its objective loses 301.548098 to the training winner. No reference-based seed, selector or model weight was used. Lower fit error was not assumed to imply better localization; all position errors were joined only after the complete eight-call experiment sealed.

The experiment crosses two previously accepted half XY states with two non-geographic sources (full versus the corresponding complete half). Only XY is transplanted for full-source seeds; complete half seeds preserve every half timing, calibration, clock and propensity parameter. Five qualification evaluations replay the original full incumbent and each new seed; exact initializer/domain checks pass. Every accepted fixed profile is released with its complete fitted state. Each call retains the 20-second, 600-actual-objective cap and the unchanged strict KKT/domain audit. The four free calls took 2.167–2.506 seconds and 289–337 objective evaluations. No unsuccessful call was retried and no acceptance threshold was relaxed.

The result demonstrates remaining basin dependence even after numerical polishing: changing the starting geography while retaining full calibration reached a better full solution. It does not identify a unique physical calibration error or establish global optimality. The independent smooth-visibility prototype remains motivated by the separately observed hard-support discontinuity and will use this new full state as the current hard-model baseline for future fits.

Sources: `38301d3bf` experiment (three tests), `b86e6aae1` post-seal evaluator (one test); Ruff passes. Evidence: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-a053-full-profiles-v1`. All four fixed outcomes were sealed before free continuation, and all fixed/free outcomes sealed before reference access. No held observations, new RF collection, QNAP mutations or golden fixture changes were used.
