# Candidate RMS comparisons: scan-hop-2e5291e998d9539d

[Ranked RMS plots for every track](scan-hop-2e5291e998d9539d-rms.md).

Recorded **2026-09-14T23:10:12.694332Z**, RX0, 10 MS/s.

[Recording assessment and plots](scan-hop-2e5291e998d9539d.md).

Each track has its own training-selected leader; there is no single satellite assignment for the whole recording. Lower RMS is better. The same observations and chronological split are used for all candidates within a track.

Gain = alternative RMS − training-leader RMS. Positive gain favors the leader; negative heldout gain means the alternative predicts better. Percent gain uses the alternative RMS as denominator; it is not identification confidence. Tau and carrier offset were selected on training data and remain frozen on heldout.

The archived screen retained the top five training candidates and top five heldout candidates, whose union is listed below. Candidate counts describe the full scored population; names/scores outside these retained lists were not archived. A blank rank means outside that top-five list. Catalogue exclusions and control results are in the linked recording assessment and evidence.

## CH1 lower, 21.67–43.98 s

Track `sha256:bdb2e28a9e0d105db9d62cbbb97a76611d6cd7bb33e9c44d3072d4d436d2fb99`; 23 observations; 502 nominal-time satellites scored. Training leader: **STARLINK-32775 (NORAD 62742)**; heldout rank 2 in the full scored population.

Against the best other heldout candidate, STARLINK-30328 (NORAD 57638): leader heldout RMS **205.67 Hz** versus **39.22 Hz**; gain **-166.45 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32775 | 62742 | 1 | 2 | 28.47 | 205.67 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-30328 | 57638 | 2 | 1 | 39.86 | 39.22 | +11.39 | -166.45 | -424.45 | +0 |
| STARLINK-37502 | 69263 | 3 | 3 | 508.19 | 1362.45 | +479.72 | +1156.78 | +84.90 | +5 |
| STARLINK-5040 | 53914 | 4 | — | 583.47 | 4020.58 | +555.00 | +3814.91 | +94.88 | -5 |
| STARLINK-32186 | 60412 | 5 | 5 | 631.75 | 3491.48 | +603.28 | +3285.81 | +94.11 | -5 |
| STARLINK-35895 | 66354 | — | 4 | 1571.35 | 3166.31 | +1542.88 | +2960.64 | +93.50 | +5 |

## CH4 upper, 83.68–121.33 s

Track `sha256:1b6319ada3fd1f665724a28030c4bd7c2cfea73b12f1ed1fa46da015d23f8445`; 43 observations; 522 nominal-time satellites scored. Training leader: **STARLINK-3049 (NORAD 49436)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-35204 (NORAD 65694): leader heldout RMS **135.91 Hz** versus **256.12 Hz**; gain **+120.21 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-3049 | 49436 | 1 | 1 | 109.44 | 135.91 | +0.00 | +0.00 | +0.00 | -5 |
| STARLINK-35204 | 65694 | 2 | 2 | 116.88 | 256.12 | +7.44 | +120.21 | +46.93 | -1 |
| STARLINK-37214 | 68345 | 3 | — | 1188.86 | 14226.83 | +1079.43 | +14090.92 | +99.04 | -5 |
| STARLINK-34659 | 64913 | 4 | 3 | 1560.31 | 3399.46 | +1450.87 | +3263.55 | +96.00 | +5 |
| STARLINK-11704 | 64245 | 5 | 5 | 2062.64 | 13682.85 | +1953.20 | +13546.94 | +99.01 | -5 |
| STARLINK-5011 | 53925 | — | 4 | 2864.17 | 12440.94 | +2754.74 | +12305.03 | +98.91 | +5 |

## CH4 lower, 84.94–121.46 s

Track `sha256:6d0d48c9b12c22f94205340482f8d186135d9d27666ed899e04532b774225593`; 41 observations; 521 nominal-time satellites scored. Training leader: **STARLINK-3049 (NORAD 49436)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-35204 (NORAD 65694): leader heldout RMS **105.80 Hz** versus **214.27 Hz**; gain **+108.47 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-3049 | 49436 | 1 | 1 | 75.20 | 105.80 | +0.00 | +0.00 | +0.00 | -5 |
| STARLINK-35204 | 65694 | 2 | 2 | 97.53 | 214.27 | +22.33 | +108.47 | +50.62 | -1 |
| STARLINK-37214 | 68345 | 3 | — | 1495.17 | 14625.87 | +1419.98 | +14520.07 | +99.28 | -5 |
| STARLINK-34659 | 64913 | 4 | 3 | 1495.92 | 3142.22 | +1420.73 | +3036.42 | +96.63 | +5 |
| STARLINK-11704 | 64245 | 5 | — | 2313.58 | 13741.03 | +2238.38 | +13635.23 | +99.23 | -5 |
| STARLINK-5011 | 53925 | — | 4 | 2975.10 | 12212.40 | +2899.91 | +12106.60 | +99.13 | +5 |
| STARLINK-35704 | 66221 | — | 5 | 3284.50 | 13730.91 | +3209.31 | +13625.11 | +99.23 | +5 |

