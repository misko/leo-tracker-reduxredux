# 13-dwell strict degree-1-only rerun

This report-only rerun starts from each sealed `standard.pilot-scan` V3 product. Every candidate was scored independently at its probe. A new trajectory bank was fitted with `polynomial_degrees=(1,)`. Persisted raw-family representatives, de-aliased membership, IQ-replay membership, and final tracks were not reused.

**Selected** means a representative of a family built entirely from degree-1 tracks. It is not a newly sealed Standard final product. This bounded rerun does not replay IQ or claim the published de-alias/replay gates, so it never labels these results as after replay.

| Contamination audit of superseded report sections | Count |
|---|---:|
| Former displayed top-three tracks from d3 membership | 15 / 15 |
| Former post-replay tracks from d2 or d3 membership | 47 / 61 |

Those old post-replay results are not inputs to this rerun.

## Observation and RF provenance

| Field | Value |
|---|---|
| Observer latitude | 37.858988° |
| Observer longitude | -122.478103° |
| Observer altitude | -29.0 m |
| LNB model reported for 3 of 4 paths | GEOSATpro UL1PLL |
| Configured acquisition LNB local oscillator | 9.75 GHz |
| Per-path physical LNB mapping | Unknown |

Reconstructed RF is tuned IF plus the configured 9.75 GHz LO. Each track used below was also checked against the authoritative channel/edge RF center; the machine-readable `rf_consistency_error_hz` records any difference. Physical LNB serial-to-path mapping remains unknown, but it does not change the requested RF encoded by the acquisition binding.

## Cross-capture basin-retention control

A separate capture, `cap-20260821T030352-0b45a2531e70`, tests search mechanics. It is outside this cohort and does not support satellite association. Fixed 8/16/32 is candidate-level and uses no trajectory prior. Alias-edge 6+2 also uses no fitted CFO trajectory.

![Candidate-level fixed basin-count timeline](figures/2026_08_21_0b45a2531e70_basin_recovery/basin-count-timeline.png)

![Candidate-level fixed basin-count summary](figures/2026_08_21_0b45a2531e70_basin_recovery/basin-count-summary.png)

![Alias-edge 6+2 output timeline](figures/2026_08_21_0b45a2531e70_basin_recovery/guided-eight-output-timeline.png)

Basin-track-consistency and CFO-guided policy figures are deliberately omitted because those analyses used a quadratic trajectory.

Machine-readable evidence: [five-dwell-d1only-evidence.json](figures/2026_08_23_thirteen_dwell_degree1_fresh/five-dwell-d1only-evidence.json)

![Degree-1-only rate distribution](figures/2026_08_23_thirteen_dwell_degree1_fresh/five-dwell-d1only-rate-distribution.png)

The raw-d1 set contains **181** trajectories; the selected-pre-replay set contains **180** families. This is not an after-replay comparison.

## Focused T1 strict-linear association and basin impact

This focused audit starts from the 32 independently scored raw-IQ GLRT candidates at each probe. RANSAC associates at most one candidate per probe, and Huber refits only an intercept and one constant slope. Its breakpoints are selected within disclosed post-hoc windows; none comes from the superseded mixed-order replay membership.

| Piece | Interval | Constant rate | Step entering | Support | Median |residual| |
|---:|---:|---:|---:|---:|---:|
| 1 | 0.000–6.825 s | -4954.6 Hz/s | — | 142/162 | 71.7 Hz |
| 2 | 6.825–13.525 s | -5560.5 Hz/s | -4.98 kHz | 235/237 | 97.9 Hz |
| 3 | 13.525–20.250 s | -6175.2 Hz/s | -4.25 kHz | 260/261 | 23.5 Hz |
| 4 | 20.250–27.250 s | -5886.1 Hz/s | -4.65 kHz | 251/262 | 39.8 Hz |

![Strict degree-1 T1 association](figures/2026_08_21_t1_dense_degree1_only/t1-dense-degree1-only.png)

The first supported transition is **6.825 s**. The earlier ≈7.9 s marker was an equal-duration plotting boundary, not a fitted changepoint. The four straight rates are real candidate-level line coherence; they do not establish that all four epochs came from one spacecraft.

### What better basin retention and CFO search change

An acquisition basin is a distinct local timing/CFO maximum for one 20 ms probe. Raising the retained count from 8 to 32 keeps more synchronization alternatives for later straight-line association; it does not add time samples or make adjacent probes dependent. A finer CFO/GLRT grid reduces quantization and refinement error after a useful basin survives.

![Strict-linear basin and grid ablation](figures/2026_08_21_t1_dense_degree1_only/t1-basin-impact-degree1-only.png)

![Full dense independent GLRT interval](figures/2026_08_21_dense_independent_glrt/dense-independent-glrt-full.png)

![Dense independent GLRT P1-endpoint zoom](figures/2026_08_21_dense_independent_glrt/dense-independent-glrt-p1-zoom.png)

A later raw-IQ one-factor sweep resolves the mechanism more precisely. In 7.5–7.9 s, Standard recovers 13/16 probes from its complete inventory; 32 basins with the original broad separation recovers 14/16; a 10 kHz coarse grid recovers 15/16; and changing only nonmaximum-suppression separation from 80 kHz/20 samples to 10 kHz/5 samples recovers 16/16. Thus candidate-retention geometry—especially separation policy—is the dominant local fix. Basin count alone helps but is not sufficient. See the [full parameter study](2026_08_22_t1_glrt_search_parameter_study.md).

This overturns one narrow interpretation: missing replay markers near the end of the old P1 panel are not evidence that the RF signal vanished or physically stepped there. The independently searched signal branch continues. The old candidate truncation and mixed-order family selection made its membership brittle.

![Matched time-permutation control](figures/2026_08_21_t1_dense_degree1_only/t1-degree1-time-permutation-null.png)

Recorded time order supports **888** probes; the largest of 80 matched time-permutation controls supports **48**. The plus-one p-value is 0.0123. This tests temporal line coherence after searching 32 alternatives, not Starlink attribution; capture selection and breakpoint-window choice remain post hoc.

The published replay is deliberately not compared here because its membership was seeded by a mixed-order family representative. A true after-replay distribution remains pending the separately versioned linear-only pipeline. See the [focused T1 report](2026_08_21_t1_dense_degree1_only.md) for full method details.

## Dwell 1: `cap-20260821T201522-841b2a20e151`

Fresh raw degree-1 tracks: **14**. Selected pre-replay d1 families: **14**.

Capture start: **2026-08-21T20:15:24.015201+00:00**. Space-Track snapshot: **2026-08-21T20:02:09.960326+00:00**, 13.2 minutes before capture. Causal: **yes**.

![Independent GLRT64 candidates and raw d1 fits](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T201522-841b2a20e151-d1only-raw.png)

![Selected pre-replay d1 families](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T201522-841b2a20e151-d1only-selected.png)

### Up to three tracks and their top three broad-sky candidates

The satellite candidates use a broader elevation ≥10° legacy scalar-rate screen as a secondary control.

| Track | Sat. rank | Path / RF | Duration | Obs. | Rate | Satellite | Elev. | Predicted | Error | TLE age | True-time rank |
|---|---:|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| **T1** | 1 | `stream-1/RX1` / 10.7096875 GHz | 26.38 s | 1346 | -6099.9 | STARLINK-11412 | 65.6° | -4615.1 | 1484.8 | 4.83 h | 6/41 |
| **T1** | 2 | `stream-1/RX1` / 10.7096875 GHz | 26.38 s | 1346 | -6099.9 | STARLINK-30533 | 72.3° | -3665.4 | 2434.6 | 17.40 h | 6/41 |
| **T1** | 3 | `stream-1/RX1` / 10.7096875 GHz | 26.38 s | 1346 | -6099.9 | STARLINK-32200 | 69.7° | -3606.8 | 2493.2 | 11.51 h | 6/41 |
| **T2** | 1 | `stream-0/RX1` / 11.6903125 GHz | 26.02 s | 1655 | -6533.5 | STARLINK-11412 | 65.6° | -5036.4 | 1497.0 | 4.83 h | 6/41 |
| **T2** | 2 | `stream-0/RX1` / 11.6903125 GHz | 26.02 s | 1655 | -6533.5 | STARLINK-30533 | 72.3° | -4000.1 | 2533.3 | 17.40 h | 6/41 |
| **T2** | 3 | `stream-0/RX1` / 11.6903125 GHz | 26.02 s | 1655 | -6533.5 | STARLINK-32200 | 69.7° | -3936.1 | 2597.3 | 11.51 h | 6/41 |
| **T3** | 1 | `stream-1/RX1` / 10.7096875 GHz | 17.12 s | 263 | -3903.4 | STARLINK-11412 | 55.4° | -3474.6 | 428.8 | 4.84 h | 39/41 |
| **T3** | 2 | `stream-1/RX1` / 10.7096875 GHz | 17.12 s | 263 | -3903.4 | STARLINK-30277 | 77.0° | -3422.1 | 481.3 | 4.98 h | 39/41 |
| **T3** | 3 | `stream-1/RX1` / 10.7096875 GHz | 17.12 s | 263 | -3903.4 | STARLINK-36506 | 74.8° | -3388.0 | 515.4 | 9.93 h | 39/41 |

