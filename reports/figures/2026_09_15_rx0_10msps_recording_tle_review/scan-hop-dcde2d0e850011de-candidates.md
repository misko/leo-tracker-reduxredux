# Candidate RMS comparisons: scan-hop-dcde2d0e850011de

Recorded **2026-09-14T15:50:12.423649Z**, RX0, 10 MS/s.

[Recording assessment and plots](scan-hop-dcde2d0e850011de.md).

Each track has its own training-selected leader; there is no single satellite assignment for the whole recording. Lower RMS is better. The same observations and chronological split are used for all candidates within a track.

Gain = alternative RMS − training-leader RMS. Positive gain favors the leader; negative heldout gain means the alternative predicts better. Percent gain uses the alternative RMS as denominator; it is not identification confidence. Tau and carrier offset were selected on training data and remain frozen on heldout.

The archived screen retained the top five training candidates and top five heldout candidates, whose union is listed below. Candidate counts describe the full scored population; names/scores outside these retained lists were not archived. A blank rank means outside that top-five list. Catalogue exclusions and control results are in the linked recording assessment and evidence.

## CH3 lower, 0.27–36.42 s

Track `sha256:a592ef2edf24677646aa389f0f30f5f2975debe16e03f8243bb00b1e52195607`; 37 observations; 562 nominal-time satellites scored. Training leader: **STARLINK-32888 (NORAD 62966)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-35827 (NORAD 66365): leader heldout RMS **115.03 Hz** versus **1826.32 Hz**; gain **+1711.29 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32888 | 62966 | 1 | 1 | 114.25 | 115.03 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-35827 | 66365 | 2 | 2 | 688.85 | 1826.32 | +574.60 | +1711.29 | +93.70 | -5 |
| STARLINK-37664 | 69044 | 3 | 4 | 853.42 | 6048.33 | +739.16 | +5933.30 | +98.10 | +5 |
| STARLINK-37777 | 69349 | 4 | — | 1121.60 | 7749.82 | +1007.35 | +7634.79 | +98.52 | -5 |
| STARLINK-31920 | 59907 | 5 | — | 1435.94 | 11945.51 | +1321.68 | +11830.48 | +99.04 | +4 |
| STARLINK-34738 | 64951 | — | 3 | 1642.36 | 3386.34 | +1528.10 | +3271.31 | +96.60 | -5 |
| STARLINK-30495 | 57968 | — | 5 | 2061.75 | 7028.38 | +1947.50 | +6913.35 | +98.36 | +5 |

## CH2 lower, 9.21–38.94 s

Track `sha256:0e213c6c494ad76e28f4d71e7110351a82b1452a030497b8d72674218573f3c3`; 31 observations; 556 nominal-time satellites scored. Training leader: **STARLINK-32888 (NORAD 62966)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-34738 (NORAD 64951): leader heldout RMS **174.95 Hz** versus **2647.86 Hz**; gain **+2472.91 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32888 | 62966 | 1 | 1 | 61.37 | 174.95 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-35827 | 66365 | 2 | 3 | 319.74 | 2984.44 | +258.38 | +2809.49 | +94.14 | -5 |
| STARLINK-34738 | 64951 | 3 | 2 | 661.85 | 2647.86 | +600.48 | +2472.91 | +93.39 | +5 |
| STARLINK-31920 | 59907 | 4 | — | 708.17 | 6765.65 | +646.80 | +6590.70 | +97.41 | -5 |
| STARLINK-37664 | 69044 | 5 | 5 | 1334.62 | 5126.62 | +1273.25 | +4951.67 | +96.59 | +0 |
| STARLINK-38324 | 100455 | — | 4 | 3657.73 | 4392.45 | +3596.36 | +4217.50 | +96.02 | +5 |

## CH3 upper, 9.84–31.76 s

