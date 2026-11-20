# Full native-factor replay of the smooth receiver oscillator

Both calibration arms published **119/135** roof positions and withheld all **9/9** omitted-tile queries. The smooth oscillator improved the fitted-`c` median error from **1.584 to 1.284 km** versus the exact same-input native joint fit. P95 moved from **4.723 to 4.751 km** and the maximum from **6.194 to 6.922 km**. The original no-repair v5 published 135/135 with fitted-`c` median and P95 of 0.988 and 2.819 km. The complete native receiver took **219.09 s** for all 144 fresh queries on four cores, with peak RSS of **154,936 KiB** under the 512 MiB address-space cap. [Frozen protocol](PROTOCOL.md) · [Detailed summary](summary.json)

## Position errors and coverage

Each triplet gives published median, P95 and maximum geodesic error in kilometers. Counts within a threshold use the whole scheduled cohort. Forced fit errors, including withheld coordinates, are available separately for all cases. [Per-attempt scores](scores.csv)

| Roof cohort | Calibration | Smooth published | Smooth error triplet | Archived native joint triplet | Smooth within 1 / 2 / 5 km |
|---|---|---:|---:|---:|---:|
| All | `c = 0` | 119/135 | 1.530 / 4.463 / 6.656 | 1.759 / 4.695 / 6.044 | 35 / 80 / 114 |
| All | Fitted `c` | 119/135 | 1.284 / 4.751 / 6.922 | 1.584 / 4.723 / 6.194 | 41 / 88 / 115 |
| DS26 | `c = 0` | 112/127 | 1.560 / 4.481 / 6.656 | 1.812 / 4.792 / 6.044 | 31 / 73 / 107 |
| DS26 | Fitted `c` | 112/127 | 1.397 / 4.802 / 6.922 | 1.590 / 4.806 / 6.194 | 36 / 81 / 108 |
| DS29 | `c = 0` | 7/8 | 0.892 / 1.575 / 1.628 | 1.324 / 1.811 / 1.922 | 4 / 7 / 7 |
| DS29 | Fitted `c` | 7/8 | 0.714 / 1.116 / 1.138 | 1.285 / 1.959 / 2.047 | 5 / 7 / 7 |

All 144 fresh native requests and rebuilt Graphs matched the archived native joint control byte for byte. Of the 135 scheduled roof inputs, both methods published 115, each exclusively published four, and both withheld 12. Relative to native joint on the 115 common publications, smooth error was at most 5% and 10% higher on 77 and 86 attempts with `c = 0`, and on 80 and 84 with fitted `c`. It reduced error on 68 and 71 common publications, respectively. Median paired error shifted by −123 m and −96 m. The largest joint-to-smooth increases were 1.673 to 3.722 km on DS26-0022 with `c = 0` and 0.443 to 2.457 km on DS26-0014 with fitted `c`. [Paired summary](summary.json)

Each original v5 option published all 135 positions. The last two columns use all 135 scheduled inputs and count only attempts where smooth published and its error was within the stated relative limit against the exact original input reference. [Original v5 and native joint figure specifications](figures.json)

| Original v5 option | `c = 0` error triplet | Fitted `c` error triplet | `c = 0` joint-clock ≤5% / ≤10% | Fitted `c` joint-clock ≤5% / ≤10% |
|---|---:|---:|---:|---:|
| Baseline | 0.982 / 2.941 / 7.269 | 0.988 / 2.819 / 6.858 | 37 / 40 | 45 / 47 |
| Selective-gap | 0.980 / 2.941 / 7.269 | 0.953 / 2.819 / 6.858 | 37 / 40 | 44 / 46 |
| Omitted-track-one | 0.980 / 2.941 / 7.269 | 0.988 / 2.819 / 6.858 | 35 / 38 | 44 / 48 |
| Omitted-tracks | 0.960 / 2.941 / 7.269 | 0.958 / 2.819 / 6.858 | 34 / 37 | 44 / 48 |

## Calibration, support and omitted tiles