### 30° zenith cone during the full capture

Half-angle 30° is equivalent to elevation ≥60°. Intervals are relative to capture start.

| Satellite | NORAD | Peak elevation | Visible interval(s) | TLE age |
|---|---:|---:|---|---:|
| STARLINK-11412 | 63062 | 66.2° | 1.40–37.38 s | 4.83 h |
| STARLINK-30277 | 57645 | 81.3° | 0.00–60.00 s | 4.97 h |
| STARLINK-30379 | 57811 | 63.8° | 0.00–19.67 s | 9.94 h |
| STARLINK-30533 | 58037 | 73.2° | 0.00–51.60 s | 17.40 h |
| STARLINK-32200 | 60258 | 70.6° | 0.00–49.82 s | 11.51 h |
| STARLINK-3312 | 50850 | 62.3° | 0.00–28.80 s | 22.26 h |
| STARLINK-35493 | 65928 | 80.1° | 0.00–25.24 s | 17.41 h |
| STARLINK-36506 | 67414 | 78.8° | 0.00–60.00 s | 9.92 h |
| STARLINK-36526 | 67508 | 66.3° | 39.56–60.00 s | 20.64 h |
| STARLINK-37407 | 69534 | 71.2° | 43.88–60.00 s | 25.55 h |
| STARLINK-5286 | 55294 | 88.1° | 16.10–60.00 s | 5.41 h |
| STARLINK-5451 | 54771 | 62.5° | 20.45–53.02 s | 9.97 h |
| STARLINK-5631 | 55346 | 60.4° | 59.15–60.00 s | 12.83 h |
| STARLINK-5663 | 55347 | 60.5° | 0.00–0.89 s | 5.01 h |
| STARLINK-6218 | 57368 | 81.9° | 29.64–60.00 s | 9.90 h |

![TLE rate field](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T201522-841b2a20e151-d1only-tle-rate.png)

![Full-capture cone and broad-control overlay](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T201522-841b2a20e151-d1only-tle-overlay.png)

![Wrong-time null controls](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T201522-841b2a20e151-d1only-null.png)

## Dwell 2: `cap-20260821T193701-87f96f47e73f`

Fresh raw degree-1 tracks: **17**. Selected pre-replay d1 families: **17**.

Capture start: **2026-08-21T19:37:03.687769+00:00**. Space-Track snapshot: **2026-08-21T19:01:38.807480+00:00**, 35.4 minutes before capture. Causal: **yes**.

![Independent GLRT64 candidates and raw d1 fits](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T193701-87f96f47e73f-d1only-raw.png)

![Selected pre-replay d1 families](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T193701-87f96f47e73f-d1only-selected.png)

### Up to three tracks and their top three broad-sky candidates

The satellite candidates use a broader elevation ≥10° legacy scalar-rate screen as a secondary control.

| Track | Sat. rank | Path / RF | Duration | Obs. | Rate | Satellite | Elev. | Predicted | Error | TLE age | True-time rank |
|---|---:|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| **T1** | 1 | `stream-1/RX1` / 11.4403125 GHz | 12.25 s | 739 | -5707.4 | STARLINK-11083 | 61.2° | -4427.5 | 1279.9 | 11.25 h | 12/41 |
| **T1** | 2 | `stream-1/RX1` / 11.4403125 GHz | 12.25 s | 739 | -5707.4 | STARLINK-1413 | 80.4° | -4170.0 | 1537.4 | 6.79 h | 12/41 |
| **T1** | 3 | `stream-1/RX1` / 11.4403125 GHz | 12.25 s | 739 | -5707.4 | STARLINK-36318 | 79.1° | -4046.3 | 1661.1 | 11.50 h | 12/41 |
| **T2** | 1 | `stream-0/RX1` / 10.9596875 GHz | 7.17 s | 85 | -4126.6 | STARLINK-3999 | 77.7° | -3761.6 | 365.1 | 18.97 h | 26/41 |
| **T2** | 2 | `stream-0/RX1` / 10.9596875 GHz | 7.17 s | 85 | -4126.6 | STARLINK-35808 | 69.3° | -3648.1 | 478.6 | 11.50 h | 26/41 |
| **T2** | 3 | `stream-0/RX1` / 10.9596875 GHz | 7.17 s | 85 | -4126.6 | STARLINK-36451 | 73.1° | -3485.6 | 641.0 | 3.66 h | 26/41 |
| **T3** | 1 | `stream-0/RX1` / 10.9596875 GHz | 6.95 s | 260 | -3816.8 | STARLINK-35808 | 68.1° | -3572.1 | 244.7 | 11.50 h | 31/41 |
| **T3** | 2 | `stream-0/RX1` / 10.9596875 GHz | 6.95 s | 260 | -3816.8 | STARLINK-32701 | 57.4° | -3121.0 | 695.7 | 5.02 h | 31/41 |
| **T3** | 3 | `stream-0/RX1` / 10.9596875 GHz | 6.95 s | 260 | -3816.8 | STARLINK-32159 | 48.2° | -2988.8 | 828.0 | 25.56 h | 31/41 |

### 30° zenith cone during the full capture

Half-angle 30° is equivalent to elevation ≥60°. Intervals are relative to capture start.

| Satellite | NORAD | Peak elevation | Visible interval(s) | TLE age |
|---|---:|---:|---|---:|
| STARLINK-11083 | 59424 | 66.1° | 0.00–14.79 s | 11.24 h |
| STARLINK-1413 | 45689 | 89.9° | 0.00–37.09 s | 6.79 h |
| STARLINK-30413 | 57814 | 64.1° | 0.00–7.29 s | 8.35 h |
| STARLINK-31512 | 59500 | 85.5° | 0.00–50.50 s | 4.98 h |
| STARLINK-34291 | 64359 | 87.4° | 0.00–60.00 s | 13.43 h |
| STARLINK-34476 | 64364 | 88.0° | 0.00–51.63 s | 5.42 h |
| STARLINK-35682 | 66467 | 82.2° | 0.00–35.20 s | 4.99 h |
| STARLINK-35808 | 68052 | 70.3° | 16.52–60.00 s | 11.49 h |
| STARLINK-36318 | 68048 | 79.3° | 0.00–48.84 s | 11.50 h |
| STARLINK-36451 | 67339 | 75.1° | 0.00–60.00 s | 3.65 h |
| STARLINK-36468 | 67415 | 62.3° | 0.00–20.94 s | 8.33 h |
| STARLINK-37603 | 69846 | 63.6° | 0.00–26.68 s | 20.51 h |
| STARLINK-3999 | 52704 | 84.1° | 0.00–60.00 s | 18.96 h |
| STARLINK-5422 | 54804 | 73.3° | 0.00–18.28 s | 11.51 h |

![TLE rate field](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T193701-87f96f47e73f-d1only-tle-rate.png)

![Full-capture cone and broad-control overlay](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T193701-87f96f47e73f-d1only-tle-overlay.png)

![Wrong-time null controls](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T193701-87f96f47e73f-d1only-null.png)

## Dwell 3: `cap-20260821T193440-17c2e0ebef6a`

Fresh raw degree-1 tracks: **12**. Selected pre-replay d1 families: **12**.

Capture start: **2026-08-21T19:34:42.311499+00:00**. Space-Track snapshot: **2026-08-21T19:01:38.807480+00:00**, 33.1 minutes before capture. Causal: **yes**.

![Independent GLRT64 candidates and raw d1 fits](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T193440-17c2e0ebef6a-d1only-raw.png)

![Selected pre-replay d1 families](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T193440-17c2e0ebef6a-d1only-selected.png)

### Up to three tracks and their top three broad-sky candidates

The satellite candidates use a broader elevation ≥10° legacy scalar-rate screen as a secondary control.

