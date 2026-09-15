# Candidate RMS comparisons: scan-hop-783c79c5b20d42b3

Recorded **2026-09-14T15:40:12.828072Z**, RX0, 10 MS/s.

[Recording assessment and plots](scan-hop-783c79c5b20d42b3.md).

Each track has its own training-selected leader; there is no single satellite assignment for the whole recording. Lower RMS is better. The same observations and chronological split are used for all candidates within a track.

Gain = alternative RMS − training-leader RMS. Positive gain favors the leader; negative heldout gain means the alternative predicts better. Percent gain uses the alternative RMS as denominator; it is not identification confidence. Tau and carrier offset were selected on training data and remain frozen on heldout.

The archived screen retained the top five training candidates and top five heldout candidates, whose union is listed below. Candidate counts describe the full scored population; names/scores outside these retained lists were not archived. A blank rank means outside that top-five list. Catalogue exclusions and control results are in the linked recording assessment and evidence.

## CH1 upper, 1.53–28.12 s

Track `sha256:0e36c0d2199f1aa07cc51c10c99e92164d7a1ab61dca16a200a9b76b3e60047c`; 32 observations; 594 nominal-time satellites scored. Training leader: **STARLINK-32897 (NORAD 62967)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-35266 (NORAD 65804): leader heldout RMS **97.59 Hz** versus **1924.55 Hz**; gain **+1826.96 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32897 | 62967 | 1 | 1 | 43.87 | 97.59 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-35266 | 65804 | 2 | 2 | 141.88 | 1924.55 | +98.01 | +1826.96 | +94.93 | +1 |
| STARLINK-38302 | 100378 | 3 | — | 515.43 | 8454.96 | +471.55 | +8357.37 | +98.85 | -2 |
| STARLINK-32836 | 62965 | 4 | — | 573.79 | 7093.79 | +529.92 | +6996.20 | +98.62 | -2 |
| STARLINK-1523 | 46028 | 5 | 4 | 701.30 | 5930.19 | +657.43 | +5832.60 | +98.35 | +2 |
| STARLINK-37732 | 69307 | — | 3 | 1452.73 | 3222.29 | +1408.85 | +3124.70 | +96.97 | +5 |
| STARLINK-34001 | 64272 | — | 5 | 1285.18 | 6758.40 | +1241.31 | +6660.81 | +98.56 | +5 |

## CH3 upper, 41.86–85.17 s

Track `sha256:955d3e6d3e08edd72894c751cb70901a59cbb0bf95b91564cc399e848fe570fb`; 44 observations; 615 nominal-time satellites scored. Training leader: **STARLINK-35891 (NORAD 67045)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4481 (NORAD 53418): leader heldout RMS **81.51 Hz** versus **1524.56 Hz**; gain **+1443.05 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35891 | 67045 | 1 | 1 | 91.24 | 81.51 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-30485 | 57920 | 2 | 4 | 383.92 | 3766.91 | +292.69 | +3685.40 | +97.84 | +5 |
| STARLINK-30204 | 57472 | 3 | — | 1273.37 | 11082.28 | +1182.13 | +11000.77 | +99.26 | -5 |
| STARLINK-37864 | 100107 | 4 | — | 1467.40 | 9456.69 | +1376.16 | +9375.18 | +99.14 | +5 |
| STARLINK-37060 | 68150 | 5 | — | 1546.38 | 12633.10 | +1455.15 | +12551.59 | +99.35 | +5 |
| STARLINK-4481 | 53418 | — | 2 | 1890.08 | 1524.56 | +1798.84 | +1443.05 | +94.65 | +5 |
| STARLINK-35851 | 66356 | — | 3 | 2917.45 | 3290.57 | +2826.21 | +3209.05 | +97.52 | -5 |
| STARLINK-34554 | 64687 | — | 5 | 5220.93 | 9306.53 | +5129.69 | +9225.02 | +99.12 | +5 |

## CH3 lower, 42.49–86.80 s

