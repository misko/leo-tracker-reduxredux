# Candidate RMS comparisons: scan-hop-dc5eb69c6fabf708

Recorded **2026-09-14T18:10:12.734255Z**, RX0, 10 MS/s.

[Recording assessment and plots](scan-hop-dc5eb69c6fabf708.md).

Each track has its own training-selected leader; there is no single satellite assignment for the whole recording. Lower RMS is better. The same observations and chronological split are used for all candidates within a track.

Gain = alternative RMS − training-leader RMS. Positive gain favors the leader; negative heldout gain means the alternative predicts better. Percent gain uses the alternative RMS as denominator; it is not identification confidence. Tau and carrier offset were selected on training data and remain frozen on heldout.

The archived screen retained the top five training candidates and top five heldout candidates, whose union is listed below. Candidate counts describe the full scored population; names/scores outside these retained lists were not archived. A blank rank means outside that top-five list. Catalogue exclusions and control results are in the linked recording assessment and evidence.

## CH4 lower, 44.11–73.83 s

Track `sha256:15b01f8191ca447d8980e00080f7e902a014b95e3d9a648aa49398ca3d1ab865`; 33 observations; 545 nominal-time satellites scored. Training leader: **STARLINK-31662 (NORAD 59584)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-3199 (NORAD 49760): leader heldout RMS **45.75 Hz** versus **329.05 Hz**; gain **+283.31 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31662 | 59584 | 1 | 1 | 37.53 | 45.75 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-3199 | 49760 | 2 | 2 | 42.70 | 329.05 | +5.16 | +283.31 | +86.10 | +4 |
| STARLINK-11082 | 59711 | 3 | 3 | 115.82 | 1286.32 | +78.28 | +1240.58 | +96.44 | +1 |
| STARLINK-35241 | 65515 | 4 | 4 | 153.17 | 1428.58 | +115.64 | +1382.83 | +96.80 | -1 |
| STARLINK-35168 | 65509 | 5 | — | 670.19 | 5992.21 | +632.66 | +5946.47 | +99.24 | -2 |
| STARLINK-30174 | 57609 | — | 5 | 936.98 | 3978.76 | +899.44 | +3933.01 | +98.85 | +5 |

## CH1 lower, 45.25–74.09 s

Track `sha256:7c7bf8c8a254a086342c7221bcc4d43f0682b4f561fc13834989aacbbf57c2ed`; 34 observations; 544 nominal-time satellites scored. Training leader: **STARLINK-31662 (NORAD 59584)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-3199 (NORAD 49760): leader heldout RMS **34.39 Hz** versus **362.46 Hz**; gain **+328.07 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31662 | 59584 | 1 | 1 | 37.89 | 34.39 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-3199 | 49760 | 2 | 2 | 48.28 | 362.46 | +10.39 | +328.07 | +90.51 | +4 |
| STARLINK-11082 | 59711 | 3 | 3 | 124.55 | 1221.15 | +86.66 | +1186.76 | +97.18 | +0 |
| STARLINK-35241 | 65515 | 4 | 4 | 156.01 | 1556.63 | +118.11 | +1522.24 | +97.79 | -1 |
| STARLINK-35168 | 65509 | 5 | — | 624.36 | 5160.92 | +586.47 | +5126.54 | +99.33 | -4 |
| STARLINK-30174 | 57609 | — | 5 | 1020.58 | 3969.51 | +982.68 | +3935.12 | +99.13 | +5 |

## CH1 upper, 45.50–73.58 s

Track `sha256:66e4c98c92da120488bfa90e0449f4dd5b64f8b3ae79067af3f52d8d9b94678c`; 34 observations; 543 nominal-time satellites scored. Training leader: **STARLINK-3199 (NORAD 49760)**; heldout rank 2 in the full scored population.