| Track | Sat. rank | Path / RF | Duration | Obs. | Rate | Satellite | Elev. | Predicted | Error | TLE age | True-time rank |
|---|---:|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| **T1** | 1 | `stream-1/RX1` / 10.9403125 GHz | 15.93 s | 948 | -6069.2 | STARLINK-6135 | 73.7° | -3465.1 | 2604.0 | 22.48 h | 38/41 |
| **T1** | 2 | `stream-1/RX1` / 10.9403125 GHz | 15.93 s | 948 | -6069.2 | STARLINK-34901 | 62.8° | -3377.0 | 2692.1 | 18.98 h | 38/41 |
| **T1** | 3 | `stream-1/RX1` / 10.9403125 GHz | 15.93 s | 948 | -6069.2 | STARLINK-35371 | 73.2° | -3286.7 | 2782.5 | 19.12 h | 38/41 |
| **T2** | 1 | `stream-0/RX1` / 10.9403125 GHz | 15.60 s | 788 | -4981.8 | STARLINK-35371 | 78.7° | -3512.7 | 1469.1 | 19.12 h | 36/41 |
| **T2** | 2 | `stream-0/RX1` / 10.9403125 GHz | 15.60 s | 788 | -4981.8 | STARLINK-3844 | 68.8° | -3368.7 | 1613.1 | 11.16 h | 36/41 |
| **T2** | 3 | `stream-0/RX1` / 10.9403125 GHz | 15.60 s | 788 | -4981.8 | STARLINK-37589 | 58.4° | -3327.8 | 1654.0 | 19.59 h | 36/41 |
| **T3** | 1 | `stream-1/RX1` / 10.9403125 GHz | 12.77 s | 634 | -4196.1 | STARLINK-35371 | 82.6° | -3626.1 | 570.0 | 19.11 h | 30/41 |
| **T3** | 2 | `stream-1/RX1` / 10.9403125 GHz | 12.77 s | 634 | -4196.1 | STARLINK-3844 | 73.0° | -3616.2 | 579.9 | 11.16 h | 30/41 |
| **T3** | 3 | `stream-1/RX1` / 10.9403125 GHz | 12.77 s | 634 | -4196.1 | STARLINK-37589 | 59.5° | -3442.4 | 753.7 | 19.59 h | 30/41 |

### 30° zenith cone during the full capture

Half-angle 30° is equivalent to elevation ≥60°. Intervals are relative to capture start.

| Satellite | NORAD | Peak elevation | Visible interval(s) | TLE age |
|---|---:|---:|---|---:|
| STARLINK-11693 | 63763 | 62.0° | 0.00–2.16 s | 8.13 h |
| STARLINK-31421 | 59218 | 64.5° | 53.03–60.00 s | 11.14 h |
| STARLINK-31504 | 59303 | 63.6° | 0.00–5.29 s | 8.36 h |
| STARLINK-32416 | 61589 | 65.8° | 0.00–19.83 s | 9.94 h |
| STARLINK-32752 | 62567 | 68.3° | 0.00–18.54 s | 19.13 h |
| STARLINK-34901 | 65207 | 65.6° | 33.16–60.00 s | 18.97 h |
| STARLINK-35371 | 66484 | 84.2° | 0.00–58.94 s | 19.11 h |
| STARLINK-36431 | 67421 | 61.0° | 19.46–40.14 s | 8.32 h |
| STARLINK-37589 | 69839 | 60.0° | 17.78–21.39 s | 19.58 h |
| STARLINK-3844 | 52705 | 79.2° | 0.00–45.68 s | 11.15 h |
| STARLINK-4209 | 52855 | 75.3° | 28.94–60.00 s | 11.52 h |
| STARLINK-6135 | 56539 | 76.3° | 16.42–60.00 s | 22.47 h |
| STARLINK-6291 | 56547 | 62.4° | 3.59–35.47 s | 9.94 h |

![TLE rate field](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T193440-17c2e0ebef6a-d1only-tle-rate.png)

![Full-capture cone and broad-control overlay](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T193440-17c2e0ebef6a-d1only-tle-overlay.png)

![Wrong-time null controls](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T193440-17c2e0ebef6a-d1only-null.png)

## Dwell 4: `cap-20260821T190912-ffd441556880`

Fresh raw degree-1 tracks: **10**. Selected pre-replay d1 families: **9**.

Capture start: **2026-08-21T19:09:13.968555+00:00**. Space-Track snapshot: **2026-08-21T19:01:38.807480+00:00**, 7.6 minutes before capture. Causal: **yes**.

![Independent GLRT64 candidates and raw d1 fits](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T190912-ffd441556880-d1only-raw.png)

![Selected pre-replay d1 families](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T190912-ffd441556880-d1only-selected.png)

### Up to three tracks and their top three broad-sky candidates

The satellite candidates use a broader elevation ≥10° legacy scalar-rate screen as a secondary control.

| Track | Sat. rank | Path / RF | Duration | Obs. | Rate | Satellite | Elev. | Predicted | Error | TLE age | True-time rank |
|---|---:|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| **T1** | 1 | `stream-1/RX1` / 11.4403125 GHz | 31.83 s | 2312 | -5485.2 | STARLINK-11182 | 74.0° | -5250.4 | 234.8 | 11.24 h | 1/41 |
| **T1** | 2 | `stream-1/RX1` / 11.4403125 GHz | 31.83 s | 2312 | -5485.2 | STARLINK-11417 | 49.7° | -4169.1 | 1316.1 | 18.56 h | 1/41 |
| **T1** | 3 | `stream-1/RX1` / 11.4403125 GHz | 31.83 s | 2312 | -5485.2 | STARLINK-3935 | 77.5° | -3981.7 | 1503.5 | 3.34 h | 1/41 |
| **T2** | 1 | `stream-0/RX1` / 11.4596875 GHz | 17.00 s | 1202 | -5569.9 | STARLINK-11182 | 61.4° | -4071.2 | 1498.7 | 11.24 h | 21/41 |
| **T2** | 2 | `stream-0/RX1` / 11.4596875 GHz | 17.00 s | 1202 | -5569.9 | STARLINK-33944 | 73.5° | -3903.2 | 1666.7 | 5.16 h | 21/41 |
| **T2** | 3 | `stream-0/RX1` / 11.4596875 GHz | 17.00 s | 1202 | -5569.9 | STARLINK-11417 | 47.8° | -3868.7 | 1701.2 | 18.55 h | 21/41 |
| **T3** | 1 | `stream-0/RX1` / 11.4596875 GHz | 13.73 s | 871 | -6551.7 | STARLINK-11182 | 71.0° | -5020.4 | 1531.4 | 11.25 h | 2/41 |
| **T3** | 2 | `stream-0/RX1` / 11.4596875 GHz | 13.73 s | 871 | -6551.7 | STARLINK-11417 | 48.1° | -3919.7 | 2632.0 | 18.56 h | 2/41 |
| **T3** | 3 | `stream-0/RX1` / 11.4596875 GHz | 13.73 s | 871 | -6551.7 | STARLINK-3935 | 72.3° | -3722.3 | 2829.4 | 3.34 h | 2/41 |

### 30° zenith cone during the full capture

Half-angle 30° is equivalent to elevation ≥60°. Intervals are relative to capture start.

| Satellite | NORAD | Peak elevation | Visible interval(s) | TLE age |
|---|---:|---:|---|---:|
| STARLINK-11182 | 60399 | 74.1° | 6.67–55.37 s | 11.24 h |
| STARLINK-1522 | 46027 | 77.4° | 0.00–27.14 s | 3.39 h |
| STARLINK-30823 | 58248 | 65.6° | 42.59–60.00 s | 4.99 h |
| STARLINK-32729 | 62497 | 64.4° | 52.93–60.00 s | 19.09 h |
| STARLINK-33944 | 64209 | 74.6° | 0.00–47.17 s | 5.15 h |
| STARLINK-34976 | 65209 | 66.7° | 46.31–60.00 s | 3.32 h |
| STARLINK-3545 | 51855 | 70.0° | 41.00–60.00 s | 11.49 h |
| STARLINK-35466 | 66457 | 69.0° | 9.98–60.00 s | 4.96 h |
| STARLINK-36458 | 67343 | 75.9° | 31.24–60.00 s | 8.32 h |
| STARLINK-3935 | 52549 | 80.7° | 0.00–57.74 s | 3.33 h |
| STARLINK-5327 | 55291 | 63.6° | 38.08–60.00 s | 13.43 h |
| STARLINK-5446 | 54789 | 78.0° | 0.00–39.09 s | 10.11 h |

![TLE rate field](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T190912-ffd441556880-d1only-tle-rate.png)

![Full-capture cone and broad-control overlay](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T190912-ffd441556880-d1only-tle-overlay.png)

![Wrong-time null controls](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T190912-ffd441556880-d1only-null.png)

## Dwell 5: `cap-20260821T190701-7a5d980ec1c6`

Fresh raw degree-1 tracks: **8**. Selected pre-replay d1 families: **8**.

Capture start: **2026-08-21T19:07:02.822230+00:00**. Space-Track snapshot: **2026-08-21T19:01:38.807480+00:00**, 5.4 minutes before capture. Causal: **yes**.

![Independent GLRT64 candidates and raw d1 fits](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T190701-7a5d980ec1c6-d1only-raw.png)

![Selected pre-replay d1 families](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T190701-7a5d980ec1c6-d1only-selected.png)

### Up to three tracks and their top three broad-sky candidates

The satellite candidates use a broader elevation ≥10° legacy scalar-rate screen as a secondary control.

