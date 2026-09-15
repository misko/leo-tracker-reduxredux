# Candidate RMS comparisons: scan-hop-51307ad2476e5cc2

Recorded **2026-09-14T19:00:12.796060Z**, RX0, 10 MS/s.

[Recording assessment and plots](scan-hop-51307ad2476e5cc2.md).

Each track has its own training-selected leader; there is no single satellite assignment for the whole recording. Lower RMS is better. The same observations and chronological split are used for all candidates within a track.

Gain = alternative RMS − training-leader RMS. Positive gain favors the leader; negative heldout gain means the alternative predicts better. Percent gain uses the alternative RMS as denominator; it is not identification confidence. Tau and carrier offset were selected on training data and remain frozen on heldout.

The archived screen retained the top five training candidates and top five heldout candidates, whose union is listed below. Candidate counts describe the full scored population; names/scores outside these retained lists were not archived. A blank rank means outside that top-five list. Catalogue exclusions and control results are in the linked recording assessment and evidence.

## CH4 lower, 5.43–27.59 s

Track `sha256:35b0ff9814eaf86b05f0c70d89293fa86fc6e1957bad65f1a86577ea5e1284b4`; 23 observations; 497 nominal-time satellites scored. Training leader: **STARLINK-32753 (NORAD 62481)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-5515 (NORAD 56884): leader heldout RMS **136.13 Hz** versus **1496.88 Hz**; gain **+1360.75 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32753 | 62481 | 1 | 1 | 66.92 | 136.13 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-35175 | 65929 | 2 | — | 369.27 | 4121.88 | +302.35 | +3985.74 | +96.70 | -5 |
| STARLINK-34729 | 65364 | 3 | 4 | 558.75 | 1738.13 | +491.83 | +1601.99 | +92.17 | -5 |
| STARLINK-31234 | 59043 | 4 | — | 626.33 | 6469.38 | +559.41 | +6333.24 | +97.90 | -5 |
| STARLINK-32678 | 62309 | 5 | — | 667.90 | 6741.39 | +600.98 | +6605.25 | +97.98 | -5 |
| STARLINK-5515 | 56884 | — | 2 | 1176.66 | 1496.88 | +1109.74 | +1360.75 | +90.91 | +5 |
| STARLINK-31696 | 59435 | — | 3 | 2047.71 | 1546.45 | +1980.79 | +1410.32 | +91.20 | +5 |
| STARLINK-35483 | 66252 | — | 5 | 1860.23 | 2201.39 | +1793.31 | +2065.25 | +93.82 | +5 |

## CH2 upper, 96.35–123.81 s

Track `sha256:336855ae3823a3074bdbc628981776b119cb4916a14b68bd95f760556362f435`; 28 observations; 508 nominal-time satellites scored. Training leader: **STARLINK-31106 (NORAD 58689)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-35529 (NORAD 66259): leader heldout RMS **151.53 Hz** versus **413.67 Hz**; gain **+262.14 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31106 | 58689 | 1 | 1 | 77.01 | 151.53 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-35529 | 66259 | 2 | 2 | 78.66 | 413.67 | +1.65 | +262.14 | +63.37 | -4 |
| STARLINK-6251 | 57087 | 3 | — | 433.12 | 4370.85 | +356.11 | +4219.31 | +96.53 | -5 |
| STARLINK-36320 | 68090 | 4 | 5 | 673.55 | 3968.65 | +596.54 | +3817.12 | +96.18 | +5 |
| STARLINK-36142 | 66981 | 5 | 4 | 859.69 | 3810.15 | +782.68 | +3658.62 | +96.02 | +5 |
| STARLINK-11740 | 64382 | — | 3 | 1652.29 | 2853.44 | +1575.27 | +2701.91 | +94.69 | +5 |

## CH4 upper, 123.56–149.16 s