Against the best other heldout candidate, STARLINK-31662 (NORAD 59584): leader heldout RMS **335.03 Hz** versus **42.17 Hz**; gain **-292.86 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-3199 | 49760 | 1 | 2 | 45.86 | 335.03 | +0.00 | +0.00 | +0.00 | +4 |
| STARLINK-31662 | 59584 | 2 | 1 | 61.90 | 42.17 | +16.04 | -292.86 | -694.50 | +0 |
| STARLINK-11082 | 59711 | 3 | 3 | 129.08 | 1145.17 | +83.22 | +810.15 | +70.74 | +0 |
| STARLINK-35241 | 65515 | 4 | 4 | 155.15 | 1465.85 | +109.29 | +1130.82 | +77.14 | -1 |
| STARLINK-35168 | 65509 | 5 | — | 586.06 | 5460.23 | +540.20 | +5125.20 | +93.86 | -3 |
| STARLINK-30174 | 57609 | — | 5 | 968.25 | 3893.38 | +922.39 | +3558.36 | +91.39 | +5 |

## CH4 upper, 46.76–76.99 s

Track `sha256:84c995cf99f5de39b6b12c350b857a7bad3336e53eac804345d2c73431f0ff6b`; 35 observations; 546 nominal-time satellites scored. Training leader: **STARLINK-31662 (NORAD 59584)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-3199 (NORAD 49760): leader heldout RMS **94.51 Hz** versus **402.60 Hz**; gain **+308.08 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31662 | 59584 | 1 | 1 | 65.74 | 94.51 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-3199 | 49760 | 2 | 2 | 78.97 | 402.60 | +13.24 | +308.08 | +76.52 | +4 |
| STARLINK-11082 | 59711 | 3 | 3 | 169.35 | 1575.59 | +103.61 | +1481.07 | +94.00 | -1 |
| STARLINK-35241 | 65515 | 4 | 4 | 202.71 | 1953.11 | +136.98 | +1858.59 | +95.16 | -2 |
| STARLINK-35168 | 65509 | 5 | — | 664.43 | 6075.62 | +598.69 | +5981.11 | +98.44 | -5 |
| STARLINK-30174 | 57609 | — | 5 | 1152.14 | 4316.57 | +1086.40 | +4222.05 | +97.81 | +5 |

## CH3 lower, 72.45–104.08 s

Track `sha256:bd83d4463be4053f5a52418d5f809ec52f1785abcbd3c40695705ec09f3e061b`; 32 observations; 546 nominal-time satellites scored. Training leader: **STARLINK-37521 (NORAD 69822)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4697 (NORAD 53726): leader heldout RMS **109.43 Hz** versus **4430.36 Hz**; gain **+4320.93 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37521 | 69822 | 1 | 1 | 100.32 | 109.43 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-11082 | 59711 | 2 | 4 | 783.64 | 7782.89 | +683.32 | +7673.46 | +98.59 | -5 |
| STARLINK-35241 | 65515 | 3 | 5 | 815.29 | 7901.54 | +714.97 | +7792.11 | +98.62 | -5 |
| STARLINK-4697 | 53726 | 4 | 2 | 879.66 | 4430.36 | +779.33 | +4320.93 | +97.53 | +5 |
| STARLINK-3199 | 49760 | 5 | — | 1276.38 | 10776.89 | +1176.06 | +10667.46 | +98.98 | -5 |
| STARLINK-30219 | 57507 | — | 3 | 1330.25 | 6791.27 | +1229.92 | +6681.84 | +98.39 | +5 |

## CH3 upper, 74.34–98.79 s

Track `sha256:dace941db67dbc413616c67e5567e58cf3be243234dba80c36d86f6f5db9416d`; 24 observations; 539 nominal-time satellites scored. Training leader: **STARLINK-37521 (NORAD 69822)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4697 (NORAD 53726): leader heldout RMS **114.57 Hz** versus **2913.93 Hz**; gain **+2799.36 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37521 | 69822 | 1 | 1 | 94.09 | 114.57 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-11082 | 59711 | 2 | 4 | 425.76 | 4646.42 | +331.66 | +4531.86 | +97.53 | -4 |
| STARLINK-35241 | 65515 | 3 | 5 | 451.72 | 4689.21 | +357.63 | +4574.64 | +97.56 | -4 |
| STARLINK-4697 | 53726 | 4 | 2 | 591.95 | 2913.93 | +497.85 | +2799.36 | +96.07 | +5 |
| STARLINK-3199 | 49760 | 5 | — | 706.56 | 6455.95 | +612.46 | +6341.39 | +98.23 | -5 |
| STARLINK-30219 | 57507 | — | 3 | 899.51 | 4468.25 | +805.41 | +4353.68 | +97.44 | +5 |

