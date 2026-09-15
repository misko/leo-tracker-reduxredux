# Candidate RMS comparisons: scan-hop-9e4724f933719f16

Recorded **2026-09-14T23:00:12.633367Z**, RX0, 10 MS/s.

[Recording assessment and plots](scan-hop-9e4724f933719f16.md).

Each track has its own training-selected leader; there is no single satellite assignment for the whole recording. Lower RMS is better. The same observations and chronological split are used for all candidates within a track.

Gain = alternative RMS − training-leader RMS. Positive gain favors the leader; negative heldout gain means the alternative predicts better. Percent gain uses the alternative RMS as denominator; it is not identification confidence. Tau and carrier offset were selected on training data and remain frozen on heldout.

The archived screen retained the top five training candidates and top five heldout candidates, whose union is listed below. Candidate counts describe the full scored population; names/scores outside these retained lists were not archived. A blank rank means outside that top-five list. Catalogue exclusions and control results are in the linked recording assessment and evidence.

## CH3 lower, 0.27–20.44 s

Track `sha256:53cf70669e5702d9287e947aa1d48441ba60932756a141931367cace5a0aa423`; 21 observations; 491 nominal-time satellites scored. Training leader: **STARLINK-32197 (NORAD 60416)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-35805 (NORAD 66359): leader heldout RMS **60.74 Hz** versus **2677.91 Hz**; gain **+2617.16 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32197 | 60416 | 1 | 1 | 11.38 | 60.74 | +0.00 | +0.00 | +0.00 | +1 |
| STARLINK-34238 | 65415 | 2 | 4 | 1223.44 | 5659.05 | +1212.06 | +5598.31 | +98.93 | -5 |
| STARLINK-34018 | 63836 | 3 | 3 | 1739.10 | 3392.12 | +1727.72 | +3331.38 | +98.21 | +5 |
| STARLINK-35805 | 66359 | 4 | 2 | 1844.26 | 2677.91 | +1832.87 | +2617.16 | +97.73 | +5 |
| STARLINK-32804 | 62846 | 5 | 5 | 2026.66 | 5831.87 | +2015.27 | +5771.12 | +98.96 | -3 |

## CH1 lower, 28.25–52.81 s

Track `sha256:91f4e70c7f050ad92dfc99e6cc83c0a7034dd2f103e1dfcb3922d58f89b6f1af`; 27 observations; 494 nominal-time satellites scored. Training leader: **STARLINK-30245 (NORAD 57612)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32365 (NORAD 61625): leader heldout RMS **117.27 Hz** versus **1615.74 Hz**; gain **+1498.47 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30245 | 57612 | 1 | 1 | 41.94 | 117.27 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-32365 | 61625 | 2 | 2 | 360.13 | 1615.74 | +318.19 | +1498.47 | +92.74 | +5 |
| STARLINK-34018 | 63836 | 3 | — | 630.49 | 4832.13 | +588.54 | +4714.86 | +97.57 | +5 |
| STARLINK-5003 | 53905 | 4 | 4 | 702.79 | 4057.77 | +660.85 | +3940.50 | +97.11 | +5 |
| STARLINK-36514 | 67641 | 5 | 5 | 839.71 | 4331.99 | +797.76 | +4214.72 | +97.29 | +5 |
| STARLINK-35805 | 66359 | — | 3 | 2384.63 | 2009.92 | +2342.69 | +1892.66 | +94.17 | +5 |

## CH2 lower, 29.39–74.23 s

Track `sha256:9482a4894e9402947dd9dd2ef9a85fbe73a5ea23ca35e3c858e299fc8e676e3a`; 53 observations; 503 nominal-time satellites scored. Training leader: **STARLINK-30245 (NORAD 57612)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32365 (NORAD 61625): leader heldout RMS **203.80 Hz** versus **4276.68 Hz**; gain **+4072.88 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30245 | 57612 | 1 | 1 | 79.42 | 203.80 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-32365 | 61625 | 2 | 2 | 982.34 | 4276.68 | +902.92 | +4072.88 | +95.23 | +5 |
| STARLINK-34018 | 63836 | 3 | — | 1455.41 | 13863.25 | +1375.99 | +13659.45 | +98.53 | -5 |
| STARLINK-35805 | 66359 | 4 | 4 | 1719.30 | 12342.72 | +1639.89 | +12138.92 | +98.35 | +5 |
| STARLINK-5003 | 53905 | 5 | 5 | 2528.26 | 12685.26 | +2448.85 | +12481.46 | +98.39 | +5 |
| STARLINK-37435 | 69265 | — | 3 | 5279.05 | 7764.57 | +5199.63 | +7560.77 | +97.38 | +5 |

## CH2 upper, 29.89–73.47 s