Track `sha256:05f8d0a2f5bdf8e76fb916fe58732d0d3a2853455ca1d51a4e5182668a6ce7d8`; 45 observations; 614 nominal-time satellites scored. Training leader: **STARLINK-35891 (NORAD 67045)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4481 (NORAD 53418): leader heldout RMS **72.98 Hz** versus **1806.31 Hz**; gain **+1733.34 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35891 | 67045 | 1 | 1 | 88.56 | 72.98 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-30485 | 57920 | 2 | 3 | 450.62 | 4176.45 | +362.06 | +4103.47 | +98.25 | +5 |
| STARLINK-37864 | 100107 | 3 | — | 1404.06 | 10732.85 | +1315.49 | +10659.87 | +99.32 | +5 |
| STARLINK-37060 | 68150 | 4 | — | 1555.76 | 12328.88 | +1467.20 | +12255.90 | +99.41 | +3 |
| STARLINK-30204 | 57472 | 5 | — | 1563.53 | 12141.55 | +1474.97 | +12068.58 | +99.40 | -5 |
| STARLINK-4481 | 53418 | — | 2 | 1802.55 | 1806.31 | +1713.99 | +1733.34 | +95.96 | +5 |
| STARLINK-35851 | 66356 | — | 4 | 2719.05 | 4766.61 | +2630.49 | +4693.64 | +98.47 | +5 |
| STARLINK-34554 | 64687 | — | 5 | 5254.82 | 8594.50 | +5166.26 | +8521.53 | +99.15 | +5 |

## CH4 lower, 59.24–88.45 s

Track `sha256:3ba89ddc0eda27e14ac041b1407620c98cbedffdaa7a9eab1641dfa599acddf2`; 30 observations; 593 nominal-time satellites scored. Training leader: **STARLINK-35891 (NORAD 67045)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-34554 (NORAD 64687): leader heldout RMS **137.84 Hz** versus **1708.59 Hz**; gain **+1570.75 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35891 | 67045 | 1 | 1 | 58.21 | 137.84 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-35851 | 66356 | 2 | 4 | 376.92 | 3354.73 | +318.71 | +3216.89 | +95.89 | -2 |
| STARLINK-4481 | 53418 | 3 | 5 | 384.62 | 3483.44 | +326.41 | +3345.60 | +96.04 | +3 |
| STARLINK-30485 | 57920 | 4 | 3 | 910.26 | 2858.57 | +852.05 | +2720.73 | +95.18 | +0 |
| STARLINK-37864 | 100107 | 5 | — | 1164.84 | 6072.57 | +1106.62 | +5934.73 | +97.73 | -5 |
| STARLINK-34554 | 64687 | — | 2 | 1942.88 | 1708.59 | +1884.67 | +1570.75 | +91.93 | +5 |

## CH1 upper, 59.37–86.55 s

Track `sha256:91f4a348a8b9ccea66f3aa6faa48cc32c1d84fc91a7cf732af64d145a6ba2ea4`; 28 observations; 592 nominal-time satellites scored. Training leader: **STARLINK-35891 (NORAD 67045)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-34554 (NORAD 64687): leader heldout RMS **333.93 Hz** versus **2176.86 Hz**; gain **+1842.93 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35891 | 67045 | 1 | 1 | 90.67 | 333.93 | +0.00 | +0.00 | +0.00 | +1 |
| STARLINK-35851 | 66356 | 2 | 5 | 299.50 | 3297.98 | +208.83 | +2964.05 | +89.87 | -1 |
| STARLINK-4481 | 53418 | 3 | 4 | 320.95 | 2984.25 | +230.28 | +2650.32 | +88.81 | +4 |
| STARLINK-30485 | 57920 | 4 | 3 | 794.87 | 2887.55 | +704.20 | +2553.62 | +88.44 | +1 |
| STARLINK-37732 | 69307 | 5 | — | 890.23 | 6999.59 | +799.56 | +6665.65 | +95.23 | -5 |
| STARLINK-34554 | 64687 | — | 2 | 1860.55 | 2176.86 | +1769.87 | +1842.93 | +84.66 | +5 |

## CH1 lower, 59.75–85.92 s

Track `sha256:b530551f8a81ef2f6ab4a0d35bbed8698f9dc9a585038092f8f74e3e97f3c0bc`; 27 observations; 591 nominal-time satellites scored. Training leader: **STARLINK-35891 (NORAD 67045)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-34554 (NORAD 64687): leader heldout RMS **66.83 Hz** versus **2048.02 Hz**; gain **+1981.19 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35891 | 67045 | 1 | 1 | 19.52 | 66.83 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-4481 | 53418 | 2 | 5 | 275.78 | 2874.23 | +256.26 | +2807.40 | +97.67 | +4 |
| STARLINK-35851 | 66356 | 3 | 4 | 314.43 | 2615.87 | +294.91 | +2549.05 | +97.45 | -2 |
| STARLINK-30485 | 57920 | 4 | 3 | 813.69 | 2580.91 | +794.17 | +2514.08 | +97.41 | +0 |
| STARLINK-37864 | 100107 | 5 | — | 978.98 | 5167.93 | +959.46 | +5101.10 | +98.71 | -5 |
| STARLINK-34554 | 64687 | — | 2 | 1809.92 | 2048.02 | +1790.40 | +1981.19 | +96.74 | +5 |