## CH2 upper, 74.71–109.24 s

Track `sha256:1b97f681600b43ac5c896a21255c4783a118b95eba39104683dc1a9ce5dd198c`; 36 observations; 545 nominal-time satellites scored. Training leader: **STARLINK-37521 (NORAD 69822)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4697 (NORAD 53726): leader heldout RMS **90.82 Hz** versus **5327.09 Hz**; gain **+5236.28 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37521 | 69822 | 1 | 1 | 112.64 | 90.82 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-4697 | 53726 | 2 | 2 | 1235.62 | 5327.09 | +1122.99 | +5236.28 | +98.30 | +5 |
| STARLINK-35241 | 65515 | 3 | — | 1456.83 | 11567.35 | +1344.20 | +11476.54 | +99.21 | -5 |
| STARLINK-11082 | 59711 | 4 | — | 1461.40 | 11285.45 | +1348.77 | +11194.63 | +99.20 | -5 |
| STARLINK-30219 | 57507 | 5 | 4 | 1875.82 | 8230.56 | +1763.18 | +8139.75 | +98.90 | +5 |
| STARLINK-11114 | 59757 | — | 3 | 3829.94 | 6708.22 | +3717.30 | +6617.40 | +98.65 | +5 |
| STARLINK-5952 | 56923 | — | 5 | 1976.23 | 9202.09 | +1863.59 | +9111.28 | +99.01 | -2 |

## CH2 lower, 75.22–111.63 s

Track `sha256:91ef3bac9f9e601f4362f91101158c8db73992d373a68da6caa02ce8373ead18`; 36 observations; 546 nominal-time satellites scored. Training leader: **STARLINK-37521 (NORAD 69822)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4697 (NORAD 53726): leader heldout RMS **71.99 Hz** versus **5664.21 Hz**; gain **+5592.22 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37521 | 69822 | 1 | 1 | 71.17 | 71.99 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-4697 | 53726 | 2 | 2 | 1294.33 | 5664.21 | +1223.16 | +5592.22 | +98.73 | +5 |
| STARLINK-35241 | 65515 | 3 | — | 1623.27 | 12797.99 | +1552.10 | +12726.01 | +99.44 | -5 |
| STARLINK-11082 | 59711 | 4 | — | 1625.10 | 12461.99 | +1553.93 | +12390.00 | +99.42 | -5 |
| STARLINK-30219 | 57507 | 5 | 4 | 1959.09 | 8766.87 | +1887.92 | +8694.89 | +99.18 | +5 |
| STARLINK-11114 | 59757 | — | 3 | 3780.77 | 6334.86 | +3709.60 | +6262.87 | +98.86 | +5 |
| STARLINK-5952 | 56923 | — | 5 | 2074.77 | 9845.70 | +2003.60 | +9773.71 | +99.27 | -2 |

## CH4 lower, 110.50–134.08 s

Track `sha256:5b61e95a0a2619426443dee4670466ef05cf43af32616af3b5ebea68c787dd00`; 29 observations; 544 nominal-time satellites scored. Training leader: **STARLINK-37923 (NORAD 69949)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11114 (NORAD 59757): leader heldout RMS **90.86 Hz** versus **333.93 Hz**; gain **+243.07 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37923 | 69949 | 1 | 1 | 51.29 | 90.86 | +0.00 | +0.00 | +0.00 | -4 |
| STARLINK-11114 | 59757 | 2 | 2 | 423.74 | 333.93 | +372.45 | +243.07 | +72.79 | -5 |
| STARLINK-37521 | 69822 | 3 | — | 1403.98 | 8682.85 | +1352.69 | +8591.99 | +98.95 | -5 |
| STARLINK-4697 | 53726 | 4 | — | 1792.48 | 9083.26 | +1741.19 | +8992.40 | +99.00 | -5 |
| STARLINK-11527 | 62523 | 5 | 3 | 1949.42 | 4937.40 | +1898.13 | +4846.54 | +98.16 | +5 |
| STARLINK-35161 | 65936 | — | 4 | 2070.97 | 6553.66 | +2019.68 | +6462.81 | +98.61 | +5 |
| STARLINK-34056 | 63841 | — | 5 | 2868.57 | 7008.36 | +2817.28 | +6917.50 | +98.70 | +5 |

