# Candidate RMS comparisons: scan-hop-cf54d8096b706750

Recorded **2026-09-14T20:40:12.394928Z**, RX0, 10 MS/s.

[Recording assessment and plots](scan-hop-cf54d8096b706750.md).

Each track has its own training-selected leader; there is no single satellite assignment for the whole recording. Lower RMS is better. The same observations and chronological split are used for all candidates within a track.

Gain = alternative RMS − training-leader RMS. Positive gain favors the leader; negative heldout gain means the alternative predicts better. Percent gain uses the alternative RMS as denominator; it is not identification confidence. Tau and carrier offset were selected on training data and remain frozen on heldout.

The archived screen retained the top five training candidates and top five heldout candidates, whose union is listed below. Candidate counts describe the full scored population; names/scores outside these retained lists were not archived. A blank rank means outside that top-five list. Catalogue exclusions and control results are in the linked recording assessment and evidence.

## CH3 upper, 51.66–89.46 s

Track `sha256:104b31d0e1ae9cd39832435f984e22c00ae1c1acff45ea6e6d14e7472122c7fb`; 42 observations; 485 nominal-time satellites scored. Training leader: **STARLINK-36842 (NORAD 67884)**; heldout rank 2 in the full scored population.

Against the best other heldout candidate, STARLINK-32825 (NORAD 62825): leader heldout RMS **860.16 Hz** versus **211.84 Hz**; gain **-648.32 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36842 | 67884 | 1 | 2 | 94.86 | 860.16 | +0.00 | +0.00 | +0.00 | +4 |
| STARLINK-32825 | 62825 | 2 | 1 | 125.79 | 211.84 | +30.93 | -648.32 | -306.04 | -1 |
| STARLINK-36071 | 66808 | 3 | 4 | 303.06 | 3264.78 | +208.20 | +2404.63 | +73.65 | +5 |
| STARLINK-35213 | 65638 | 4 | 3 | 633.93 | 1329.98 | +539.07 | +469.82 | +35.33 | -5 |
| STARLINK-1893 | 46786 | 5 | — | 1052.36 | 10169.39 | +957.50 | +9309.23 | +91.54 | -5 |
| STARLINK-30966 | 58454 | — | 5 | 1346.09 | 6842.24 | +1251.22 | +5982.09 | +87.43 | +5 |

## CH3 lower, 52.79–89.33 s

Track `sha256:46f1b005b4b5e06e8c2059ff3b06dcf24c0c8c851e736498aa34a8a5001b4a78`; 42 observations; 485 nominal-time satellites scored. Training leader: **STARLINK-36842 (NORAD 67884)**; heldout rank 2 in the full scored population.

Against the best other heldout candidate, STARLINK-32825 (NORAD 62825): leader heldout RMS **814.95 Hz** versus **132.87 Hz**; gain **-682.08 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36842 | 67884 | 1 | 2 | 56.17 | 814.95 | +0.00 | +0.00 | +0.00 | +4 |
| STARLINK-32825 | 62825 | 2 | 1 | 76.86 | 132.87 | +20.69 | -682.08 | -513.36 | -2 |
| STARLINK-36071 | 66808 | 3 | 4 | 271.95 | 3271.45 | +215.78 | +2456.51 | +75.09 | +5 |
| STARLINK-35213 | 65638 | 4 | 3 | 633.75 | 1347.40 | +577.58 | +532.45 | +39.52 | -5 |
| STARLINK-1893 | 46786 | 5 | — | 1000.67 | 10137.88 | +944.49 | +9322.93 | +91.96 | -5 |
| STARLINK-30966 | 58454 | — | 5 | 1295.96 | 6843.01 | +1239.78 | +6028.06 | +88.09 | +5 |

## CH1 lower, 59.60–88.70 s

Track `sha256:7f050f2daeda898e5cea586a47513ec237c0f3aa788bbb180d3a9f6a571dcff6`; 30 observations; 476 nominal-time satellites scored. Training leader: **STARLINK-36842 (NORAD 67884)**; heldout rank 2 in the full scored population.