| Track | Sat. rank | Path / RF | Duration | Obs. | Rate | Satellite | Elev. | Predicted | Error | TLE age | True-time rank |
|---|---:|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| **T1** | 1 | `stream-1/RX1` / 11.4403125 GHz | 14.75 s | 1979 | -5387.3 | STARLINK-11599 | 50.8° | -4083.3 | 1304.0 | 3.57 h | 22/41 |
| **T1** | 2 | `stream-1/RX1` / 11.4403125 GHz | 14.75 s | 1979 | -5387.3 | STARLINK-31239 | 78.7° | -3998.7 | 1388.6 | 11.51 h | 22/41 |
| **T1** | 3 | `stream-1/RX1` / 11.4403125 GHz | 14.75 s | 1979 | -5387.3 | STARLINK-3659 | 67.8° | -3751.3 | 1635.9 | 27.11 h | 22/41 |
| **T2** | 1 | `stream-0/RX1` / 11.4403125 GHz | 14.72 s | 1835 | -5466.6 | STARLINK-11599 | 50.8° | -4083.7 | 1382.9 | 3.57 h | 22/41 |
| **T2** | 2 | `stream-0/RX1` / 11.4403125 GHz | 14.72 s | 1835 | -5466.6 | STARLINK-31239 | 78.7° | -3998.5 | 1468.2 | 11.51 h | 22/41 |
| **T2** | 3 | `stream-0/RX1` / 11.4403125 GHz | 14.72 s | 1835 | -5466.6 | STARLINK-3659 | 67.8° | -3751.1 | 1715.5 | 27.11 h | 22/41 |
| **T3** | 1 | `stream-1/RX0` / 11.4403125 GHz | 7.95 s | 328 | -4991.2 | STARLINK-31239 | 80.2° | -4052.9 | 938.4 | 11.51 h | 22/41 |
| **T3** | 2 | `stream-1/RX0` / 11.4403125 GHz | 7.95 s | 328 | -4991.2 | STARLINK-11599 | 49.8° | -3931.2 | 1060.0 | 3.57 h | 22/41 |
| **T3** | 3 | `stream-1/RX0` / 11.4403125 GHz | 7.95 s | 328 | -4991.2 | STARLINK-3659 | 68.9° | -3829.0 | 1162.2 | 27.11 h | 22/41 |

### 30° zenith cone during the full capture

Half-angle 30° is equivalent to elevation ≥60°. Intervals are relative to capture start.

| Satellite | NORAD | Peak elevation | Visible interval(s) | TLE age |
|---|---:|---:|---|---:|
| STARLINK-11567 | 62909 | 61.9° | 31.04–52.46 s | 12.48 h |
| STARLINK-30849 | 58245 | 65.1° | 47.73–60.00 s | 19.11 h |
| STARLINK-31076 | 58736 | 75.4° | 0.00–51.52 s | 8.36 h |
| STARLINK-31239 | 60093 | 80.9° | 0.00–49.63 s | 11.51 h |
| STARLINK-31480 | 59306 | 62.2° | 0.00–11.91 s | 8.33 h |
| STARLINK-32773 | 62571 | 83.5° | 0.00–55.21 s | 19.10 h |
| STARLINK-34289 | 64225 | 87.0° | 9.08–60.00 s | 11.49 h |
| STARLINK-34302 | 65216 | 64.5° | 0.00–35.15 s | 17.40 h |
| STARLINK-36225 | 67207 | 89.4° | 0.00–60.00 s | 16.20 h |
| STARLINK-36267 | 67198 | 88.8° | 0.00–50.27 s | 16.20 h |
| STARLINK-3659 | 52001 | 70.1° | 0.00–46.75 s | 27.11 h |
| STARLINK-4530 | 53393 | 67.2° | 0.00–10.89 s | 5.12 h |
| STARLINK-5665 | 55361 | 76.0° | 0.00–23.98 s | 19.12 h |
| STARLINK-6252 | 56555 | 89.0° | 11.69–60.00 s | 8.34 h |
| STARLINK-6311 | 56537 | 66.4° | 49.43–60.00 s | 8.32 h |

![TLE rate field](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T190701-7a5d980ec1c6-d1only-tle-rate.png)

![Full-capture cone and broad-control overlay](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T190701-7a5d980ec1c6-d1only-tle-overlay.png)

![Wrong-time null controls](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T190701-7a5d980ec1c6-d1only-null.png)

## Dwell 6: `cap-20260821T183005-a987f97b643c`

Fresh raw degree-1 tracks: **2**. Selected pre-replay d1 families: **2**.

Capture start: **2026-08-21T18:30:07.629663+00:00**. Space-Track snapshot: **2026-08-21T17:27:18.955478+00:00**, 62.8 minutes before capture. Causal: **yes**.

![Independent GLRT64 candidates and raw d1 fits](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T183005-a987f97b643c-d1only-raw.png)

![Selected pre-replay d1 families](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T183005-a987f97b643c-d1only-selected.png)

### Up to three tracks and their top three broad-sky candidates

The satellite candidates use a broader elevation ≥10° legacy scalar-rate screen as a secondary control.

| Track | Sat. rank | Path / RF | Duration | Obs. | Rate | Satellite | Elev. | Predicted | Error | TLE age | True-time rank |
|---|---:|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| **T1** | 1 | `stream-1/RX1` / 11.4403125 GHz | 7.85 s | 175 | -5734.8 | STARLINK-33795 | 81.8° | -4070.6 | 1664.3 | 18.98 h | 19/41 |
| **T1** | 2 | `stream-1/RX1` / 11.4403125 GHz | 7.85 s | 175 | -5734.8 | STARLINK-33803 | 71.3° | -3896.3 | 1838.5 | 18.97 h | 19/41 |
| **T1** | 3 | `stream-1/RX1` / 11.4403125 GHz | 7.85 s | 175 | -5734.8 | STARLINK-31830 | 76.3° | -3700.6 | 2034.2 | 11.54 h | 19/41 |
| **T2** | 1 | `stream-1/RX1` / 11.4403125 GHz | 1.80 s | 37 | -5826.8 | STARLINK-33795 | 81.7° | -4068.7 | 1758.0 | 18.98 h | 17/41 |
| **T2** | 2 | `stream-1/RX1` / 11.4403125 GHz | 1.80 s | 37 | -5826.8 | STARLINK-33803 | 69.3° | -3763.3 | 2063.5 | 18.97 h | 17/41 |
| **T2** | 3 | `stream-1/RX1` / 11.4403125 GHz | 1.80 s | 37 | -5826.8 | STARLINK-4476 | 66.4° | -3655.3 | 2171.5 | 17.41 h | 17/41 |

### 30° zenith cone during the full capture

Half-angle 30° is equivalent to elevation ≥60°. Intervals are relative to capture start.

| Satellite | NORAD | Peak elevation | Visible interval(s) | TLE age |
|---|---:|---:|---|---:|
| STARLINK-11460 | 62069 | 60.0° | 0.00–0.05 s | 11.26 h |
| STARLINK-30867 | 58231 | 71.3° | 41.05–60.00 s | 19.08 h |
| STARLINK-31830 | 59769 | 86.0° | 22.14–60.00 s | 11.52 h |
| STARLINK-31870 | 59787 | 68.0° | 12.90–60.00 s | 25.62 h |
| STARLINK-33549 | 62289 | 74.8° | 0.00–25.10 s | 24.04 h |
| STARLINK-33795 | 63457 | 82.2° | 5.91–60.00 s | 18.97 h |
| STARLINK-33803 | 63517 | 72.1° | 20.42–60.00 s | 18.96 h |
| STARLINK-35172 | 65533 | 69.5° | 47.02–60.00 s | 14.69 h |
| STARLINK-35334 | 66450 | 62.0° | 0.00–5.34 s | 12.86 h |
| STARLINK-3554 | 51872 | 68.1° | 0.00–13.21 s | 27.12 h |
| STARLINK-35784 | 67093 | 61.3° | 39.70–60.00 s | 13.43 h |
| STARLINK-35818 | 66540 | 77.4° | 0.00–48.81 s | 12.84 h |
| STARLINK-4200 | 52876 | 71.0° | 0.00–45.44 s | 11.52 h |
| STARLINK-4476 | 53419 | 69.6° | 0.00–50.86 s | 17.40 h |
| STARLINK-5346 | 56518 | 77.0° | 36.38–60.00 s | 22.46 h |

![TLE rate field](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T183005-a987f97b643c-d1only-tle-rate.png)

![Full-capture cone and broad-control overlay](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T183005-a987f97b643c-d1only-tle-overlay.png)

![Wrong-time null controls](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T183005-a987f97b643c-d1only-null.png)

## Dwell 7: `cap-20260821T162727-0abff1c9aa8e`

Fresh raw degree-1 tracks: **22**. Selected pre-replay d1 families: **22**.

Capture start: **2026-08-21T16:27:29.639830+00:00**. Space-Track snapshot: **2026-08-21T16:02:36.177090+00:00**, 24.9 minutes before capture. Causal: **yes**.

