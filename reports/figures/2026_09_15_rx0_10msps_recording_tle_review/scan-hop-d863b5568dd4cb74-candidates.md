# Candidate RMS comparisons: scan-hop-d863b5568dd4cb74

[Ranked RMS plots for every track](scan-hop-d863b5568dd4cb74-rms.md).

Recorded **2026-09-14T17:50:12.620976Z**, RX0, 10 MS/s.

[Recording assessment and plots](scan-hop-d863b5568dd4cb74.md).

Each track has its own training-selected leader; there is no single satellite assignment for the whole recording. Lower RMS is better. The same observations and chronological split are used for all candidates within a track.

Gain = alternative RMS − training-leader RMS. Positive gain favors the leader; negative heldout gain means the alternative predicts better. Percent gain uses the alternative RMS as denominator; it is not identification confidence. Tau and carrier offset were selected on training data and remain frozen on heldout.

The archived screen retained the top five training candidates and top five heldout candidates, whose union is listed below. Candidate counts describe the full scored population; names/scores outside these retained lists were not archived. A blank rank means outside that top-five list. Catalogue exclusions and control results are in the linked recording assessment and evidence.

## CH4 lower, 14.53–36.72 s

Track `sha256:d0c056706a7faa5f3c63d7dc77f4b2524dae644a6cd03115e62b5fad2948d88d`; 23 observations; 540 nominal-time satellites scored. Training leader: **STARLINK-36565 (NORAD 67544)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-3069 (NORAD 49176): leader heldout RMS **362.30 Hz** versus **1072.19 Hz**; gain **+709.89 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36565 | 67544 | 1 | 1 | 38.78 | 362.30 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-3069 | 49176 | 2 | 2 | 514.99 | 1072.19 | +476.22 | +709.89 | +66.21 | +5 |
| STARLINK-11098 | 59760 | 3 | — | 608.46 | 5820.58 | +569.68 | +5458.28 | +93.78 | +0 |
| STARLINK-11692 | 64381 | 4 | 3 | 651.21 | 2422.16 | +612.43 | +2059.86 | +85.04 | -3 |
| STARLINK-2443 | 48107 | 5 | 4 | 1191.16 | 4193.91 | +1152.38 | +3831.60 | +91.36 | +0 |
| STARLINK-30266 | 57529 | — | 5 | 2161.51 | 5624.20 | +2122.73 | +5261.90 | +93.56 | +5 |

## CH1 upper, 34.83–64.83 s

Track `sha256:9b781ad54f2ddf63c8e0c142509f9e014d9f150b6797e7bb4da8b8ca3df9c5e9`; 30 observations; 545 nominal-time satellites scored. Training leader: **STARLINK-37371 (NORAD 68977)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4674 (NORAD 53591): leader heldout RMS **89.92 Hz** versus **286.21 Hz**; gain **+196.28 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37371 | 68977 | 1 | 1 | 91.56 | 89.92 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-4674 | 53591 | 2 | 2 | 143.52 | 286.21 | +51.96 | +196.28 | +68.58 | -5 |
| STARLINK-30266 | 57529 | 3 | 4 | 836.97 | 7434.59 | +745.41 | +7344.67 | +98.79 | +5 |
| STARLINK-2443 | 48107 | 4 | — | 944.78 | 9074.27 | +853.21 | +8984.35 | +99.01 | -5 |
| STARLINK-5801 | 56005 | 5 | 3 | 1011.09 | 5893.72 | +919.53 | +5803.79 | +98.47 | +5 |
| STARLINK-34186 | 64145 | — | 5 | 2214.24 | 8556.35 | +2122.68 | +8466.43 | +98.95 | +5 |

## CH1 lower, 36.34–70.12 s

