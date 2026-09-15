# Candidate RMS comparisons: scan-hop-bcd8d20ced9c3968

Recorded **2026-09-14T16:10:12.539968Z**, RX0, 10 MS/s.

[Recording assessment and plots](scan-hop-bcd8d20ced9c3968.md).

Each track has its own training-selected leader; there is no single satellite assignment for the whole recording. Lower RMS is better. The same observations and chronological split are used for all candidates within a track.

Gain = alternative RMS − training-leader RMS. Positive gain favors the leader; negative heldout gain means the alternative predicts better. Percent gain uses the alternative RMS as denominator; it is not identification confidence. Tau and carrier offset were selected on training data and remain frozen on heldout.

The archived screen retained the top five training candidates and top five heldout candidates, whose union is listed below. Candidate counts describe the full scored population; names/scores outside these retained lists were not archived. A blank rank means outside that top-five list. Catalogue exclusions and control results are in the linked recording assessment and evidence.

## CH3 lower, 17.41–37.45 s

Track `sha256:cbbadea8f833c0e7eb17244b7b40c0143a0f5b65f6d6cbe1e6a2b081c09319be`; 22 observations; 584 nominal-time satellites scored. Training leader: **STARLINK-36292 (NORAD 68509)**; heldout rank 2 in the full scored population.

Against the best other heldout candidate, STARLINK-33965 (NORAD 64755): leader heldout RMS **740.12 Hz** versus **58.32 Hz**; gain **-681.80 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36292 | 68509 | 1 | 2 | 97.55 | 740.12 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-33965 | 64755 | 2 | 1 | 117.72 | 58.32 | +20.17 | -681.80 | -1169.10 | -2 |
| STARLINK-37762 | 100415 | 3 | 5 | 393.05 | 2633.10 | +295.50 | +1892.98 | +71.89 | -5 |
| STARLINK-5344 | 55494 | 4 | 4 | 534.07 | 2181.78 | +436.52 | +1441.66 | +66.08 | +1 |
| STARLINK-37996 | 100410 | 5 | 3 | 1635.79 | 2066.78 | +1538.24 | +1326.66 | +64.19 | +5 |

## CH2 lower, 37.33–58.86 s

Track `sha256:a139ffd108625189d4cf3b2e5f25095172265562e0ab8c3f48dc198f99b1d751`; 25 observations; 580 nominal-time satellites scored. Training leader: **STARLINK-32873 (NORAD 62857)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37996 (NORAD 100410): leader heldout RMS **53.10 Hz** versus **1750.64 Hz**; gain **+1697.55 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32873 | 62857 | 1 | 1 | 21.92 | 53.10 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-37996 | 100410 | 2 | 2 | 417.60 | 1750.64 | +395.68 | +1697.55 | +96.97 | -5 |
| STARLINK-37762 | 100415 | 3 | 5 | 601.12 | 4081.98 | +579.21 | +4028.88 | +98.70 | +5 |
| STARLINK-11491 | 62269 | 4 | — | 684.21 | 5254.22 | +662.29 | +5201.12 | +98.99 | -2 |
| STARLINK-30951 | 58439 | 5 | 4 | 838.97 | 3864.01 | +817.05 | +3810.91 | +98.63 | +2 |
| STARLINK-37277 | 68751 | — | 3 | 1473.49 | 1984.65 | +1451.57 | +1931.55 | +97.32 | +5 |

## CH2 upper, 37.71–59.24 s

Track `sha256:31f0fd00749dcd34c087abf3217fcf248071885bc945150978a9e548e1654003`; 26 observations; 581 nominal-time satellites scored. Training leader: **STARLINK-32873 (NORAD 62857)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37277 (NORAD 68751): leader heldout RMS **31.49 Hz** versus **1777.46 Hz**; gain **+1745.97 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32873 | 62857 | 1 | 1 | 95.29 | 31.49 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-37996 | 100410 | 2 | 3 | 427.80 | 1814.51 | +332.51 | +1783.02 | +98.26 | -5 |
| STARLINK-37762 | 100415 | 3 | — | 570.20 | 4183.85 | +474.91 | +4152.36 | +99.25 | +5 |
| STARLINK-11491 | 62269 | 4 | — | 648.08 | 4695.36 | +552.79 | +4663.87 | +99.33 | -3 |
| STARLINK-30951 | 58439 | 5 | 4 | 878.79 | 3817.75 | +783.50 | +3786.26 | +99.18 | +2 |
| STARLINK-37277 | 68751 | — | 2 | 1439.66 | 1777.46 | +1344.38 | +1745.97 | +98.23 | +5 |
| STARLINK-37929 | 69557 | — | 5 | 1839.01 | 4064.52 | +1743.72 | +4033.03 | +99.23 | +5 |