![Independent GLRT64 candidates and raw d1 fits](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T162727-0abff1c9aa8e-d1only-raw.png)

![Selected pre-replay d1 families](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T162727-0abff1c9aa8e-d1only-selected.png)

### Up to three tracks and their top three broad-sky candidates

The satellite candidates use a broader elevation ≥10° legacy scalar-rate screen as a secondary control.

| Track | Sat. rank | Path / RF | Duration | Obs. | Rate | Satellite | Elev. | Predicted | Error | TLE age | True-time rank |
|---|---:|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| **T1** | 1 | `stream-1/RX1` / 11.4596875 GHz | 16.75 s | 1606 | -6773.5 | STARLINK-37915 | 71.0° | -4232.4 | 2541.2 | 13.15 h | 20/41 |
| **T1** | 2 | `stream-1/RX1` / 11.4596875 GHz | 16.75 s | 1606 | -6773.5 | STARLINK-30898 | 75.2° | -3901.3 | 2872.3 | 9.94 h | 20/41 |
| **T1** | 3 | `stream-1/RX1` / 11.4596875 GHz | 16.75 s | 1606 | -6773.5 | STARLINK-36625 | 56.7° | -3774.9 | 2998.6 | 14.71 h | 20/41 |
| **T2** | 1 | `stream-1/RX0` / 11.4596875 GHz | 13.60 s | 310 | -6925.7 | STARLINK-37915 | 71.3° | -4252.1 | 2673.6 | 13.15 h | 19/41 |
| **T2** | 2 | `stream-1/RX0` / 11.4596875 GHz | 13.60 s | 310 | -6925.7 | STARLINK-30898 | 74.4° | -3858.5 | 3067.2 | 9.94 h | 19/41 |
| **T2** | 3 | `stream-1/RX0` / 11.4596875 GHz | 13.60 s | 310 | -6925.7 | STARLINK-36625 | 56.9° | -3799.9 | 3125.7 | 14.71 h | 19/41 |
| **T3** | 1 | `stream-0/RX1` / 10.7096875 GHz | 9.85 s | 962 | -5715.2 | STARLINK-37915 | 70.3° | -3912.5 | 1802.7 | 13.15 h | 19/41 |
| **T3** | 2 | `stream-0/RX1` / 10.7096875 GHz | 9.85 s | 962 | -5715.2 | STARLINK-36625 | 57.1° | -3581.8 | 2133.5 | 14.71 h | 19/41 |
| **T3** | 3 | `stream-0/RX1` / 10.7096875 GHz | 9.85 s | 962 | -5715.2 | STARLINK-37263 | 66.0° | -3516.6 | 2198.6 | 9.93 h | 19/41 |

### 30° zenith cone during the full capture

Half-angle 30° is equivalent to elevation ≥60°. Intervals are relative to capture start.

| Satellite | NORAD | Peak elevation | Visible interval(s) | TLE age |
|---|---:|---:|---|---:|
| STARLINK-30898 | 58387 | 78.3° | 0.00–46.02 s | 9.94 h |
| STARLINK-32560 | 61982 | 77.7° | 10.37–60.00 s | 9.92 h |
| STARLINK-32598 | 62046 | 63.1° | 52.58–60.00 s | 22.21 h |
| STARLINK-34159 | 63952 | 65.2° | 0.00–38.05 s | 9.94 h |
| STARLINK-35945 | 66925 | 72.1° | 0.00–15.94 s | 11.51 h |
| STARLINK-36726 | 67925 | 67.7° | 0.00–15.39 s | 28.54 h |
| STARLINK-37263 | 68544 | 66.4° | 17.08–60.00 s | 9.92 h |
| STARLINK-37915 | 69722 | 71.5° | 0.00–55.92 s | 13.14 h |
| STARLINK-5977 | 56791 | 68.3° | 0.00–20.88 s | 11.84 h |
| STARLINK-6282 | 56407 | 70.1° | 0.00–24.33 s | 9.91 h |

![TLE rate field](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T162727-0abff1c9aa8e-d1only-tle-rate.png)

![Full-capture cone and broad-control overlay](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T162727-0abff1c9aa8e-d1only-tle-overlay.png)

![Wrong-time null controls](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T162727-0abff1c9aa8e-d1only-null.png)

## Dwell 8: `cap-20260821T162517-85cfb560afe8`

Fresh raw degree-1 tracks: **16**. Selected pre-replay d1 families: **16**.

Capture start: **2026-08-21T16:25:18.807384+00:00**. Space-Track snapshot: **2026-08-21T16:02:36.177090+00:00**, 22.7 minutes before capture. Causal: **yes**.

![Independent GLRT64 candidates and raw d1 fits](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T162517-85cfb560afe8-d1only-raw.png)

![Selected pre-replay d1 families](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T162517-85cfb560afe8-d1only-selected.png)

### Up to three tracks and their top three broad-sky candidates

The satellite candidates use a broader elevation ≥10° legacy scalar-rate screen as a secondary control.

| Track | Sat. rank | Path / RF | Duration | Obs. | Rate | Satellite | Elev. | Predicted | Error | TLE age | True-time rank |
|---|---:|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| **T1** | 1 | `stream-0/RX1` / 11.4596875 GHz | 27.67 s | 1916 | -6074.0 | STARLINK-37236 | 75.7° | -4356.1 | 1718.0 | 14.71 h | 21/41 |
| **T1** | 2 | `stream-0/RX1` / 11.4596875 GHz | 27.67 s | 1916 | -6074.0 | STARLINK-11385 | 59.9° | -3846.8 | 2227.2 | 11.24 h | 21/41 |
| **T1** | 3 | `stream-0/RX1` / 11.4596875 GHz | 27.67 s | 1916 | -6074.0 | STARLINK-30217 | 84.8° | -3826.4 | 2247.6 | 22.25 h | 21/41 |
| **T2** | 1 | `stream-1/RX1` / 11.6903125 GHz | 18.35 s | 1470 | -6162.6 | STARLINK-37236 | 75.9° | -4454.0 | 1708.6 | 14.71 h | 21/41 |
| **T2** | 2 | `stream-1/RX1` / 11.6903125 GHz | 18.35 s | 1470 | -6162.6 | STARLINK-11385 | 63.1° | -4265.4 | 1897.2 | 11.24 h | 21/41 |
| **T2** | 3 | `stream-1/RX1` / 11.6903125 GHz | 18.35 s | 1470 | -6162.6 | STARLINK-30217 | 86.1° | -3923.3 | 2239.3 | 22.25 h | 21/41 |
| **T3** | 1 | `stream-1/RX1` / 11.6903125 GHz | 16.12 s | 672 | -4001.9 | STARLINK-37236 | 69.3° | -4022.3 | 20.4 | 14.71 h | 4/41 |
| **T3** | 2 | `stream-1/RX1` / 11.6903125 GHz | 16.12 s | 672 | -4001.9 | STARLINK-31588 | 69.8° | -3667.3 | 334.5 | 9.91 h | 4/41 |
| **T3** | 3 | `stream-1/RX1` / 11.6903125 GHz | 16.12 s | 672 | -4001.9 | STARLINK-36736 | 70.7° | -3627.6 | 374.2 | 22.26 h | 4/41 |

### 30° zenith cone during the full capture

Half-angle 30° is equivalent to elevation ≥60°. Intervals are relative to capture start.

| Satellite | NORAD | Peak elevation | Visible interval(s) | TLE age |
|---|---:|---:|---|---:|
| STARLINK-11385 | 62014 | 76.6° | 27.53–60.00 s | 11.24 h |
| STARLINK-30217 | 57450 | 86.1° | 0.00–60.00 s | 22.24 h |
| STARLINK-31588 | 59335 | 70.6° | 0.00–36.05 s | 9.90 h |
| STARLINK-31817 | 59731 | 69.5° | 0.00–13.85 s | 9.92 h |
| STARLINK-34120 | 63898 | 64.1° | 6.44–47.26 s | 9.93 h |
| STARLINK-34386 | 66096 | 73.7° | 36.97–60.00 s | 20.52 h |
| STARLINK-35094 | 65395 | 78.0° | 32.64–60.00 s | 12.91 h |
| STARLINK-35297 | 66010 | 63.6° | 22.29–59.09 s | 18.97 h |
| STARLINK-36736 | 67911 | 72.9° | 0.00–34.06 s | 22.26 h |
| STARLINK-37236 | 68781 | 75.9° | 0.00–60.00 s | 14.70 h |

![TLE rate field](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T162517-85cfb560afe8-d1only-tle-rate.png)

![Full-capture cone and broad-control overlay](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T162517-85cfb560afe8-d1only-tle-overlay.png)

![Wrong-time null controls](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T162517-85cfb560afe8-d1only-null.png)

## Dwell 9: `cap-20260821T162303-580cc01dffb5`

Fresh raw degree-1 tracks: **20**. Selected pre-replay d1 families: **20**.

