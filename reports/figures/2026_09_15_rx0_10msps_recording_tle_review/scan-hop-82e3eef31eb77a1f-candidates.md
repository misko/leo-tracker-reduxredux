# Candidate RMS comparisons: scan-hop-82e3eef31eb77a1f

[Ranked RMS plots for every track](scan-hop-82e3eef31eb77a1f-rms.md).

Recorded **2026-09-14T22:20:12.556934Z**, RX0, 10 MS/s.

[Recording assessment and plots](scan-hop-82e3eef31eb77a1f.md).

Each track has its own training-selected leader; there is no single satellite assignment for the whole recording. Lower RMS is better. The same observations and chronological split are used for all candidates within a track.

Gain = alternative RMS − training-leader RMS. Positive gain favors the leader; negative heldout gain means the alternative predicts better. Percent gain uses the alternative RMS as denominator; it is not identification confidence. Tau and carrier offset were selected on training data and remain frozen on heldout.

The archived screen retained the top five training candidates and top five heldout candidates, whose union is listed below. Candidate counts describe the full scored population; names/scores outside these retained lists were not archived. A blank rank means outside that top-five list. Catalogue exclusions and control results are in the linked recording assessment and evidence.

## CH2 lower, 104.96–133.56 s

Track `sha256:914a15bfe4fa5fc7766439f6d46db60e90e1ca66bff8a61a311b593efa30225e`; 40 observations; 492 nominal-time satellites scored. Training leader: **STARLINK-36595 (NORAD 67639)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4383 (NORAD 53473): leader heldout RMS **72.68 Hz** versus **2249.00 Hz**; gain **+2176.32 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36595 | 67639 | 1 | 1 | 20.45 | 72.68 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-4383 | 53473 | 2 | 2 | 180.08 | 2249.00 | +159.63 | +2176.32 | +96.77 | -1 |
| STARLINK-33773 | 63713 | 3 | 3 | 572.74 | 2285.04 | +552.30 | +2212.36 | +96.82 | +5 |
| STARLINK-11536 | 62563 | 4 | — | 586.98 | 7937.41 | +566.54 | +7864.72 | +99.08 | -3 |
| STARLINK-37427 | 69381 | 5 | 5 | 1395.94 | 3039.33 | +1375.49 | +2966.65 | +97.61 | +5 |
| STARLINK-35275 | 65756 | — | 4 | 2066.22 | 2400.21 | +2045.77 | +2327.53 | +96.97 | +5 |

## CH1 lower, 112.64–134.06 s

Track `sha256:55339ea9a41e3b558c90f71aa7b3ae3d42ad72c8be130bc39a93d13d026f8d1e`; 26 observations; 486 nominal-time satellites scored. Training leader: **STARLINK-36595 (NORAD 67639)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-35275 (NORAD 65756): leader heldout RMS **91.06 Hz** versus **842.99 Hz**; gain **+751.93 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36595 | 67639 | 1 | 1 | 73.90 | 91.06 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-4383 | 53473 | 2 | — | 176.87 | 1940.79 | +102.97 | +1849.73 | +95.31 | -5 |
| STARLINK-33773 | 63713 | 3 | — | 558.07 | 1688.66 | +484.17 | +1597.61 | +94.61 | +4 |
| STARLINK-35275 | 65756 | 4 | 2 | 814.98 | 842.99 | +741.08 | +751.93 | +89.20 | +5 |
| STARLINK-37427 | 69381 | 5 | 5 | 840.21 | 1542.34 | +766.31 | +1451.28 | +94.10 | +5 |
| STARLINK-11290 | 61000 | — | 3 | 1142.89 | 1018.67 | +1068.99 | +927.61 | +91.06 | +5 |
| STARLINK-1446 | 45663 | — | 4 | 1112.14 | 1467.54 | +1038.24 | +1376.48 | +93.80 | +5 |

## CH3 upper, 129.65–153.45 s

Track `sha256:9db5a80a79a2eb672b48fadadd254f68fa47ebd27a83cfe4dd5dcf78b1a8dbf0`; 25 observations; 493 nominal-time satellites scored. Training leader: **STARLINK-31423 (NORAD 59242)**; heldout rank 2 in the full scored population.