## CH2 lower, 59.49–88.10 s

Track `sha256:ece4a41b044d192530a2c0d49d766fa4500ab6b2d3b92a9b5ed6ecd0a0ca8733`; 39 observations; 587 nominal-time satellites scored. Training leader: **STARLINK-37277 (NORAD 68751)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37996 (NORAD 100410): leader heldout RMS **59.32 Hz** versus **7145.68 Hz**; gain **+7086.36 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37277 | 68751 | 1 | 1 | 72.04 | 59.32 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-37996 | 100410 | 2 | 2 | 661.26 | 7145.68 | +589.22 | +7086.36 | +99.17 | -5 |
| STARLINK-32873 | 62857 | 3 | — | 1587.01 | 10279.31 | +1514.97 | +10219.99 | +99.42 | -5 |
| STARLINK-37929 | 69557 | 4 | 4 | 1803.87 | 8448.05 | +1731.82 | +8388.73 | +99.30 | +3 |
| STARLINK-11420 | 62591 | 5 | 3 | 2099.71 | 8252.44 | +2027.67 | +8193.12 | +99.28 | +5 |
| STARLINK-5782 | 56034 | — | 5 | 2378.39 | 9033.42 | +2306.35 | +8974.10 | +99.34 | +5 |

## CH2 upper, 59.86–88.73 s

Track `sha256:86afd7018858fa7120f6e6425660a2537ca4e5ed02b0d2071578d1373ba37913`; 37 observations; 587 nominal-time satellites scored. Training leader: **STARLINK-37277 (NORAD 68751)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37996 (NORAD 100410): leader heldout RMS **53.71 Hz** versus **8067.36 Hz**; gain **+8013.65 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37277 | 68751 | 1 | 1 | 58.97 | 53.71 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-37996 | 100410 | 2 | 2 | 1012.24 | 8067.36 | +953.27 | +8013.65 | +99.33 | -5 |
| STARLINK-32873 | 62857 | 3 | — | 2044.09 | 11131.72 | +1985.11 | +11078.01 | +99.52 | -5 |
| STARLINK-37929 | 69557 | 4 | 4 | 2127.59 | 8591.90 | +2068.61 | +8538.19 | +99.37 | +2 |
| STARLINK-11420 | 62591 | 5 | 3 | 2388.27 | 8435.23 | +2329.29 | +8381.51 | +99.36 | +5 |
| STARLINK-5782 | 56034 | — | 5 | 2685.28 | 9187.81 | +2626.31 | +9134.10 | +99.42 | +5 |

## CH1 upper, 89.48–113.54 s

Track `sha256:0d0d3ac6f2ad095ee35bb4a463e8a1e7a60eaaac794734337d01adb3d21f3a1e`; 29 observations; 580 nominal-time satellites scored. Training leader: **STARLINK-30088 (NORAD 57462)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-2334 (NORAD 47792): leader heldout RMS **100.33 Hz** versus **940.06 Hz**; gain **+839.72 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30088 | 57462 | 1 | 1 | 107.31 | 100.33 | +0.00 | +0.00 | +0.00 | +1 |
| STARLINK-2334 | 47792 | 2 | 2 | 130.78 | 940.06 | +23.47 | +839.72 | +89.33 | +3 |
| STARLINK-3124 | 49456 | 3 | 3 | 151.38 | 1316.81 | +44.07 | +1216.48 | +92.38 | +5 |
| STARLINK-5782 | 56034 | 4 | — | 361.66 | 4153.28 | +254.35 | +4052.95 | +97.58 | -4 |
| STARLINK-11420 | 62591 | 5 | — | 382.23 | 4243.66 | +274.92 | +4143.33 | +97.64 | -3 |
| STARLINK-5094 | 53977 | — | 4 | 1194.44 | 1837.16 | +1087.14 | +1736.83 | +94.54 | +5 |
| STARLINK-37698 | 100423 | — | 5 | 2111.63 | 3753.14 | +2004.32 | +3652.81 | +97.33 | +5 |