Track `sha256:adddcfbfaec409dffd7f063b1030d5030e5c4e3216bff216a97f76b61f2c6010`; 52 observations; 503 nominal-time satellites scored. Training leader: **STARLINK-30245 (NORAD 57612)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32365 (NORAD 61625): leader heldout RMS **191.61 Hz** versus **4190.04 Hz**; gain **+3998.43 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30245 | 57612 | 1 | 1 | 104.36 | 191.61 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-32365 | 61625 | 2 | 2 | 1016.72 | 4190.04 | +912.36 | +3998.43 | +95.43 | +5 |
| STARLINK-34018 | 63836 | 3 | — | 1509.88 | 13510.21 | +1405.52 | +13318.60 | +98.58 | -5 |
| STARLINK-35805 | 66359 | 4 | 4 | 1639.13 | 11990.82 | +1534.77 | +11799.21 | +98.40 | +5 |
| STARLINK-5003 | 53905 | 5 | 5 | 2598.33 | 12416.51 | +2493.97 | +12224.90 | +98.46 | +5 |
| STARLINK-37435 | 69265 | — | 3 | 5239.28 | 7703.60 | +5134.92 | +7511.99 | +97.51 | +5 |

## CH1 upper, 50.92–73.35 s

Track `sha256:4758da79043a5d9291397ad5565de3abc8ff1c34256012ae34e53e037654ffc0`; 22 observations; 486 nominal-time satellites scored. Training leader: **STARLINK-30245 (NORAD 57612)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37435 (NORAD 69265): leader heldout RMS **105.26 Hz** versus **891.92 Hz**; gain **+786.66 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30245 | 57612 | 1 | 1 | 44.72 | 105.26 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-32365 | 61625 | 2 | 3 | 828.72 | 2174.75 | +784.00 | +2069.49 | +95.16 | +2 |
| STARLINK-37435 | 69265 | 3 | 2 | 1018.31 | 891.92 | +973.58 | +786.66 | +88.20 | +5 |
| STARLINK-35805 | 66359 | 4 | 5 | 1154.34 | 5791.49 | +1109.62 | +5686.23 | +98.18 | -5 |
| STARLINK-5003 | 53905 | 5 | — | 2154.41 | 6259.84 | +2109.69 | +6154.58 | +98.32 | -5 |
| STARLINK-30820 | 58190 | — | 4 | 2304.35 | 4482.41 | +2259.63 | +4377.15 | +97.65 | +5 |

## CH4 lower, 62.65–90.22 s

Track `sha256:1e98705a378fe07cd973748cf1b391ca0ae22e9ea2a231162c61c4ff33803ae8`; 29 observations; 490 nominal-time satellites scored. Training leader: **STARLINK-37435 (NORAD 69265)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30245 (NORAD 57612): leader heldout RMS **21.90 Hz** versus **6674.37 Hz**; gain **+6652.47 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37435 | 69265 | 1 | 1 | 31.89 | 21.90 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-30245 | 57612 | 2 | 2 | 798.91 | 6674.37 | +767.02 | +6652.47 | +99.67 | -5 |
| STARLINK-32365 | 61625 | 3 | 4 | 1350.58 | 7739.39 | +1318.69 | +7717.49 | +99.72 | -5 |
| STARLINK-30820 | 58190 | 4 | 3 | 1749.55 | 7143.36 | +1717.66 | +7121.45 | +99.69 | +5 |
| STARLINK-2315 | 47789 | 5 | 5 | 3177.32 | 11496.33 | +3145.43 | +11474.42 | +99.81 | +5 |

## CH3 lower, 86.06–116.04 s

Track `sha256:0b0c04197b1498a05613427d0976a8cf4241c9572da3cf2da7f5cd60b716e677`; 32 observations; 493 nominal-time satellites scored. Training leader: **STARLINK-33620 (NORAD 63069)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-35748 (NORAD 66206): leader heldout RMS **128.68 Hz** versus **3758.39 Hz**; gain **+3629.70 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33620 | 63069 | 1 | 1 | 59.51 | 128.68 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-35748 | 66206 | 2 | 2 | 583.18 | 3758.39 | +523.67 | +3629.70 | +96.58 | +5 |
| STARLINK-30820 | 58190 | 3 | 4 | 768.46 | 6930.93 | +708.95 | +6802.24 | +98.14 | -5 |
| STARLINK-3115 | 49447 | 4 | 3 | 820.82 | 4515.10 | +761.30 | +4386.41 | +97.15 | +5 |
| STARLINK-37435 | 69265 | 5 | 5 | 1002.82 | 7067.78 | +943.31 | +6939.09 | +98.18 | +5 |

## CH3 upper, 86.83–115.92 s