Track `sha256:7d542322c7db9c84f04246ee7ddf5786f1deeceef29ca82450afcfd01410d0fc`; 35 observations; 545 nominal-time satellites scored. Training leader: **STARLINK-37371 (NORAD 68977)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4674 (NORAD 53591): leader heldout RMS **148.93 Hz** versus **638.51 Hz**; gain **+489.58 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37371 | 68977 | 1 | 1 | 70.82 | 148.93 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-4674 | 53591 | 2 | 2 | 102.67 | 638.51 | +31.85 | +489.58 | +76.68 | -5 |
| STARLINK-30266 | 57529 | 3 | 3 | 927.06 | 7002.71 | +856.24 | +6853.79 | +97.87 | -4 |
| STARLINK-36565 | 67544 | 4 | — | 1406.61 | 11298.83 | +1335.79 | +11149.90 | +98.68 | -4 |
| STARLINK-3069 | 49176 | 5 | — | 1559.66 | 13449.33 | +1488.84 | +13300.41 | +98.89 | -5 |
| STARLINK-5801 | 56005 | — | 4 | 1594.22 | 8333.15 | +1523.40 | +8184.22 | +98.21 | +5 |
| STARLINK-34186 | 64145 | — | 5 | 2802.80 | 10627.14 | +2731.97 | +10478.21 | +98.60 | +5 |

## CH2 lower, 49.59–71.25 s

Track `sha256:f875f43bcef72858d123793afe9bd97277161d61aadfe09879f010232d384723`; 22 observations; 537 nominal-time satellites scored. Training leader: **STARLINK-37371 (NORAD 68977)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4674 (NORAD 53591): leader heldout RMS **137.60 Hz** versus **733.79 Hz**; gain **+596.19 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37371 | 68977 | 1 | 1 | 36.69 | 137.60 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-4674 | 53591 | 2 | 2 | 156.90 | 733.79 | +120.21 | +596.19 | +81.25 | -5 |
| STARLINK-30266 | 57529 | 3 | — | 1704.70 | 7616.43 | +1668.01 | +7478.83 | +98.19 | -5 |
| STARLINK-5801 | 56005 | 4 | 3 | 1933.25 | 6465.01 | +1896.56 | +6327.41 | +97.87 | +2 |
| STARLINK-34186 | 64145 | 5 | — | 2424.84 | 7490.36 | +2388.15 | +7352.76 | +98.16 | +5 |
| STARLINK-11685 | 63552 | — | 4 | 2478.00 | 6521.02 | +2441.31 | +6383.42 | +97.89 | +5 |
| STARLINK-37035 | 68180 | — | 5 | 3266.40 | 6863.13 | +3229.71 | +6725.53 | +98.00 | +5 |

## CH2 upper, 50.22–71.00 s

Track `sha256:29f3643f44b63233d86cf65672a84fa224c4fc86c3875d3b169c3b004e1cb88d`; 21 observations; 537 nominal-time satellites scored. Training leader: **STARLINK-37371 (NORAD 68977)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4674 (NORAD 53591): leader heldout RMS **169.13 Hz** versus **699.83 Hz**; gain **+530.71 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37371 | 68977 | 1 | 1 | 92.34 | 169.13 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-4674 | 53591 | 2 | 2 | 173.08 | 699.83 | +80.74 | +530.71 | +75.83 | -5 |
| STARLINK-30266 | 57529 | 3 | — | 1621.01 | 7363.72 | +1528.67 | +7194.60 | +97.70 | -5 |
| STARLINK-5801 | 56005 | 4 | 3 | 1816.51 | 6231.93 | +1724.17 | +6062.81 | +97.29 | +2 |
| STARLINK-34186 | 64145 | 5 | — | 2270.93 | 7209.54 | +2178.59 | +7040.41 | +97.65 | +5 |
| STARLINK-11685 | 63552 | — | 4 | 2309.29 | 6266.47 | +2216.95 | +6097.34 | +97.30 | +5 |
| STARLINK-37035 | 68180 | — | 5 | 3025.46 | 6573.03 | +2933.12 | +6403.90 | +97.43 | +5 |

## CH1 upper, 74.93–106.55 s