## CH2 lower, 149.92–171.47 s

Track `sha256:9d8cb56aa8ad39b5755d43888509e5ea4ddc186d54519137db59f525a0a8377f`; 25 observations; 590 nominal-time satellites scored. Training leader: **STARLINK-35747 (NORAD 66207)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-36140 (NORAD 67034): leader heldout RMS **61.39 Hz** versus **155.70 Hz**; gain **+94.30 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35747 | 66207 | 1 | 1 | 48.55 | 61.39 | +0.00 | +0.00 | +0.00 | -4 |
| STARLINK-36140 | 67034 | 2 | 2 | 54.80 | 155.70 | +6.25 | +94.30 | +60.57 | -3 |
| STARLINK-32901 | 62895 | 3 | 4 | 72.83 | 673.74 | +24.28 | +612.35 | +90.89 | -5 |
| STARLINK-34575 | 64859 | 4 | 5 | 104.12 | 1225.61 | +55.56 | +1164.22 | +94.99 | +0 |
| STARLINK-3128 | 49441 | 5 | — | 129.15 | 1406.52 | +80.60 | +1345.12 | +95.64 | +0 |
| STARLINK-35829 | 66350 | — | 3 | 228.77 | 514.96 | +180.22 | +453.57 | +88.08 | +5 |

## CH2 upper, 151.55–173.87 s

Track `sha256:2bea06ec4c60d022289f9bcd1c645617ed4d04d4fd3121a947e867761a06dada`; 26 observations; 590 nominal-time satellites scored. Training leader: **STARLINK-35747 (NORAD 66207)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-36140 (NORAD 67034): leader heldout RMS **54.10 Hz** versus **136.98 Hz**; gain **+82.88 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35747 | 66207 | 1 | 1 | 46.09 | 54.10 | +0.00 | +0.00 | +0.00 | -4 |
| STARLINK-36140 | 67034 | 2 | 2 | 61.28 | 136.98 | +15.19 | +82.88 | +60.50 | -3 |
| STARLINK-32901 | 62895 | 3 | 4 | 85.49 | 521.48 | +39.40 | +467.38 | +89.63 | -4 |
| STARLINK-34575 | 64859 | 4 | 5 | 149.58 | 1406.38 | +103.49 | +1352.28 | +96.15 | +1 |
| STARLINK-3128 | 49441 | 5 | — | 182.65 | 1826.69 | +136.56 | +1772.59 | +97.04 | +1 |
| STARLINK-35829 | 66350 | — | 3 | 213.19 | 407.32 | +167.10 | +353.21 | +86.72 | +5 |

## CH4 upper, 162.02–193.78 s

Track `sha256:532536913473a326451c9f0a0bc0f47cde595ca43041a16e0fde31f958646e36`; 33 observations; 590 nominal-time satellites scored. Training leader: **STARLINK-36140 (NORAD 67034)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-35747 (NORAD 66207): leader heldout RMS **92.40 Hz** versus **489.04 Hz**; gain **+396.64 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36140 | 67034 | 1 | 1 | 57.95 | 92.40 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-35829 | 66350 | 2 | 3 | 76.27 | 825.00 | +18.31 | +732.60 | +88.80 | +5 |
| STARLINK-35747 | 66207 | 3 | 2 | 94.60 | 489.04 | +36.64 | +396.64 | +81.11 | -5 |
| STARLINK-32901 | 62895 | 4 | 5 | 259.76 | 2996.88 | +201.81 | +2904.48 | +96.92 | +2 |
| STARLINK-11713 | 64070 | 5 | 4 | 884.96 | 1161.34 | +827.01 | +1068.94 | +92.04 | +5 |

## CH4 lower, 162.15–193.90 s

Track `sha256:bfd402194e837ac1fb4c93ac5ef2936b6cdf26021fd2b4766be3ce0de7e13592`; 32 observations; 590 nominal-time satellites scored. Training leader: **STARLINK-36140 (NORAD 67034)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-35747 (NORAD 66207): leader heldout RMS **120.37 Hz** versus **474.50 Hz**; gain **+354.13 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36140 | 67034 | 1 | 1 | 66.35 | 120.37 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-35829 | 66350 | 2 | 3 | 80.93 | 817.13 | +14.58 | +696.76 | +85.27 | +5 |
| STARLINK-35747 | 66207 | 3 | 2 | 96.75 | 474.50 | +30.40 | +354.13 | +74.63 | -5 |
| STARLINK-32901 | 62895 | 4 | 5 | 319.34 | 3116.52 | +252.99 | +2996.14 | +96.14 | +2 |
| STARLINK-11713 | 64070 | 5 | 4 | 949.10 | 1092.66 | +882.75 | +972.29 | +88.98 | +5 |