## CH4 upper, 111.88–133.83 s

Track `sha256:dcfcc83c7989c32e6d73ccda4d845188fd8654ae110d01dc5a76cef688919cca`; 26 observations; 543 nominal-time satellites scored. Training leader: **STARLINK-37923 (NORAD 69949)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11114 (NORAD 59757): leader heldout RMS **95.17 Hz** versus **2123.10 Hz**; gain **+2027.93 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37923 | 69949 | 1 | 1 | 49.72 | 95.17 | +0.00 | +0.00 | +0.00 | -4 |
| STARLINK-11114 | 59757 | 2 | 2 | 355.65 | 2123.10 | +305.93 | +2027.93 | +95.52 | +5 |
| STARLINK-37521 | 69822 | 3 | — | 1319.50 | 8667.80 | +1269.78 | +8572.64 | +98.90 | -5 |
| STARLINK-4697 | 53726 | 4 | — | 1646.82 | 8996.52 | +1597.10 | +8901.35 | +98.94 | -5 |
| STARLINK-11527 | 62523 | 5 | 3 | 1660.96 | 4694.78 | +1611.24 | +4599.62 | +97.97 | +5 |
| STARLINK-35161 | 65936 | — | 4 | 1801.37 | 6333.30 | +1751.65 | +6238.14 | +98.50 | +5 |
| STARLINK-34056 | 63841 | — | 5 | 2456.45 | 6643.30 | +2406.74 | +6548.13 | +98.57 | +5 |

## CH1 upper, 120.70–144.66 s

Track `sha256:17efc9516fb8a81414cf0f120f3986d83c1426f4abbb80c49ea6c3e8c125b29e`; 27 observations; 547 nominal-time satellites scored. Training leader: **STARLINK-37923 (NORAD 69949)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11114 (NORAD 59757): leader heldout RMS **230.14 Hz** versus **1641.90 Hz**; gain **+1411.76 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37923 | 69949 | 1 | 1 | 104.71 | 230.14 | +0.00 | +0.00 | +0.00 | -4 |
| STARLINK-11114 | 59757 | 2 | 2 | 241.05 | 1641.90 | +136.34 | +1411.76 | +85.98 | -5 |
| STARLINK-11527 | 62523 | 3 | 3 | 1387.53 | 2882.38 | +1282.82 | +2652.23 | +92.02 | +5 |
| STARLINK-34056 | 63841 | 4 | 4 | 1886.22 | 3533.82 | +1781.51 | +3303.68 | +93.49 | +5 |
| STARLINK-5727 | 55587 | 5 | 5 | 1928.59 | 3868.74 | +1823.88 | +3638.60 | +94.05 | +5 |

## CH2 lower, 122.58–148.57 s

Track `sha256:4f9b9800a845091860133e22caa38cb66ddda2c46ac4749cbdfee4748b864718`; 35 observations; 549 nominal-time satellites scored. Training leader: **STARLINK-37923 (NORAD 69949)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11527 (NORAD 62523): leader heldout RMS **72.93 Hz** versus **2040.07 Hz**; gain **+1967.14 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37923 | 69949 | 1 | 1 | 58.83 | 72.93 | +0.00 | +0.00 | +0.00 | -5 |
| STARLINK-11114 | 59757 | 2 | 4 | 528.19 | 2282.96 | +469.36 | +2210.03 | +96.81 | -5 |
| STARLINK-11527 | 62523 | 3 | 2 | 1434.41 | 2040.07 | +1375.57 | +1967.14 | +96.43 | +5 |
| STARLINK-34056 | 63841 | 4 | 3 | 1861.26 | 2133.52 | +1802.43 | +2060.60 | +96.58 | +5 |
| STARLINK-5727 | 55587 | 5 | 5 | 1962.31 | 2595.62 | +1903.48 | +2522.69 | +97.19 | +5 |