Against the best other heldout candidate, STARLINK-30811 (NORAD 58167): leader heldout RMS **135.69 Hz** versus **53.30 Hz**; gain **-82.39 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31423 | 59242 | 1 | 2 | 55.41 | 135.69 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-30811 | 58167 | 2 | 1 | 71.52 | 53.30 | +16.11 | -82.39 | -154.57 | +1 |
| STARLINK-3515 | 51738 | 3 | 5 | 248.53 | 2342.53 | +193.12 | +2206.84 | +94.21 | -3 |
| STARLINK-30144 | 56835 | 4 | — | 343.43 | 3208.87 | +288.02 | +3073.18 | +95.77 | -5 |
| STARLINK-36937 | 68113 | 5 | — | 364.08 | 2969.44 | +308.67 | +2833.75 | +95.43 | +0 |
| STARLINK-4383 | 53473 | — | 3 | 1788.12 | 1114.82 | +1732.71 | +979.13 | +87.83 | +5 |
| STARLINK-37427 | 69381 | — | 4 | 854.57 | 1668.36 | +799.16 | +1532.67 | +91.87 | +5 |

## CH2 lower, 134.44–171.87 s

Track `sha256:ecacf582eeb26bbffc30261a4b35d57b05975df7903e8eb5b92abac5dadd79f3`; 37 observations; 501 nominal-time satellites scored. Training leader: **STARLINK-31423 (NORAD 59242)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30811 (NORAD 58167): leader heldout RMS **247.71 Hz** versus **723.90 Hz**; gain **+476.20 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31423 | 59242 | 1 | 1 | 170.13 | 247.71 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-30811 | 58167 | 2 | 2 | 214.04 | 723.90 | +43.91 | +476.20 | +65.78 | +2 |
| STARLINK-37427 | 69381 | 3 | — | 803.19 | 5908.86 | +633.06 | +5661.15 | +95.81 | -5 |
| STARLINK-4383 | 53473 | 4 | — | 1248.69 | 8493.64 | +1078.56 | +8245.93 | +97.08 | +1 |
| STARLINK-34519 | 64608 | 5 | — | 1322.41 | 2879.45 | +1152.28 | +2631.74 | +91.40 | +5 |
| STARLINK-11290 | 61000 | — | 3 | 1992.62 | 1343.02 | +1822.49 | +1095.31 | +81.56 | +5 |
| STARLINK-30764 | 58170 | — | 4 | 2002.65 | 1357.69 | +1832.52 | +1109.98 | +81.76 | +5 |
| STARLINK-35275 | 65756 | — | 5 | 2846.05 | 1626.92 | +2675.92 | +1379.21 | +84.77 | +5 |

## CH1 lower, 211.68–238.42 s

Track `sha256:7f4609f13d00e71f8da7da04c4c677c0de6f60c2993ce81f32b132d3771ecb71`; 27 observations; 487 nominal-time satellites scored. Training leader: **STARLINK-36438 (NORAD 67625)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-36355 (NORAD 68298): leader heldout RMS **102.01 Hz** versus **1509.37 Hz**; gain **+1407.36 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36438 | 67625 | 1 | 1 | 146.03 | 102.01 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-30947 | 58473 | 2 | 3 | 203.48 | 1971.53 | +57.46 | +1869.51 | +94.83 | +5 |
| STARLINK-36355 | 68298 | 3 | 2 | 362.09 | 1509.37 | +216.07 | +1407.36 | +93.24 | +5 |
| STARLINK-33776 | 63851 | 4 | 5 | 481.79 | 4797.30 | +335.76 | +4695.29 | +97.87 | +0 |
| STARLINK-32549 | 62118 | 5 | — | 571.79 | 6149.11 | +425.76 | +6047.10 | +98.34 | -3 |
| STARLINK-32875 | 62951 | — | 4 | 1015.25 | 3624.70 | +869.23 | +3522.69 | +97.19 | +5 |

## CH2 lower, 223.04–251.76 s