## CH1 lower, 89.99–112.53 s

Track `sha256:0698d1680994edc2d4ed113a5c3e2b617e6df5f0547ec6ca4273fb8cd6644e33`; 26 observations; 580 nominal-time satellites scored. Training leader: **STARLINK-30088 (NORAD 57462)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-2334 (NORAD 47792): leader heldout RMS **56.34 Hz** versus **864.56 Hz**; gain **+808.22 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30088 | 57462 | 1 | 1 | 45.34 | 56.34 | +0.00 | +0.00 | +0.00 | +1 |
| STARLINK-2334 | 47792 | 2 | 2 | 60.17 | 864.56 | +14.83 | +808.22 | +93.48 | +3 |
| STARLINK-3124 | 49456 | 3 | 3 | 82.18 | 1228.04 | +36.83 | +1171.70 | +95.41 | +5 |
| STARLINK-5782 | 56034 | 4 | — | 288.51 | 4485.15 | +243.17 | +4428.80 | +98.74 | -3 |
| STARLINK-11420 | 62591 | 5 | — | 301.48 | 4593.16 | +256.13 | +4536.82 | +98.77 | -2 |
| STARLINK-5094 | 53977 | — | 4 | 1061.38 | 1897.68 | +1016.04 | +1841.33 | +97.03 | +5 |
| STARLINK-37698 | 100423 | — | 5 | 1881.42 | 3803.80 | +1836.07 | +3747.45 | +98.52 | +5 |

## CH2 lower, 115.69–136.60 s

Track `sha256:cef85526f7f60b099c284408003b4b30288018233be3c136278b20d3bfc0b889`; 23 observations; 579 nominal-time satellites scored. Training leader: **STARLINK-33914 (NORAD 63774)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-34371 (NORAD 64756): leader heldout RMS **98.81 Hz** versus **280.26 Hz**; gain **+181.45 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33914 | 63774 | 1 | 1 | 29.15 | 98.81 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-34371 | 64756 | 2 | 2 | 37.00 | 280.26 | +7.85 | +181.45 | +64.74 | -4 |
| STARLINK-30842 | 58357 | 3 | 4 | 58.36 | 497.03 | +29.20 | +398.22 | +80.12 | +0 |
| STARLINK-5684 | 55453 | 4 | — | 71.30 | 827.48 | +42.14 | +728.68 | +88.06 | +2 |
| STARLINK-34939 | 65183 | 5 | — | 127.49 | 1761.24 | +98.33 | +1662.43 | +94.39 | +1 |
| STARLINK-36616 | 67672 | — | 3 | 182.12 | 330.14 | +152.97 | +231.33 | +70.07 | +5 |
| STARLINK-36500 | 67320 | — | 5 | 828.03 | 715.45 | +798.87 | +616.64 | +86.19 | -5 |

## CH2 lower, 159.27–179.32 s

Track `sha256:40e50e90c0f7c323459e504246c649afce04b9e967aec85d4040e25be078e4fd`; 25 observations; 577 nominal-time satellites scored. Training leader: **STARLINK-36616 (NORAD 67672)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37866 (NORAD 69430): leader heldout RMS **47.11 Hz** versus **729.70 Hz**; gain **+682.59 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36616 | 67672 | 1 | 1 | 33.30 | 47.11 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-37866 | 69430 | 2 | 2 | 262.14 | 729.70 | +228.84 | +682.59 | +93.54 | +5 |
| STARLINK-30842 | 58357 | 3 | 3 | 1534.26 | 5677.31 | +1500.96 | +5630.19 | +99.17 | -4 |
| STARLINK-33914 | 63774 | 4 | 5 | 2420.50 | 8312.10 | +2387.20 | +8264.99 | +99.43 | -4 |
| STARLINK-34786 | 65391 | 5 | 4 | 2520.45 | 7801.21 | +2487.15 | +7754.10 | +99.40 | +5 |

## CH2 lower, 194.93–214.99 s

