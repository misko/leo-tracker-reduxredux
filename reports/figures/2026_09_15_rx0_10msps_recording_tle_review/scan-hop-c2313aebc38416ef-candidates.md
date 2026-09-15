# Candidate RMS comparisons: scan-hop-c2313aebc38416ef

[Ranked RMS plots for every track](scan-hop-c2313aebc38416ef-rms.md).

Recorded **2026-09-14T16:30:12.553220Z**, RX0, 10 MS/s.

[Recording assessment and plots](scan-hop-c2313aebc38416ef.md).

Each track has its own training-selected leader; there is no single satellite assignment for the whole recording. Lower RMS is better. The same observations and chronological split are used for all candidates within a track.

Gain = alternative RMS − training-leader RMS. Positive gain favors the leader; negative heldout gain means the alternative predicts better. Percent gain uses the alternative RMS as denominator; it is not identification confidence. Tau and carrier offset were selected on training data and remain frozen on heldout.

The archived screen retained the top five training candidates and top five heldout candidates, whose union is listed below. Candidate counts describe the full scored population; names/scores outside these retained lists were not archived. A blank rank means outside that top-five list. Catalogue exclusions and control results are in the linked recording assessment and evidence.

## CH2 lower, 0.14–24.60 s

Track `sha256:2b47b980520a1855712080c7dd85144f840ad0354cae4efd158c8d820f591eca`; 25 observations; 600 nominal-time satellites scored. Training leader: **STARLINK-38253 (NORAD 100302)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37413 (NORAD 68789): leader heldout RMS **2347.57 Hz** versus **3300.43 Hz**; gain **+952.87 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-38253 | 100302 | 1 | 1 | 270.66 | 2347.57 | +0.00 | +0.00 | +0.00 | -5 |
| STARLINK-37413 | 68789 | 2 | 2 | 395.39 | 3300.43 | +124.73 | +952.87 | +28.87 | +5 |
| STARLINK-38013 | 100430 | 3 | 5 | 1287.80 | 8554.23 | +1017.14 | +6206.66 | +72.56 | -5 |
| STARLINK-1067 | 44771 | 4 | — | 1372.54 | 10983.44 | +1101.88 | +8635.87 | +78.63 | -1 |
| STARLINK-37312 | 68676 | 5 | 4 | 1910.28 | 5974.56 | +1639.62 | +3626.99 | +60.71 | -2 |
| STARLINK-36108 | 66868 | — | 3 | 2213.97 | 5643.74 | +1943.31 | +3296.17 | +58.40 | +5 |

## CH2 upper, 0.65–24.10 s

Track `sha256:61790a7af61f61019a63c218cfc777161d7e5698db2523f3b6ffca1955c7dd5a`; 25 observations; 599 nominal-time satellites scored. Training leader: **STARLINK-38253 (NORAD 100302)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37413 (NORAD 68789): leader heldout RMS **2202.00 Hz** versus **2537.89 Hz**; gain **+335.90 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-38253 | 100302 | 1 | 1 | 262.23 | 2202.00 | +0.00 | +0.00 | +0.00 | -5 |
| STARLINK-37413 | 68789 | 2 | 2 | 340.46 | 2537.89 | +78.23 | +335.90 | +13.24 | +4 |
| STARLINK-1067 | 44771 | 3 | — | 1223.70 | 8888.33 | +961.47 | +6686.33 | +75.23 | -2 |
| STARLINK-38013 | 100430 | 4 | 5 | 1326.47 | 8000.82 | +1064.24 | +5798.82 | +72.48 | -5 |
| STARLINK-37312 | 68676 | 5 | 4 | 1880.47 | 5592.92 | +1618.24 | +3390.92 | +60.63 | -2 |
| STARLINK-36108 | 66868 | — | 3 | 2157.98 | 5279.18 | +1895.76 | +3077.18 | +58.29 | +5 |

## CH3 lower, 2.28–29.38 s