Track `sha256:81583bf13c73268fc64f29c9bf21e5fb90e84b6327af8a61fc778149b52d3a0c`; 33 observations; 554 nominal-time satellites scored. Training leader: **STARLINK-37035 (NORAD 68180)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4427 (NORAD 53210): leader heldout RMS **79.95 Hz** versus **3426.48 Hz**; gain **+3346.53 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37035 | 68180 | 1 | 1 | 33.53 | 79.95 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-31181 | 58746 | 2 | 4 | 1302.72 | 6665.84 | +1269.19 | +6585.88 | +98.80 | +5 |
| STARLINK-34996 | 65223 | 3 | 3 | 1408.19 | 6286.50 | +1374.66 | +6206.54 | +98.73 | +5 |
| STARLINK-4674 | 53591 | 4 | — | 2050.90 | 13657.71 | +2017.37 | +13577.75 | +99.41 | -5 |
| STARLINK-37371 | 68977 | 5 | — | 2098.02 | 13558.67 | +2064.49 | +13478.72 | +99.41 | -5 |
| STARLINK-4427 | 53210 | — | 2 | 2873.10 | 3426.48 | +2839.57 | +3346.53 | +97.67 | +5 |
| STARLINK-5732 | 55572 | — | 5 | 2298.38 | 8209.18 | +2264.85 | +8129.22 | +99.03 | +5 |

## CH1 lower, 75.18–107.68 s

Track `sha256:34cce860f1feba78bbf9912f8c491ae605e6197300be2a2b6f7b0ec7ead582ec`; 34 observations; 556 nominal-time satellites scored. Training leader: **STARLINK-37035 (NORAD 68180)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4427 (NORAD 53210): leader heldout RMS **123.98 Hz** versus **2929.76 Hz**; gain **+2805.78 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37035 | 68180 | 1 | 1 | 82.56 | 123.98 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-31181 | 58746 | 2 | 4 | 1479.99 | 6714.49 | +1397.43 | +6590.51 | +98.15 | +4 |
| STARLINK-34996 | 65223 | 3 | 3 | 1574.29 | 6532.39 | +1491.73 | +6408.41 | +98.10 | +5 |
| STARLINK-4674 | 53591 | 4 | — | 2444.84 | 14567.62 | +2362.28 | +14443.64 | +99.15 | -5 |
| STARLINK-37371 | 68977 | 5 | — | 2486.70 | 14440.88 | +2404.14 | +14316.90 | +99.14 | -5 |
| STARLINK-4427 | 53210 | — | 2 | 2901.91 | 2929.76 | +2819.34 | +2805.78 | +95.77 | +5 |
| STARLINK-5732 | 55572 | — | 5 | 2488.76 | 8405.86 | +2406.20 | +8281.89 | +98.53 | +5 |

## CH4 upper, 128.09–149.78 s

Track `sha256:92a0bf28d16a3a1b37b7e9c14e7a58b3e725e858ff5dd5ee035bfa4722c49889`; 22 observations; 531 nominal-time satellites scored. Training leader: **STARLINK-31520 (NORAD 59210)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-31499 (NORAD 59217): leader heldout RMS **70.06 Hz** versus **1346.67 Hz**; gain **+1276.61 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31520 | 59210 | 1 | 1 | 19.14 | 70.06 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-4427 | 53210 | 2 | 3 | 212.09 | 2466.41 | +192.95 | +2396.34 | +97.16 | -1 |
| STARLINK-31499 | 59217 | 3 | 2 | 243.66 | 1346.67 | +224.52 | +1276.61 | +94.80 | -5 |
| STARLINK-6110 | 56907 | 4 | 5 | 1069.47 | 4521.30 | +1050.33 | +4451.24 | +98.45 | -5 |
| STARLINK-2418 | 48097 | 5 | 4 | 1685.60 | 2605.20 | +1666.46 | +2535.13 | +97.31 | +5 |

## CH4 lower, 128.35–148.39 s

Track `sha256:03d560572dfe234a92e2f6c8fccb0fd189ef5b02b25622021b15b2c8aab30cf1`; 24 observations; 530 nominal-time satellites scored. Training leader: **STARLINK-31520 (NORAD 59210)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-31499 (NORAD 59217): leader heldout RMS **48.77 Hz** versus **1235.14 Hz**; gain **+1186.37 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31520 | 59210 | 1 | 1 | 37.39 | 48.77 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-4427 | 53210 | 2 | 3 | 227.25 | 1725.57 | +189.86 | +1676.79 | +97.17 | -2 |
| STARLINK-31499 | 59217 | 3 | 2 | 242.77 | 1235.14 | +205.38 | +1186.37 | +96.05 | -5 |
| STARLINK-6110 | 56907 | 4 | 5 | 1051.69 | 4189.36 | +1014.30 | +4140.59 | +98.84 | -5 |
| STARLINK-2418 | 48097 | 5 | 4 | 1609.02 | 2399.60 | +1571.63 | +2350.83 | +97.97 | +5 |