Against the best other heldout candidate, STARLINK-32825 (NORAD 62825): leader heldout RMS **1282.20 Hz** versus **565.50 Hz**; gain **-716.71 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36842 | 67884 | 1 | 2 | 599.80 | 1282.20 | +0.00 | +0.00 | +0.00 | +5 |
| STARLINK-32825 | 62825 | 2 | 1 | 652.39 | 565.50 | +52.59 | -716.71 | -126.74 | +1 |
| STARLINK-35213 | 65638 | 3 | 3 | 828.77 | 1666.77 | +228.97 | +384.57 | +23.07 | -5 |
| STARLINK-36071 | 66808 | 4 | 4 | 1209.31 | 3208.46 | +609.50 | +1926.25 | +60.04 | +5 |
| STARLINK-11124 | 59952 | 5 | — | 1671.30 | 9195.04 | +1071.50 | +7912.83 | +86.06 | +1 |
| STARLINK-30966 | 58454 | — | 5 | 2102.41 | 5904.71 | +1502.60 | +4622.51 | +78.29 | +5 |

## CH1 upper, 63.38–84.04 s

Track `sha256:5caea69f8ed70e297b9b9dcf5db0cd840c68231ce704e446569820169ad2c6e5`; 22 observations; 468 nominal-time satellites scored. Training leader: **STARLINK-1893 (NORAD 46786)**; heldout rank 4 in the full scored population.

Against the best other heldout candidate, STARLINK-30966 (NORAD 58454): leader heldout RMS **2853.06 Hz** versus **1187.48 Hz**; gain **-1665.58 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-1893 | 46786 | 1 | 4 | 538.85 | 2853.06 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-30949 | 58415 | 2 | 3 | 608.63 | 2640.57 | +69.78 | -212.49 | -8.05 | -5 |
| STARLINK-11124 | 59952 | 3 | — | 655.50 | 4590.90 | +116.65 | +1737.84 | +37.85 | +5 |
| STARLINK-5822 | 57064 | 4 | — | 657.23 | 3989.88 | +118.39 | +1136.82 | +28.49 | -5 |
| STARLINK-30966 | 58454 | 5 | 1 | 681.17 | 1187.48 | +142.32 | -1665.58 | -140.26 | -5 |
| STARLINK-35213 | 65638 | — | 2 | 1410.20 | 2395.09 | +871.35 | -457.98 | -19.12 | +5 |
| STARLINK-36071 | 66808 | — | 5 | 997.61 | 3031.28 | +458.76 | +178.22 | +5.88 | -5 |

## CH4 upper, 90.59–131.43 s

Track `sha256:a5a6641bdd25775dcc2d41f3e85a4a15c375ab46ab80c11e03e19812f8d36d98`; 62 observations; 482 nominal-time satellites scored. Training leader: **STARLINK-5792 (NORAD 56035)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32267 (NORAD 60363): leader heldout RMS **209.74 Hz** versus **1475.18 Hz**; gain **+1265.44 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-5792 | 56035 | 1 | 1 | 68.38 | 209.74 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-32267 | 60363 | 2 | 2 | 363.08 | 1475.18 | +294.71 | +1265.44 | +85.78 | +2 |
| STARLINK-36842 | 67884 | 3 | 4 | 1201.76 | 6972.82 | +1133.39 | +6763.08 | +96.99 | -5 |
| STARLINK-34379 | 64302 | 4 | 5 | 2685.77 | 7057.46 | +2617.39 | +6847.72 | +97.03 | +0 |
| STARLINK-32435 | 61259 | 5 | — | 3352.16 | 9736.16 | +3283.78 | +9526.42 | +97.85 | -5 |
| STARLINK-11620 | 63271 | — | 3 | 7294.87 | 5640.94 | +7226.49 | +5431.20 | +96.28 | +5 |

## CH4 lower, 103.96–129.29 s

Track `sha256:d61295f61e96819d91862a467ee05553ab2c56263a6e15c9608fee4c425c8cb4`; 44 observations; 470 nominal-time satellites scored. Training leader: **STARLINK-5792 (NORAD 56035)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32267 (NORAD 60363): leader heldout RMS **112.49 Hz** versus **283.83 Hz**; gain **+171.34 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-5792 | 56035 | 1 | 1 | 32.36 | 112.49 | +0.00 | +0.00 | +0.00 | +1 |
| STARLINK-32267 | 60363 | 2 | 2 | 227.91 | 283.83 | +195.54 | +171.34 | +60.37 | -2 |
| STARLINK-36842 | 67884 | 3 | — | 1256.39 | 6139.23 | +1224.02 | +6026.74 | +98.17 | -5 |
| STARLINK-34379 | 64302 | 4 | 4 | 1568.75 | 4058.31 | +1536.39 | +3945.82 | +97.23 | -5 |
| STARLINK-32435 | 61259 | 5 | — | 2229.91 | 7003.22 | +2197.55 | +6890.73 | +98.39 | -5 |
| STARLINK-11620 | 63271 | — | 3 | 2451.72 | 2048.95 | +2419.35 | +1936.47 | +94.51 | +5 |
| STARLINK-31297 | 59158 | — | 5 | 2345.22 | 4222.86 | +2312.86 | +4110.37 | +97.34 | +5 |