Track `sha256:3b3e246f43df5f2f0f707ad380539b3e88fa5f1252da40634b226552a47bd820`; 26 observations; 599 nominal-time satellites scored. Training leader: **STARLINK-36108 (NORAD 66868)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37413 (NORAD 68789): leader heldout RMS **853.37 Hz** versus **1949.79 Hz**; gain **+1096.41 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36108 | 66868 | 1 | 1 | 43.27 | 853.37 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-37312 | 68676 | 2 | 3 | 437.05 | 2991.46 | +393.78 | +2138.09 | +71.47 | +5 |
| STARLINK-35977 | 66604 | 3 | 4 | 682.18 | 3277.85 | +638.91 | +2424.48 | +73.97 | +5 |
| STARLINK-38253 | 100302 | 4 | 5 | 898.01 | 4200.47 | +854.74 | +3347.10 | +79.68 | +5 |
| STARLINK-32106 | 59690 | 5 | — | 911.89 | 7544.62 | +868.62 | +6691.25 | +88.69 | -5 |
| STARLINK-37413 | 68789 | — | 2 | 2222.51 | 1949.79 | +2179.24 | +1096.41 | +56.23 | +5 |

## CH1 lower, 14.78–45.63 s

Track `sha256:b9584fc338d9cb012cc4c7e4c17cfba8558ba2c22313eaa7846b3290022ffa5c`; 35 observations; 603 nominal-time satellites scored. Training leader: **STARLINK-36108 (NORAD 66868)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-33769 (NORAD 63773): leader heldout RMS **68.46 Hz** versus **1140.78 Hz**; gain **+1072.32 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36108 | 66868 | 1 | 1 | 44.54 | 68.46 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-37413 | 68789 | 2 | — | 673.18 | 4216.26 | +628.63 | +4147.80 | +98.38 | -2 |
| STARLINK-37312 | 68676 | 3 | — | 937.42 | 3710.39 | +892.88 | +3641.93 | +98.15 | -5 |
| STARLINK-38253 | 100302 | 4 | — | 1240.56 | 6557.73 | +1196.01 | +6489.27 | +98.96 | -5 |
| STARLINK-35977 | 66604 | 5 | 5 | 1395.37 | 2383.91 | +1350.83 | +2315.45 | +97.13 | -5 |
| STARLINK-33769 | 63773 | — | 2 | 1748.18 | 1140.78 | +1703.63 | +1072.32 | +94.00 | +5 |
| STARLINK-31444 | 59236 | — | 3 | 2271.17 | 1356.11 | +2226.63 | +1287.66 | +94.95 | +5 |
| STARLINK-35744 | 66581 | — | 4 | 2724.93 | 2065.04 | +2680.39 | +1996.58 | +96.68 | +5 |

## CH1 upper, 15.28–42.73 s

Track `sha256:2f3d269219d7fc764cd107f2c3903079a72f46fadcb0c230170fd68521f648c5`; 33 observations; 601 nominal-time satellites scored. Training leader: **STARLINK-36108 (NORAD 66868)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-33769 (NORAD 63773): leader heldout RMS **71.14 Hz** versus **1489.31 Hz**; gain **+1418.18 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36108 | 66868 | 1 | 1 | 77.99 | 71.14 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-37413 | 68789 | 2 | — | 572.96 | 3990.46 | +494.97 | +3919.32 | +98.22 | -1 |
| STARLINK-37312 | 68676 | 3 | — | 778.57 | 3177.21 | +700.58 | +3106.08 | +97.76 | -5 |
| STARLINK-38253 | 100302 | 4 | — | 962.10 | 5404.59 | +884.11 | +5333.45 | +98.68 | -5 |
| STARLINK-35977 | 66604 | 5 | 4 | 1255.53 | 2377.01 | +1177.54 | +2305.87 | +97.01 | -5 |
| STARLINK-33769 | 63773 | — | 2 | 1622.96 | 1489.31 | +1544.97 | +1418.18 | +95.22 | +5 |
| STARLINK-31444 | 59236 | — | 3 | 2109.60 | 1747.75 | +2031.61 | +1676.61 | +95.93 | +5 |
| STARLINK-35744 | 66581 | — | 5 | 2506.98 | 2622.81 | +2428.99 | +2551.67 | +97.29 | +5 |