Track `sha256:8cfc86d991abcf490daacff9eacf7822bc7f06e5d11ac23fc9eee1dc3f1724cf`; 21 observations; 581 nominal-time satellites scored. Training leader: **STARLINK-36950 (NORAD 67992)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30524 (NORAD 57965): leader heldout RMS **153.06 Hz** versus **295.69 Hz**; gain **+142.62 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36950 | 67992 | 1 | 1 | 54.05 | 153.06 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-30524 | 57965 | 2 | 2 | 65.02 | 295.69 | +10.97 | +142.62 | +48.24 | -1 |
| STARLINK-34394 | 64669 | 3 | — | 373.50 | 4039.84 | +319.45 | +3886.78 | +96.21 | +1 |
| STARLINK-35421 | 66062 | 4 | 5 | 378.25 | 1945.86 | +324.20 | +1792.80 | +92.13 | +5 |
| STARLINK-34786 | 65391 | 5 | — | 402.76 | 4574.58 | +348.71 | +4421.52 | +96.65 | +4 |
| STARLINK-34775 | 64934 | — | 3 | 830.39 | 1186.03 | +776.34 | +1032.97 | +87.09 | -5 |
| STARLINK-2107 | 47723 | — | 4 | 1627.19 | 1515.59 | +1573.14 | +1362.53 | +89.90 | +5 |

## CH4 lower, 200.98–224.18 s

Track `sha256:c6fe60ff7f177c49c37e45a427e0f6fd2913ef9837cd4585ba979a35f79678e5`; 24 observations; 588 nominal-time satellites scored. Training leader: **STARLINK-34638 (NORAD 64762)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37776 (NORAD 69343): leader heldout RMS **85.15 Hz** versus **2706.73 Hz**; gain **+2621.58 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34638 | 64762 | 1 | 1 | 34.25 | 85.15 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-37776 | 69343 | 2 | 2 | 270.92 | 2706.73 | +236.67 | +2621.58 | +96.85 | +0 |
| STARLINK-2063 | 48553 | 3 | 3 | 550.66 | 3005.05 | +516.41 | +2919.90 | +97.17 | -1 |
| STARLINK-37208 | 68523 | 4 | 5 | 744.95 | 3495.67 | +710.70 | +3410.51 | +97.56 | +4 |
| STARLINK-5945 | 56018 | 5 | — | 830.10 | 5063.52 | +795.85 | +4978.37 | +98.32 | -5 |
| STARLINK-30524 | 57965 | — | 4 | 1378.79 | 3461.97 | +1344.54 | +3376.82 | +97.54 | +5 |

## CH2 lower, 218.01–251.27 s

Track `sha256:1f6bd4afd862cb7aabb692dd6e5a83d4cd29bcbc6f121a702727033540f464c0`; 34 observations; 595 nominal-time satellites scored. Training leader: **STARLINK-36950 (NORAD 67992)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30524 (NORAD 57965): leader heldout RMS **250.50 Hz** versus **1225.11 Hz**; gain **+974.61 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36950 | 67992 | 1 | 1 | 46.61 | 250.50 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-30524 | 57965 | 2 | 2 | 206.03 | 1225.11 | +159.43 | +974.61 | +79.55 | +4 |
| STARLINK-34638 | 64762 | 3 | 5 | 516.90 | 4157.26 | +470.29 | +3906.76 | +93.97 | +2 |
| STARLINK-32833 | 62873 | 4 | — | 553.55 | 6092.47 | +506.95 | +5841.97 | +95.89 | -1 |
| STARLINK-37208 | 68523 | 5 | 4 | 588.42 | 3797.13 | +541.81 | +3546.63 | +93.40 | -5 |
| STARLINK-5694 | 55481 | — | 3 | 3011.95 | 2428.08 | +2965.34 | +2177.58 | +89.68 | +5 |

## CH2 upper, 223.68–249.89 s

Track `sha256:a5f8dabd177bd7f4d76469d2d0351f498a381bc4405a0e99deede9b38a0202a9`; 27 observations; 590 nominal-time satellites scored. Training leader: **STARLINK-36950 (NORAD 67992)**; heldout rank 2 in the full scored population.