## CH1 lower, 134.56–169.18 s

Track `sha256:47b844115d73f3d5fa79f7b3f64c5fb61910f9395e0d051ccd63e20fef80af15`; 44 observations; 518 nominal-time satellites scored. Training leader: **STARLINK-30249 (NORAD 57618)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-2526 (NORAD 48378): leader heldout RMS **117.86 Hz** versus **711.56 Hz**; gain **+593.71 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30249 | 57618 | 1 | 1 | 24.86 | 117.86 | +0.00 | +0.00 | +0.00 | +1 |
| STARLINK-2526 | 48378 | 2 | 2 | 91.33 | 711.56 | +66.47 | +593.71 | +83.44 | -1 |
| STARLINK-32364 | 61622 | 3 | 3 | 97.15 | 992.23 | +72.29 | +874.37 | +88.12 | +0 |
| STARLINK-34997 | 65418 | 4 | 5 | 581.38 | 5341.65 | +556.52 | +5223.79 | +97.79 | +1 |
| STARLINK-11377 | 62013 | 5 | — | 788.74 | 9031.45 | +763.88 | +8913.60 | +98.70 | -5 |
| STARLINK-35075 | 65702 | — | 4 | 3568.88 | 5144.70 | +3544.01 | +5026.84 | +97.71 | +5 |

## CH1 upper, 134.68–170.94 s

Track `sha256:1c410c799c1dee565e468dbb27fbdb0191fc40f473aea595732ee24ec3e9cf1a`; 44 observations; 519 nominal-time satellites scored. Training leader: **STARLINK-30249 (NORAD 57618)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-2526 (NORAD 48378): leader heldout RMS **97.85 Hz** versus **874.45 Hz**; gain **+776.60 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30249 | 57618 | 1 | 1 | 76.97 | 97.85 | +0.00 | +0.00 | +0.00 | +1 |
| STARLINK-2526 | 48378 | 2 | 2 | 113.86 | 874.45 | +36.89 | +776.60 | +88.81 | +0 |
| STARLINK-32364 | 61622 | 3 | 3 | 121.24 | 1132.60 | +44.27 | +1034.74 | +91.36 | +0 |
| STARLINK-34997 | 65418 | 4 | 5 | 573.10 | 5307.06 | +496.13 | +5209.20 | +98.16 | +0 |
| STARLINK-11377 | 62013 | 5 | — | 804.34 | 9959.99 | +727.37 | +9862.14 | +99.02 | -5 |
| STARLINK-35075 | 65702 | — | 4 | 3575.51 | 4923.79 | +3498.54 | +4825.93 | +98.01 | +5 |

## CH4 lower, 241.52–269.36 s

Track `sha256:2758c94cefb875075d9fd1328334996d4a2dab909fa0665cc41a2973a0764102`; 38 observations; 515 nominal-time satellites scored. Training leader: **STARLINK-35828 (NORAD 66351)**; heldout rank 3 in the full scored population.

Against the best other heldout candidate, STARLINK-30052 (NORAD 57611): leader heldout RMS **580.12 Hz** versus **118.85 Hz**; gain **-461.26 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35828 | 66351 | 1 | 3 | 55.70 | 580.12 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-30052 | 57611 | 2 | 1 | 79.15 | 118.85 | +23.45 | -461.26 | -388.10 | +1 |
| STARLINK-36254 | 68338 | 3 | 2 | 153.03 | 548.24 | +97.33 | -31.87 | -5.81 | -5 |
| STARLINK-30591 | 58088 | 4 | — | 444.62 | 5197.91 | +388.92 | +4617.79 | +88.84 | -5 |
| STARLINK-37503 | 69262 | 5 | — | 578.75 | 6321.84 | +523.04 | +5741.73 | +90.82 | -2 |
| STARLINK-30280 | 57643 | — | 4 | 712.15 | 1502.62 | +656.44 | +922.51 | +61.39 | -5 |
| STARLINK-32850 | 62950 | — | 5 | 964.60 | 4638.85 | +908.90 | +4058.73 | +87.49 | +5 |

## CH4 upper, 242.15–271.51 s

Track `sha256:0a3375127f4f678971f89e01e28aea3a88dc31ea9c0250cea1e48ebbb68f7aa8`; 38 observations; 516 nominal-time satellites scored. Training leader: **STARLINK-35828 (NORAD 66351)**; heldout rank 3 in the full scored population.