## CH2 lower, 58.64–88.87 s

Track `sha256:2d389ace0d6cb3813daf9dd5e2ff0df34790e15162abb202f13cf74dd4eaaf66`; 45 observations; 595 nominal-time satellites scored. Training leader: **STARLINK-36910 (NORAD 68005)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-33780 (NORAD 63459): leader heldout RMS **175.49 Hz** versus **3880.75 Hz**; gain **+3705.26 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36910 | 68005 | 1 | 1 | 56.61 | 175.49 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-33780 | 63459 | 2 | 2 | 459.90 | 3880.75 | +403.29 | +3705.26 | +95.48 | -1 |
| STARLINK-31444 | 59236 | 3 | — | 1626.07 | 8909.18 | +1569.45 | +8733.68 | +98.03 | -5 |
| STARLINK-35744 | 66581 | 4 | — | 1671.74 | 8875.55 | +1615.13 | +8700.06 | +98.02 | -5 |
| STARLINK-35693 | 66490 | 5 | 3 | 2021.41 | 6082.92 | +1964.80 | +5907.43 | +97.11 | +5 |
| STARLINK-34973 | 65250 | — | 4 | 3226.16 | 6190.12 | +3169.55 | +6014.62 | +97.16 | +5 |
| STARLINK-34949 | 65175 | — | 5 | 4396.74 | 7354.51 | +4340.13 | +7179.02 | +97.61 | +5 |

## CH2 upper, 59.65–89.24 s

Track `sha256:9218fdebf7915f961e094c78501509bd318c7fc5f60266fdb800c8220d86234f`; 45 observations; 593 nominal-time satellites scored. Training leader: **STARLINK-36910 (NORAD 68005)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-33780 (NORAD 63459): leader heldout RMS **203.97 Hz** versus **3080.52 Hz**; gain **+2876.55 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36910 | 68005 | 1 | 1 | 113.11 | 203.97 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-33780 | 63459 | 2 | 2 | 417.12 | 3080.52 | +304.01 | +2876.55 | +93.38 | -3 |
| STARLINK-31444 | 59236 | 3 | — | 1747.97 | 9147.83 | +1634.87 | +8943.85 | +97.77 | -5 |
| STARLINK-35744 | 66581 | 4 | — | 1790.06 | 9104.12 | +1676.95 | +8900.15 | +97.76 | -5 |
| STARLINK-35693 | 66490 | 5 | 4 | 2054.00 | 6098.31 | +1940.90 | +5894.33 | +96.66 | +5 |
| STARLINK-34973 | 65250 | — | 3 | 3181.08 | 6006.83 | +3067.98 | +5802.85 | +96.60 | +5 |
| STARLINK-34949 | 65175 | — | 5 | 4300.86 | 7034.08 | +4187.75 | +6830.10 | +97.10 | +5 |

## CH1 lower, 60.15–89.12 s

Track `sha256:a4969b3c90ccdf3bd61392c98abd9c2f839792a15972de4535de37e2aabbbf39`; 37 observations; 593 nominal-time satellites scored. Training leader: **STARLINK-36910 (NORAD 68005)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-33780 (NORAD 63459): leader heldout RMS **222.16 Hz** versus **2563.51 Hz**; gain **+2341.35 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36910 | 68005 | 1 | 1 | 47.41 | 222.16 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-33780 | 63459 | 2 | 2 | 406.68 | 2563.51 | +359.26 | +2341.35 | +91.33 | -4 |
| STARLINK-31444 | 59236 | 3 | — | 2041.05 | 8582.40 | +1993.64 | +8360.24 | +97.41 | -5 |
| STARLINK-35744 | 66581 | 4 | — | 2073.79 | 8529.29 | +2026.38 | +8307.13 | +97.40 | -5 |
| STARLINK-35693 | 66490 | 5 | 4 | 2121.00 | 5517.89 | +2073.59 | +5295.73 | +95.97 | +5 |
| STARLINK-34973 | 65250 | — | 3 | 3121.93 | 5174.88 | +3074.52 | +4952.72 | +95.71 | +5 |
| STARLINK-34949 | 65175 | — | 5 | 4182.02 | 5932.74 | +4134.61 | +5710.57 | +96.26 | +5 |