## CH4 lower, 170.23–208.67 s

Track `sha256:60f22076a9dca330d6e84a7978a228bb20fd1f775f788429ae2b122bf5c21cc3`; 52 observations; 478 nominal-time satellites scored. Training leader: **STARLINK-36098 (NORAD 66816)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30928 (NORAD 58452): leader heldout RMS **30.40 Hz** versus **4440.35 Hz**; gain **+4409.96 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36098 | 66816 | 1 | 1 | 30.27 | 30.40 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-30928 | 58452 | 2 | 2 | 716.64 | 4440.35 | +686.37 | +4409.96 | +99.32 | +5 |
| STARLINK-33869 | 63790 | 3 | 4 | 1056.04 | 8813.87 | +1025.77 | +8783.47 | +99.66 | -5 |
| STARLINK-1913 | 47179 | 4 | — | 1119.92 | 9662.64 | +1089.65 | +9632.24 | +99.69 | -5 |
| STARLINK-4462 | 53781 | 5 | 5 | 1482.72 | 9344.71 | +1452.46 | +9314.31 | +99.67 | -5 |
| STARLINK-3799 | 52382 | — | 3 | 3729.79 | 8354.10 | +3699.53 | +8323.71 | +99.64 | +5 |

## CH1 lower, 177.03–203.49 s

Track `sha256:8330ca852a0cbc51f2c238f18e665f6df088ddea3555c549c0b005ba215e3814`; 31 observations; 469 nominal-time satellites scored. Training leader: **STARLINK-36098 (NORAD 66816)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30928 (NORAD 58452): leader heldout RMS **28.99 Hz** versus **3256.55 Hz**; gain **+3227.56 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36098 | 66816 | 1 | 1 | 34.67 | 28.99 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-30928 | 58452 | 2 | 2 | 704.74 | 3256.55 | +670.07 | +3227.56 | +99.11 | +5 |
| STARLINK-33869 | 63790 | 3 | 4 | 1203.91 | 6568.85 | +1169.24 | +6539.86 | +99.56 | -5 |
| STARLINK-1913 | 47179 | 4 | — | 1298.98 | 7230.06 | +1264.31 | +7201.07 | +99.60 | -5 |
| STARLINK-4462 | 53781 | 5 | 5 | 1483.98 | 6879.17 | +1449.32 | +6850.18 | +99.58 | -5 |
| STARLINK-3799 | 52382 | — | 3 | 2481.75 | 5703.56 | +2447.08 | +5674.57 | +99.49 | +5 |

## CH4 upper, 177.54–206.40 s

Track `sha256:18211266d7f1ed37181d06329e9bbbe7fe7a08039371376269ead572d81ef430`; 39 observations; 472 nominal-time satellites scored. Training leader: **STARLINK-36098 (NORAD 66816)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30928 (NORAD 58452): leader heldout RMS **66.63 Hz** versus **3804.45 Hz**; gain **+3737.82 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36098 | 66816 | 1 | 1 | 81.52 | 66.63 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-30928 | 58452 | 2 | 2 | 785.93 | 3804.45 | +704.41 | +3737.82 | +98.25 | +5 |
| STARLINK-33869 | 63790 | 3 | 4 | 1381.70 | 7826.05 | +1300.18 | +7759.41 | +99.15 | -5 |
| STARLINK-1913 | 47179 | 4 | — | 1497.92 | 8626.90 | +1416.41 | +8560.27 | +99.23 | -5 |
| STARLINK-4462 | 53781 | 5 | — | 1649.29 | 8050.54 | +1567.77 | +7983.91 | +99.17 | -5 |
| STARLINK-3799 | 52382 | — | 3 | 2496.34 | 5868.07 | +2414.82 | +5801.44 | +98.86 | +5 |
| STARLINK-31414 | 59418 | — | 5 | 2593.55 | 8022.18 | +2512.03 | +7955.55 | +99.17 | +5 |

## CH1 upper, 180.43–206.78 s