## CH1 upper, 180.30–202.34 s

Track `sha256:d29e83b53175a55a0f8fc2aa0234497251914b2e427f1d89a1d04b1f42bbe1b2`; 23 observations; 583 nominal-time satellites scored. Training leader: **STARLINK-36140 (NORAD 67034)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-35747 (NORAD 66207): leader heldout RMS **93.00 Hz** versus **985.77 Hz**; gain **+892.77 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36140 | 67034 | 1 | 1 | 67.47 | 93.00 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-35747 | 66207 | 2 | 2 | 123.05 | 985.77 | +55.58 | +892.77 | +90.57 | +4 |
| STARLINK-11713 | 64070 | 3 | 5 | 138.98 | 1505.53 | +71.51 | +1412.53 | +93.82 | +3 |
| STARLINK-35829 | 66350 | 4 | — | 152.13 | 1682.61 | +84.66 | +1589.61 | +94.47 | -1 |
| STARLINK-37878 | 69479 | 5 | 4 | 166.55 | 1460.75 | +99.08 | +1367.75 | +93.63 | -2 |
| STARLINK-30973 | 58713 | — | 3 | 1535.14 | 1358.88 | +1467.67 | +1265.89 | +93.16 | +5 |

## CH1 lower, 200.45–225.17 s

Track `sha256:dee0c4caaac42f604791f8c8d04d5db1ac17bc9e0dac22e40f0055cf930320b2`; 33 observations; 582 nominal-time satellites scored. Training leader: **STARLINK-30973 (NORAD 58713)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11713 (NORAD 64070): leader heldout RMS **66.04 Hz** versus **3908.81 Hz**; gain **+3842.77 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30973 | 58713 | 1 | 1 | 58.90 | 66.04 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-11713 | 64070 | 2 | 2 | 778.20 | 3908.81 | +719.30 | +3842.77 | +98.31 | -5 |
| STARLINK-35829 | 66350 | 3 | 4 | 1082.71 | 5300.42 | +1023.81 | +5234.39 | +98.75 | -5 |
| STARLINK-30966 | 58454 | 4 | 3 | 1353.97 | 4139.20 | +1295.07 | +4073.16 | +98.40 | +5 |
| STARLINK-1641 | 46174 | 5 | 5 | 2437.84 | 7287.29 | +2378.94 | +7221.25 | +99.09 | -1 |

## CH2 lower, 240.04–260.08 s

Track `sha256:70c21a5278f04fe422c969d3477fac4f9c01e17045f244c882c3260c725f16e6`; 26 observations; 592 nominal-time satellites scored. Training leader: **STARLINK-35849 (NORAD 66348)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37701 (NORAD 69306): leader heldout RMS **117.79 Hz** versus **780.88 Hz**; gain **+663.09 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35849 | 66348 | 1 | 1 | 24.16 | 117.79 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-35330 | 65791 | 2 | 3 | 163.94 | 1376.89 | +139.78 | +1259.09 | +91.44 | -1 |
| STARLINK-11386 | 62098 | 3 | — | 619.82 | 5004.03 | +595.66 | +4886.24 | +97.65 | +0 |
| STARLINK-38284 | 100379 | 4 | — | 699.91 | 6163.60 | +675.75 | +6045.81 | +98.09 | +2 |
| STARLINK-37701 | 69306 | 5 | 2 | 1210.46 | 780.88 | +1186.30 | +663.09 | +84.92 | +5 |
| STARLINK-4519 | 53439 | — | 4 | 2546.31 | 3815.43 | +2522.15 | +3697.64 | +96.91 | +5 |
| STARLINK-37932 | 69564 | — | 5 | 1966.17 | 4558.42 | +1942.01 | +4440.63 | +97.42 | -4 |

## CH3 upper, 269.92–299.89 s