Capture start: **2026-08-21T16:23:06.382921+00:00**. Space-Track snapshot: **2026-08-21T16:02:36.177090+00:00**, 20.5 minutes before capture. Causal: **yes**.

![Independent GLRT64 candidates and raw d1 fits](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T162303-580cc01dffb5-d1only-raw.png)

![Selected pre-replay d1 families](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T162303-580cc01dffb5-d1only-selected.png)

### Up to three tracks and their top three broad-sky candidates

The satellite candidates use a broader elevation ≥10° legacy scalar-rate screen as a secondary control.

| Track | Sat. rank | Path / RF | Duration | Obs. | Rate | Satellite | Elev. | Predicted | Error | TLE age | True-time rank |
|---|---:|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| **T1** | 1 | `stream-0/RX0` / 10.7096875 GHz | 15.08 s | 631 | -5615.0 | STARLINK-11631 | 46.8° | -3814.6 | 1800.5 | 18.55 h | 31/41 |
| **T1** | 2 | `stream-0/RX0` / 10.7096875 GHz | 15.08 s | 631 | -5615.0 | STARLINK-38173 | 51.3° | -3505.1 | 2109.9 | 9.75 h | 31/41 |
| **T1** | 3 | `stream-0/RX0` / 10.7096875 GHz | 15.08 s | 631 | -5615.0 | STARLINK-35596 | 71.0° | -3364.6 | 2250.4 | 20.55 h | 31/41 |
| **T2** | 1 | `stream-0/RX1` / 10.7096875 GHz | 14.70 s | 1183 | -6236.5 | STARLINK-38173 | 64.6° | -5254.0 | 982.5 | 9.74 h | 7/41 |
| **T2** | 2 | `stream-0/RX1` / 10.7096875 GHz | 14.70 s | 1183 | -6236.5 | STARLINK-35596 | 81.4° | -3812.7 | 2423.8 | 20.54 h | 7/41 |
| **T2** | 3 | `stream-0/RX1` / 10.7096875 GHz | 14.70 s | 1183 | -6236.5 | STARLINK-11604 | 50.7° | -3422.7 | 2813.8 | 9.63 h | 7/41 |
| **T3** | 1 | `stream-1/RX1` / 10.9403125 GHz | 13.73 s | 416 | -5118.4 | STARLINK-38173 | 59.5° | -4707.5 | 410.9 | 9.74 h | 13/41 |
| **T3** | 2 | `stream-1/RX1` / 10.9403125 GHz | 13.73 s | 416 | -5118.4 | STARLINK-35596 | 79.3° | -3826.5 | 1291.8 | 20.54 h | 13/41 |
| **T3** | 3 | `stream-1/RX1` / 10.9403125 GHz | 13.73 s | 416 | -5118.4 | STARLINK-11631 | 45.9° | -3738.7 | 1379.6 | 18.55 h | 13/41 |

### 30° zenith cone during the full capture

Half-angle 30° is equivalent to elevation ≥60°. Intervals are relative to capture start.

| Satellite | NORAD | Peak elevation | Visible interval(s) | TLE age |
|---|---:|---:|---|---:|
| STARLINK-32571 | 62055 | 60.9° | 0.00–5.06 s | 22.23 h |
| STARLINK-33802 | 64392 | 74.0° | 40.31–60.00 s | 9.90 h |
| STARLINK-34187 | 63956 | 69.2° | 17.08–60.00 s | 9.92 h |
| STARLINK-34669 | 64811 | 80.4° | 21.44–60.00 s | 9.77 h |
| STARLINK-35058 | 65394 | 62.4° | 0.00–4.53 s | 12.94 h |
| STARLINK-35311 | 66032 | 64.4° | 0.00–9.38 s | 20.55 h |
| STARLINK-35596 | 66086 | 81.6° | 0.00–47.60 s | 20.54 h |
| STARLINK-36153 | 66934 | 87.2° | 18.50–60.00 s | 9.93 h |
| STARLINK-36642 | 67659 | 66.1° | 39.71–60.00 s | 14.69 h |
| STARLINK-37641 | 69445 | 61.5° | 29.76–53.99 s | 27.14 h |
| STARLINK-38007 | 69723 | 62.0° | 44.94–60.00 s | 14.70 h |
| STARLINK-38173 | 100151 | 66.0° | 0.00–19.28 s | 9.74 h |
| STARLINK-4483 | 53532 | 60.5° | 4.90–22.44 s | 20.90 h |
| STARLINK-5212 | 54075 | 81.2° | 27.09–60.00 s | 11.51 h |
| STARLINK-5350 | 56419 | 67.6° | 0.00–51.04 s | 9.90 h |
| STARLINK-6321 | 57340 | 68.3° | 46.02–60.00 s | 26.92 h |

![TLE rate field](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T162303-580cc01dffb5-d1only-tle-rate.png)

![Full-capture cone and broad-control overlay](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T162303-580cc01dffb5-d1only-tle-overlay.png)

![Wrong-time null controls](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T162303-580cc01dffb5-d1only-null.png)

## Dwell 10: `cap-20260821T161404-d421b003eb3b`

Fresh raw degree-1 tracks: **14**. Selected pre-replay d1 families: **14**.

Capture start: **2026-08-21T16:14:06.062503+00:00**. Space-Track snapshot: **2026-08-21T16:02:36.177090+00:00**, 11.5 minutes before capture. Causal: **yes**.

![Independent GLRT64 candidates and raw d1 fits](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T161404-d421b003eb3b-d1only-raw.png)

![Selected pre-replay d1 families](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T161404-d421b003eb3b-d1only-selected.png)

### Up to three tracks and their top three broad-sky candidates

The satellite candidates use a broader elevation ≥10° legacy scalar-rate screen as a secondary control.

| Track | Sat. rank | Path / RF | Duration | Obs. | Rate | Satellite | Elev. | Predicted | Error | TLE age | True-time rank |
|---|---:|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| **T1** | 1 | `stream-1/RX1` / 11.4596875 GHz | 20.02 s | 1674 | -6382.8 | STARLINK-38247 | 67.9° | -6180.5 | 202.3 | 25.98 h | 3/41 |
| **T1** | 2 | `stream-1/RX1` / 11.4596875 GHz | 20.02 s | 1674 | -6382.8 | STARLINK-38147 | 68.0° | -6143.2 | 239.7 | 25.99 h | 3/41 |
| **T1** | 3 | `stream-1/RX1` / 11.4596875 GHz | 20.02 s | 1674 | -6382.8 | STARLINK-38132 | 74.7° | -5658.6 | 724.2 | 14.32 h | 3/41 |
| **T2** | 1 | `stream-0/RX1` / 11.6903125 GHz | 14.60 s | 767 | -6245.4 | STARLINK-38247 | 67.4° | -6231.4 | 14.0 | 25.98 h | 1/41 |
| **T2** | 2 | `stream-0/RX1` / 11.6903125 GHz | 14.60 s | 767 | -6245.4 | STARLINK-38147 | 68.2° | -6286.8 | 41.4 | 25.99 h | 1/41 |
| **T2** | 3 | `stream-0/RX1` / 11.6903125 GHz | 14.60 s | 767 | -6245.4 | STARLINK-38132 | 78.4° | -6038.8 | 206.6 | 14.32 h | 1/41 |
| **T3** | 1 | `stream-0/RX1` / 11.6903125 GHz | 12.82 s | 675 | -6757.1 | STARLINK-38247 | 66.3° | -6099.1 | 658.0 | 25.98 h | 4/41 |
| **T3** | 2 | `stream-0/RX1` / 11.6903125 GHz | 12.82 s | 675 | -6757.1 | STARLINK-38147 | 64.7° | -5843.3 | 913.8 | 25.99 h | 4/41 |
| **T3** | 3 | `stream-0/RX1` / 11.6903125 GHz | 12.82 s | 675 | -6757.1 | STARLINK-11128 | 64.7° | -5032.1 | 1725.0 | 17.03 h | 4/41 |

### 30° zenith cone during the full capture

Half-angle 30° is equivalent to elevation ≥60°. Intervals are relative to capture start.

