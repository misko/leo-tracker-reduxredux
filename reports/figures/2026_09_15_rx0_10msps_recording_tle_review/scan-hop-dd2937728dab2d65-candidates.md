# Candidate RMS comparisons: scan-hop-dd2937728dab2d65

Recorded **2026-09-14T21:20:12.440309Z**, RX0, 10 MS/s.

[Recording assessment and plots](scan-hop-dd2937728dab2d65.md).

Each track has its own training-selected leader; there is no single satellite assignment for the whole recording. Lower RMS is better. The same observations and chronological split are used for all candidates within a track.

Gain = alternative RMS − training-leader RMS. Positive gain favors the leader; negative heldout gain means the alternative predicts better. Percent gain uses the alternative RMS as denominator; it is not identification confidence. Tau and carrier offset were selected on training data and remain frozen on heldout.

The archived screen retained the top five training candidates and top five heldout candidates, whose union is listed below. Candidate counts describe the full scored population; names/scores outside these retained lists were not archived. A blank rank means outside that top-five list. Catalogue exclusions and control results are in the linked recording assessment and evidence.

## CH3 lower, 73.19–118.66 s

Track `sha256:9882ab17a10de51dcd9731dc4f9710b0e95cf486d557f917762f8fa63892faae`; 56 observations; 509 nominal-time satellites scored. Training leader: **STARLINK-33923 (NORAD 63786)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-5944 (NORAD 56001): leader heldout RMS **137.47 Hz** versus **8672.06 Hz**; gain **+8534.60 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33923 | 63786 | 1 | 1 | 89.54 | 137.47 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-5944 | 56001 | 2 | 2 | 1109.15 | 8672.06 | +1019.61 | +8534.60 | +98.41 | -5 |
| STARLINK-31320 | 58886 | 3 | 3 | 1548.51 | 11118.80 | +1458.97 | +10981.33 | +98.76 | +1 |
| STARLINK-34911 | 65325 | 4 | 5 | 1922.13 | 14773.07 | +1832.59 | +14635.60 | +99.07 | +5 |
| STARLINK-36951 | 67990 | 5 | — | 2852.79 | 17126.14 | +2763.25 | +16988.67 | +99.20 | -5 |
| STARLINK-31068 | 58623 | — | 4 | 3979.08 | 11549.45 | +3889.54 | +11411.98 | +98.81 | +5 |

## CH3 upper, 76.08–111.23 s

Track `sha256:46de24bbc5b6768b73cf95112378a4864bd87985847b9343c9c66b2f498a2391`; 43 observations; 494 nominal-time satellites scored. Training leader: **STARLINK-33923 (NORAD 63786)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-5944 (NORAD 56001): leader heldout RMS **112.15 Hz** versus **6045.46 Hz**; gain **+5933.31 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33923 | 63786 | 1 | 1 | 64.36 | 112.15 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-5944 | 56001 | 2 | 2 | 743.65 | 6045.46 | +679.28 | +5933.31 | +98.14 | -5 |
| STARLINK-31320 | 58886 | 3 | 3 | 959.48 | 7946.36 | +895.11 | +7834.21 | +98.59 | +2 |
| STARLINK-34911 | 65325 | 4 | 5 | 1176.73 | 9888.83 | +1112.37 | +9776.68 | +98.87 | +5 |
| STARLINK-36951 | 67990 | 5 | — | 2064.06 | 12460.33 | +1999.70 | +12348.17 | +99.10 | -5 |
| STARLINK-31068 | 58623 | — | 4 | 3069.78 | 9452.42 | +3005.42 | +9340.27 | +98.81 | +5 |

## CH1 lower, 106.31–135.80 s

Track `sha256:53df073ce55bfae845bbd1b1b963013498c2e6d8321fd506d307c4fccbd7bf2c`; 36 observations; 488 nominal-time satellites scored. Training leader: **STARLINK-32891 (NORAD 62927)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-31415 (NORAD 59419): leader heldout RMS **900.06 Hz** versus **2339.50 Hz**; gain **+1439.44 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32891 | 62927 | 1 | 1 | 261.88 | 900.06 | +0.00 | +0.00 | +0.00 | +3 |
| STARLINK-31415 | 59419 | 2 | 2 | 340.91 | 2339.50 | +79.02 | +1439.44 | +61.53 | -1 |
| STARLINK-33923 | 63786 | 3 | 5 | 488.91 | 6559.78 | +227.03 | +5659.72 | +86.28 | +2 |
| STARLINK-31068 | 58623 | 4 | 4 | 962.07 | 6340.58 | +700.18 | +5440.52 | +85.80 | -5 |
| STARLINK-33585 | 62782 | 5 | 3 | 1076.24 | 3379.07 | +814.36 | +2479.02 | +73.36 | +5 |