## CH1 lower, 224.54–248.34 s

Track `sha256:c48a2eea14785c85ae3ad12426098a94c7b5f6adbc9d982b1c9d41c3ad244bc9`; 33 observations; 532 nominal-time satellites scored. Training leader: **STARLINK-36735 (NORAD 68976)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-36576 (NORAD 67534): leader heldout RMS **44.04 Hz** versus **392.11 Hz**; gain **+348.07 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36735 | 68976 | 1 | 1 | 26.87 | 44.04 | +0.00 | +0.00 | +0.00 | -4 |
| STARLINK-36576 | 67534 | 2 | 2 | 56.90 | 392.11 | +30.03 | +348.07 | +88.77 | -3 |
| STARLINK-34163 | 64008 | 3 | 3 | 489.98 | 1406.84 | +463.10 | +1362.80 | +96.87 | -5 |
| STARLINK-30774 | 58625 | 4 | — | 699.65 | 7925.71 | +672.78 | +7881.67 | +99.44 | -5 |
| STARLINK-35107 | 65464 | 5 | 5 | 712.72 | 5545.44 | +685.84 | +5501.39 | +99.21 | +5 |
| STARLINK-36590 | 67577 | — | 4 | 820.50 | 4460.19 | +793.63 | +4416.14 | +99.01 | +5 |

## CH4 lower, 239.51–269.13 s

Track `sha256:b5073f701f728581618ac363736e94b6e54a54060b220ed15b70d04d425e55b8`; 34 observations; 536 nominal-time satellites scored. Training leader: **STARLINK-36576 (NORAD 67534)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-36735 (NORAD 68976): leader heldout RMS **111.83 Hz** versus **2589.69 Hz**; gain **+2477.87 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36576 | 67534 | 1 | 1 | 34.63 | 111.83 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-36735 | 68976 | 2 | 2 | 467.48 | 2589.69 | +432.85 | +2477.87 | +95.68 | +0 |
| STARLINK-37098 | 68192 | 3 | 3 | 2611.20 | 3184.91 | +2576.57 | +3073.09 | +96.49 | +5 |
| STARLINK-34163 | 64008 | 4 | — | 3303.62 | 12387.99 | +3268.99 | +12276.16 | +99.10 | -5 |
| STARLINK-36590 | 67577 | 5 | — | 4387.72 | 17647.64 | +4353.09 | +17535.81 | +99.37 | -5 |
| STARLINK-34999 | 65222 | — | 4 | 4809.08 | 10436.62 | +4774.44 | +10324.80 | +98.93 | +5 |
| STARLINK-32818 | 63036 | — | 5 | 4584.33 | 10537.49 | +4549.70 | +10425.66 | +98.94 | +5 |

## CH4 upper, 248.08–268.62 s

Track `sha256:e0ab30247cab35aca0eca57d04bcfa0905b6c707047c9b5259807d19b17c8f96`; 24 observations; 528 nominal-time satellites scored. Training leader: **STARLINK-36576 (NORAD 67534)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37098 (NORAD 68192): leader heldout RMS **136.35 Hz** versus **758.20 Hz**; gain **+621.85 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36576 | 67534 | 1 | 1 | 58.13 | 136.35 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-36735 | 68976 | 2 | 3 | 436.78 | 1134.01 | +378.65 | +997.66 | +87.98 | -5 |
| STARLINK-37098 | 68192 | 3 | 2 | 1036.14 | 758.20 | +978.01 | +621.85 | +82.02 | +5 |
| STARLINK-32818 | 63036 | 4 | 5 | 2753.57 | 6320.55 | +2695.44 | +6184.20 | +97.84 | +5 |
| STARLINK-34999 | 65222 | 5 | 4 | 2776.90 | 5994.55 | +2718.77 | +5858.20 | +97.73 | +5 |