## CH1 upper, 65.44–88.99 s

Track `sha256:486da7819ded1caef520d207454b94c1524ceaf5cc621f4d2731efd13b5aeb4f`; 34 observations; 588 nominal-time satellites scored. Training leader: **STARLINK-36910 (NORAD 68005)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-33780 (NORAD 63459): leader heldout RMS **185.55 Hz** versus **2438.45 Hz**; gain **+2252.90 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36910 | 68005 | 1 | 1 | 71.18 | 185.55 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-33780 | 63459 | 2 | 2 | 356.53 | 2438.45 | +285.35 | +2252.90 | +92.39 | -5 |
| STARLINK-35693 | 66490 | 3 | — | 1770.04 | 4781.23 | +1698.86 | +4595.68 | +96.12 | +5 |
| STARLINK-31444 | 59236 | 4 | — | 2160.90 | 8287.40 | +2089.72 | +8101.85 | +97.76 | -5 |
| STARLINK-35744 | 66581 | 5 | — | 2166.55 | 8203.67 | +2095.37 | +8018.12 | +97.74 | -5 |
| STARLINK-34973 | 65250 | — | 3 | 2207.19 | 3743.03 | +2136.00 | +3557.49 | +95.04 | +5 |
| STARLINK-34949 | 65175 | — | 4 | 2825.06 | 3904.41 | +2753.88 | +3718.86 | +95.25 | +5 |
| STARLINK-30919 | 58411 | — | 5 | 2772.79 | 4535.98 | +2701.61 | +4350.43 | +95.91 | +5 |

## CH3 upper, 94.54–127.15 s

Track `sha256:2d2f8cb5989ad0d633464491941651f3b9c7971b8c4f32d4441cf2f9b28b600f`; 37 observations; 604 nominal-time satellites scored. Training leader: **STARLINK-30919 (NORAD 58411)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-5365 (NORAD 55498): leader heldout RMS **215.09 Hz** versus **316.54 Hz**; gain **+101.46 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30919 | 58411 | 1 | 1 | 62.49 | 215.09 | +0.00 | +0.00 | +0.00 | +1 |
| STARLINK-5365 | 55498 | 2 | 2 | 182.06 | 316.54 | +119.58 | +101.46 | +32.05 | +1 |
| STARLINK-34973 | 65250 | 3 | 3 | 695.81 | 1379.76 | +633.32 | +1164.67 | +84.41 | -5 |
| STARLINK-34949 | 65175 | 4 | — | 1793.18 | 7875.77 | +1730.69 | +7660.69 | +97.27 | -5 |
| STARLINK-35082 | 65392 | 5 | 4 | 2569.25 | 2964.15 | +2506.77 | +2749.06 | +92.74 | +5 |
| STARLINK-31718 | 59556 | — | 5 | 4037.05 | 4115.51 | +3974.56 | +3900.42 | +94.77 | +5 |

## CH3 lower, 100.72–125.51 s

