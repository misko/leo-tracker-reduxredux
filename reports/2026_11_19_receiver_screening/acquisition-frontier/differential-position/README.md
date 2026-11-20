# Position influence of differential pilot timing

The blind rank-one timing hint added eight gated winner observations across the four recordings. It moved the largest estimate by **24.0 m at `c = 0` and 17.3 m with fitted `c`**, both on DS29-0082. That recording still had 2.47 km and 2.33 km of position error. All four recordings issued fixes in both arms under stock, rank-one and sham. Every sham position, RF residual and frequency score was exactly equal to stock. [Zero calibration chart](charts/c0/differential-partial-iq-position.png) · [Fitted calibration chart](charts/fitted_c/differential-partial-iq-position.png)

## Matched recordings and position effects

| Recording | Stock error `c = 0` / fitted (km) | Rank-one error `c = 0` / fitted (km) | Rank-one error change `c = 0` / fitted (m) | Rank-one displacement `c = 0` / fitted (m) |
|---|---:|---:|---:|---:|
| DS26-0162 | 0.682 / 0.670 | 0.679 / 0.666 | −3.75 / −3.90 | 6.84 / 7.31 |
| DS26-0237 | 0.382 / 0.323 | 0.382 / 0.323 | 0 / 0 | 0 / 0 |
| DS29-0082 | 2.489 / 2.346 | 2.467 / 2.329 | −22.62 / −16.80 | 24.00 / 17.27 |
| DS29-0519 | 0.334 / 0.324 | 0.335 / 0.324 | +0.23 / +0.19 | 0.23 / 0.21 |

Median error moved by 1.88 m at `c = 0` and 1.85 m with fitted `c`, from 0.5321/0.4969 km to 0.5302/0.4950 km. The four original v5 options each fixed 4/4 in both arms. Their median errors are shown for the same recordings. They use their original capture-era factors. The matched position comparison uses rank-one, stock and sham on the common wide archive. [All 56 recording–method–arm rows](scores.csv)

| Original v5 option | Median `c = 0` (km) | Median fitted `c` (km) |
|---|---:|---:|
| No repair | 0.3803 | 0.3671 |
| Selective gap | 0.3803 | 0.3671 |
| One omitted track | 0.3051 | 0.3699 |
| Two omitted tracks | 0.3051 | 0.3699 |

RF residual changes were below 0.1 Hz in each paired estimate. On DS26-0162 the rank-one conditional frequency objective decreased by 54.39/54.54 while its RF RMS increased by 0.093/0.093 Hz. On DS29-0082 the position error decreased while the objective increased by 2.53/2.50 and residual RMS decreased by 0.031/0.038 Hz. The conditional objective is unnormalized across models with different selected support. Its direction supplies no replacement for the spatial errors. DS26-0237 kept exactly the same frequency objectives, RMS and coordinates. [Frequency and position CSV](scores.csv)

## Which observations reached the fit

The source panel scheduled exactly 24 primary and eight confirmation windows. All were processed. The rank-one packet differed from stock at 15 primary and six confirmation visits. The measured winner fingerprint changed at six and three, respectively. Sham differed at 20 primary and seven confirmation visits, with zero changes to the winner fingerprint. The source trial independently scored recovery of five historically missed target families in the primary panel and two in confirmation. Those target-family counts and the eight additional gated observations answer different questions. The replay includes complete native packets for every window, including the raw trials that did not recover their target. [Original detector trial](../differential-pilot/README.md) · [Window and Graph audit](graph-probes.csv)

| Recording | Additional gated winners | Stock → rank-one Graph points | Stock → rank-one active-curvature tracks | Edited probes / assigned to Graph / on active-curvature tracks |
|---|---:|---:|---:|---:|
| DS26-0162 | 2 | 5,129 → 5,127 | 90 → 89 | 6 / 2 / 1 |
| DS26-0237 | 2 | 3,626 → 3,626 | 69 → 69 | 6 / 0 / 0 |
| DS29-0082 | 3 | 1,789 → 1,792 | 29 → 29 | 5 / 3 / 1 |
| DS29-0519 | 1 | 4,274 → 4,275 | 88 → 88 | 4 / 1 / 0 |

The full Graph reassigned support in response to the altered winners, gaining eight observation keys and losing six across the four recordings. Only two of 21 altered probes are on active-curvature tracks, at DS26-0162 visit 76 and DS29-0082 visit 130. Total component count and cavity nomination are unchanged for each recording. The independent installed Graph replay reproduced the inference worker’s observation and component counters. It records whether a physical probe reached Graph preparation. That output cannot identify individual final solver ownership or assign the endpoint movement to a single probe. [Graph totals](graph-support.csv) · [Full track membership](graph-tracks.jsonl.gz)

## Execution and evidence boundary

The stock and hint-off calls reproduced all 64 scheduled physical probe packets from the full-wide archives. All four compositions reproduced the exact native archive SHA in stock. The four fresh stock position workers also reproduced the archived science fields apart from stage timing. All 12 factor-to-position workers terminated successfully on their assigned CPUs, under the 210 s cap, 512 MiB limit and no swap. Position-stage wall time ranged 27.41–81.09 s for stock, 26.88–75.22 s for rank-one and 26.06–72.54 s for sham. These one-run timings reflect the order of the replay and shared host. The cgroup memory and process CPU receipts are recorded separately from the scout's raw work. [Prediction seal](prediction-lock.json) · [Resource receipts](resources.json)

A full recording retained 9,736 to 13,532 physical receiver probes. Each composition applied eight raw windows per recording and used stock wide factors for every other window. Capture clocks, retune fields, receiver metadata, solver configuration, original tile and causal TLE authority stayed fixed. The timing hint itself uses raw samples. The window roster was deliberately selected using historical misses and preservation controls. The four recordings are therefore a selected partial-IQ position replay and cannot establish whole-IQ performance or geographic transfer. [Frozen protocol](PROTOCOL.md) · [Source and input lock](source-lock.json) · [Standard figure manifest](figures.json) · [Figure data seal](figure-lock.json)