Track `sha256:2ef133c73f6d31e1f092df2edfdab5f724db4b8249395b3a05091f38a9180a39`; 24 observations; 548 nominal-time satellites scored. Training leader: **STARLINK-32888 (NORAD 62966)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-34738 (NORAD 64951): leader heldout RMS **65.55 Hz** versus **798.20 Hz**; gain **+732.65 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32888 | 62966 | 1 | 1 | 19.46 | 65.55 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-35827 | 66365 | 2 | 3 | 129.11 | 1514.88 | +109.66 | +1449.34 | +95.67 | -5 |
| STARLINK-31920 | 59907 | 3 | 5 | 400.94 | 4313.55 | +381.48 | +4248.00 | +98.48 | -3 |
| STARLINK-34738 | 64951 | 4 | 2 | 628.06 | 798.20 | +608.61 | +732.65 | +91.79 | +5 |
| STARLINK-37664 | 69044 | 5 | 4 | 867.49 | 3870.67 | +848.03 | +3805.12 | +98.31 | +2 |

## CH2 upper, 11.73–38.19 s

Track `sha256:55d5382e443e8aefdab4e9ec6071039a74a4325efb0e8a616a5f90cef9838968`; 28 observations; 554 nominal-time satellites scored. Training leader: **STARLINK-32888 (NORAD 62966)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-34738 (NORAD 64951): leader heldout RMS **196.92 Hz** versus **2617.72 Hz**; gain **+2420.80 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32888 | 62966 | 1 | 1 | 97.57 | 196.92 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-34738 | 64951 | 2 | 2 | 414.57 | 2617.72 | +317.00 | +2420.80 | +92.48 | +5 |
| STARLINK-35827 | 66365 | 3 | 3 | 414.64 | 2819.04 | +317.07 | +2622.12 | +93.01 | -5 |
| STARLINK-31920 | 59907 | 4 | — | 735.54 | 6517.73 | +637.97 | +6320.81 | +96.98 | -5 |
| STARLINK-37664 | 69044 | 5 | 5 | 1299.16 | 4488.73 | +1201.58 | +4291.81 | +95.61 | -1 |
| STARLINK-38324 | 100455 | — | 4 | 2996.81 | 3492.80 | +2899.24 | +3295.88 | +94.36 | +5 |

## CH4 lower, 16.65–37.68 s

Track `sha256:b3d8ee67431d6e1313ca72f70d4122e03fe0802064c6750f9a3041ef9c4508e8`; 22 observations; 550 nominal-time satellites scored. Training leader: **STARLINK-32888 (NORAD 62966)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-38324 (NORAD 100455): leader heldout RMS **211.43 Hz** versus **1375.88 Hz**; gain **+1164.45 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32888 | 62966 | 1 | 1 | 90.45 | 211.43 | +0.00 | +0.00 | +0.00 | +1 |
| STARLINK-34738 | 64951 | 2 | 3 | 196.54 | 1474.74 | +106.08 | +1263.31 | +85.66 | +2 |
| STARLINK-35827 | 66365 | 3 | 4 | 549.94 | 2704.60 | +459.49 | +2493.17 | +92.18 | -5 |
| STARLINK-37664 | 69044 | 4 | 5 | 1111.01 | 3107.51 | +1020.55 | +2896.08 | +93.20 | -5 |
| STARLINK-31920 | 59907 | 5 | — | 1197.03 | 6435.53 | +1106.57 | +6224.10 | +96.71 | -5 |
| STARLINK-38324 | 100455 | — | 2 | 1709.33 | 1375.88 | +1618.87 | +1164.45 | +84.63 | +5 |

## CH4 lower, 46.76–78.87 s

Track `sha256:524313aa01f0fb36643eac82c2fdeca0d8f6dde56753978eeed0dbd19272cb3c`; 33 observations; 554 nominal-time satellites scored. Training leader: **STARLINK-37260 (NORAD 68510)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-38324 (NORAD 100455): leader heldout RMS **63.85 Hz** versus **1500.09 Hz**; gain **+1436.24 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37260 | 68510 | 1 | 1 | 18.91 | 63.85 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-3129 | 49453 | 2 | 4 | 1074.48 | 5710.19 | +1055.57 | +5646.34 | +98.88 | -5 |
| STARLINK-31880 | 59661 | 3 | 5 | 1245.95 | 6055.92 | +1227.04 | +5992.07 | +98.95 | -5 |
| STARLINK-1942 | 46794 | 4 | — | 1364.59 | 8498.24 | +1345.69 | +8434.39 | +99.25 | -5 |
| STARLINK-38324 | 100455 | 5 | 2 | 2132.67 | 1500.09 | +2113.77 | +1436.24 | +95.74 | +5 |
| STARLINK-38334 | 100454 | — | 3 | 4028.62 | 5023.73 | +4009.71 | +4959.88 | +98.73 | +5 |

