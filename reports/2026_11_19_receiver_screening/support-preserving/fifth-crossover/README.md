# Keep four starts and add a fifth on complete saved IQ

Across six recordings, the genuine fifth-center union reached the original v5 error within 5% on **4/6** cases in either calibration arm, compared with **3/6** for stock. It reduced the upper tail and improved both positions on four recordings. Both arms worsened on the other two. Published coverage stayed at 6/6 for both methods. [Six-recording chart, zero calibration](charts/c0/fifth-center-all-six.png) · [Six-recording chart, fitted calibration](charts/fitted_c/fifth-center-all-six.png) · [Six-recording scores](six-scores.csv)

The primary chart compares stock wide with the genuine fifth-center union across six recordings from one roof. The matched crossover separately compares stock, fourth-center replacement, and fifth-center union on four earlier recordings. The historical two development recordings and two manifest-selected recordings each have their own chart. Two independently selected recordings contribute fresh stock and fifth-center pairs to the six-recording comparison. Both calibration arms and the four original capture-era v5 options appear throughout. [Crossover protocol](PROTOCOL.md) · [Six-recording protocol](SIX-RECORDINGS.md)

The two hint policies use the same compiled FFTW scout, the same current-window IQ, and the same compact phase release. Replacement can overwrite the fourth stock start. Union preserves all original timing starts and local nominations, then adds the distinct hint neighborhood before the common top eight and normal fine and fractional stages. Final gates may change after ranking. Within each case all modes use the original truth-free request, capture clock, exclusions, causal TLE and offered 25 km tile. [Original detector and fit authority](source-lock.json)

## Six-recording comparison

The six-recording pool uses the same stock binary, FFTW scout, genuine fifth-center binary, raw adapter source, and installed numerical source and libraries across the two studies. The four-recording group is retrospective for this change, including its two earlier manifest-held cases. The two fresh recordings were selected independently by capture manifest digest in their own study. [Executable and input identity audit](six-authority.json) · [Zero-calibration retrospective chart](charts/c0/fifth-center-retrospective-four.png) · [Fitted retrospective chart](charts/fitted_c/fifth-center-retrospective-four.png) · [Zero-calibration fresh chart](charts/c0/fifth-center-fresh-two.png) · [Fitted fresh chart](charts/fitted_c/fifth-center-fresh-two.png)

Each two-value cell gives zero / fitted calibration. The 5% and 10% counts use original no-repair v5 as the per-recording comparator and include all attempted recordings. P95 interpolates among published position errors. [Complete summary and distributions](six-summary.json)

| Cohort | Published, each method | Within 5% of v5, stock → fifth | Within 10%, stock → fifth | Median position error, stock → fifth (km) |
| --- | ---: | ---: | ---: | ---: |
| All six | 6/6 | 3 → 4 / 3 → 4 | 4 → 4 / 3 → 4 | 0.798 → 0.795 / 0.824 → 0.892 |
| Four retrospective | 4/4 | 2 → 3 / 2 → 3 | 3 → 3 / 2 → 3 | 0.770 → 1.171 / 0.765 → 1.184 |
| Two fresh | 2/2 | 1 → 1 / 1 → 1 | 1 → 1 / 1 → 1 | 0.813 → 0.488 / 0.922 → 0.577 |

Across all six, P95 error changed from 2.075 to 1.679 km at `c = 0` and from 2.007 to 1.698 km with fitted `c`. The fitted-calibration median rose because the fifth center hurt both of the previously manifest-held cases relative to their stock controls. DS29-0316 contributed the largest improvement among the two fresh cases, from about 0.84 km to 0.22 km in each arm. [Original two fresh measurements](../whole-center-union/README.md)

## Four-recording crossover

All 25,164 valid dual-receiver visits reproduced exactly the same FFTW hint in the two hint policies. The comparison can therefore measure the difference between keeping the fourth stock start and replacing it under the same scout. All four new fifth-center services and all eight archived comparator services completed. [Crossover prediction seal](prediction-lock.json) · [Historical native evidence](historical-authority.json) · [Three-policy charts, zero](charts/c0/fifth-crossover-all.png) · [Three-policy chart, fitted](charts/fitted_c/fifth-crossover-all.png)

| Cohort and recording | Original v5 no-repair | Stock wide | Replace fourth | Keep four + add fifth |
| --- | ---: | ---: | ---: | ---: |
| Development DS26-0237 | 0.362 / 0.271 km | 0.382 / 0.323 km | 0.295 / 0.221 km | 0.219 / 0.179 km |
| Development DS29-0082 | 0.567 / 0.517 km | 2.489 / 2.346 km | 2.296 / 2.055 km | 1.735 / 1.757 km |
| Earlier held DS26-0168 | 1.515 / 1.551 km | 0.805 / 0.796 km | 1.724 / 1.722 km | 1.511 / 1.521 km |
| Earlier held DS29-0604 | 0.982 / 1.041 km | 0.735 / 0.734 km | 0.760 / 0.775 km | 0.832 / 0.848 km |

The fifth center improved on replacement in both calibration arms on three of four recordings and on stock on the two development recordings. It recovered both v5 tolerance thresholds on DS26-0168 while stock remained considerably more accurate. DS29-0082 made the largest improvement against replacement and remained well above original v5. Conditional RF and accuracy moved in different directions on DS29-0604. At `c = 0`, union lowered RMS from 98.637 to 97.394 Hz relative to replacement while position error rose by 0.071 km. Fitting `c` for the fifth center reduced position error by 0.040 km on DS26-0237 and increased it by 0.022 km on DS29-0082, while conditional RMS fell by 0.070 and 0.360 Hz respectively. [Per-arm position and RF values](scores.csv) · [Paired calibration contrasts](calibration.csv)

The fifth center lost a stock-positive receiver probe on 32 of 50,328 paired receiver visits, compared with 78 for replacement. It added 1,568 newly positive probes relative to stock, compared with 1,609 for replacement. Existing positive measurements can change at the common top eight even though the fifth center preserves the original coarse start neighborhoods. [Per-recording and per-probe agreement](probe-audit.json)

## Runtime boundary

The four new fifth-center calls used fixed core pairs, 512 MiB charged memory and zero swap, with a 450-second cap. Their full pipeline wall times ranged from 139.92 to 250.48 seconds. Measured complete detector calls at or below 20 ms totaled 7,061/25,164 for the new fifth trials, 7,245/25,164 for archived stock and 5,606/25,164 for the earlier replacement. The earlier timings describe different run schedules and load. On the two fresh same-core comparisons in the sister report, the fifth center increased detector CPU and reduced deadline compliance on both recordings. The first crossover export inherited a 450-second deadline annotation for two archived stock services. The corrected evidence uses their sealed 360-second cap. [All stage and detector timings](deadlines.csv) · [Original service receipts](resources.json) · [Timing annotation correction](timing-correction.json)

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.fifth_crossover_results score
.venv/bin/pytest -q tests/pipeline_eval/test_fifth_crossover.py tests/pipeline_eval/test_whole_center_union.py
```