Track `sha256:80eae5fad94fc47a57a8c59638d565aab3f76ab32404e572e2e4310b803ea330`; 28 observations; 495 nominal-time satellites scored. Training leader: **STARLINK-32369 (NORAD 60917)**; heldout rank 2 in the full scored population.

Against the best other heldout candidate, STARLINK-4031 (NORAD 52679): leader heldout RMS **62.33 Hz** versus **51.65 Hz**; gain **-10.68 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32369 | 60917 | 1 | 2 | 55.80 | 62.33 | +0.00 | +0.00 | +0.00 | -5 |
| STARLINK-4031 | 52679 | 2 | 1 | 64.26 | 51.65 | +8.47 | -10.68 | -20.67 | +4 |
| STARLINK-30231 | 57514 | 3 | 4 | 89.16 | 1118.43 | +33.37 | +1056.10 | +94.43 | +1 |
| STARLINK-32809 | 62849 | 4 | 3 | 99.49 | 228.16 | +43.70 | +165.83 | +72.68 | -2 |
| STARLINK-11084 | 59717 | 5 | — | 159.01 | 1978.68 | +103.21 | +1916.35 | +96.85 | +0 |
| STARLINK-30575 | 58052 | — | 5 | 691.35 | 1385.21 | +635.55 | +1322.88 | +95.50 | -5 |

## CH4 lower, 123.68–148.53 s

Track `sha256:93e94ad04c51d9deb04e310ad67f7f298c3a606cefc0a4ad3b66f370e6ba2250`; 27 observations; 493 nominal-time satellites scored. Training leader: **STARLINK-32369 (NORAD 60917)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4031 (NORAD 52679): leader heldout RMS **36.69 Hz** versus **47.30 Hz**; gain **+10.61 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32369 | 60917 | 1 | 1 | 40.09 | 36.69 | +0.00 | +0.00 | +0.00 | -5 |
| STARLINK-4031 | 52679 | 2 | 2 | 67.44 | 47.30 | +27.34 | +10.61 | +22.42 | +4 |
| STARLINK-32809 | 62849 | 3 | 3 | 74.18 | 160.62 | +34.08 | +123.93 | +77.16 | -3 |
| STARLINK-30231 | 57514 | 4 | 4 | 115.38 | 1027.38 | +75.29 | +990.69 | +96.43 | +1 |
| STARLINK-11084 | 59717 | 5 | — | 183.67 | 1844.72 | +143.58 | +1808.03 | +98.01 | +0 |
| STARLINK-30575 | 58052 | — | 5 | 712.37 | 1229.03 | +672.27 | +1192.34 | +97.01 | -5 |

## CH2 lower, 124.06–148.91 s

Track `sha256:1b5f77c70b728298efb35524c9308133e63be5e05083bbba2559a4c2c3a0c79f`; 27 observations; 493 nominal-time satellites scored. Training leader: **STARLINK-32369 (NORAD 60917)**; heldout rank 2 in the full scored population.

Against the best other heldout candidate, STARLINK-4031 (NORAD 52679): leader heldout RMS **98.50 Hz** versus **95.20 Hz**; gain **-3.31 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32369 | 60917 | 1 | 2 | 41.20 | 98.50 | +0.00 | +0.00 | +0.00 | -5 |
| STARLINK-4031 | 52679 | 2 | 1 | 67.38 | 95.20 | +26.18 | -3.31 | -3.47 | +4 |
| STARLINK-32809 | 62849 | 3 | 3 | 71.82 | 189.80 | +30.62 | +91.30 | +48.10 | -3 |
| STARLINK-30231 | 57514 | 4 | 4 | 121.63 | 1123.17 | +80.43 | +1024.67 | +91.23 | +1 |
| STARLINK-11084 | 59717 | 5 | — | 200.98 | 1974.42 | +159.78 | +1875.92 | +95.01 | +0 |
| STARLINK-30575 | 58052 | — | 5 | 669.12 | 1419.46 | +627.93 | +1320.95 | +93.06 | -5 |