## CH3 upper, 116.02–148.77 s

Track `sha256:51bb4327d96a93fc8c4112002fd1b9417d98223f8491f2a16bafe4eb0d1037cd`; 38 observations; 488 nominal-time satellites scored. Training leader: **STARLINK-31415 (NORAD 59419)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32891 (NORAD 62927): leader heldout RMS **98.49 Hz** versus **3883.01 Hz**; gain **+3784.53 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31415 | 59419 | 1 | 1 | 119.33 | 98.49 | +0.00 | +0.00 | +0.00 | +1 |
| STARLINK-32891 | 62927 | 2 | 2 | 828.48 | 3883.01 | +709.15 | +3784.53 | +97.46 | +5 |
| STARLINK-33585 | 62782 | 3 | 3 | 2361.72 | 7879.26 | +2242.40 | +7780.77 | +98.75 | +5 |
| STARLINK-33923 | 63786 | 4 | — | 2977.32 | 15291.66 | +2857.99 | +15193.17 | +99.36 | -5 |
| STARLINK-31068 | 58623 | 5 | — | 3864.19 | 15587.37 | +3744.86 | +15488.88 | +99.37 | -5 |
| STARLINK-32092 | 59700 | — | 4 | 5390.11 | 11190.95 | +5270.78 | +11092.47 | +99.12 | +5 |
| STARLINK-35657 | 66399 | — | 5 | 3945.55 | 11564.76 | +3826.22 | +11466.27 | +99.15 | +5 |

## CH1 lower, 179.62–210.98 s

Track `sha256:56c73724082b5f08c02457dee81f60221221fc1b94c3ef879924b1f78217f000`; 40 observations; 485 nominal-time satellites scored. Training leader: **STARLINK-37070 (NORAD 68280)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-36630 (NORAD 67703): leader heldout RMS **101.22 Hz** versus **4208.08 Hz**; gain **+4106.85 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37070 | 68280 | 1 | 1 | 35.04 | 101.22 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-5432 | 54848 | 2 | 4 | 363.49 | 4828.78 | +328.46 | +4727.56 | +97.90 | -5 |
| STARLINK-31253 | 58830 | 3 | — | 746.47 | 6860.80 | +711.43 | +6759.58 | +98.52 | -3 |
| STARLINK-36630 | 67703 | 4 | 2 | 983.87 | 4208.08 | +948.83 | +4106.85 | +97.59 | -5 |
| STARLINK-11352 | 62880 | 5 | — | 1582.10 | 8847.95 | +1547.07 | +8746.72 | +98.86 | +5 |
| STARLINK-11395 | 61951 | — | 3 | 3556.84 | 4566.13 | +3521.80 | +4464.91 | +97.78 | +5 |
| STARLINK-34918 | 65331 | — | 5 | 1980.47 | 5041.64 | +1945.44 | +4940.42 | +97.99 | +5 |

## CH1 upper, 182.39–210.73 s

Track `sha256:306b8190ecadd45908b6459ca65de44c98b2148a897f288b67aa23407f223bbc`; 34 observations; 484 nominal-time satellites scored. Training leader: **STARLINK-37070 (NORAD 68280)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11395 (NORAD 61951): leader heldout RMS **97.72 Hz** versus **2407.89 Hz**; gain **+2310.16 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37070 | 68280 | 1 | 1 | 36.95 | 97.72 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-5432 | 54848 | 2 | 5 | 606.09 | 4759.36 | +569.14 | +4661.63 | +97.95 | -5 |
| STARLINK-36630 | 67703 | 3 | 3 | 975.89 | 3635.56 | +938.94 | +3537.84 | +97.31 | -5 |
| STARLINK-31253 | 58830 | 4 | — | 1041.01 | 6111.50 | +1004.06 | +6013.78 | +98.40 | -5 |
| STARLINK-34918 | 65331 | 5 | 4 | 1682.59 | 3758.63 | +1645.64 | +3660.90 | +97.40 | +5 |
| STARLINK-11395 | 61951 | — | 2 | 2676.87 | 2407.89 | +2639.92 | +2310.16 | +95.94 | +5 |

## CH3 upper, 192.46–221.81 s