Track `sha256:30b327584e6aa6e25ae56b3f3e4144bb069e345d3236844dd6f4d07cd30b284e`; 35 observations; 488 nominal-time satellites scored. Training leader: **STARLINK-36438 (NORAD 67625)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11669 (NORAD 63548): leader heldout RMS **41.60 Hz** versus **2249.74 Hz**; gain **+2208.13 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36438 | 67625 | 1 | 1 | 32.01 | 41.60 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-36355 | 68298 | 2 | 5 | 433.80 | 4161.49 | +401.78 | +4119.89 | +99.00 | +0 |
| STARLINK-11669 | 63548 | 3 | 2 | 959.00 | 2249.74 | +926.98 | +2208.13 | +98.15 | +5 |
| STARLINK-30947 | 58473 | 4 | 4 | 1099.17 | 3993.55 | +1067.16 | +3951.94 | +98.96 | +3 |
| STARLINK-32875 | 62951 | 5 | 3 | 1318.00 | 3520.15 | +1285.98 | +3478.54 | +98.82 | +5 |

## CH2 upper, 224.43–251.89 s

Track `sha256:6ed9072d5e58bfeabd63631756e56baa05d9dbbe74cc3ae9b71728cc820c65be`; 34 observations; 488 nominal-time satellites scored. Training leader: **STARLINK-36438 (NORAD 67625)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11669 (NORAD 63548): leader heldout RMS **50.93 Hz** versus **2386.63 Hz**; gain **+2335.70 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36438 | 67625 | 1 | 1 | 24.77 | 50.93 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-36355 | 68298 | 2 | 5 | 375.15 | 3859.82 | +350.37 | +3808.89 | +98.68 | -1 |
| STARLINK-11669 | 63548 | 3 | 2 | 834.63 | 2386.63 | +809.86 | +2335.70 | +97.87 | +5 |
| STARLINK-30947 | 58473 | 4 | 4 | 1067.13 | 3793.23 | +1042.36 | +3742.30 | +98.66 | +2 |
| STARLINK-32875 | 62951 | 5 | 3 | 1257.08 | 3464.75 | +1232.31 | +3413.82 | +98.53 | +5 |

## CH4 lower, 224.80–251.39 s

Track `sha256:67b37f8a174f141d7d14c977701059a3f4f550917e6d3f621d7222d6409af90e`; 32 observations; 487 nominal-time satellites scored. Training leader: **STARLINK-36438 (NORAD 67625)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11669 (NORAD 63548): leader heldout RMS **41.15 Hz** versus **2198.27 Hz**; gain **+2157.12 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36438 | 67625 | 1 | 1 | 39.08 | 41.15 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-36355 | 68298 | 2 | 4 | 351.19 | 3616.10 | +312.11 | +3574.95 | +98.86 | -1 |
| STARLINK-11669 | 63548 | 3 | 2 | 787.80 | 2198.27 | +748.73 | +2157.12 | +98.13 | +5 |
| STARLINK-30947 | 58473 | 4 | 5 | 999.83 | 3630.39 | +960.76 | +3589.24 | +98.87 | +2 |
| STARLINK-32875 | 62951 | 5 | 3 | 1183.57 | 3340.11 | +1144.50 | +3298.96 | +98.77 | +5 |

## CH2 lower, 271.29–296.59 s

Track `sha256:36d0e796659cdf2c9575ba09cc4670872deacfcf9152ac6e22650b14b4d8d1d6`; 28 observations; 481 nominal-time satellites scored. Training leader: **STARLINK-30798 (NORAD 58196)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-5387 (NORAD 54842): leader heldout RMS **227.49 Hz** versus **869.96 Hz**; gain **+642.47 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30798 | 58196 | 1 | 1 | 47.21 | 227.49 | +0.00 | +0.00 | +0.00 | -4 |
| STARLINK-33624 | 63071 | 2 | 4 | 171.49 | 1717.36 | +124.28 | +1489.88 | +86.75 | +5 |
| STARLINK-11669 | 63548 | 3 | — | 233.88 | 2242.06 | +186.66 | +2014.57 | +89.85 | +1 |
| STARLINK-36355 | 68298 | 4 | — | 235.55 | 2265.03 | +188.34 | +2037.54 | +89.96 | -5 |
| STARLINK-5387 | 54842 | 5 | 2 | 1125.04 | 869.96 | +1077.82 | +642.47 | +73.85 | +5 |
| STARLINK-33622 | 63066 | — | 3 | 1506.09 | 1186.31 | +1458.87 | +958.82 | +80.82 | +5 |
| STARLINK-11502 | 62474 | — | 5 | 2121.12 | 1894.46 | +2073.90 | +1666.97 | +87.99 | +5 |