## CH2 upper, 128.85–149.03 s

Track `sha256:6da7533f5fb65fee90b3210b4e1f22ccce5b29f2d8ede19f08b173218213aad2`; 22 observations; 488 nominal-time satellites scored. Training leader: **STARLINK-32369 (NORAD 60917)**; heldout rank 2 in the full scored population.

Against the best other heldout candidate, STARLINK-4031 (NORAD 52679): leader heldout RMS **73.99 Hz** versus **57.35 Hz**; gain **-16.64 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32369 | 60917 | 1 | 2 | 31.47 | 73.99 | +0.00 | +0.00 | +0.00 | -5 |
| STARLINK-4031 | 52679 | 2 | 1 | 40.78 | 57.35 | +9.31 | -16.64 | -29.02 | +4 |
| STARLINK-32809 | 62849 | 3 | 3 | 58.27 | 135.15 | +26.80 | +61.17 | +45.26 | -3 |
| STARLINK-30231 | 57514 | 4 | 4 | 107.42 | 924.47 | +75.95 | +850.49 | +92.00 | +3 |
| STARLINK-11084 | 59717 | 5 | — | 193.65 | 1872.41 | +162.18 | +1798.43 | +96.05 | +5 |
| STARLINK-30575 | 58052 | — | 5 | 230.82 | 1822.38 | +199.35 | +1748.39 | +95.94 | -5 |

## CH1 upper, 134.27–170.19 s

Track `sha256:de0e746939bfd7b18072316be1bb5ffca445f8f98ecb6097aa8e7324e60d0b39`; 41 observations; 495 nominal-time satellites scored. Training leader: **STARLINK-32809 (NORAD 62849)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32369 (NORAD 60917): leader heldout RMS **130.45 Hz** versus **389.37 Hz**; gain **+258.92 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32809 | 62849 | 1 | 1 | 97.25 | 130.45 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-32369 | 60917 | 2 | 2 | 103.13 | 389.37 | +5.88 | +258.92 | +66.50 | -4 |
| STARLINK-4031 | 52679 | 3 | 3 | 112.15 | 580.92 | +14.90 | +450.48 | +77.54 | +5 |
| STARLINK-11740 | 64382 | 4 | 4 | 938.01 | 5134.46 | +840.76 | +5004.01 | +97.46 | +5 |
| STARLINK-30231 | 57514 | 5 | 5 | 1068.14 | 5140.25 | +970.90 | +5009.80 | +97.46 | +3 |

## CH1 lower, 136.54–169.82 s

Track `sha256:85e1b1009aa75aca9954b98cbcac3214e6e3c0cc6312f1d25b9b3dfc105fda94`; 39 observations; 495 nominal-time satellites scored. Training leader: **STARLINK-32809 (NORAD 62849)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32369 (NORAD 60917): leader heldout RMS **57.07 Hz** versus **425.25 Hz**; gain **+368.18 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32809 | 62849 | 1 | 1 | 44.50 | 57.07 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-32369 | 60917 | 2 | 2 | 54.81 | 425.25 | +10.31 | +368.18 | +86.58 | -4 |
| STARLINK-4031 | 52679 | 3 | 3 | 73.69 | 623.80 | +29.19 | +566.73 | +90.85 | +5 |
| STARLINK-11740 | 64382 | 4 | 5 | 694.42 | 5590.62 | +649.92 | +5533.55 | +98.98 | +5 |
| STARLINK-30231 | 57514 | 5 | 4 | 1119.52 | 4575.49 | +1075.02 | +4518.42 | +98.75 | +1 |

## CH2 upper, 211.28–232.94 s