Track `sha256:781cab605843a0abf1a0942c04034f5cd53bf8e866eeb1eb7e75cb5399ac7a87`; 32 observations; 486 nominal-time satellites scored. Training leader: **STARLINK-36630 (NORAD 67703)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37070 (NORAD 68280): leader heldout RMS **210.53 Hz** versus **3554.48 Hz**; gain **+3343.95 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36630 | 67703 | 1 | 1 | 35.10 | 210.53 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-37070 | 68280 | 2 | 2 | 1372.88 | 3554.48 | +1337.78 | +3343.95 | +94.08 | -1 |
| STARLINK-11395 | 61951 | 3 | 4 | 1383.33 | 7320.74 | +1348.23 | +7110.21 | +97.12 | +5 |
| STARLINK-34918 | 65331 | 4 | 3 | 2540.05 | 4454.11 | +2504.95 | +4243.58 | +95.27 | +5 |
| STARLINK-5432 | 54848 | 5 | — | 3536.56 | 11711.30 | +3501.46 | +11500.77 | +98.20 | -5 |
| STARLINK-31444 | 59236 | — | 5 | 5365.01 | 8477.14 | +5329.91 | +8266.61 | +97.52 | +5 |

## CH3 lower, 192.72–218.67 s

Track `sha256:4a6f291d3cf774c6daf0e4f184cfaf14e1e78cd27dbabce99aaa26a37dd2fb64`; 32 observations; 484 nominal-time satellites scored. Training leader: **STARLINK-36630 (NORAD 67703)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37070 (NORAD 68280): leader heldout RMS **189.08 Hz** versus **3477.25 Hz**; gain **+3288.17 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36630 | 67703 | 1 | 1 | 23.53 | 189.08 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-37070 | 68280 | 2 | 2 | 1252.20 | 3477.25 | +1228.67 | +3288.17 | +94.56 | +0 |
| STARLINK-11395 | 61951 | 3 | 4 | 1286.72 | 5748.03 | +1263.19 | +5558.95 | +96.71 | +5 |
| STARLINK-34918 | 65331 | 4 | 3 | 2350.60 | 4238.92 | +2327.07 | +4049.84 | +95.54 | +5 |
| STARLINK-5432 | 54848 | 5 | — | 3189.46 | 10515.09 | +3165.93 | +10326.01 | +98.20 | -5 |
| STARLINK-31444 | 59236 | — | 5 | 4974.76 | 8200.95 | +4951.22 | +8011.87 | +97.69 | +5 |

## CH4 upper, 260.63–298.96 s

Track `sha256:15414e58a0bbea8e886e10d75946ee5ef5c4ca8bc2a770acadd5f5e21e7fcd4c`; 46 observations; 499 nominal-time satellites scored. Training leader: **STARLINK-5300 (NORAD 55676)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-33576 (NORAD 62775): leader heldout RMS **86.90 Hz** versus **1563.72 Hz**; gain **+1476.81 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-5300 | 55676 | 1 | 1 | 46.57 | 86.90 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-30759 | 58122 | 2 | 5 | 278.03 | 2390.04 | +231.45 | +2303.14 | +96.36 | -2 |
| STARLINK-5987 | 56455 | 3 | 4 | 326.39 | 2356.77 | +279.82 | +2269.86 | +96.31 | -5 |
| STARLINK-30895 | 58418 | 4 | — | 632.87 | 5301.52 | +586.30 | +5214.62 | +98.36 | +3 |
| STARLINK-3806 | 52378 | 5 | — | 866.19 | 5655.99 | +819.62 | +5569.09 | +98.46 | +5 |
| STARLINK-33576 | 62775 | — | 2 | 3010.85 | 1563.72 | +2964.27 | +1476.81 | +94.44 | +5 |
| STARLINK-30991 | 58484 | — | 3 | 3378.59 | 2310.02 | +3332.02 | +2223.12 | +96.24 | +5 |

## CH3 lower, 117.03–148.90 s

Track `sha256:6a83119f07ba619ebf4bc5cd2e1b2482852900748043af23e02afbacc9671dbd`; 38 observations; 488 nominal-time satellites scored. Training leader: **STARLINK-31415 (NORAD 59419)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32891 (NORAD 62927): leader heldout RMS **153.78 Hz** versus **3865.41 Hz**; gain **+3711.63 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31415 | 59419 | 1 | 1 | 44.20 | 153.78 | +0.00 | +0.00 | +0.00 | +1 |
| STARLINK-32891 | 62927 | 2 | 2 | 840.84 | 3865.41 | +796.64 | +3711.63 | +96.02 | +5 |
| STARLINK-33585 | 62782 | 3 | 3 | 2333.11 | 7620.29 | +2288.91 | +7466.52 | +97.98 | +5 |
| STARLINK-33923 | 63786 | 4 | — | 3137.33 | 15047.48 | +3093.13 | +14893.71 | +98.98 | -5 |
| STARLINK-35657 | 66399 | 5 | 5 | 3852.73 | 11050.20 | +3808.53 | +10896.42 | +98.61 | +5 |
| STARLINK-32092 | 59700 | — | 4 | 5123.42 | 10380.27 | +5079.22 | +10226.50 | +98.52 | +5 |