Against the best other heldout candidate, STARLINK-30524 (NORAD 57965): leader heldout RMS **553.95 Hz** versus **364.46 Hz**; gain **-189.49 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36950 | 67992 | 1 | 2 | 102.79 | 553.95 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-30524 | 57965 | 2 | 1 | 149.97 | 364.46 | +47.18 | -189.49 | -51.99 | +2 |
| STARLINK-34638 | 64762 | 3 | 4 | 314.81 | 2109.48 | +212.02 | +1555.53 | +73.74 | -1 |
| STARLINK-32833 | 62873 | 4 | — | 423.52 | 4939.92 | +320.73 | +4385.97 | +88.79 | -5 |
| STARLINK-37208 | 68523 | 5 | — | 771.97 | 3405.51 | +669.19 | +2851.56 | +83.73 | -5 |
| STARLINK-5694 | 55481 | — | 3 | 1684.90 | 1159.21 | +1582.12 | +605.26 | +52.21 | +5 |
| STARLINK-36131 | 67032 | — | 5 | 1964.45 | 3185.95 | +1861.66 | +2632.00 | +82.61 | +5 |

## CH4 lower, 225.18–256.44 s

Track `sha256:d0e1843800e6874b167b3d8a8fbf34fb0563dcfe52955434d297dbd479609b66`; 32 observations; 596 nominal-time satellites scored. Training leader: **STARLINK-32833 (NORAD 62873)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-5694 (NORAD 55481): leader heldout RMS **31.13 Hz** versus **5417.53 Hz**; gain **+5386.40 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32833 | 62873 | 1 | 1 | 14.57 | 31.13 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-30524 | 57965 | 2 | 3 | 844.12 | 6283.39 | +829.56 | +6252.27 | +99.50 | -5 |
| STARLINK-36950 | 67992 | 3 | 4 | 1116.76 | 7222.53 | +1102.19 | +7191.40 | +99.57 | -5 |
| STARLINK-34638 | 64762 | 4 | 5 | 1159.33 | 9671.97 | +1144.77 | +9640.84 | +99.68 | -5 |
| STARLINK-5694 | 55481 | 5 | 2 | 2345.86 | 5417.53 | +2331.30 | +5386.40 | +99.43 | +5 |

## CH4 upper, 227.58–253.79 s

Track `sha256:cd5e392addd77435ab07708f286c6f37be94ec537f860aa1029cf05e7903d909`; 27 observations; 589 nominal-time satellites scored. Training leader: **STARLINK-32833 (NORAD 62873)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-5694 (NORAD 55481): leader heldout RMS **74.52 Hz** versus **4666.76 Hz**; gain **+4592.24 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32833 | 62873 | 1 | 1 | 49.27 | 74.52 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-30524 | 57965 | 2 | 3 | 791.78 | 5174.31 | +742.51 | +5099.80 | +98.56 | -5 |
| STARLINK-36950 | 67992 | 3 | 4 | 1038.79 | 5977.68 | +989.52 | +5903.17 | +98.75 | -5 |
| STARLINK-34638 | 64762 | 4 | 5 | 1091.99 | 7989.07 | +1042.73 | +7914.56 | +99.07 | -5 |
| STARLINK-5694 | 55481 | 5 | 2 | 1945.64 | 4666.76 | +1896.37 | +4592.24 | +98.40 | +5 |

## CH2 lower, 194.93–224.05 s

Track `sha256:a371389a19bc489a4bdd1cf3b6c9c0305f093a1da09ba93b0a86e0d70803e740`; 30 observations; 592 nominal-time satellites scored. Training leader: **STARLINK-34638 (NORAD 64762)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-2063 (NORAD 48553): leader heldout RMS **75.48 Hz** versus **3114.45 Hz**; gain **+3038.96 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34638 | 64762 | 1 | 1 | 48.33 | 75.48 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-2063 | 48553 | 2 | 2 | 343.76 | 3114.45 | +295.43 | +3038.96 | +97.58 | +0 |
| STARLINK-5945 | 56018 | 3 | — | 494.15 | 4849.23 | +445.82 | +4773.75 | +98.44 | -5 |
| STARLINK-37208 | 68523 | 4 | 3 | 555.74 | 3751.64 | +507.41 | +3676.15 | +97.99 | +5 |
| STARLINK-37776 | 69343 | 5 | 4 | 760.03 | 4164.84 | +711.70 | +4089.36 | +98.19 | +5 |
| STARLINK-30524 | 57965 | — | 5 | 1883.25 | 4678.16 | +1834.92 | +4602.68 | +98.39 | +5 |