## CH3 lower, 47.01–74.07 s

Track `sha256:f8858f7b6972f1a1039339f1f2e7d6b2499d9822e976d4490deeb091e6326820`; 28 observations; 551 nominal-time satellites scored. Training leader: **STARLINK-37260 (NORAD 68510)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-38324 (NORAD 100455): leader heldout RMS **39.72 Hz** versus **1795.79 Hz**; gain **+1756.07 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37260 | 68510 | 1 | 1 | 23.29 | 39.72 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-3129 | 49453 | 2 | 3 | 773.50 | 4333.86 | +750.21 | +4294.14 | +99.08 | -5 |
| STARLINK-31880 | 59661 | 3 | 4 | 927.70 | 4676.96 | +904.41 | +4637.24 | +99.15 | -5 |
| STARLINK-1942 | 46794 | 4 | 5 | 954.34 | 6164.23 | +931.05 | +6124.51 | +99.36 | -5 |
| STARLINK-38324 | 100455 | 5 | 2 | 2045.66 | 1795.79 | +2022.37 | +1756.07 | +97.79 | +5 |

## CH4 lower, 104.82–131.02 s

Track `sha256:fefc46c61d4925cff21168eb19ad2c26de4814b25016ca1f42e39bd7513007ea`; 31 observations; 553 nominal-time satellites scored. Training leader: **STARLINK-35286 (NORAD 65803)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37935 (NORAD 69562): leader heldout RMS **70.81 Hz** versus **4797.15 Hz**; gain **+4726.34 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35286 | 65803 | 1 | 1 | 47.38 | 70.81 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-37935 | 69562 | 2 | 2 | 952.86 | 4797.15 | +905.48 | +4726.34 | +98.52 | -3 |
| STARLINK-38334 | 100454 | 3 | 5 | 1444.04 | 10437.24 | +1396.66 | +10366.43 | +99.32 | -5 |
| STARLINK-30856 | 58725 | 4 | 4 | 2356.20 | 9899.43 | +2308.82 | +9828.62 | +99.28 | -5 |
| STARLINK-37731 | 69304 | 5 | 3 | 2667.26 | 5287.06 | +2619.88 | +5216.25 | +98.66 | +5 |

## CH2 lower, 104.94–135.18 s

Track `sha256:d4f38bc4266b716c0643d8862039c2ea9e23856f94ad708ef5d9614c67de2e56`; 34 observations; 558 nominal-time satellites scored. Training leader: **STARLINK-35286 (NORAD 65803)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37731 (NORAD 69304): leader heldout RMS **236.09 Hz** versus **4644.14 Hz**; gain **+4408.05 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35286 | 65803 | 1 | 1 | 67.11 | 236.09 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-37935 | 69562 | 2 | 3 | 1191.70 | 5638.11 | +1124.59 | +5402.02 | +95.81 | -4 |
| STARLINK-38334 | 100454 | 3 | — | 2004.67 | 13726.69 | +1937.56 | +13490.60 | +98.28 | -5 |
| STARLINK-30856 | 58725 | 4 | 5 | 2800.26 | 11902.31 | +2733.15 | +11666.22 | +98.02 | -5 |
| STARLINK-37731 | 69304 | 5 | 2 | 2838.26 | 4644.14 | +2771.15 | +4408.05 | +94.92 | +5 |
| STARLINK-11367 | 62097 | — | 4 | 5963.86 | 9103.80 | +5896.75 | +8867.71 | +97.41 | +5 |

## CH2 upper, 105.45–132.66 s

