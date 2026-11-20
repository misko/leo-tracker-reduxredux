# Native fractional GLRT winner calibration

The fixed 0.060 native margin gate changed detector agreement by at most 0.41 percentage points across six recordings. It preserved all fixes within 5 km and exceeded the 10% error tolerance for the median and P95 in both datasets and both calibration arms. The native candidate inventory omits 8.1–16.4% of the original v5 winners, which sets the limit for any selection rule that consumes these factors.

## Calibration and transfer

Calibration used the complete DS26-0036 native and original fractional-factor documents only. The original detector's eligible maximum margin candidate, with lower rank breaking ties, provided the label. A detector match required a fractional epoch difference of at most two samples modulo the frame and a CFO difference of at most 1 kHz modulo 227,272.73 Hz. The F1 denominator counts all selected winners and all eligible original winners, so a replacement by a different candidate incurs both kinds of error.

The 0.060 threshold sits near the best margin-only F1 in both alternating 512-visit partitions. Subtracting a reweighted control score, scaling by the control, and rewarding alias agreement within a probe did not improve performance consistently across those partitions. The sealed rule keeps the maximum native fractional margin and resolves ties by rank. It emits the measured CFO, original score and original epoch for each winner. The seal predates reading DS29 factors or scoring endpoints. [Calibration seal](calibration.json)

| DS26 calibration threshold | Even 512-visit blocks F1 | Odd 512-visit blocks F1 |
|---:|---:|---:|
| 0.025 | 0.85415 | 0.83819 |
| 0.060 | 0.85604 | 0.83988 |
| 0.075 | 0.85619 | 0.83827 |
| 0.100 | 0.85344 | 0.83644 |

| Case | Method | Probes | Original positives | Matched | Different winner | Original only | Native only | Both null | Matched F1 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DS26-0036 | Stock 0.025 | 13,530 | 3,395 | 2,967 | 122 | 306 | 521 | 9,614 | 0.84711 |
| DS26-0036 | Sealed 0.060 | 13,530 | 3,395 | 2,964 | 121 | 310 | 503 | 9,632 | 0.84892 |
| DS26-0122 | Stock 0.025 | 13,542 | 4,623 | 3,942 | 223 | 458 | 445 | 8,474 | 0.85389 |
| DS26-0122 | Sealed 0.060 | 13,542 | 4,623 | 3,893 | 221 | 509 | 425 | 8,494 | 0.84981 |
| DS26-0237 | Stock 0.025 | 13,532 | 3,740 | 3,201 | 165 | 374 | 561 | 9,231 | 0.83501 |
| DS26-0237 | Sealed 0.060 | 13,532 | 3,740 | 3,192 | 163 | 385 | 546 | 9,246 | 0.83549 |
| DS29-0082 | Stock 0.025 | 9,736 | 1,868 | 1,511 | 107 | 250 | 426 | 7,442 | 0.77249 |
| DS29-0082 | Sealed 0.060 | 9,736 | 1,868 | 1,497 | 105 | 266 | 418 | 7,450 | 0.77006 |
| DS29-0174 | Stock 0.025 | 13,408 | 4,018 | 3,577 | 142 | 299 | 415 | 8,975 | 0.87758 |
| DS29-0174 | Sealed 0.060 | 13,408 | 4,018 | 3,567 | 141 | 310 | 402 | 8,988 | 0.87771 |
| DS29-0247 | Stock 0.025 | 13,534 | 5,111 | 4,473 | 296 | 342 | 345 | 8,078 | 0.87491 |
| DS29-0247 | Sealed 0.060 | 13,534 | 5,111 | 4,462 | 292 | 357 | 331 | 8,092 | 0.87525 |

Searching every complete native candidate against the original winner found 3,047 of 3,395 possible matches on DS26-0036 and 1,562 of 1,868 on DS29-0082. The stock threshold alone retained 3,041 and 1,552 of these. A static ranking of complete candidates therefore has no way to recover 348 and 306 original winners. On the four additional recordings, the complete-candidate ceiling was 88.7%, 88.6%, 91.2% and 91.9% in roster order. The study labels detector agreement. A native-only winner can be a real pilot the original detector missed.