## CH1 lower, 149.32–171.99 s

Track `sha256:c93ac67618263f02aadf933cf7be4b91a4de1b24de70c0354f8d6f4df7a6894a`; 31 observations; 544 nominal-time satellites scored. Training leader: **STARLINK-34056 (NORAD 63841)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-5727 (NORAD 55587): leader heldout RMS **132.38 Hz** versus **302.18 Hz**; gain **+169.79 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34056 | 63841 | 1 | 1 | 22.41 | 132.38 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-5727 | 55587 | 2 | 2 | 57.20 | 302.18 | +34.79 | +169.79 | +56.19 | -5 |
| STARLINK-11527 | 62523 | 3 | 3 | 186.61 | 812.92 | +164.20 | +680.53 | +83.71 | -5 |
| STARLINK-36629 | 67596 | 4 | — | 316.77 | 4218.04 | +294.36 | +4085.65 | +96.86 | +2 |
| STARLINK-35725 | 67565 | 5 | — | 324.24 | 4329.19 | +301.83 | +4196.81 | +96.94 | +5 |
| STARLINK-35156 | 65607 | — | 4 | 1174.81 | 980.98 | +1152.41 | +848.59 | +86.50 | +5 |
| STARLINK-3198 | 49763 | — | 5 | 2004.96 | 1984.13 | +1982.56 | +1851.74 | +93.33 | +5 |

## CH1 upper, 151.59–173.50 s

Track `sha256:63437177101b5d3c69d7666b322409d13155e8e079fa9e76bb692978cf336c85`; 27 observations; 545 nominal-time satellites scored. Training leader: **STARLINK-34056 (NORAD 63841)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-5727 (NORAD 55587): leader heldout RMS **177.03 Hz** versus **431.62 Hz**; gain **+254.59 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34056 | 63841 | 1 | 1 | 59.56 | 177.03 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-5727 | 55587 | 2 | 2 | 75.54 | 431.62 | +15.98 | +254.59 | +58.99 | -5 |
| STARLINK-11527 | 62523 | 3 | 3 | 235.66 | 807.68 | +176.09 | +630.65 | +78.08 | -5 |
| STARLINK-36629 | 67596 | 4 | — | 419.47 | 4191.72 | +359.91 | +4014.70 | +95.78 | -2 |
| STARLINK-35725 | 67565 | 5 | — | 425.84 | 4279.02 | +366.28 | +4102.00 | +95.86 | +1 |
| STARLINK-30328 | 57638 | — | 4 | 1375.04 | 1081.48 | +1315.47 | +904.45 | +83.63 | +5 |
| STARLINK-35156 | 65607 | — | 5 | 851.53 | 1127.30 | +791.97 | +950.27 | +84.30 | +5 |

## CH4 lower, 179.81–203.85 s

Track `sha256:606a989796a32134714989cdd234130145080562a3b3fbb6a88c1d85acedba90`; 25 observations; 536 nominal-time satellites scored. Training leader: **STARLINK-3198 (NORAD 49763)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-35725 (NORAD 67565): leader heldout RMS **252.87 Hz** versus **1107.44 Hz**; gain **+854.57 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-3198 | 49763 | 1 | 1 | 53.50 | 252.87 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-35725 | 67565 | 2 | 2 | 147.61 | 1107.44 | +94.11 | +854.57 | +77.17 | -5 |
| STARLINK-36629 | 67596 | 3 | 4 | 333.56 | 2532.75 | +280.06 | +2279.88 | +90.02 | -5 |
| STARLINK-11523 | 62565 | 4 | 3 | 1423.47 | 2388.42 | +1369.97 | +2135.55 | +89.41 | +5 |
| STARLINK-35156 | 65607 | 5 | — | 1534.43 | 5227.75 | +1480.93 | +4974.88 | +95.16 | -5 |
| STARLINK-31059 | 58596 | — | 5 | 2457.66 | 4917.40 | +2404.16 | +4664.53 | +94.86 | +5 |