Track `sha256:39c9494b3b709f808d1d9c9fa14898a12d222f1cbf0ee70b5b9d58a2c794c7a8`; 29 observations; 555 nominal-time satellites scored. Training leader: **STARLINK-35286 (NORAD 65803)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37731 (NORAD 69304): leader heldout RMS **83.06 Hz** versus **4365.84 Hz**; gain **+4282.78 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35286 | 65803 | 1 | 1 | 73.97 | 83.06 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-37935 | 69562 | 2 | 3 | 1033.60 | 4680.01 | +959.64 | +4596.95 | +98.23 | -4 |
| STARLINK-38334 | 100454 | 3 | — | 1798.87 | 11170.96 | +1724.90 | +11087.90 | +99.26 | -5 |
| STARLINK-37731 | 69304 | 4 | 2 | 2470.21 | 4365.84 | +2396.25 | +4282.78 | +98.10 | +5 |
| STARLINK-30856 | 58725 | 5 | 5 | 2481.16 | 9951.44 | +2407.19 | +9868.38 | +99.17 | -5 |
| STARLINK-11367 | 62097 | — | 4 | 5241.46 | 8748.03 | +5167.49 | +8664.97 | +99.05 | +5 |

## CH4 upper, 105.83–129.26 s

Track `sha256:d2e174804e35811b780ffbf9298ad664d9e8ce0c3b1555d28654b95d902c8f35`; 25 observations; 551 nominal-time satellites scored. Training leader: **STARLINK-35286 (NORAD 65803)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37935 (NORAD 69562): leader heldout RMS **196.94 Hz** versus **4212.53 Hz**; gain **+4015.59 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35286 | 65803 | 1 | 1 | 53.77 | 196.94 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-37935 | 69562 | 2 | 2 | 1013.01 | 4212.53 | +959.24 | +4015.59 | +95.32 | -4 |
| STARLINK-38334 | 100454 | 3 | 5 | 1712.18 | 9487.61 | +1658.41 | +9290.67 | +97.92 | -5 |
| STARLINK-30856 | 58725 | 4 | 4 | 2438.54 | 8965.01 | +2384.76 | +8768.08 | +97.80 | -5 |
| STARLINK-37731 | 69304 | 5 | 3 | 2485.01 | 4784.19 | +2431.24 | +4587.25 | +95.88 | +5 |

## CH4 lower, 134.68–155.70 s

Track `sha256:98aa34915523e5e7171faa499a2d4d7248671cf7f2c650ee7332101cdc5f9a82`; 22 observations; 558 nominal-time satellites scored. Training leader: **STARLINK-37731 (NORAD 69304)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-35286 (NORAD 65803): leader heldout RMS **128.13 Hz** versus **6961.84 Hz**; gain **+6833.70 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37731 | 69304 | 1 | 1 | 22.29 | 128.13 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-11367 | 62097 | 2 | 4 | 1379.27 | 8634.13 | +1356.98 | +8505.99 | +98.52 | -5 |
| STARLINK-35286 | 65803 | 3 | 2 | 1529.69 | 6961.84 | +1507.40 | +6833.70 | +98.16 | -5 |
| STARLINK-31610 | 59473 | 4 | 3 | 3022.61 | 8601.04 | +3000.33 | +8472.91 | +98.51 | -4 |
| STARLINK-32857 | 62949 | 5 | 5 | 3482.54 | 9648.10 | +3460.25 | +9519.97 | +98.67 | +5 |

## CH3 lower, 143.74–163.90 s

Track `sha256:080c689bed3b50c086bd7c83be81de3b89913d8d15c3684cc32c9aa4aa9c5cec`; 21 observations; 552 nominal-time satellites scored. Training leader: **STARLINK-37731 (NORAD 69304)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32857 (NORAD 62949): leader heldout RMS **222.79 Hz** versus **6610.21 Hz**; gain **+6387.42 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37731 | 69304 | 1 | 1 | 51.98 | 222.79 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-31610 | 59473 | 2 | 3 | 2458.44 | 6642.17 | +2406.46 | +6419.38 | +96.65 | -5 |
| STARLINK-35286 | 65803 | 3 | — | 2518.33 | 9123.07 | +2466.35 | +8900.28 | +97.56 | -5 |
| STARLINK-32857 | 62949 | 4 | 2 | 2683.28 | 6610.21 | +2631.30 | +6387.42 | +96.63 | +0 |
| STARLINK-36491 | 67310 | 5 | 5 | 3147.85 | 7124.11 | +3095.87 | +6901.32 | +96.87 | +5 |
| STARLINK-35734 | 66225 | — | 4 | 3711.02 | 7047.14 | +3659.04 | +6824.35 | +96.84 | +5 |

## CH3 upper, 185.31–209.40 s