Track `sha256:afa34aa68e003f70e67ee3e88772c788a5c2ec09aa4cff3091415f26bb8a1675`; 27 observations; 597 nominal-time satellites scored. Training leader: **STARLINK-30919 (NORAD 58411)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-5365 (NORAD 55498): leader heldout RMS **215.67 Hz** versus **300.89 Hz**; gain **+85.22 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30919 | 58411 | 1 | 1 | 37.66 | 215.67 | +0.00 | +0.00 | +0.00 | +1 |
| STARLINK-5365 | 55498 | 2 | 2 | 77.06 | 300.89 | +39.40 | +85.22 | +28.32 | -1 |
| STARLINK-34973 | 65250 | 3 | 3 | 525.11 | 1006.10 | +487.45 | +790.43 | +78.56 | -5 |
| STARLINK-35082 | 65392 | 4 | 5 | 1097.09 | 3160.08 | +1059.43 | +2944.41 | +93.18 | +5 |
| STARLINK-34949 | 65175 | 5 | — | 1816.33 | 6587.90 | +1778.68 | +6372.23 | +96.73 | -5 |
| STARLINK-31718 | 59556 | — | 4 | 2410.11 | 2182.33 | +2372.45 | +1966.66 | +90.12 | +5 |

## CH1 lower, 143.67–173.90 s

Track `sha256:492d37daa3d608ec51e574d7506aee50a3e6de6e0c01ad1a68338ea24b48628d`; 31 observations; 593 nominal-time satellites scored. Training leader: **STARLINK-35061 (NORAD 66191)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32265 (NORAD 60415): leader heldout RMS **253.60 Hz** versus **5478.54 Hz**; gain **+5224.94 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35061 | 66191 | 1 | 1 | 48.90 | 253.60 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-35082 | 65392 | 2 | 3 | 676.92 | 5946.88 | +628.03 | +5693.28 | +95.74 | +0 |
| STARLINK-32265 | 60415 | 3 | 2 | 1259.04 | 5478.54 | +1210.14 | +5224.94 | +95.37 | -4 |
| STARLINK-31718 | 59556 | 4 | — | 1723.96 | 9368.97 | +1675.06 | +9115.37 | +97.29 | -5 |
| STARLINK-33844 | 63768 | 5 | 4 | 2320.18 | 8542.28 | +2271.28 | +8288.68 | +97.03 | +4 |
| STARLINK-2338 | 47793 | — | 5 | 3686.40 | 9346.62 | +3637.51 | +9093.02 | +97.29 | +5 |

## CH4 lower, 194.43–223.41 s

Track `sha256:462e6f0ff0e40a735f77c3829aaf74a35bc5a0cef069e9f0259dbb574118ea94`; 33 observations; 594 nominal-time satellites scored. Training leader: **STARLINK-33867 (NORAD 63795)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37310 (NORAD 68679): leader heldout RMS **54.56 Hz** versus **1730.67 Hz**; gain **+1676.12 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33867 | 63795 | 1 | 1 | 112.22 | 54.56 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-4634 | 53967 | 2 | 3 | 159.39 | 1824.12 | +47.17 | +1769.56 | +97.01 | +3 |
| STARLINK-37364 | 68783 | 3 | 5 | 247.52 | 3146.82 | +135.29 | +3092.26 | +98.27 | +3 |
| STARLINK-4476 | 53419 | 4 | 4 | 427.06 | 2620.55 | +314.83 | +2565.99 | +97.92 | -5 |
| STARLINK-35899 | 66497 | 5 | — | 432.39 | 4156.03 | +320.16 | +4101.48 | +98.69 | -5 |
| STARLINK-37310 | 68679 | — | 2 | 1109.64 | 1730.67 | +997.42 | +1676.12 | +96.85 | +5 |

## CH1 upper, 194.56–222.53 s