| Satellite | NORAD | Peak elevation | Visible interval(s) | TLE age |
|---|---:|---:|---|---:|
| STARLINK-11128 | 60302 | 65.2° | 29.21–60.00 s | 17.01 h |
| STARLINK-32569 | 61867 | 60.3° | 24.88–37.15 s | 30.11 h |
| STARLINK-33957 | 63897 | 80.1° | 0.00–41.22 s | 9.93 h |
| STARLINK-35574 | 66111 | 75.5° | 0.00–21.94 s | 22.10 h |
| STARLINK-36100 | 66942 | 70.5° | 0.00–56.62 s | 9.93 h |
| STARLINK-36690 | 67913 | 66.3° | 0.00–9.26 s | 22.26 h |
| STARLINK-36771 | 67928 | 65.6° | 51.59–60.00 s | 22.23 h |
| STARLINK-37242 | 68728 | 82.6° | 9.12–60.00 s | 12.68 h |
| STARLINK-37578 | 69451 | 76.5° | 17.44–60.00 s | 11.49 h |
| STARLINK-38116 | 100307 | 65.3° | 0.00–14.97 s | 25.99 h |
| STARLINK-38132 | 100154 | 86.6° | 35.94–60.00 s | 14.30 h |
| STARLINK-38147 | 100306 | 68.2° | 34.30–60.00 s | 25.97 h |
| STARLINK-38215 | 100305 | 66.3° | 50.89–60.00 s | 50.23 h |
| STARLINK-38247 | 100303 | 68.0° | 31.13–60.00 s | 25.97 h |
| STARLINK-4119 | 53026 | 67.5° | 0.00–13.88 s | 22.15 h |
| STARLINK-6040 | 56809 | 84.1° | 11.66–60.00 s | 11.82 h |
| STARLINK-6316 | 57335 | 79.3° | 0.00–43.19 s | 17.53 h |

![TLE rate field](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T161404-d421b003eb3b-d1only-tle-rate.png)

![Full-capture cone and broad-control overlay](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T161404-d421b003eb3b-d1only-tle-overlay.png)

![Wrong-time null controls](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T161404-d421b003eb3b-d1only-null.png)

## Dwell 11: `cap-20260821T161151-dcbe9267c25e`

Fresh raw degree-1 tracks: **16**. Selected pre-replay d1 families: **16**.

Capture start: **2026-08-21T16:11:52.731697+00:00**. Space-Track snapshot: **2026-08-21T16:02:36.177090+00:00**, 9.3 minutes before capture. Causal: **yes**.

![Independent GLRT64 candidates and raw d1 fits](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T161151-dcbe9267c25e-d1only-raw.png)

![Selected pre-replay d1 families](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T161151-dcbe9267c25e-d1only-selected.png)

### Up to three tracks and their top three broad-sky candidates

The satellite candidates use a broader elevation ≥10° legacy scalar-rate screen as a secondary control.

| Track | Sat. rank | Path / RF | Duration | Obs. | Rate | Satellite | Elev. | Predicted | Error | TLE age | True-time rank |
|---|---:|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| **T1** | 1 | `stream-0/RX1` / 11.6903125 GHz | 17.78 s | 989 | -6606.5 | STARLINK-38264 | 58.8° | -5855.9 | 750.6 | 50.20 h | 7/41 |
| **T1** | 2 | `stream-0/RX1` / 11.6903125 GHz | 17.78 s | 989 | -6606.5 | STARLINK-37416 | 49.2° | -4243.4 | 2363.0 | 50.20 h | 7/41 |
| **T1** | 3 | `stream-0/RX1` / 11.6903125 GHz | 17.78 s | 989 | -6606.5 | STARLINK-3535 | 68.6° | -3966.5 | 2639.9 | 9.95 h | 7/41 |
| **T2** | 1 | `stream-1/RX1` / 11.6903125 GHz | 13.07 s | 731 | -6385.1 | STARLINK-38264 | 58.7° | -5835.7 | 549.4 | 50.20 h | 9/41 |
| **T2** | 2 | `stream-1/RX1` / 11.6903125 GHz | 13.07 s | 731 | -6385.1 | STARLINK-37416 | 48.1° | -4052.3 | 2332.8 | 50.20 h | 9/41 |
| **T2** | 3 | `stream-1/RX1` / 11.6903125 GHz | 13.07 s | 731 | -6385.1 | STARLINK-3535 | 68.2° | -3940.8 | 2444.3 | 9.95 h | 9/41 |
| **T3** | 1 | `stream-1/RX1` / 11.6903125 GHz | 9.32 s | 481 | -6085.2 | STARLINK-38264 | 55.6° | -5291.5 | 793.7 | 50.20 h | 14/41 |
| **T3** | 2 | `stream-1/RX1` / 11.6903125 GHz | 9.32 s | 481 | -6085.2 | STARLINK-36673 | 74.8° | -4223.0 | 1862.2 | 14.71 h | 14/41 |
| **T3** | 3 | `stream-1/RX1` / 11.6903125 GHz | 9.32 s | 481 | -6085.2 | STARLINK-34144 | 81.2° | -3883.2 | 2202.0 | 9.93 h | 14/41 |

### 30° zenith cone during the full capture

Half-angle 30° is equivalent to elevation ≥60°. Intervals are relative to capture start.

| Satellite | NORAD | Peak elevation | Visible interval(s) | TLE age |
|---|---:|---:|---|---:|
| STARLINK-11326 | 62010 | 60.1° | 0.00–0.21 s | 11.25 h |
| STARLINK-11597 | 63115 | 63.5° | 48.78–60.00 s | 9.64 h |
| STARLINK-2507 | 48316 | 62.0° | 37.65–60.00 s | 14.31 h |
| STARLINK-2509 | 48318 | 65.1° | 52.45–60.00 s | 17.42 h |
| STARLINK-31213 | 58860 | 79.0° | 0.00–56.57 s | 22.23 h |
| STARLINK-31805 | 59745 | 64.7° | 51.39–60.00 s | 9.88 h |
| STARLINK-32322 | 61720 | 72.8° | 29.70–60.00 s | 17.40 h |
| STARLINK-33903 | 63828 | 64.0° | 0.00–11.40 s | 9.94 h |
| STARLINK-34144 | 63958 | 81.6° | 0.00–58.32 s | 9.92 h |
| STARLINK-34271 | 64384 | 83.5° | 15.62–60.00 s | 9.90 h |
| STARLINK-34849 | 66005 | 63.3° | 55.41–60.00 s | 22.08 h |
| STARLINK-3535 | 51722 | 68.9° | 0.00–33.87 s | 9.94 h |
| STARLINK-36459 | 67427 | 61.4° | 30.92–55.52 s | 28.54 h |
| STARLINK-36673 | 67660 | 82.1° | 5.02–60.00 s | 14.70 h |
| STARLINK-37788 | 69338 | 63.8° | 47.61–60.00 s | 14.69 h |
| STARLINK-37823 | 69427 | 78.6° | 14.89–60.00 s | 12.68 h |
| STARLINK-38152 | 100157 | 64.9° | 0.00–5.71 s | 14.33 h |
| STARLINK-6348 | 57360 | 65.6° | 48.43–60.00 s | 22.24 h |
| STARLINK-6379 | 57343 | 63.3° | 35.14–60.00 s | 26.92 h |

![TLE rate field](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T161151-dcbe9267c25e-d1only-tle-rate.png)

![Full-capture cone and broad-control overlay](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T161151-dcbe9267c25e-d1only-tle-overlay.png)

![Wrong-time null controls](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T161151-dcbe9267c25e-d1only-null.png)

## Dwell 12: `cap-20260821T160941-a38f080a2122`

Fresh raw degree-1 tracks: **11**. Selected pre-replay d1 families: **11**.

Capture start: **2026-08-21T16:09:43.499013+00:00**. Space-Track snapshot: **2026-08-21T16:02:36.177090+00:00**, 7.1 minutes before capture. Causal: **yes**.

![Independent GLRT64 candidates and raw d1 fits](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T160941-a38f080a2122-d1only-raw.png)

![Selected pre-replay d1 families](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T160941-a38f080a2122-d1only-selected.png)

### Up to three tracks and their top three broad-sky candidates

The satellite candidates use a broader elevation ≥10° legacy scalar-rate screen as a secondary control.

| Track | Sat. rank | Path / RF | Duration | Obs. | Rate | Satellite | Elev. | Predicted | Error | TLE age | True-time rank |
|---|---:|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| **T1** | 1 | `stream-0/RX1` / 11.6903125 GHz | 17.05 s | 781 | -6505.7 | STARLINK-38261 | 48.3° | -4263.8 | 2241.9 | 50.17 h | 36/41 |
| **T1** | 2 | `stream-0/RX1` / 11.6903125 GHz | 17.05 s | 781 | -6505.7 | STARLINK-35399 | 75.3° | -3882.7 | 2622.9 | 17.41 h | 36/41 |
| **T1** | 3 | `stream-0/RX1` / 11.6903125 GHz | 17.05 s | 781 | -6505.7 | STARLINK-3628 | 68.8° | -3770.4 | 2735.3 | 9.95 h | 36/41 |
| **T2** | 1 | `stream-0/RX0` / 11.6903125 GHz | 16.65 s | 1167 | -6152.9 | STARLINK-38261 | 51.5° | -4857.3 | 1295.6 | 50.16 h | 25/41 |
| **T2** | 2 | `stream-0/RX0` / 11.6903125 GHz | 16.65 s | 1167 | -6152.9 | STARLINK-32511 | 76.4° | -4038.8 | 2114.1 | 20.54 h | 25/41 |
| **T2** | 3 | `stream-0/RX0` / 11.6903125 GHz | 16.65 s | 1167 | -6152.9 | STARLINK-36728 | 83.8° | -3872.9 | 2280.0 | 22.25 h | 25/41 |
| **T3** | 1 | `stream-1/RX0` / 11.6903125 GHz | 13.05 s | 193 | -6160.6 | STARLINK-38261 | 50.9° | -4756.4 | 1404.2 | 50.16 h | 25/41 |
| **T3** | 2 | `stream-1/RX0` / 11.6903125 GHz | 13.05 s | 193 | -6160.6 | STARLINK-32511 | 75.6° | -3999.1 | 2161.5 | 20.55 h | 25/41 |
| **T3** | 3 | `stream-1/RX0` / 11.6903125 GHz | 13.05 s | 193 | -6160.6 | STARLINK-36728 | 82.4° | -3841.4 | 2319.1 | 22.25 h | 25/41 |