Track `sha256:98729d036c3b10cf553f2e058742f44c4b2e4e18ca27223bd795f053d27246f4`; 27 observations; 557 nominal-time satellites scored. Training leader: **STARLINK-35822 (NORAD 66362)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30946 (NORAD 58450): leader heldout RMS **153.12 Hz** versus **493.32 Hz**; gain **+340.20 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35822 | 66362 | 1 | 1 | 92.16 | 153.12 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-11257 | 61201 | 2 | 5 | 367.66 | 4780.68 | +275.50 | +4627.56 | +96.80 | +2 |
| STARLINK-30946 | 58450 | 3 | 2 | 432.66 | 493.32 | +340.50 | +340.20 | +68.96 | -5 |
| STARLINK-3764 | 52280 | 4 | 3 | 479.62 | 2599.20 | +387.46 | +2446.08 | +94.11 | +5 |
| STARLINK-35734 | 66225 | 5 | — | 480.37 | 5961.03 | +388.20 | +5807.91 | +97.43 | +5 |
| STARLINK-38309 | 100381 | — | 4 | 1719.11 | 3982.29 | +1626.95 | +3829.17 | +96.15 | +5 |

## CH1 upper, 186.44–209.27 s

Track `sha256:4fc72b09117f40ce33f8b3e880b90a9b7d64c725adc3f9f802324eb9f63c1c01`; 24 observations; 557 nominal-time satellites scored. Training leader: **STARLINK-35822 (NORAD 66362)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30946 (NORAD 58450): leader heldout RMS **163.33 Hz** versus **461.51 Hz**; gain **+298.18 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35822 | 66362 | 1 | 1 | 68.11 | 163.33 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-11257 | 61201 | 2 | 5 | 348.45 | 3889.89 | +280.34 | +3726.56 | +95.80 | +1 |
| STARLINK-30946 | 58450 | 3 | 2 | 389.32 | 461.51 | +321.21 | +298.18 | +64.61 | -5 |
| STARLINK-35734 | 66225 | 4 | — | 501.98 | 5078.06 | +433.87 | +4914.73 | +96.78 | +3 |
| STARLINK-3764 | 52280 | 5 | 3 | 549.12 | 2485.38 | +481.01 | +2322.05 | +93.43 | +5 |
| STARLINK-38309 | 100381 | — | 4 | 1732.35 | 3612.74 | +1664.24 | +3449.41 | +95.48 | +5 |

## CH3 lower, 187.83–218.60 s

Track `sha256:8ca65be999205a34e8031a720acbf1595358d79a4ce6a185253bc011e51da337`; 34 observations; 571 nominal-time satellites scored. Training leader: **STARLINK-35822 (NORAD 66362)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30946 (NORAD 58450): leader heldout RMS **121.91 Hz** versus **2309.05 Hz**; gain **+2187.14 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35822 | 66362 | 1 | 1 | 85.43 | 121.91 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-30946 | 58450 | 2 | 2 | 292.75 | 2309.05 | +207.33 | +2187.14 | +94.72 | -5 |
| STARLINK-11257 | 61201 | 3 | — | 625.10 | 8036.05 | +539.67 | +7914.14 | +98.48 | -1 |
| STARLINK-35734 | 66225 | 4 | 5 | 659.48 | 7334.89 | +574.05 | +7212.99 | +98.34 | -5 |
| STARLINK-3764 | 52280 | 5 | 4 | 889.52 | 4262.69 | +804.09 | +4140.79 | +97.14 | +5 |
| STARLINK-38309 | 100381 | — | 3 | 1907.64 | 2415.56 | +1822.22 | +2293.65 | +94.95 | +5 |

## CH1 lower, 188.21–219.11 s