## CH1 lower, 256.90–283.62 s

Track `sha256:44206fb244bdcddc9b14571f3476b01b42c82096c2c5a161232f8535f1e4ba49`; 29 observations; 532 nominal-time satellites scored. Training leader: **STARLINK-37098 (NORAD 68192)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32179 (NORAD 60734): leader heldout RMS **644.41 Hz** versus **5150.21 Hz**; gain **+4505.80 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37098 | 68192 | 1 | 1 | 366.23 | 644.41 | +0.00 | +0.00 | +0.00 | -5 |
| STARLINK-36735 | 68976 | 2 | 4 | 719.09 | 5701.70 | +352.86 | +5057.29 | +88.70 | -4 |
| STARLINK-36576 | 67534 | 3 | 5 | 788.58 | 6167.97 | +422.34 | +5523.56 | +89.55 | +3 |
| STARLINK-34999 | 65222 | 4 | 3 | 1084.17 | 5267.23 | +717.93 | +4622.82 | +87.77 | +5 |
| STARLINK-32818 | 63036 | 5 | — | 1433.48 | 6774.52 | +1067.24 | +6130.11 | +90.49 | +5 |
| STARLINK-32179 | 60734 | — | 2 | 1818.04 | 5150.21 | +1451.80 | +4505.80 | +87.49 | +5 |

## CH2 lower, 269.64–298.11 s

Track `sha256:d7a9428dc84a6e147475da600acd418c52c6407d786bf32e55872812fbdb6a16`; 33 observations; 534 nominal-time satellites scored. Training leader: **STARLINK-37098 (NORAD 68192)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-33729 (NORAD 63647): leader heldout RMS **161.03 Hz** versus **4742.11 Hz**; gain **+4581.08 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37098 | 68192 | 1 | 1 | 132.75 | 161.03 | +0.00 | +0.00 | +0.00 | -5 |
| STARLINK-32179 | 60734 | 2 | 3 | 1902.60 | 5237.34 | +1769.85 | +5076.31 | +96.93 | +5 |
| STARLINK-33729 | 63647 | 3 | 2 | 2298.23 | 4742.11 | +2165.48 | +4581.08 | +96.60 | +5 |
| STARLINK-36576 | 67534 | 4 | — | 2379.03 | 11971.24 | +2246.29 | +11810.20 | +98.65 | -5 |
| STARLINK-34999 | 65222 | 5 | 4 | 2444.50 | 8141.10 | +2311.76 | +7980.07 | +98.02 | -2 |
| STARLINK-32461 | 61701 | — | 5 | 4651.18 | 9484.68 | +4518.43 | +9323.64 | +98.30 | +5 |

## CH2 upper, 270.14–296.73 s

Track `sha256:80454a55dc083c377c4eea42bf79a323ee986f362c36c3f9a4350bea1aad5ee5`; 29 observations; 534 nominal-time satellites scored. Training leader: **STARLINK-37098 (NORAD 68192)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-33729 (NORAD 63647): leader heldout RMS **101.77 Hz** versus **4763.38 Hz**; gain **+4661.61 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37098 | 68192 | 1 | 1 | 120.62 | 101.77 | +0.00 | +0.00 | +0.00 | -5 |
| STARLINK-32179 | 60734 | 2 | 3 | 1680.58 | 5028.68 | +1559.96 | +4926.91 | +97.98 | +5 |
| STARLINK-36576 | 67534 | 3 | — | 1966.43 | 10777.17 | +1845.81 | +10675.40 | +99.06 | -5 |
| STARLINK-33729 | 63647 | 4 | 2 | 2057.61 | 4763.38 | +1936.99 | +4661.61 | +97.86 | +5 |
| STARLINK-34999 | 65222 | 5 | 4 | 2119.67 | 7783.63 | +1999.05 | +7681.86 | +98.69 | -1 |
| STARLINK-32818 | 63036 | — | 5 | 2537.45 | 9108.06 | +2416.83 | +9006.29 | +98.88 | -5 |