Track `sha256:e6c74a72b01c1b509e251cb51589b6225bd62fdcb59350795f19e7af81044225`; 31 observations; 599 nominal-time satellites scored. Training leader: **STARLINK-36470 (NORAD 67319)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30498 (NORAD 57971): leader heldout RMS **128.05 Hz** versus **1450.29 Hz**; gain **+1322.24 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36470 | 67319 | 1 | 1 | 27.31 | 128.05 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-31913 | 59667 | 2 | 3 | 137.96 | 1463.03 | +110.65 | +1334.99 | +91.25 | -2 |
| STARLINK-33632 | 63577 | 3 | — | 694.22 | 6184.76 | +666.90 | +6056.72 | +97.93 | -5 |
| STARLINK-11623 | 63276 | 4 | — | 782.60 | 6042.47 | +755.29 | +5914.43 | +97.88 | +5 |
| STARLINK-35330 | 65791 | 5 | — | 1034.90 | 8643.74 | +1007.59 | +8515.70 | +98.52 | +2 |
| STARLINK-30498 | 57971 | — | 2 | 1655.68 | 1450.29 | +1628.37 | +1322.24 | +91.17 | +5 |
| STARLINK-37020 | 68144 | — | 4 | 1521.64 | 1611.75 | +1494.33 | +1483.71 | +92.06 | +5 |
| STARLINK-3751 | 52289 | — | 5 | 1922.92 | 2916.29 | +1895.60 | +2788.24 | +95.61 | -5 |

## CH3 lower, 276.34–300.01 s

Track `sha256:0a059e17d4edf3834766b703b3577f3a14ee9e0eb33da5378783665f66354124`; 29 observations; 595 nominal-time satellites scored. Training leader: **STARLINK-36470 (NORAD 67319)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4519 (NORAD 53439): leader heldout RMS **28.06 Hz** versus **987.90 Hz**; gain **+959.84 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36470 | 67319 | 1 | 1 | 24.62 | 28.06 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-31913 | 59667 | 2 | 3 | 129.80 | 1136.81 | +105.17 | +1108.75 | +97.53 | -3 |
| STARLINK-11623 | 63276 | 3 | — | 491.11 | 4743.40 | +466.49 | +4715.34 | +99.41 | +3 |
| STARLINK-37020 | 68144 | 4 | — | 498.51 | 2541.64 | +473.89 | +2513.58 | +98.90 | +5 |
| STARLINK-30498 | 57971 | 5 | 5 | 594.64 | 2322.85 | +570.02 | +2294.79 | +98.79 | +5 |
| STARLINK-4519 | 53439 | — | 2 | 1637.55 | 987.90 | +1612.93 | +959.84 | +97.16 | +5 |
| STARLINK-3751 | 52289 | — | 4 | 869.05 | 1342.67 | +844.42 | +1314.61 | +97.91 | +5 |

## CH1 upper, 194.41–225.42 s

Track `sha256:f6eda34db2dba5d778849ec6d443bd126185f547ee0aa6de0ff2adf51c99bbde`; 39 observations; 587 nominal-time satellites scored. Training leader: **STARLINK-30973 (NORAD 58713)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11713 (NORAD 64070): leader heldout RMS **42.59 Hz** versus **3880.01 Hz**; gain **+3837.42 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30973 | 58713 | 1 | 1 | 31.13 | 42.59 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-11713 | 64070 | 2 | 2 | 508.21 | 3880.01 | +477.08 | +3837.42 | +98.90 | -5 |
| STARLINK-35829 | 66350 | 3 | 4 | 706.82 | 5304.15 | +675.69 | +5261.57 | +99.20 | -5 |
| STARLINK-30966 | 58454 | 4 | 3 | 1469.11 | 5027.74 | +1437.98 | +4985.15 | +99.15 | +5 |
| STARLINK-35747 | 66207 | 5 | — | 2168.35 | 11408.67 | +2137.22 | +11366.08 | +99.63 | -5 |
| STARLINK-1641 | 46174 | — | 5 | 2635.38 | 9412.58 | +2604.25 | +9369.99 | +99.55 | +3 |

## CH1 lower, 215.08–239.28 s

Track `sha256:41938b413890c38cea71e522f30b0fa8a3677b88f5fb107d9152d3864151f127`; 29 observations; 589 nominal-time satellites scored. Training leader: **STARLINK-38307 (NORAD 100377)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30973 (NORAD 58713): leader heldout RMS **7751.76 Hz** versus **24663.20 Hz**; gain **+16911.44 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-38307 | 100377 | 1 | 1 | 732.52 | 7751.76 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-30973 | 58713 | 2 | 2 | 6279.84 | 24663.20 | +5547.32 | +16911.44 | +68.57 | -5 |
| STARLINK-30966 | 58454 | 3 | 5 | 7534.09 | 28394.12 | +6801.57 | +20642.37 | +72.70 | -5 |
| STARLINK-35849 | 66348 | 4 | 3 | 7593.84 | 25234.91 | +6861.32 | +17483.16 | +69.28 | +5 |
| STARLINK-11713 | 64070 | 5 | — | 8346.23 | 33931.94 | +7613.72 | +26180.18 | +77.15 | -5 |
| STARLINK-35330 | 65791 | — | 4 | 8777.98 | 28115.63 | +8045.46 | +20363.87 | +72.43 | +5 |