Track `sha256:44a1c87859e48d4dcd97033066c14d1af253c04dd2bba961fb51e83fa3725f5b`; 32 observations; 571 nominal-time satellites scored. Training leader: **STARLINK-35822 (NORAD 66362)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-38309 (NORAD 100381): leader heldout RMS **117.38 Hz** versus **1875.63 Hz**; gain **+1758.24 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35822 | 66362 | 1 | 1 | 101.56 | 117.38 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-30946 | 58450 | 2 | 3 | 274.95 | 2511.87 | +173.40 | +2394.48 | +95.33 | -5 |
| STARLINK-11257 | 61201 | 3 | — | 756.96 | 8770.46 | +655.40 | +8653.08 | +98.66 | -1 |
| STARLINK-35734 | 66225 | 4 | 5 | 770.11 | 7871.14 | +668.55 | +7753.75 | +98.51 | -5 |
| STARLINK-3764 | 52280 | 5 | 4 | 1024.58 | 4256.40 | +923.03 | +4139.02 | +97.24 | +5 |
| STARLINK-38309 | 100381 | — | 2 | 1966.10 | 1875.63 | +1864.54 | +1758.24 | +93.74 | +5 |

## CH4 lower, 194.89–221.88 s

Track `sha256:a61fd174ef2b9819e03f4e8f83599fe653f7eed230d619b51a170a5a12b169f8`; 28 observations; 568 nominal-time satellites scored. Training leader: **STARLINK-35822 (NORAD 66362)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-38309 (NORAD 100381): leader heldout RMS **62.77 Hz** versus **1534.66 Hz**; gain **+1471.90 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35822 | 66362 | 1 | 1 | 83.98 | 62.77 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-30946 | 58450 | 2 | 3 | 501.15 | 3425.33 | +417.18 | +3362.57 | +98.17 | -5 |
| STARLINK-11257 | 61201 | 3 | — | 672.63 | 7478.24 | +588.65 | +7415.48 | +99.16 | -5 |
| STARLINK-38309 | 100381 | 4 | 2 | 1020.04 | 1534.66 | +936.07 | +1471.90 | +95.91 | +5 |
| STARLINK-3764 | 52280 | 5 | 4 | 1144.93 | 4213.95 | +1060.95 | +4151.19 | +98.51 | +5 |
| STARLINK-31968 | 59927 | — | 5 | 2565.54 | 5779.87 | +2481.56 | +5717.11 | +98.91 | +5 |

## CH4 upper, 195.77–221.00 s

Track `sha256:04d5c3d170977b5394769e48ebc320e75e5b1e7c6333be7308c312a6fbab1d84`; 26 observations; 566 nominal-time satellites scored. Training leader: **STARLINK-35822 (NORAD 66362)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-38309 (NORAD 100381): leader heldout RMS **86.04 Hz** versus **1409.61 Hz**; gain **+1323.57 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35822 | 66362 | 1 | 1 | 108.56 | 86.04 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-30946 | 58450 | 2 | 3 | 484.43 | 3216.69 | +375.87 | +3130.65 | +97.33 | -5 |
| STARLINK-11257 | 61201 | 3 | — | 622.60 | 6963.36 | +514.04 | +6877.33 | +98.76 | -5 |
| STARLINK-38309 | 100381 | 4 | 2 | 863.03 | 1409.61 | +754.47 | +1323.57 | +93.90 | +5 |
| STARLINK-3764 | 52280 | 5 | 4 | 1071.65 | 3948.61 | +963.09 | +3862.58 | +97.82 | +5 |
| STARLINK-31968 | 59927 | — | 5 | 2351.74 | 5388.78 | +2243.18 | +5302.74 | +98.40 | +5 |

## CH2 lower, 210.15–239.13 s

Track `sha256:813d027aa7ab3e150dc0c21e4e56daa9f0f9e501795b07d88c26b75cbde90010`; 30 observations; 572 nominal-time satellites scored. Training leader: **STARLINK-31968 (NORAD 59927)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37775 (NORAD 69348): leader heldout RMS **44.02 Hz** versus **2066.77 Hz**; gain **+2022.75 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31968 | 59927 | 1 | 1 | 51.78 | 44.02 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-37775 | 69348 | 2 | 2 | 179.01 | 2066.77 | +127.23 | +2022.75 | +97.87 | +3 |
| STARLINK-3764 | 52280 | 3 | 3 | 255.89 | 2254.14 | +204.11 | +2210.13 | +98.05 | -5 |
| STARLINK-34373 | 64944 | 4 | — | 385.72 | 4405.01 | +333.93 | +4360.99 | +99.00 | +5 |
| STARLINK-35822 | 66362 | 5 | — | 746.92 | 4663.01 | +695.14 | +4618.99 | +99.06 | +5 |
| STARLINK-33911 | 63777 | — | 4 | 837.49 | 2755.69 | +785.71 | +2711.67 | +98.40 | +5 |
| STARLINK-34288 | 64673 | — | 5 | 2273.05 | 2785.59 | +2221.26 | +2741.58 | +98.42 | +5 |