DS26-0036 native-only decisions concentrated on RX0 of channels 5 and 6, with 70 per lane after calibration. On the same recording, RX1 of channels 1 and 3 had 49 and 36 original-only positives. On DS29-0082, RX0 of channel 5 had 208 matches and 61 native-only decisions, while RX1 had 91 matches and 42 original-only decisions. Both DS29-0082 receivers were almost entirely null on channel 2, with 837 of 838 probes null in both detectors. Per-channel and receiver counts and conditional match residuals are available for all six recordings. [Detector audits](detectors.jsonl.gz)

The median absolute wrapped CFO difference among matching winners was 25.06 Hz on DS26 and 26.44 Hz on DS29 for the calibrated rule. There were 113 and 170 matches on different raw CFO alias branches. The rule passes through the native measured branch for the track stage.

## Position on the two original IQ replay cases

The fresh fits used `v5_lean`, which runs the frozen v5 no-repair science and omits rendering. Every detector input was bound to its original blind request. The runs used the same causal TLE and search settings and solved both c arms on the same prepared detector observations. Fresh controls on the original v5 factors reproduced both archived endpoints on each recording. [DS26 control](/srv/bulk/leo-dev/pipeline-eval-20261119-native-winner/DS26-0036/reference/prediction.json) · [DS29 control](/srv/bulk/leo-dev/pipeline-eval-20261119-native-winner/DS29-0082/reference/prediction.json)

| Case | Detector input | c = 0 error (km) | Fitted c error (km) | Selected observations |
|---|---|---:|---:|---:|
| DS26-0036 | Original v5 | 1.278 | 1.208 | 3,395 |
| DS26-0036 | Stock native | 0.231 | 0.186 | 3,610 |
| DS26-0036 | Sealed 0.060 | 1.508 | 1.382 | 3,588 |
| DS29-0082 | Original v5 | 0.567 | 0.517 | 1,868 |
| DS29-0082 | Stock native | 2.802 | 2.662 | 2,044 |
| DS29-0082 | Sealed 0.060 | 2.849 | 2.705 | 2,020 |

The higher threshold worsened both position arms on both recordings versus stock native. DS26 moved from better than original v5 to 14% above its fitted-c error. In that case, removing 22 detector winners changed the final association count by 64 and lowered the conditional RMS. The fitted-c arm moved closer to the surveyed position than the c = 0 arm in both sealed runs, while both its in-sample RMS and frequency objective increased slightly. The conditional metrics depend on each detector input's final associations.

| Case | Detector input | c = 0 RMS (Hz) | Fitted c RMS (Hz) | c = 0 frequency score | Fitted c frequency score | Final owned points, c = 0 / fitted c |
|---|---|---:|---:|---:|---:|---:|
| DS26-0036 | Original v5 | 74.761 | 74.682 | 25,232.15 | 25,232.29 | 2,690 / 2,690 |
| DS26-0036 | Stock native | 102.260 | 102.296 | 25,156.81 | 25,163.54 | 2,521 / 2,521 |
| DS26-0036 | Sealed 0.060 | 101.128 | 101.158 | 24,610.17 | 24,617.88 | 2,457 / 2,457 |
| DS29-0082 | Original v5 | 97.004 | 96.684 | 6,337.72 | 6,342.81 | 929 / 929 |
| DS29-0082 | Stock native | 106.677 | 106.591 | 11,815.16 | 11,818.34 | 1,310 / 1,310 |
| DS29-0082 | Sealed 0.060 | 108.803 | 108.880 | 11,928.40 | 11,931.88 | 1,370 / 1,370 |

## Additional complete recording transfers

The same sealed rule was run on four previously unreplayed recordings from the same physical site. The stock controls and sealed refits used the same ordinary native IQ-derived factor documents and frozen `v5_lean` solver. Original v5 position errors come from the frozen scorer inventory. [Stock full IQ results](/tmp/leo-complete-frontend-20261119/ordinary) · [Sealed refits](/tmp/leo-complete-frontend-20261119/winner)

All pairs are c = 0 / fitted c.