Track `sha256:e1b0f7c5375efe6db7f98d0c3b3d0d0f4aa8645147b0f8df9131d6159f1c5610`; 27 observations; 470 nominal-time satellites scored. Training leader: **STARLINK-36098 (NORAD 66816)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30928 (NORAD 58452): leader heldout RMS **30.89 Hz** versus **3964.86 Hz**; gain **+3933.97 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36098 | 66816 | 1 | 1 | 76.35 | 30.89 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-30928 | 58452 | 2 | 2 | 731.53 | 3964.86 | +655.18 | +3933.97 | +99.22 | +5 |
| STARLINK-33869 | 63790 | 3 | 5 | 1353.46 | 8275.70 | +1277.11 | +8244.82 | +99.63 | -5 |
| STARLINK-1913 | 47179 | 4 | — | 1477.70 | 9135.35 | +1401.35 | +9104.46 | +99.66 | -5 |
| STARLINK-4462 | 53781 | 5 | — | 1552.04 | 8390.91 | +1475.69 | +8360.03 | +99.63 | -5 |
| STARLINK-3799 | 52382 | — | 3 | 2027.99 | 5417.67 | +1951.63 | +5386.79 | +99.43 | +5 |
| STARLINK-31414 | 59418 | — | 4 | 2201.66 | 7857.38 | +2125.31 | +7826.49 | +99.61 | +5 |

## CH2 lower, 258.58–299.14 s

Track `sha256:c52eea662cd334afe2f655914dc2148d3b952e9db155c3da784fa232915c7dda`; 47 observations; 482 nominal-time satellites scored. Training leader: **STARLINK-35141 (NORAD 65644)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32039 (NORAD 60604): leader heldout RMS **166.14 Hz** versus **4391.58 Hz**; gain **+4225.44 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35141 | 65644 | 1 | 1 | 88.96 | 166.14 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-5845 | 57050 | 2 | 4 | 915.54 | 7356.51 | +826.58 | +7190.37 | +97.74 | +5 |
| STARLINK-31983 | 60602 | 3 | — | 946.64 | 9243.48 | +857.68 | +9077.34 | +98.20 | -5 |
| STARLINK-31317 | 58931 | 4 | — | 1750.24 | 8147.65 | +1661.28 | +7981.51 | +97.96 | +5 |
| STARLINK-33951 | 63803 | 5 | 5 | 1900.88 | 7752.89 | +1811.92 | +7586.76 | +97.86 | +5 |
| STARLINK-32039 | 60604 | — | 2 | 2300.96 | 4391.58 | +2212.00 | +4225.44 | +96.22 | +5 |
| STARLINK-11529 | 62599 | — | 3 | 3559.87 | 6177.81 | +3470.91 | +6011.67 | +97.31 | +5 |

## CH4 lower, 259.59–293.21 s

Track `sha256:a8ce65eed6e189d62f858e78d531542ff81d989fc1049b2fdd82017fcbf291d5`; 40 observations; 477 nominal-time satellites scored. Training leader: **STARLINK-35141 (NORAD 65644)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11529 (NORAD 62599): leader heldout RMS **142.67 Hz** versus **2910.09 Hz**; gain **+2767.42 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35141 | 65644 | 1 | 1 | 53.02 | 142.67 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-5845 | 57050 | 2 | 5 | 691.57 | 5263.57 | +638.55 | +5120.90 | +97.29 | +5 |
| STARLINK-31983 | 60602 | 3 | — | 750.74 | 6022.14 | +697.72 | +5879.48 | +97.63 | -5 |
| STARLINK-11324 | 61879 | 4 | — | 1578.22 | 13134.51 | +1525.20 | +12991.84 | +98.91 | -4 |
| STARLINK-31317 | 58931 | 5 | 4 | 1591.34 | 4691.05 | +1538.32 | +4548.39 | +96.96 | +5 |
| STARLINK-11529 | 62599 | — | 2 | 3246.35 | 2910.09 | +3193.32 | +2767.42 | +95.10 | +5 |
| STARLINK-32039 | 60604 | — | 3 | 2032.43 | 4364.14 | +1979.41 | +4221.47 | +96.73 | +5 |

## CH4 upper, 259.71–288.43 s