## CH2 upper, 233.59–260.84 s

Track `sha256:ff6e62bce4628859cfe776c6a92f7e1a8beb2870f67fd5a1bd424c54be474be2`; 28 observations; 568 nominal-time satellites scored. Training leader: **STARLINK-34288 (NORAD 64673)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37775 (NORAD 69348): leader heldout RMS **69.98 Hz** versus **1150.05 Hz**; gain **+1080.06 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34288 | 64673 | 1 | 1 | 53.26 | 69.98 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-37775 | 69348 | 2 | 2 | 368.35 | 1150.05 | +315.09 | +1080.06 | +93.91 | -5 |
| STARLINK-11489 | 62271 | 3 | 4 | 1008.53 | 3910.06 | +955.27 | +3840.07 | +98.21 | +5 |
| STARLINK-31968 | 59927 | 4 | — | 1109.86 | 7293.61 | +1056.60 | +7223.63 | +99.04 | -5 |
| STARLINK-11257 | 61201 | 5 | — | 1152.25 | 9636.60 | +1099.00 | +9566.61 | +99.27 | +5 |
| STARLINK-38309 | 100381 | — | 3 | 1160.15 | 3849.98 | +1106.89 | +3780.00 | +98.18 | +5 |
| STARLINK-34373 | 64944 | — | 5 | 1400.32 | 4593.41 | +1347.06 | +4523.43 | +98.48 | -5 |

## CH2 lower, 234.09–257.30 s

Track `sha256:e03c20473b4f181746443035a1040d71215ec5e7de17aea2cce86e0c741aa790`; 24 observations; 566 nominal-time satellites scored. Training leader: **STARLINK-34288 (NORAD 64673)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-38309 (NORAD 100381): leader heldout RMS **92.57 Hz** versus **2208.70 Hz**; gain **+2116.13 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34288 | 64673 | 1 | 1 | 53.49 | 92.57 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-37775 | 69348 | 2 | 3 | 339.58 | 3088.61 | +286.08 | +2996.04 | +97.00 | +5 |
| STARLINK-11489 | 62271 | 3 | 4 | 854.37 | 3241.29 | +800.88 | +3148.72 | +97.14 | +5 |
| STARLINK-31968 | 59927 | 4 | — | 867.82 | 5554.71 | +814.33 | +5462.14 | +98.33 | -5 |
| STARLINK-11257 | 61201 | 5 | — | 999.44 | 6559.15 | +945.94 | +6466.59 | +98.59 | +5 |
| STARLINK-38309 | 100381 | — | 2 | 1106.74 | 2208.70 | +1053.24 | +2116.13 | +95.81 | +5 |
| STARLINK-34373 | 64944 | — | 5 | 1227.52 | 3919.19 | +1174.03 | +3826.62 | +97.64 | -5 |

## CH2 lower, 135.18–159.23 s

Track `sha256:6919fee5db7cf5aeabab4ad9af00e29047caa1f2f16ee4b45b39c214730f97f3`; 25 observations; 563 nominal-time satellites scored. Training leader: **STARLINK-37731 (NORAD 69304)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-35286 (NORAD 65803): leader heldout RMS **181.33 Hz** versus **8734.19 Hz**; gain **+8552.86 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37731 | 69304 | 1 | 1 | 29.40 | 181.33 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-35286 | 65803 | 2 | 2 | 2054.70 | 8734.19 | +2025.30 | +8552.86 | +97.92 | -5 |
| STARLINK-11367 | 62097 | 3 | 5 | 2090.01 | 11707.36 | +2060.60 | +11526.02 | +98.45 | -5 |
| STARLINK-31610 | 59473 | 4 | 3 | 3453.46 | 9209.36 | +3424.06 | +9028.03 | +98.03 | -5 |
| STARLINK-32857 | 62949 | 5 | 4 | 3957.91 | 10383.41 | +3928.51 | +10202.08 | +98.25 | +5 |