Track `sha256:06dcf11155e7d3dd803202123f79ccd3961069f2f49c09a5909c43c8e05b04a5`; 28 observations; 593 nominal-time satellites scored. Training leader: **STARLINK-32244 (NORAD 60411)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11659 (NORAD 63266): leader heldout RMS **129.57 Hz** versus **251.05 Hz**; gain **+121.48 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32244 | 60411 | 1 | 1 | 77.73 | 129.57 | +0.00 | +0.00 | +0.00 | +1 |
| STARLINK-11659 | 63266 | 2 | 2 | 89.05 | 251.05 | +11.32 | +121.48 | +48.39 | -5 |
| STARLINK-4476 | 53419 | 3 | 3 | 150.29 | 1164.86 | +72.56 | +1035.29 | +88.88 | +5 |
| STARLINK-34801 | 66076 | 4 | — | 645.27 | 5678.64 | +567.54 | +5549.08 | +97.72 | -5 |
| STARLINK-33867 | 63795 | 5 | 5 | 1212.77 | 2921.62 | +1135.04 | +2792.05 | +95.57 | +5 |
| STARLINK-37364 | 68783 | — | 4 | 1663.88 | 1238.13 | +1586.15 | +1108.56 | +89.54 | +5 |

## CH2 lower, 195.06–223.03 s

Track `sha256:ed1a1c3e9ea00f9a6037330329ea78bad68e20f77245d1612c2cc39aea855069`; 32 observations; 591 nominal-time satellites scored. Training leader: **STARLINK-11659 (NORAD 63266)**; heldout rank 2 in the full scored population.

Against the best other heldout candidate, STARLINK-32244 (NORAD 60411): leader heldout RMS **255.74 Hz** versus **126.83 Hz**; gain **-128.91 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-11659 | 63266 | 1 | 2 | 31.30 | 255.74 | +0.00 | +0.00 | +0.00 | -5 |
| STARLINK-32244 | 60411 | 2 | 1 | 34.23 | 126.83 | +2.93 | -128.91 | -101.63 | +1 |
| STARLINK-4476 | 53419 | 3 | 3 | 111.95 | 1017.67 | +80.65 | +761.93 | +74.87 | +4 |
| STARLINK-34801 | 66076 | 4 | — | 606.69 | 5854.21 | +575.40 | +5598.47 | +95.63 | -5 |
| STARLINK-33867 | 63795 | 5 | 5 | 1142.60 | 2994.00 | +1111.30 | +2738.26 | +91.46 | +5 |
| STARLINK-37364 | 68783 | — | 4 | 1552.59 | 1322.79 | +1521.29 | +1067.05 | +80.67 | +5 |

## CH2 upper, 195.18–223.28 s

Track `sha256:38ac8eeab0883762e2ed06a2b503bf63333ee4dd1505c42de4841478e505521e`; 31 observations; 591 nominal-time satellites scored. Training leader: **STARLINK-32244 (NORAD 60411)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11659 (NORAD 63266): leader heldout RMS **152.43 Hz** versus **287.58 Hz**; gain **+135.15 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32244 | 60411 | 1 | 1 | 66.66 | 152.43 | +0.00 | +0.00 | +0.00 | +1 |
| STARLINK-11659 | 63266 | 2 | 2 | 77.25 | 287.58 | +10.59 | +135.15 | +46.99 | -5 |
| STARLINK-4476 | 53419 | 3 | 3 | 109.75 | 1252.02 | +43.08 | +1099.58 | +87.82 | +5 |
| STARLINK-34801 | 66076 | 4 | — | 595.82 | 6048.13 | +529.16 | +5895.69 | +97.48 | -5 |
| STARLINK-33867 | 63795 | 5 | 5 | 1128.30 | 3081.12 | +1061.64 | +2928.69 | +95.05 | +5 |
| STARLINK-37364 | 68783 | — | 4 | 1537.74 | 1378.30 | +1471.08 | +1225.87 | +88.94 | +5 |

## CH4 upper, 195.57–245.96 s