Track `sha256:399e9513c591ded0851e5d4044e6c7a39f0bfb0f4289804f90c8536ea4c4104c`; 33 observations; 473 nominal-time satellites scored. Training leader: **STARLINK-35141 (NORAD 65644)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-31317 (NORAD 58931): leader heldout RMS **153.20 Hz** versus **2223.64 Hz**; gain **+2070.44 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35141 | 65644 | 1 | 1 | 93.12 | 153.20 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-5845 | 57050 | 2 | 4 | 387.67 | 3657.60 | +294.55 | +3504.40 | +95.81 | +5 |
| STARLINK-31983 | 60602 | 3 | — | 622.43 | 6042.58 | +529.31 | +5889.38 | +97.46 | +1 |
| STARLINK-11324 | 61879 | 4 | — | 1125.90 | 11148.35 | +1032.78 | +10995.15 | +98.63 | -1 |
| STARLINK-33951 | 63803 | 5 | — | 1253.78 | 5053.94 | +1160.66 | +4900.74 | +96.97 | +5 |
| STARLINK-31317 | 58931 | — | 2 | 1688.99 | 2223.64 | +1595.87 | +2070.44 | +93.11 | +5 |
| STARLINK-11529 | 62599 | — | 3 | 3252.13 | 2633.94 | +3159.01 | +2480.75 | +94.18 | +5 |
| STARLINK-32039 | 60604 | — | 5 | 1772.97 | 4333.45 | +1679.85 | +4180.25 | +96.46 | +5 |

## CH2 upper, 259.96–290.70 s

Track `sha256:7c5f9e490ae79e48bc964f9c4592f56ab9fb1d8e30d46fd55bc146f519d1ec6f`; 34 observations; 474 nominal-time satellites scored. Training leader: **STARLINK-35141 (NORAD 65644)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11529 (NORAD 62599): leader heldout RMS **147.40 Hz** versus **2467.45 Hz**; gain **+2320.06 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35141 | 65644 | 1 | 1 | 71.76 | 147.40 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-5845 | 57050 | 2 | 4 | 431.04 | 4178.59 | +359.27 | +4031.19 | +96.47 | +5 |
| STARLINK-31983 | 60602 | 3 | — | 614.37 | 6611.08 | +542.61 | +6463.68 | +97.77 | +0 |
| STARLINK-11324 | 61879 | 4 | — | 1158.55 | 11937.94 | +1086.78 | +11790.55 | +98.77 | -2 |
| STARLINK-33951 | 63803 | 5 | — | 1284.03 | 5442.49 | +1212.26 | +5295.09 | +97.29 | +5 |
| STARLINK-11529 | 62599 | — | 2 | 3096.00 | 2467.45 | +3024.23 | +2320.06 | +94.03 | +5 |
| STARLINK-31317 | 58931 | — | 3 | 1574.73 | 3007.83 | +1502.96 | +2860.43 | +95.10 | +5 |
| STARLINK-32039 | 60604 | — | 5 | 1768.51 | 4361.03 | +1696.74 | +4213.63 | +96.62 | +5 |

## CH1 lower, 260.72–285.03 s

Track `sha256:a2be9f408a96d4a9fe41f0639209cd1df2a28ecadae75c6bb9b178db934baeef`; 24 observations; 469 nominal-time satellites scored. Training leader: **STARLINK-35141 (NORAD 65644)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-31317 (NORAD 58931): leader heldout RMS **111.63 Hz** versus **1302.84 Hz**; gain **+1191.21 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35141 | 65644 | 1 | 1 | 55.94 | 111.63 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-5845 | 57050 | 2 | 4 | 354.65 | 2769.23 | +298.71 | +2657.60 | +95.97 | +5 |
| STARLINK-31983 | 60602 | 3 | — | 511.63 | 4088.66 | +455.69 | +3977.03 | +97.27 | +0 |
| STARLINK-11324 | 61879 | 4 | — | 942.96 | 7607.40 | +887.02 | +7495.77 | +98.53 | -2 |
| STARLINK-33951 | 63803 | 5 | — | 1099.34 | 4044.45 | +1043.40 | +3932.82 | +97.24 | +5 |
| STARLINK-31317 | 58931 | — | 2 | 1385.45 | 1302.84 | +1329.51 | +1191.21 | +91.43 | +5 |
| STARLINK-11529 | 62599 | — | 3 | 2715.49 | 2273.95 | +2659.55 | +2162.32 | +95.09 | +5 |
| STARLINK-32039 | 60604 | — | 5 | 1523.91 | 3647.60 | +1467.97 | +3535.97 | +96.94 | +5 |