## CH4 upper, 180.56–204.98 s

Track `sha256:2b0a59b0fd114d5c778163e776fdf1640b50e9e12cb1880c8b5f48c7d219ff9f`; 25 observations; 537 nominal-time satellites scored. Training leader: **STARLINK-3198 (NORAD 49763)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-35725 (NORAD 67565): leader heldout RMS **55.45 Hz** versus **1266.74 Hz**; gain **+1211.29 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-3198 | 49763 | 1 | 1 | 100.41 | 55.45 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-35725 | 67565 | 2 | 2 | 178.67 | 1266.74 | +78.26 | +1211.29 | +95.62 | -5 |
| STARLINK-36629 | 67596 | 3 | 4 | 442.47 | 2777.78 | +342.07 | +2722.33 | +98.00 | -5 |
| STARLINK-11523 | 62565 | 4 | 3 | 1347.38 | 2101.83 | +1246.98 | +2046.38 | +97.36 | +5 |
| STARLINK-35156 | 65607 | 5 | — | 1606.49 | 5293.88 | +1506.09 | +5238.43 | +98.95 | -5 |
| STARLINK-31059 | 58596 | — | 5 | 2367.46 | 4450.16 | +2267.06 | +4394.71 | +98.75 | +5 |

## CH1 upper, 199.32–225.15 s

Track `sha256:25839802f1f0e1c1b879716cefa3088a805ae698aa8bd1f1788279103d36ae78`; 29 observations; 533 nominal-time satellites scored. Training leader: **STARLINK-32289 (NORAD 60737)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-31059 (NORAD 58596): leader heldout RMS **179.58 Hz** versus **2829.01 Hz**; gain **+2649.43 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32289 | 60737 | 1 | 1 | 90.57 | 179.58 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-31059 | 58596 | 2 | 2 | 320.27 | 2829.01 | +229.70 | +2649.43 | +93.65 | -4 |
| STARLINK-3198 | 49763 | 3 | 5 | 736.86 | 5955.22 | +646.30 | +5775.63 | +96.98 | -4 |
| STARLINK-5950 | 56913 | 4 | 4 | 785.10 | 5526.25 | +694.53 | +5346.66 | +96.75 | -5 |
| STARLINK-37090 | 68193 | 5 | 3 | 844.21 | 5148.04 | +753.64 | +4968.46 | +96.51 | +5 |

## CH1 lower, 199.57–228.30 s

Track `sha256:5d88903fc95ef781da9c65fa631e06ae41b154f42c1b7c8d46d50768a5c40b1d`; 32 observations; 535 nominal-time satellites scored. Training leader: **STARLINK-32289 (NORAD 60737)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-31059 (NORAD 58596): leader heldout RMS **129.48 Hz** versus **4045.61 Hz**; gain **+3916.13 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32289 | 60737 | 1 | 1 | 29.12 | 129.48 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-31059 | 58596 | 2 | 2 | 405.20 | 4045.61 | +376.08 | +3916.13 | +96.80 | -3 |
| STARLINK-3198 | 49763 | 3 | 5 | 822.83 | 7841.71 | +793.71 | +7712.23 | +98.35 | -5 |
| STARLINK-11523 | 62565 | 4 | — | 1040.39 | 9002.05 | +1011.28 | +8872.57 | +98.56 | -1 |
| STARLINK-5950 | 56913 | 5 | 4 | 1043.01 | 7254.16 | +1013.89 | +7124.68 | +98.22 | -5 |
| STARLINK-37090 | 68193 | — | 3 | 1076.22 | 6616.65 | +1047.10 | +6487.17 | +98.04 | +5 |

## CH2 upper, 206.49–229.94 s