Both arms fit the same rebuilt observations, candidate assignments, supplied tile and search budget, with `c` controlled jointly with the receiver clock model. Fitted `c` reduced position error on 64/119 published pairs and increased it on 55, with a −19 m paired median change. Across all 135 roof fits it lowered conditional RMS on 132, with a −25.20 Hz paired median change. Median conditional RMS was 151.72 and 126.04 Hz for smooth versus 182.56 and 159.23 Hz for native joint. Smooth reduced conditional RMS on every same-Graph fit in both arms, by median 19.60 and 20.99 Hz. [Calibration and fit distributions](summary.json)

Median roof held score was 0.683 and 0.710 for smooth versus 0.643 and 0.663 for native joint. Smooth mean-loss scores on the held tracks and held RF RMS are separate telemetry. Smooth's held RF RMS medians were 1,255 and 1,218 Hz. The stock worker reports held scores and held orbit counts. Original v5 uses its archived publication RMS, recorded separately. Fifteen roof withholdings were due to the geometry gate and one to the tile boundary. Across both arms, the largest fitted radius was 3.499 km, below the 6 km gate. Pooled displacement had median 1.632 km and P95 4.951 km. [Held evidence and geometry histograms](summary.json)

Both models withheld all nine omitted tiles. Smooth triggered the boundary gate on five, held-track support on two and geometry on two. Its forced fits reached the offered tile edge in all nine cases. Forced error median / P95 / maximum was 28.943 / 41.733 / 43.461 km with `c = 0` and 28.969 / 41.600 / 43.493 km with fitted `c`. Smooth improved conditional frequency fit on all nine even though the offered square excluded the true site on every query. [Sealed omitted inputs](omitted-queries.json)

## Prepared overlap and measured boundary

The archive contained ten prior prepared roof cases with matching native, catalogue and offer bindings. Seven DS26 canonical Graph hashes matched exactly and reproduced both positions, RF fit scores and decisions bitwise. The three DS29 canonical Graph hashes differed. Their forced positions agreed within 4.8 µm and objectives within 7 × 10⁻¹¹, recorded as cross-boundary numerical differences. The matched DS26-0036 omitted query reproduced its decision and both arm outputs exactly. Two other prepared omitted offers were outside the previously sealed nine-query roster. [Prepared overlap and raw bindings](prepared-overlap.json)

The sandbox processed all stored native GLRT factors through streaming peak selection, anonymous Graph rebuild and the frozen smooth oscillator backend using causal TLEs and the supplied offer. It used neither prepared observation files nor v5 localization imports. The four original v5 methods and native joint are authenticated archived controls. Fresh roof wall time at median / P95 / maximum was 6.03 / 7.58 / 8.53 s and worker CPU was 5.68 / 7.13 / 7.77 s. Median Graph and smooth-solver wall time were 2.70 and 2.45 s. The highest virtual address-space measurement was 396,584 KiB with the 512 MiB cap active before numerical imports. There were zero failures and zero timeouts. Previous native joint timing came from a separate eight-worker run. IQ acquisition and IQ-to-GLRT computation are outside this measured path. [Run and source seal](prediction-lock.json) · [Fresh request roster](plan.json) · [Worker telemetry](positions.jsonl.gz)

Run from the checkout containing the frozen protocol, with the verified deployed source bundle from the native-lean trial and a fresh output directory. [Native source inventory](../../inference/native-lean/deployment.json)

```sh
clock_work=$(mktemp -d /tmp/leo-native-clock-full.XXXXXX)
timeout --kill-after=2s 720s taskset -c 8,9,16,18 .venv/bin/python \
  -m tools.pipeline_eval.qualification.native_clock_full \
  --work "$clock_work/run" --bundle /path/to/deployed-source \
  --output "$clock_work/report"
.venv/bin/python -m tools.pipeline_eval.qualification.native_clock_full_results \
  --work "$clock_work/run" --bundle /path/to/deployed-source \
  --output "$clock_work/report"
```