Track `sha256:0726eb25f269bf7040621ea4a28ee1a5616b729dbecba66594db450b4704e53b`; 27 observations; 494 nominal-time satellites scored. Training leader: **STARLINK-36145 (NORAD 66983)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-6209 (NORAD 56877): leader heldout RMS **241.07 Hz** versus **1477.84 Hz**; gain **+1236.77 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36145 | 66983 | 1 | 1 | 19.53 | 241.07 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-30404 | 57853 | 2 | 3 | 140.11 | 2299.66 | +120.58 | +2058.59 | +89.52 | -5 |
| STARLINK-11626 | 63556 | 3 | — | 270.23 | 3879.49 | +250.70 | +3638.42 | +93.79 | -2 |
| STARLINK-3148 | 49736 | 4 | 4 | 679.95 | 2361.65 | +660.42 | +2120.59 | +89.79 | +1 |
| STARLINK-11709 | 64065 | 5 | — | 902.21 | 3745.01 | +882.68 | +3503.94 | +93.56 | +5 |
| STARLINK-6209 | 56877 | — | 2 | 963.34 | 1477.84 | +943.81 | +1236.77 | +83.69 | +5 |
| STARLINK-6248 | 57082 | — | 5 | 1041.82 | 3715.13 | +1022.30 | +3474.06 | +93.51 | -1 |

## CH2 lower, 211.41–233.07 s

Track `sha256:406b3a4524fd15ce134e9b93c3f6a47ea85de282d61dea2060a82adbd46bfc4d`; 26 observations; 494 nominal-time satellites scored. Training leader: **STARLINK-36145 (NORAD 66983)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-6209 (NORAD 56877): leader heldout RMS **87.40 Hz** versus **1453.16 Hz**; gain **+1365.75 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36145 | 66983 | 1 | 1 | 13.30 | 87.40 | +0.00 | +0.00 | +0.00 | -4 |
| STARLINK-30404 | 57853 | 2 | 3 | 125.63 | 1901.46 | +112.34 | +1814.06 | +95.40 | -5 |
| STARLINK-11626 | 63556 | 3 | — | 241.77 | 3924.86 | +228.47 | +3837.45 | +97.77 | -1 |
| STARLINK-3148 | 49736 | 4 | 4 | 643.58 | 2091.63 | +630.28 | +2004.23 | +95.82 | +1 |
| STARLINK-11709 | 64065 | 5 | 5 | 871.69 | 3146.09 | +858.39 | +3058.69 | +97.22 | +5 |
| STARLINK-6209 | 56877 | — | 2 | 918.44 | 1453.16 | +905.14 | +1365.75 | +93.99 | +5 |

## CH2 lower, 95.59–126.08 s

Track `sha256:a5480b35d43c8aabb30996861480002a987e76b7530c380b6a6d7023a53423f7`; 32 observations; 508 nominal-time satellites scored. Training leader: **STARLINK-35529 (NORAD 66259)**; heldout rank 2 in the full scored population.

Against the best other heldout candidate, STARLINK-31106 (NORAD 58689): leader heldout RMS **471.77 Hz** versus **154.49 Hz**; gain **-317.28 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35529 | 66259 | 1 | 2 | 69.07 | 471.77 | +0.00 | +0.00 | +0.00 | -4 |
| STARLINK-31106 | 58689 | 2 | 1 | 79.69 | 154.49 | +10.62 | -317.28 | -205.36 | +0 |
| STARLINK-6251 | 57087 | 3 | — | 630.42 | 5186.38 | +561.35 | +4714.61 | +90.90 | -5 |
| STARLINK-36320 | 68090 | 4 | — | 741.34 | 5062.32 | +672.27 | +4590.55 | +90.68 | +5 |
| STARLINK-36142 | 66981 | 5 | 5 | 923.99 | 4954.17 | +854.92 | +4482.40 | +90.48 | +5 |
| STARLINK-11740 | 64382 | — | 3 | 1879.32 | 2641.09 | +1810.26 | +2169.32 | +82.14 | +5 |
| STARLINK-30575 | 58052 | — | 4 | 1691.86 | 4527.09 | +1622.79 | +4055.32 | +89.58 | +5 |