Track `sha256:13b09e1807e56894276c8f5abf9ad971e57af88fe10db711d516b2d3ff0c15b1`; 31 observations; 493 nominal-time satellites scored. Training leader: **STARLINK-33620 (NORAD 63069)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-35748 (NORAD 66206): leader heldout RMS **135.93 Hz** versus **3706.99 Hz**; gain **+3571.06 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33620 | 63069 | 1 | 1 | 61.59 | 135.93 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-35748 | 66206 | 2 | 2 | 583.03 | 3706.99 | +521.44 | +3571.06 | +96.33 | +5 |
| STARLINK-30820 | 58190 | 3 | 4 | 770.13 | 6867.34 | +708.54 | +6731.41 | +98.02 | -5 |
| STARLINK-3115 | 49447 | 4 | 3 | 813.73 | 4446.26 | +752.13 | +4310.33 | +96.94 | +5 |
| STARLINK-37435 | 69265 | 5 | 5 | 884.30 | 7047.63 | +822.71 | +6911.70 | +98.07 | +5 |

## CH1 lower, 161.53–196.54 s

Track `sha256:e08b535c17233b96cc681c2a8bd5df1780626fc7f7145c669028f270d8743277`; 41 observations; 504 nominal-time satellites scored. Training leader: **STARLINK-30294 (NORAD 57651)**; heldout rank 2 in the full scored population.

Against the best other heldout candidate, STARLINK-35035 (NORAD 65407): leader heldout RMS **1563.74 Hz** versus **1467.55 Hz**; gain **-96.19 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30294 | 57651 | 1 | 2 | 536.69 | 1563.74 | +0.00 | +0.00 | +0.00 | -5 |
| STARLINK-35035 | 65407 | 2 | 1 | 1472.13 | 1467.55 | +935.44 | -96.19 | -6.55 | +5 |
| STARLINK-11683 | 64239 | 3 | 3 | 2215.21 | 2057.44 | +1678.52 | +493.70 | +24.00 | +5 |
| STARLINK-31802 | 59636 | 4 | — | 3284.26 | 9112.79 | +2747.57 | +7549.06 | +82.84 | -5 |
| STARLINK-30830 | 58194 | 5 | 4 | 3459.94 | 5652.88 | +2923.25 | +4089.15 | +72.34 | +5 |
| STARLINK-32960 | 63197 | — | 5 | 4611.43 | 6189.02 | +4074.74 | +4625.29 | +74.73 | +5 |

## CH1 upper, 165.31–196.16 s

Track `sha256:fce96c8ecd6f1a19cb3e3d5a10b7af3c50e871ba299a04271758872b4f09245e`; 38 observations; 503 nominal-time satellites scored. Training leader: **STARLINK-30294 (NORAD 57651)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11683 (NORAD 64239): leader heldout RMS **87.03 Hz** versus **1253.83 Hz**; gain **+1166.81 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30294 | 57651 | 1 | 1 | 77.84 | 87.03 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-35035 | 65407 | 2 | 3 | 451.19 | 2067.75 | +373.35 | +1980.72 | +95.79 | +5 |
| STARLINK-11683 | 64239 | 3 | 2 | 1916.99 | 1253.83 | +1839.15 | +1166.81 | +93.06 | +5 |
| STARLINK-30830 | 58194 | 4 | 5 | 3080.72 | 4398.00 | +3002.88 | +4310.98 | +98.02 | +5 |
| STARLINK-31802 | 59636 | 5 | — | 3282.34 | 8258.08 | +3204.50 | +8171.06 | +98.95 | -5 |
| STARLINK-32960 | 63197 | — | 4 | 3902.06 | 4379.86 | +3824.22 | +4292.83 | +98.01 | +5 |

## CH1 lower, 276.76–298.81 s

Track `sha256:35350264b5ddf3478cd4948403fdcea171cd26097fce7473ab9a825fc5f4ec44`; 21 observations; 494 nominal-time satellites scored. Training leader: **STARLINK-31795 (NORAD 59645)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-34220 (NORAD 64930): leader heldout RMS **142.84 Hz** versus **300.72 Hz**; gain **+157.89 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31795 | 59645 | 1 | 1 | 26.72 | 142.84 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-36309 | 68325 | 2 | 3 | 196.36 | 1868.16 | +169.64 | +1725.33 | +92.35 | +2 |
| STARLINK-37665 | 69238 | 3 | 4 | 279.35 | 2274.55 | +252.63 | +2131.71 | +93.72 | -5 |
| STARLINK-34220 | 64930 | 4 | 2 | 386.70 | 300.72 | +359.98 | +157.89 | +52.50 | +5 |
| STARLINK-11486 | 62467 | 5 | — | 613.66 | 5995.02 | +586.95 | +5852.18 | +97.62 | -1 |
| STARLINK-34055 | 63819 | — | 5 | 1005.88 | 3109.22 | +979.16 | +2966.38 | +95.41 | +5 |