Track `sha256:e1c322841bc5f0fc1cd4714edcff49d100e40a6f3a59a8216b561d1e891f2f60`; 54 observations; 618 nominal-time satellites scored. Training leader: **STARLINK-33867 (NORAD 63795)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-2406 (NORAD 47821): leader heldout RMS **335.04 Hz** versus **2991.07 Hz**; gain **+2656.03 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33867 | 63795 | 1 | 1 | 70.94 | 335.04 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-4634 | 53967 | 2 | — | 924.68 | 7124.77 | +853.74 | +6789.73 | +95.30 | +5 |
| STARLINK-37364 | 68783 | 3 | — | 927.57 | 11009.00 | +856.62 | +10673.96 | +96.96 | -1 |
| STARLINK-37310 | 68679 | 4 | — | 1102.42 | 5246.25 | +1031.48 | +4911.21 | +93.61 | +5 |
| STARLINK-4476 | 53419 | 5 | — | 1417.00 | 7193.20 | +1346.06 | +6858.16 | +95.34 | -5 |
| STARLINK-2406 | 47821 | — | 2 | 3506.47 | 2991.07 | +3435.53 | +2656.03 | +88.80 | +5 |
| STARLINK-34468 | 64424 | — | 3 | 1961.46 | 3742.68 | +1890.52 | +3407.64 | +91.05 | +5 |
| STARLINK-32244 | 60411 | — | 4 | 2252.25 | 4402.31 | +2181.31 | +4067.27 | +92.39 | -5 |
| STARLINK-11165 | 60063 | — | 5 | 6098.57 | 4736.73 | +6027.63 | +4401.69 | +92.93 | +5 |

## CH4 lower, 225.42–248.60 s

Track `sha256:65c9b6afff68b0dd9d1801c7e45b8a4294ffa774ff5b735998581bacc2c5c370`; 24 observations; 589 nominal-time satellites scored. Training leader: **STARLINK-33867 (NORAD 63795)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-35176 (NORAD 65662): leader heldout RMS **73.69 Hz** versus **637.24 Hz**; gain **+563.55 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33867 | 63795 | 1 | 1 | 113.09 | 73.69 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-32244 | 60411 | 2 | 5 | 165.60 | 965.12 | +52.52 | +891.43 | +92.36 | -3 |
| STARLINK-4476 | 53419 | 3 | 4 | 242.10 | 962.15 | +129.02 | +888.46 | +92.34 | +5 |
| STARLINK-11165 | 60063 | 4 | — | 292.92 | 2261.44 | +179.83 | +2187.75 | +96.74 | -1 |
| STARLINK-11659 | 63266 | 5 | — | 411.61 | 2473.68 | +298.52 | +2399.99 | +97.02 | -5 |
| STARLINK-35176 | 65662 | — | 2 | 678.52 | 637.24 | +565.43 | +563.55 | +88.44 | -4 |
| STARLINK-31534 | 59398 | — | 3 | 1158.91 | 922.26 | +1045.83 | +848.57 | +92.01 | +5 |

## CH2 lower, 253.27–280.11 s

Track `sha256:144b7be5d3d36064179d0130a8255c61fb854a9100747db48a67ea6ee2f82faa`; 29 observations; 591 nominal-time satellites scored. Training leader: **STARLINK-34472 (NORAD 64434)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-36091 (NORAD 66848): leader heldout RMS **116.39 Hz** versus **4537.02 Hz**; gain **+4420.63 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34472 | 64434 | 1 | 1 | 74.88 | 116.39 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-33795 | 63457 | 2 | 3 | 513.34 | 5340.92 | +438.46 | +5224.52 | +97.82 | -5 |
| STARLINK-36091 | 66848 | 3 | 2 | 598.26 | 4537.02 | +523.38 | +4420.63 | +97.43 | -5 |
| STARLINK-2406 | 47821 | 4 | — | 910.07 | 7351.59 | +835.18 | +7235.20 | +98.42 | -5 |
| STARLINK-37310 | 68679 | 5 | — | 1028.88 | 8121.50 | +953.99 | +8005.11 | +98.57 | -5 |
| STARLINK-35358 | 66564 | — | 4 | 2188.73 | 5777.96 | +2113.85 | +5661.57 | +97.99 | +5 |
| STARLINK-38186 | 100162 | — | 5 | 1494.67 | 6435.93 | +1419.79 | +6319.54 | +98.19 | +0 |