Track `sha256:c89a1b587aaaabef588cf7aeeaab3b98fa88fd88e2e638fde0eefc0cb6b0e3eb`; 27 observations; 532 nominal-time satellites scored. Training leader: **STARLINK-32289 (NORAD 60737)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-31059 (NORAD 58596): leader heldout RMS **184.42 Hz** versus **4324.27 Hz**; gain **+4139.86 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32289 | 60737 | 1 | 1 | 34.61 | 184.42 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-31059 | 58596 | 2 | 2 | 871.18 | 4324.27 | +836.58 | +4139.86 | +95.74 | -5 |
| STARLINK-11523 | 62565 | 3 | 5 | 1149.16 | 8094.81 | +1114.55 | +7910.39 | +97.72 | -5 |
| STARLINK-37090 | 68193 | 4 | 3 | 1544.04 | 6182.16 | +1509.43 | +5997.75 | +97.02 | +1 |
| STARLINK-5950 | 56913 | 5 | 4 | 1734.82 | 7678.85 | +1700.22 | +7494.43 | +97.60 | -5 |

## CH3 lower, 233.35–255.76 s

Track `sha256:a346487220bcfbff0a41720264bbe621b9d11638feda9f6522f12119d98f5770`; 26 observations; 539 nominal-time satellites scored. Training leader: **STARLINK-31689 (NORAD 59567)**; heldout rank 2 in the full scored population.

Against the best other heldout candidate, STARLINK-34026 (NORAD 63842): leader heldout RMS **200.26 Hz** versus **78.40 Hz**; gain **-121.86 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31689 | 59567 | 1 | 2 | 24.57 | 200.26 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-34026 | 63842 | 2 | 1 | 42.54 | 78.40 | +17.97 | -121.86 | -155.43 | -1 |
| STARLINK-2491 | 48148 | 3 | 4 | 362.26 | 3310.09 | +337.68 | +3109.83 | +93.95 | -3 |
| STARLINK-37090 | 68193 | 4 | — | 563.52 | 5612.42 | +538.95 | +5412.16 | +96.43 | -5 |
| STARLINK-31059 | 58596 | 5 | — | 957.48 | 7670.30 | +932.91 | +7470.04 | +97.39 | -5 |
| STARLINK-32289 | 60737 | — | 3 | 1238.81 | 2869.74 | +1214.24 | +2669.48 | +93.02 | +5 |
| STARLINK-30915 | 58380 | — | 5 | 1283.04 | 3877.19 | +1258.46 | +3676.93 | +94.83 | -5 |

## CH4 upper, 240.39–283.88 s

Track `sha256:f87a654ba66e6320450648d07bafaf8245eba2f15af84a1bcc55efe6bea378f1`; 47 observations; 561 nominal-time satellites scored. Training leader: **STARLINK-31689 (NORAD 59567)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-34026 (NORAD 63842): leader heldout RMS **220.24 Hz** versus **1416.97 Hz**; gain **+1196.73 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31689 | 59567 | 1 | 1 | 69.74 | 220.24 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-34026 | 63842 | 2 | 2 | 184.38 | 1416.97 | +114.64 | +1196.73 | +84.46 | -2 |
| STARLINK-37887 | 69832 | 3 | 3 | 1801.64 | 2537.12 | +1731.89 | +2316.88 | +91.32 | +5 |
| STARLINK-32289 | 60737 | 4 | — | 2583.79 | 20020.89 | +2514.05 | +19800.65 | +98.90 | -5 |
| STARLINK-30915 | 58380 | 5 | 5 | 2631.65 | 6734.90 | +2561.90 | +6514.66 | +96.73 | -5 |
| STARLINK-4699 | 53716 | — | 4 | 3658.64 | 3779.00 | +3588.90 | +3558.76 | +94.17 | +5 |

## CH3 upper, 243.54–268.63 s