| Case | Original v5 error (km) | Stock native error (km) | Sealed 0.060 error (km) | Reused raw assembly (s) | Fresh sealed fit (s) |
|---|---:|---:|---:|---:|---:|
| DS26-0122 | 0.751 / 0.747 | 1.254 / 1.254 | 1.268 / 1.267 | 187.33 | 220.32 |
| DS26-0237 | 0.362 / 0.271 | 0.896 / 0.821 | 0.931 / 0.861 | 178.43 | 183.10 |
| DS29-0174 | 0.885 / 0.917 | 1.159 / 1.225 | 1.144 / 1.213 | 222.76 | 163.59 |
| DS29-0247 | 1.320 / 1.458 | 0.711 / 0.980 | 1.231 / 1.171 | 179.30 | 357.97 |

| Case | Stock conditional RMS (Hz) | Sealed conditional RMS (Hz) | Stock frequency score | Sealed frequency score | Owned points, stock → sealed |
|---|---:|---:|---:|---:|---:|
| DS26-0122 | unavailable | unavailable | 36,821.45 / 36,836.40 | 36,467.98 / 36,482.92 | 3,544 → 3,516 |
| DS26-0237 | 110.245 / 110.116 | 109.592 / 109.459 | 35,315.06 / 35,314.35 | 35,068.43 / 35,068.12 | 3,435 → 3,422 |
| DS29-0174 | 113.047 / 113.148 | 112.317 / 112.411 | 31,318.31 / 31,312.36 | 30,854.18 / 30,847.73 | 3,028 → 3,036 |
| DS29-0247 | 98.280 / 98.324 | unavailable | 34,763.87 / 34,761.69 | 37,442.02 / 37,433.65 | 3,867 → 4,129 |

The selected v5 outputs supplied frequency scores and ownership for every run. Conditional RMS was unavailable for both DS26-0122 variants and the sealed DS29-0247 variant. Fitted c reduced sealed position error in five of the six cases. Its within-run frequency score increased on DS26-0036, DS26-0122 and DS29-0082 and fell on the other three.

## Six-recording position gate

Each row has three recordings. Every method published three fixes within 5 km in each row. Stock native exceeded the permitted 10% deterioration in three of the four median comparisons. The sealed gate exceeded it in all four median and all four P95 comparisons. [Position predictions](positions.jsonl.gz)

| Dataset | Calibration | Original v5 median / P95 (km) | Stock native median / P95 (km) | Sealed 0.060 median / P95 (km) |
|---|---|---:|---:|---:|
| DS26 | c = 0 | 0.751 / 1.226 | 0.896 / 1.218 | 1.268 / 1.484 |
| DS26 | Fitted c | 0.747 / 1.162 | 0.821 / 1.211 | 1.267 / 1.371 |
| DS29 | c = 0 | 0.885 / 1.276 | 1.159 / 2.638 | 1.231 / 2.687 |
| DS29 | Fitted c | 0.917 / 1.404 | 1.225 / 2.518 | 1.213 / 2.556 |

## Timing boundary

The calibrated inputs reused the prior authenticated native replay of all 6,769 DS26 raw visits and 6,772 DS29 raw visits, including their 4 and 1,904 capture exclusions. That replay read 10.830 GB and 10.835 GB of IQ and took 176.11 s and 116.94 s through factor assembly. The present trial read the immutable factor documents, checked matching capture and clock authority, reduced candidates and ran fresh positioning. The Python selector took 1.44 µs and 1.09 µs per receiver probe on one host CPU. In-memory factor conversion including identity derivation took 0.11 s and 0.06 s. These timings leave the C detector's per-visit work unchanged and measure the selector on the host. [Prior full replay and inference](/srv/bulk/leo-dev/pipeline-eval-20261118/full-v5-check)

The six fresh sealed fits took 100.30–357.97 s each on one host core, with selector costs of 1.09–1.77 µs per receiver probe. Adding the separately measured raw assembly and fresh fit times gives 217–537 s against roughly 300 s of recorded delivery per case. Only the DS29-0082 sum was under 300 s. The compressed predictions record fresh fit time, reused raw assembly and original capture span separately. [DS26-0036 stock and control](/srv/bulk/leo-dev/pipeline-eval-20261119-native-winner/DS26-0036/scores.json) · [DS29-0082 stock and control](/srv/bulk/leo-dev/pipeline-eval-20261119-native-winner/DS29-0082/scores.json)