## CH1 lower, 0.02–23.47 s

Track `sha256:680da4f14ba218b312d1ad7b782a13b627a921740ee65683b23d3f8c1ff25878`; 24 observations; 599 nominal-time satellites scored. Training leader: **STARLINK-37413 (NORAD 68789)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-38253 (NORAD 100302): leader heldout RMS **17.98 Hz** versus **2280.56 Hz**; gain **+2262.58 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37413 | 68789 | 1 | 1 | 25.10 | 17.98 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-38013 | 100430 | 2 | 5 | 665.68 | 7526.23 | +640.58 | +7508.25 | +99.76 | -5 |
| STARLINK-38253 | 100302 | 3 | 2 | 768.54 | 2280.56 | +743.44 | +2262.58 | +99.21 | -5 |
| STARLINK-1067 | 44771 | 4 | — | 950.57 | 8247.21 | +925.47 | +8229.23 | +99.78 | -2 |
| STARLINK-37312 | 68676 | 5 | 4 | 2455.30 | 6188.66 | +2430.21 | +6170.68 | +99.71 | -1 |
| STARLINK-36108 | 66868 | — | 3 | 2798.33 | 5895.45 | +2773.23 | +5877.47 | +99.70 | +5 |

## CH4 lower, 184.36–208.80 s

Track `sha256:428a92328842951dab75e13543675f53c284904570fb6b1cb7df55cf1817f61b`; 27 observations; 596 nominal-time satellites scored. Training leader: **STARLINK-32244 (NORAD 60411)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11659 (NORAD 63266): leader heldout RMS **69.54 Hz** versus **204.23 Hz**; gain **+134.69 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32244 | 60411 | 1 | 1 | 18.56 | 69.54 | +0.00 | +0.00 | +0.00 | +1 |
| STARLINK-11659 | 63266 | 2 | 2 | 79.67 | 204.23 | +61.11 | +134.69 | +65.95 | -4 |
| STARLINK-4476 | 53419 | 3 | 3 | 273.83 | 269.98 | +255.27 | +200.44 | +74.24 | +5 |
| STARLINK-35899 | 66497 | 4 | — | 591.88 | 4270.09 | +573.32 | +4200.55 | +98.37 | +2 |
| STARLINK-32943 | 63023 | 5 | — | 862.71 | 5556.47 | +844.14 | +5486.92 | +98.75 | -5 |
| STARLINK-34801 | 66076 | — | 4 | 1267.98 | 1881.54 | +1249.42 | +1812.00 | +96.30 | +5 |
| STARLINK-33867 | 63795 | — | 5 | 1230.49 | 3266.09 | +1211.92 | +3196.55 | +97.87 | +5 |

## CH1 upper, 3.54–23.98 s

Track `sha256:97ea1a0e9769668731bf61d446105979bb1f1034cc192e39cb836ad67e47c76a`; 21 observations; 594 nominal-time satellites scored. Training leader: **STARLINK-37413 (NORAD 68789)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-38253 (NORAD 100302): leader heldout RMS **41.15 Hz** versus **1906.23 Hz**; gain **+1865.08 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37413 | 68789 | 1 | 1 | 76.74 | 41.15 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-38253 | 100302 | 2 | 2 | 724.44 | 1906.23 | +647.71 | +1865.08 | +97.84 | -5 |
| STARLINK-1067 | 44771 | 3 | 5 | 812.00 | 6356.24 | +735.26 | +6315.09 | +99.35 | -4 |
| STARLINK-38013 | 100430 | 4 | — | 1137.08 | 8279.19 | +1060.34 | +8238.04 | +99.50 | -5 |
| STARLINK-37312 | 68676 | 5 | 4 | 2045.09 | 4533.42 | +1968.35 | +4492.27 | +99.09 | -4 |
| STARLINK-36108 | 66868 | — | 3 | 2190.83 | 4343.94 | +2114.09 | +4302.79 | +99.05 | +5 |