Track `sha256:61d1c9212da983f583e5a90832d07a58d4b0169b03149fe6d7869bf50479ec6a`; 28 observations; 538 nominal-time satellites scored. Training leader: **STARLINK-34026 (NORAD 63842)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-31689 (NORAD 59567): leader heldout RMS **29.49 Hz** versus **527.23 Hz**; gain **+497.74 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34026 | 63842 | 1 | 1 | 88.81 | 29.49 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-31689 | 59567 | 2 | 2 | 94.31 | 527.23 | +5.49 | +497.74 | +94.41 | +1 |
| STARLINK-32289 | 60737 | 3 | — | 627.60 | 7638.93 | +538.79 | +7609.43 | +99.61 | -5 |
| STARLINK-30915 | 58380 | 4 | 4 | 1273.17 | 4046.49 | +1184.36 | +4016.99 | +99.27 | -5 |
| STARLINK-37887 | 69832 | 5 | 3 | 1357.99 | 2536.05 | +1269.17 | +2506.56 | +98.84 | +5 |
| STARLINK-4699 | 53716 | — | 5 | 2368.25 | 5938.17 | +2279.44 | +5908.68 | +99.50 | +5 |

## CH4 lower, 258.41–280.23 s

Track `sha256:b9a429ac0e5b1d93c50c76fae69e0481119fec72a51e156f6bf7965f4836c76e`; 23 observations; 541 nominal-time satellites scored. Training leader: **STARLINK-31689 (NORAD 59567)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-34026 (NORAD 63842): leader heldout RMS **32.07 Hz** versus **647.15 Hz**; gain **+615.08 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31689 | 59567 | 1 | 1 | 35.00 | 32.07 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-34026 | 63842 | 2 | 2 | 98.09 | 647.15 | +63.09 | +615.08 | +95.04 | +5 |
| STARLINK-37887 | 69832 | 3 | 5 | 232.93 | 2453.00 | +197.93 | +2420.92 | +98.69 | +2 |
| STARLINK-30915 | 58380 | 4 | 4 | 317.26 | 1369.47 | +282.25 | +1337.39 | +97.66 | +5 |
| STARLINK-4699 | 53716 | 5 | 3 | 601.65 | 1048.66 | +566.64 | +1016.58 | +96.94 | +5 |

## CH1 lower, 29.36–51.17 s

Track `sha256:66a7e9ff7fe2b82cec1d956350205904bb39073892708a55ac49b43c8c481e06`; 32 observations; 539 nominal-time satellites scored. Training leader: **STARLINK-35168 (NORAD 65509)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30615 (NORAD 58092): leader heldout RMS **66.76 Hz** versus **3778.31 Hz**; gain **+3711.55 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35168 | 65509 | 1 | 1 | 30.40 | 66.76 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-5760 | 55591 | 2 | 3 | 1107.28 | 3867.63 | +1076.89 | +3800.88 | +98.27 | -5 |
| STARLINK-30615 | 58092 | 3 | 2 | 1144.36 | 3778.31 | +1113.97 | +3711.55 | +98.23 | -4 |
| STARLINK-36964 | 68184 | 4 | 4 | 1513.41 | 5613.85 | +1483.01 | +5547.10 | +98.81 | -5 |
| STARLINK-31662 | 59584 | 5 | 5 | 2555.57 | 5682.95 | +2525.18 | +5616.19 | +98.83 | +5 |

## CH1 upper, 29.87–51.42 s

Track `sha256:d3f9ade91d48c40e4578244223ccf96e1c9476fcfb153f916a5c9a026dd717bd`; 31 observations; 540 nominal-time satellites scored. Training leader: **STARLINK-35168 (NORAD 65509)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30615 (NORAD 58092): leader heldout RMS **312.35 Hz** versus **3693.11 Hz**; gain **+3380.76 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35168 | 65509 | 1 | 1 | 64.90 | 312.35 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-5760 | 55591 | 2 | 3 | 1071.22 | 3794.51 | +1006.32 | +3482.16 | +91.77 | -5 |
| STARLINK-30615 | 58092 | 3 | 2 | 1103.80 | 3693.11 | +1038.90 | +3380.76 | +91.54 | -4 |
| STARLINK-36964 | 68184 | 4 | 5 | 1472.77 | 5535.53 | +1407.87 | +5223.18 | +94.36 | -5 |
| STARLINK-31662 | 59584 | 5 | 4 | 2431.37 | 5385.35 | +2366.47 | +5073.00 | +94.20 | +5 |