Against the best other heldout candidate, STARLINK-30052 (NORAD 57611): leader heldout RMS **614.92 Hz** versus **144.47 Hz**; gain **-470.44 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35828 | 66351 | 1 | 3 | 62.71 | 614.92 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-30052 | 57611 | 2 | 1 | 80.98 | 144.47 | +18.27 | -470.44 | -325.63 | +1 |
| STARLINK-36254 | 68338 | 3 | 2 | 158.49 | 593.54 | +95.78 | -21.37 | -3.60 | -5 |
| STARLINK-30591 | 58088 | 4 | — | 463.17 | 5830.42 | +400.46 | +5215.51 | +89.45 | -5 |
| STARLINK-37503 | 69262 | 5 | — | 566.28 | 6639.30 | +503.58 | +6024.38 | +90.74 | -3 |
| STARLINK-30280 | 57643 | — | 4 | 639.21 | 4005.26 | +576.50 | +3390.35 | +84.65 | +5 |
| STARLINK-32850 | 62950 | — | 5 | 836.04 | 5429.96 | +773.33 | +4815.05 | +88.68 | +5 |

## CH2 lower, 270.50–299.73 s

Track `sha256:dce55fd3029ca4792021b0bac7a5244f85e515ad6ecdb5271841b162dbca943e`; 32 observations; 512 nominal-time satellites scored. Training leader: **STARLINK-35205 (NORAD 65679)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32930 (NORAD 63203): leader heldout RMS **134.00 Hz** versus **3766.91 Hz**; gain **+3632.91 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35205 | 65679 | 1 | 1 | 76.87 | 134.00 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-30052 | 57611 | 2 | 4 | 571.77 | 5311.63 | +494.90 | +5177.64 | +97.48 | -5 |
| STARLINK-35828 | 66351 | 3 | — | 598.78 | 6735.98 | +521.92 | +6601.99 | +98.01 | -5 |
| STARLINK-36254 | 68338 | 4 | 5 | 674.70 | 6628.32 | +597.84 | +6494.33 | +97.98 | -5 |
| STARLINK-11434 | 62420 | 5 | — | 880.30 | 8984.42 | +803.44 | +8850.42 | +98.51 | -4 |
| STARLINK-32930 | 63203 | — | 2 | 1125.57 | 3766.91 | +1048.70 | +3632.91 | +96.44 | +5 |
| STARLINK-5096 | 54006 | — | 3 | 1491.86 | 3783.43 | +1414.99 | +3649.44 | +96.46 | +5 |

## CH4 lower, 274.41–299.35 s

Track `sha256:819110e5ac15664330aef942bae8d310df9c029fd8da42fd887013c5ea390cb4`; 29 observations; 512 nominal-time satellites scored. Training leader: **STARLINK-35205 (NORAD 65679)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-5096 (NORAD 54006): leader heldout RMS **92.80 Hz** versus **2918.77 Hz**; gain **+2825.98 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35205 | 65679 | 1 | 1 | 69.61 | 92.80 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-30052 | 57611 | 2 | 4 | 658.75 | 5338.03 | +589.14 | +5245.23 | +98.26 | -5 |
| STARLINK-36254 | 68338 | 3 | — | 864.40 | 6618.24 | +794.79 | +6525.44 | +98.60 | -5 |
| STARLINK-35828 | 66351 | 4 | — | 1002.76 | 6550.09 | +933.15 | +6457.29 | +98.58 | -5 |
| STARLINK-11434 | 62420 | 5 | — | 1087.73 | 8295.39 | +1018.12 | +8202.59 | +98.88 | -5 |
| STARLINK-5096 | 54006 | — | 2 | 1325.73 | 2918.77 | +1256.12 | +2825.98 | +96.82 | +5 |
| STARLINK-32930 | 63203 | — | 3 | 1096.13 | 3115.45 | +1026.52 | +3022.65 | +97.02 | +5 |
| STARLINK-32529 | 62139 | — | 5 | 2159.47 | 6385.05 | +2089.86 | +6292.26 | +98.55 | +5 |

## CH4 upper, 276.93–299.60 s

Track `sha256:20a862d665118c43b36428522e1c0a7e33de0d45ad8d493ba3947a3dd3b582eb`; 23 observations; 511 nominal-time satellites scored. Training leader: **STARLINK-35205 (NORAD 65679)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-5096 (NORAD 54006): leader heldout RMS **56.26 Hz** versus **2196.31 Hz**; gain **+2140.05 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35205 | 65679 | 1 | 1 | 56.43 | 56.26 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-32930 | 63203 | 2 | 3 | 1035.46 | 2600.36 | +979.03 | +2544.09 | +97.84 | +5 |
| STARLINK-30052 | 57611 | 3 | 5 | 1090.70 | 5497.06 | +1034.27 | +5440.79 | +98.98 | -5 |
| STARLINK-5096 | 54006 | 4 | 2 | 1141.40 | 2196.31 | +1084.97 | +2140.05 | +97.44 | +5 |
| STARLINK-36254 | 68338 | 5 | — | 1391.64 | 6761.40 | +1335.21 | +6705.13 | +99.17 | -5 |
| STARLINK-32529 | 62139 | — | 4 | 2079.45 | 5401.75 | +2023.02 | +5345.49 | +98.96 | +5 |