### 30° zenith cone during the full capture

Half-angle 30° is equivalent to elevation ≥60°. Intervals are relative to capture start.

| Satellite | NORAD | Peak elevation | Visible interval(s) | TLE age |
|---|---:|---:|---|---:|
| STARLINK-31244 | 58856 | 76.9° | 0.79–60.00 s | 26.94 h |
| STARLINK-32499 | 61959 | 83.4° | 25.24–60.00 s | 9.90 h |
| STARLINK-32511 | 61727 | 78.2° | 0.00–34.30 s | 20.54 h |
| STARLINK-34092 | 63904 | 84.2° | 0.00–60.00 s | 9.92 h |
| STARLINK-34139 | 63975 | 69.1° | 0.00–30.52 s | 9.94 h |
| STARLINK-35399 | 66029 | 84.1° | 0.00–60.00 s | 17.40 h |
| STARLINK-35500 | 66093 | 75.1° | 29.11–60.00 s | 20.52 h |
| STARLINK-3628 | 51783 | 70.7° | 0.00–56.91 s | 9.95 h |
| STARLINK-36487 | 67416 | 62.6° | 40.48–60.00 s | 22.26 h |
| STARLINK-36728 | 67927 | 87.7° | 0.00–39.68 s | 22.25 h |
| STARLINK-37351 | 68742 | 77.3° | 38.64–60.00 s | 12.67 h |
| STARLINK-37498 | 69459 | 65.5° | 52.35–60.00 s | 25.55 h |
| STARLINK-37861 | 69552 | 60.2° | 58.73–60.00 s | 14.69 h |

![TLE rate field](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T160941-a38f080a2122-d1only-tle-rate.png)

![Full-capture cone and broad-control overlay](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T160941-a38f080a2122-d1only-tle-overlay.png)

![Wrong-time null controls](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T160941-a38f080a2122-d1only-null.png)

## Dwell 13: `cap-20260821T160027-658dc7f1422e`

Fresh raw degree-1 tracks: **19**. Selected pre-replay d1 families: **19**.

Capture start: **2026-08-21T16:00:29.194348+00:00**. Space-Track snapshot: **2026-08-21T15:01:24.015414+00:00**, 59.1 minutes before capture. Causal: **yes**.

![Independent GLRT64 candidates and raw d1 fits](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T160027-658dc7f1422e-d1only-raw.png)

![Selected pre-replay d1 families](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T160027-658dc7f1422e-d1only-selected.png)

### Up to three tracks and their top three broad-sky candidates

The satellite candidates use a broader elevation ≥10° legacy scalar-rate screen as a secondary control.

| Track | Sat. rank | Path / RF | Duration | Obs. | Rate | Satellite | Elev. | Predicted | Error | TLE age | True-time rank |
|---|---:|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| **T1** | 1 | `stream-1/RX1` / 10.9403125 GHz | 16.80 s | 1336 | -5385.4 | STARLINK-38162 | 43.8° | -4097.0 | 1288.4 | 14.32 h | 28/41 |
| **T1** | 2 | `stream-1/RX1` / 10.9403125 GHz | 16.80 s | 1336 | -5385.4 | STARLINK-37537 | 66.3° | -3819.3 | 1566.1 | 12.69 h | 28/41 |
| **T1** | 3 | `stream-1/RX1` / 10.9403125 GHz | 16.80 s | 1336 | -5385.4 | STARLINK-36987 | 74.2° | -3801.1 | 1584.3 | 11.51 h | 28/41 |
| **T2** | 1 | `stream-0/RX1` / 10.7096875 GHz | 8.67 s | 166 | -4922.5 | STARLINK-38162 | 43.2° | -3887.7 | 1034.7 | 14.32 h | 30/41 |
| **T2** | 2 | `stream-0/RX1` / 10.7096875 GHz | 8.67 s | 166 | -4922.5 | STARLINK-36987 | 74.6° | -3737.5 | 1185.0 | 11.51 h | 30/41 |
| **T2** | 3 | `stream-0/RX1` / 10.7096875 GHz | 8.67 s | 166 | -4922.5 | STARLINK-37537 | 64.8° | -3623.8 | 1298.6 | 12.69 h | 30/41 |
| **T3** | 1 | `stream-0/RX0` / 10.7096875 GHz | 8.52 s | 152 | -5695.3 | STARLINK-38162 | 44.5° | -4141.7 | 1553.5 | 14.32 h | 22/41 |
| **T3** | 2 | `stream-0/RX0` / 10.7096875 GHz | 8.52 s | 152 | -5695.3 | STARLINK-37537 | 67.9° | -3867.0 | 1828.3 | 12.69 h | 22/41 |
| **T3** | 3 | `stream-0/RX0` / 10.7096875 GHz | 8.52 s | 152 | -5695.3 | STARLINK-36987 | 72.9° | -3650.7 | 2044.6 | 11.51 h | 22/41 |

### 30° zenith cone during the full capture

Half-angle 30° is equivalent to elevation ≥60°. Intervals are relative to capture start.

| Satellite | NORAD | Peak elevation | Visible interval(s) | TLE age |
|---|---:|---:|---|---:|
| STARLINK-11224 | 60304 | 69.2° | 0.00–9.95 s | 18.55 h |
| STARLINK-2630 | 48381 | 71.7° | 0.00–53.14 s | 11.53 h |
| STARLINK-2763 | 48670 | 60.2° | 0.00–5.02 s | 20.56 h |
| STARLINK-31203 | 58869 | 63.9° | 54.24–60.00 s | 22.22 h |
| STARLINK-31547 | 59364 | 67.9° | 0.00–33.41 s | 22.23 h |
| STARLINK-31816 | 59742 | 60.3° | 58.03–60.00 s | 31.85 h |
| STARLINK-32517 | 61980 | 71.8° | 7.19–60.00 s | 9.90 h |
| STARLINK-32528 | 61724 | 78.4° | 0.00–24.29 s | 17.41 h |
| STARLINK-32682 | 62196 | 69.4° | 0.00–56.40 s | 28.53 h |
| STARLINK-33984 | 63830 | 62.6° | 55.63–60.00 s | 9.91 h |
| STARLINK-34105 | 63977 | 67.2° | 0.00–11.09 s | 9.94 h |
| STARLINK-34137 | 63953 | 86.2° | 0.00–43.82 s | 9.92 h |
| STARLINK-35243 | 66016 | 67.0° | 0.00–41.71 s | 20.53 h |
| STARLINK-35373 | 65792 | 72.6° | 33.90–60.00 s | 11.31 h |
| STARLINK-36987 | 68321 | 74.6° | 0.00–49.56 s | 11.51 h |
| STARLINK-37537 | 69420 | 69.2° | 9.00–60.00 s | 12.69 h |
| STARLINK-37640 | 69447 | 67.6° | 47.25–60.00 s | 25.55 h |
| STARLINK-37781 | 69341 | 83.9° | 19.02–60.00 s | 14.70 h |
| STARLINK-4167 | 53033 | 81.7° | 0.00–29.96 s | 10.01 h |
| STARLINK-4482 | 53530 | 84.7° | 4.97–60.00 s | 17.69 h |
| STARLINK-5037 | 53896 | 77.5° | 34.11–60.00 s | 10.01 h |
| STARLINK-6299 | 57358 | 80.4° | 23.15–60.00 s | 28.52 h |

![TLE rate field](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T160027-658dc7f1422e-d1only-tle-rate.png)

![Full-capture cone and broad-control overlay](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T160027-658dc7f1422e-d1only-tle-overlay.png)

![Wrong-time null controls](figures/2026_08_23_thirteen_dwell_degree1_fresh/20260821T160027-658dc7f1422e-d1only-null.png)

## Scope and limitations

No quadratic or cubic radio fit, family member, selector, observation membership, or curvature statistic is used. TLE curve curvature is orbital prediction, not a nonlinear radio estimate. Space-Track snapshots are the newest archived snapshot at or before each dwell. This is compatibility evidence, not satellite identification.
