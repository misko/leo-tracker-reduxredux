# Full roof replay of native GLRT and joint orbit fitting

The capped offline receiver completed all 135 roof replays and nine omitted-tile queries in **102.90 s** with eight single-threaded workers. Both calibration arms published the same **119/135** roof positions and withheld all nine omitted-tile queries. Fitted `c` lowered the published median error from **1.759 to 1.584 km**. The published P95 was **4.695 and 4.723 km**, respectively. All four original v5 options published 135/135 and reached a P95 between 2.819 and 2.941 km. [Frozen protocol](PROTOCOL.md) · [Full score summary](summary.json)

## Roof positioning

Each error triplet below gives the median, P95 and maximum in kilometers. Counts within an error threshold use the whole scheduled cohort as their denominator. The separate forced-fit distributions include all 135 roof replays, including the 16 withholdings. [Per-attempt scores](scores.csv)

| Roof cohort | Calibration | Published | Published error triplet | Forced-fit error triplet | Within 1 / 2 / 5 km |
|---|---|---:|---:|---:|---:|
| All | `c = 0` | 119/135 | 1.759 / 4.695 / 6.044 | 1.803 / 5.044 / 7.417 | 26 / 77 / 114 |
| All | Fitted `c` | 119/135 | 1.584 / 4.723 / 6.194 | 1.630 / 4.980 / 7.396 | 36 / 80 / 114 |
| DS26 | `c = 0` | 112/127 | 1.812 / 4.792 / 6.044 | 1.832 / 5.178 / 7.417 | 25 / 70 / 107 |
| DS26 | Fitted `c` | 112/127 | 1.590 / 4.806 / 6.194 | 1.630 / 5.038 / 7.396 | 33 / 74 / 107 |
| DS29 | `c = 0` | 7/8 | 1.324 / 1.811 / 1.922 | 1.368 / 2.376 / 2.620 | 1 / 7 / 7 |
| DS29 | Fitted `c` | 7/8 | 1.285 / 1.959 / 2.047 | 1.464 / 2.337 / 2.494 | 3 / 6 / 7 |

The archive authenticates the four original v5 options on the same stored native data, causal catalogue and original search center. Each original option returned a position on all 135 inputs. The last two columns count attempts where joint published and its error was at most 5% or 10% above that option's error, with denominator 135 per arm. On the 119 matched publications, original v5 P95 ranged from 2.656 to 2.666 km. The largest published increase over the original baseline was DS26-0078, which changed from 0.770 to 5.743 km with `c = 0` and 0.791 to 5.674 km with fitted `c`. [Paired scores and reference provenance](summary.json)

| Original v5 option | `c = 0` error triplet | Fitted `c` error triplet | `c = 0` joint ≤5% / ≤10% | Fitted `c` joint ≤5% / ≤10% |
|---|---:|---:|---:|---:|
| Baseline | 0.982 / 2.941 / 7.269 | 0.988 / 2.819 / 6.858 | 33 / 34 | 32 / 34 |
| Selective-gap | 0.980 / 2.941 / 7.269 | 0.953 / 2.819 / 6.858 | 32 / 33 | 32 / 34 |
| Omitted-track-one | 0.980 / 2.941 / 7.269 | 0.988 / 2.819 / 6.858 | 33 / 34 | 32 / 34 |
| Omitted-tracks | 0.960 / 2.941 / 7.269 | 0.958 / 2.819 / 6.858 | 33 / 34 | 32 / 34 |

## Calibration, support and omitted tiles

The arms shared the native observations, candidate inventory, orbit assignments, region and search budget. Fitting `c` lowered position error on 72 of 119 published pairs and increased it on 47. The median paired shift in error was −67 m. DS26 improved on 70/112 published pairs and DS29 on 2/7. Conditional frequency RMS across all 135 fits fell from a median of 182.56 to 159.23 Hz, decreasing on 131/135 with a median paired change of −22.19 Hz. Median held-track score increased from 0.643 to 0.663, and held score increased on 117/135. Median joint frequency objective fell from 663.44 to 593.03. The separate original v5 RMS columns retain the archived publication metric. [Calibration and frequency diagnostics](summary.json)

Fourteen roof queries were withheld on position geometry, one on held-track support and one on the tile boundary. The geometry cases all exceeded the 4 km pooled displacement gate. The largest fitted radius across both roof arms was 3.192 km, below the shared 6 km radius gate. Median pooled displacement was 1.432 km and P95 was 5.022 km. The median repeated-orbit and cross-radio-orbit counts were both 26. The joint model's median accepted reassignment counts were one in training and zero on the full fit. The summary contains held-track, radius, displacement and inward tile-margin histograms separated by status and dataset. Shared phase is represented by the frozen worker's repeated-arc and cross-radio support telemetry. [Geometry, holdouts and phase support](summary.json)

Ground truth was 20.47–41.80 km outside the supplied square for the nine omitted queries, measured in the solver's tangent coordinates. Each arm withheld all nine. The shared gate recorded four held-track, three tile-boundary and two geometry causes. Every forced fit reached a tile edge. Forced error was 29.598 / 42.114 / 43.587 km with `c = 0` and 29.751 / 42.208 / 43.568 km with fitted `c`. These are nine fixed omitted-region controls, eight from the lean-support archive plus the prior DS26-0036 `r0` query. DS26-0277 belongs only to this control cohort. [Sealed omitted offers](omitted-queries.json) · [Both figure specifications](figures.json)

## Measured receiver boundary

Each fresh worker scanned and authenticated the complete archived native GLRT document, applied the frozen streaming peak selector, built the anonymous Graph, loaded the causal catalogue and fit both arms inside the supplied 25 km square. The numerical worker was single-threaded, with no v5 localization imports. All nine repeated queries from the smaller joint trial returned identical native, catalogue, offer and Graph bindings and identical decisions and arm outputs. [Prediction seal](prediction-lock.json) · [Raw worker telemetry](positions.jsonl.gz)

Roof worker elapsed time was 5.36 / 7.15 / 12.89 s at median / P95 / maximum. Worker CPU time was 5.00 / 6.28 / 7.06 s. Median Graph and joint solver times were 2.71 and 1.89 s. Peak RSS was 153,612 KiB and peak virtual address space was 394,896 KiB across all 144 runs. The worker applied a 512 MiB address-space limit before scientific imports. The process group had a 14-minute hard deadline and each case a 60 s cap. There were zero failures and zero timeouts. These latencies measure archived factor processing and localization. IQ acquisition and IQ-to-GLRT computation are outside this measured path. [Run receipt and exact requests](plan.json)

The runner uses the verified native-lean deployed-source bundle and pinned joint implementation from the smaller native-joint trial. Run from the checkout containing the frozen protocol, with fresh work and output paths. [Prior native-joint source lock](../../inference/native-joint/source-lock.json)

```sh
native_joint_work=$(mktemp -d /tmp/leo-native-joint-full.XXXXXX)
timeout --kill-after=2s 840s taskset -c 12-19 .venv/bin/python \
  -m tools.pipeline_eval.qualification.native_joint_full \
  --work "$native_joint_work/run" --bundle /path/to/deployed-source \
  --output "$native_joint_work/report"
.venv/bin/python -m tools.pipeline_eval.qualification.native_joint_full_results \
  --work "$native_joint_work/run" --bundle /path/to/deployed-source \
  --output "$native_joint_work/report"
```
