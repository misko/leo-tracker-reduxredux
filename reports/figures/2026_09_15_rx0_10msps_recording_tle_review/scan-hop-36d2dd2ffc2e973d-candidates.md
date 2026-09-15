# Candidate RMS comparisons: scan-hop-36d2dd2ffc2e973d

Recorded **2026-09-14T20:10:12.907428Z**, RX0, 10 MS/s.

[Recording assessment and plots](scan-hop-36d2dd2ffc2e973d.md).

Each track has its own training-selected leader; there is no single satellite assignment for the whole recording. Lower RMS is better. The same observations and chronological split are used for all candidates within a track.

Gain = alternative RMS − training-leader RMS. Positive gain favors the leader; negative heldout gain means the alternative predicts better. Percent gain uses the alternative RMS as denominator; it is not identification confidence. Tau and carrier offset were selected on training data and remain frozen on heldout.

The archived screen retained the top five training candidates and top five heldout candidates, whose union is listed below. Candidate counts describe the full scored population; names/scores outside these retained lists were not archived. A blank rank means outside that top-five list. Catalogue exclusions and control results are in the linked recording assessment and evidence.

## CH3 lower, 23.32–43.76 s

Track `sha256:54731f344f8cf39f70a84915da0707ca6ee19af229b388a5c6c968b3d380ce6e`; 31 observations; 473 nominal-time satellites scored. Training leader: **STARLINK-34721 (NORAD 65039)**; heldout rank 2 in the full scored population.

Against the best other heldout candidate, STARLINK-33703 (NORAD 63418): leader heldout RMS **200.24 Hz** versus **136.79 Hz**; gain **-63.45 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34721 | 65039 | 1 | 2 | 93.55 | 200.24 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-33703 | 63418 | 2 | 1 | 101.72 | 136.79 | +8.18 | -63.45 | -46.38 | -2 |
| STARLINK-31590 | 59198 | 3 | 4 | 136.67 | 1179.54 | +43.13 | +979.30 | +83.02 | +5 |
| STARLINK-36345 | 68243 | 4 | — | 344.48 | 2802.22 | +250.93 | +2601.99 | +92.85 | -3 |
| STARLINK-31545 | 59400 | 5 | — | 367.95 | 3058.31 | +274.40 | +2858.07 | +93.45 | +4 |
| STARLINK-35604 | 66802 | — | 3 | 1346.61 | 885.21 | +1253.06 | +684.97 | +77.38 | +5 |
| STARLINK-30320 | 57678 | — | 5 | 2188.61 | 1295.15 | +2095.06 | +1094.91 | +84.54 | +5 |

## CH3 upper, 43.63–80.43 s

Track `sha256:5fa12fb3f2ff721ae7cedae1a4e6fd3bc459b54689acf6b05b002ece5a9f85a9`; 44 observations; 481 nominal-time satellites scored. Training leader: **STARLINK-33703 (NORAD 63418)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-1771 (NORAD 46384): leader heldout RMS **202.03 Hz** versus **3211.03 Hz**; gain **+3009.00 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33703 | 63418 | 1 | 1 | 105.74 | 202.03 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-34721 | 65039 | 2 | 3 | 800.21 | 5824.49 | +694.47 | +5622.47 | +96.53 | +5 |
| STARLINK-5939 | 56015 | 3 | — | 822.61 | 8716.78 | +716.87 | +8514.75 | +97.68 | -5 |
| STARLINK-2728 | 48478 | 4 | — | 1135.30 | 11460.96 | +1029.56 | +11258.93 | +98.24 | +4 |
| STARLINK-5798 | 56040 | 5 | — | 2283.57 | 15321.90 | +2177.82 | +15119.87 | +98.68 | -5 |
| STARLINK-1771 | 46384 | — | 2 | 4459.44 | 3211.03 | +4353.70 | +3009.00 | +93.71 | +5 |
| STARLINK-11419 [DTC] | 62883 | — | 4 | 7047.30 | 6166.74 | +6941.56 | +5964.71 | +96.72 | +5 |
| STARLINK-4077 | 53154 | — | 5 | 3732.40 | 6456.39 | +3626.66 | +6254.36 | +96.87 | +5 |

## CH1 lower, 44.65–85.59 s

Track `sha256:7a6e667d138d9b4eca0c5776ab9e0018ad4481e5e4e3f0bc3f5c1f4fb65f1dfa`; 47 observations; 486 nominal-time satellites scored. Training leader: **STARLINK-33703 (NORAD 63418)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4077 (NORAD 53154): leader heldout RMS **186.98 Hz** versus **4593.82 Hz**; gain **+4406.84 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33703 | 63418 | 1 | 1 | 70.32 | 186.98 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-34721 | 65039 | 2 | 5 | 1219.50 | 7450.83 | +1149.19 | +7263.85 | +97.49 | +5 |
| STARLINK-2728 | 48478 | 3 | — | 1261.20 | 11548.32 | +1190.89 | +11361.34 | +98.38 | -1 |
| STARLINK-5939 | 56015 | 4 | — | 1476.62 | 11821.85 | +1406.30 | +11634.87 | +98.42 | -5 |
| STARLINK-36931 | 68000 | 5 | — | 3336.57 | 11827.81 | +3266.26 | +11640.83 | +98.42 | +5 |
| STARLINK-4077 | 53154 | — | 2 | 3729.58 | 4593.82 | +3659.26 | +4406.84 | +95.93 | +5 |
| STARLINK-11419 [DTC] | 62883 | — | 3 | 6265.35 | 4619.31 | +6195.04 | +4432.32 | +95.95 | +5 |
| STARLINK-1771 | 46384 | — | 4 | 3769.05 | 5900.49 | +3698.73 | +5713.51 | +96.83 | +5 |

## CH1 upper, 45.66–88.23 s

Track `sha256:ebd0e3e474152255ee1fbba775d41f4a8ac577d64cb7431113b9059fee85c8d5`; 47 observations; 486 nominal-time satellites scored. Training leader: **STARLINK-33703 (NORAD 63418)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4077 (NORAD 53154): leader heldout RMS **192.05 Hz** versus **3205.63 Hz**; gain **+3013.59 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33703 | 63418 | 1 | 1 | 70.16 | 192.05 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-2728 | 48478 | 2 | — | 1208.05 | 10338.33 | +1137.89 | +10146.29 | +98.14 | -5 |
| STARLINK-34721 | 65039 | 3 | 4 | 1518.52 | 8305.83 | +1448.36 | +8113.79 | +97.69 | +5 |
| STARLINK-5939 | 56015 | 4 | — | 2022.95 | 13556.48 | +1952.79 | +13364.43 | +98.58 | -5 |
| STARLINK-1771 | 46384 | 5 | 5 | 2925.37 | 8736.86 | +2855.21 | +8544.82 | +97.80 | +5 |
| STARLINK-4077 | 53154 | — | 2 | 3426.57 | 3205.63 | +3356.41 | +3013.59 | +94.01 | +5 |
| STARLINK-11419 [DTC] | 62883 | — | 3 | 5129.91 | 6819.08 | +5059.75 | +6627.03 | +97.18 | +5 |

## CH3 lower, 74.00–118.75 s

Track `sha256:51206c4af433f2b83e1a58762ea161811de3ceead6178909986d7e5901786cf6`; 51 observations; 489 nominal-time satellites scored. Training leader: **STARLINK-35765 (NORAD 67041)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32182 (NORAD 60319): leader heldout RMS **69.15 Hz** versus **456.35 Hz**; gain **+387.21 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35765 | 67041 | 1 | 1 | 47.65 | 69.15 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-32182 | 60319 | 2 | 2 | 61.58 | 456.35 | +13.92 | +387.21 | +84.85 | -4 |
| STARLINK-37440 | 69189 | 3 | 5 | 431.73 | 4017.16 | +384.08 | +3948.01 | +98.28 | -2 |
| STARLINK-33989 | 63929 | 4 | 3 | 562.77 | 487.16 | +515.12 | +418.02 | +85.81 | +5 |
| STARLINK-2500 | 48485 | 5 | 4 | 1603.92 | 3891.72 | +1556.27 | +3822.58 | +98.22 | +5 |

## CH1 upper, 89.12–119.00 s

Track `sha256:64fcdb77d638856f4dc9c9e22f05acfc458f77a86053b4ac87c1fef526099b19`; 35 observations; 476 nominal-time satellites scored. Training leader: **STARLINK-35765 (NORAD 67041)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32182 (NORAD 60319): leader heldout RMS **178.98 Hz** versus **751.99 Hz**; gain **+573.02 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35765 | 67041 | 1 | 1 | 47.27 | 178.98 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-32182 | 60319 | 2 | 2 | 90.70 | 751.99 | +43.43 | +573.02 | +76.20 | -5 |
| STARLINK-33989 | 63929 | 3 | 3 | 111.75 | 902.95 | +64.48 | +723.97 | +80.18 | +5 |
| STARLINK-4077 | 53154 | 4 | 5 | 547.55 | 2416.34 | +500.28 | +2237.37 | +92.59 | +5 |
| STARLINK-37440 | 69189 | 5 | — | 587.72 | 4083.54 | +540.45 | +3904.56 | +95.62 | -5 |
| STARLINK-2500 | 48485 | — | 4 | 962.53 | 2246.43 | +915.26 | +2067.46 | +92.03 | +5 |

## CH1 lower, 89.50–118.62 s

Track `sha256:596e3e4e0a977670d16c4b2badfe6411b8dd06094de650b56a4cb4f0e4710932`; 35 observations; 475 nominal-time satellites scored. Training leader: **STARLINK-35765 (NORAD 67041)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32182 (NORAD 60319): leader heldout RMS **52.08 Hz** versus **695.45 Hz**; gain **+643.37 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35765 | 67041 | 1 | 1 | 19.17 | 52.08 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-32182 | 60319 | 2 | 2 | 77.52 | 695.45 | +58.35 | +643.37 | +92.51 | -5 |
| STARLINK-33989 | 63929 | 3 | 3 | 88.59 | 842.49 | +69.43 | +790.41 | +93.82 | +5 |
| STARLINK-4077 | 53154 | 4 | 5 | 518.32 | 2434.15 | +499.15 | +2382.07 | +97.86 | +5 |
| STARLINK-37440 | 69189 | 5 | — | 610.77 | 3999.03 | +591.60 | +3946.96 | +98.70 | -5 |
| STARLINK-2500 | 48485 | — | 4 | 951.44 | 2243.12 | +932.28 | +2191.04 | +97.68 | +5 |

## CH4 lower, 126.94–156.95 s

Track `sha256:0556543b30e37f76a2a44b776da860bb563ee9563d65792bb321bd43a356d154`; 41 observations; 473 nominal-time satellites scored. Training leader: **STARLINK-30982 (NORAD 58512)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-35056 (NORAD 66266): leader heldout RMS **155.86 Hz** versus **2341.30 Hz**; gain **+2185.44 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30982 | 58512 | 1 | 1 | 62.45 | 155.86 | +0.00 | +0.00 | +0.00 | +1 |
| STARLINK-35056 | 66266 | 2 | 2 | 204.17 | 2341.30 | +141.73 | +2185.44 | +93.34 | +5 |
| STARLINK-33989 | 63929 | 3 | — | 946.79 | 9795.14 | +884.34 | +9639.28 | +98.41 | -5 |
| STARLINK-6330 | 57239 | 4 | 5 | 1162.99 | 6212.22 | +1100.54 | +6056.36 | +97.49 | +5 |
| STARLINK-31777 | 59619 | 5 | 4 | 1220.10 | 3590.48 | +1157.65 | +3434.62 | +95.66 | +5 |
| STARLINK-35550 | 66267 | — | 3 | 2890.93 | 3188.53 | +2828.48 | +3032.67 | +95.11 | +5 |

## CH4 upper, 128.32–160.10 s

Track `sha256:8ee0188e2bfb02c77aa0a22a5080778ce09b6fd4dec90638994c304ed3b54b35`; 43 observations; 471 nominal-time satellites scored. Training leader: **STARLINK-30982 (NORAD 58512)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-35550 (NORAD 66267): leader heldout RMS **129.03 Hz** versus **2112.06 Hz**; gain **+1983.03 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30982 | 58512 | 1 | 1 | 78.28 | 129.03 | +0.00 | +0.00 | +0.00 | +1 |
| STARLINK-35056 | 66266 | 2 | 3 | 184.61 | 2479.41 | +106.33 | +2350.39 | +94.80 | +4 |
| STARLINK-31777 | 59619 | 3 | 4 | 945.79 | 5612.49 | +867.52 | +5483.46 | +97.70 | +5 |
| STARLINK-33989 | 63929 | 4 | — | 1421.63 | 12632.46 | +1343.35 | +12503.43 | +98.98 | -5 |
| STARLINK-6330 | 57239 | 5 | — | 1424.59 | 7362.37 | +1346.32 | +7233.34 | +98.25 | +5 |
| STARLINK-35550 | 66267 | — | 2 | 2639.34 | 2112.06 | +2561.07 | +1983.03 | +93.89 | +5 |
| STARLINK-35239 | 65623 | — | 5 | 2307.54 | 6524.46 | +2229.26 | +6395.44 | +98.02 | +5 |

## CH1 upper, 150.91–176.47 s

Track `sha256:f11168fff8258886b57ea1891e0f749486b54307c95a57741b6ddf3b776f74ad`; 33 observations; 470 nominal-time satellites scored. Training leader: **STARLINK-31866 (NORAD 59668)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-31325 (NORAD 59165): leader heldout RMS **57.32 Hz** versus **505.23 Hz**; gain **+447.91 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31866 | 59668 | 1 | 1 | 29.23 | 57.32 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-31325 | 59165 | 2 | 2 | 121.22 | 505.23 | +91.99 | +447.91 | +88.65 | -2 |
| STARLINK-6330 | 57239 | 3 | — | 490.14 | 4501.82 | +460.91 | +4444.50 | +98.73 | -1 |
| STARLINK-31777 | 59619 | 4 | — | 759.35 | 6766.23 | +730.12 | +6708.91 | +99.15 | -4 |
| STARLINK-35550 | 66267 | 5 | — | 848.63 | 8010.20 | +819.40 | +7952.87 | +99.28 | +5 |
| STARLINK-35239 | 65623 | — | 3 | 971.26 | 1270.70 | +942.02 | +1213.37 | +95.49 | -5 |
| STARLINK-30982 | 58512 | — | 4 | 2411.21 | 1969.27 | +2381.97 | +1911.95 | +97.09 | +5 |
| STARLINK-32474 | 61260 | — | 5 | 1243.07 | 2385.70 | +1213.84 | +2328.38 | +97.60 | +5 |

## CH2 lower, 189.57–237.70 s

Track `sha256:7f084320125fa6c66bcf8c57fc2c0febc85ae01c98db1db42850ff2d954606c4`; 51 observations; 487 nominal-time satellites scored. Training leader: **STARLINK-35905 (NORAD 67048)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-33980 (NORAD 63930): leader heldout RMS **197.45 Hz** versus **4322.14 Hz**; gain **+4124.70 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35905 | 67048 | 1 | 1 | 40.46 | 197.45 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-32474 | 61260 | 2 | 3 | 1788.24 | 10665.16 | +1747.78 | +10467.71 | +98.15 | +5 |
| STARLINK-31325 | 59165 | 3 | — | 1888.24 | 15582.84 | +1847.78 | +15385.39 | +98.73 | -5 |
| STARLINK-31866 | 59668 | 4 | — | 2899.06 | 18847.59 | +2858.60 | +18650.15 | +98.95 | -5 |
| STARLINK-33980 | 63930 | 5 | 2 | 3184.29 | 4322.14 | +3143.83 | +4124.70 | +95.43 | +5 |
| STARLINK-30958 | 58457 | — | 4 | 8083.09 | 13065.14 | +8042.63 | +12867.69 | +98.49 | +5 |
| STARLINK-3315 | 50848 | — | 5 | 3869.25 | 15079.40 | +3828.79 | +14881.95 | +98.69 | +1 |

## CH2 upper, 202.67–233.16 s

Track `sha256:667986faefaf32bcfc13fba242e102636df75725d5e94246763ebc09f13366e0`; 32 observations; 470 nominal-time satellites scored. Training leader: **STARLINK-35905 (NORAD 67048)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-33980 (NORAD 63930): leader heldout RMS **166.26 Hz** versus **1915.76 Hz**; gain **+1749.50 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35905 | 67048 | 1 | 1 | 46.73 | 166.26 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-32474 | 61260 | 2 | 3 | 443.55 | 3405.82 | +396.82 | +3239.57 | +95.12 | -5 |
| STARLINK-33980 | 63930 | 3 | 2 | 1439.23 | 1915.76 | +1392.50 | +1749.50 | +91.32 | +5 |
| STARLINK-31325 | 59165 | 4 | — | 2859.95 | 13450.11 | +2813.22 | +13283.86 | +98.76 | -5 |
| STARLINK-3315 | 50848 | 5 | 5 | 3109.06 | 9908.74 | +3062.33 | +9742.49 | +98.32 | -5 |
| STARLINK-30958 | 58457 | — | 4 | 3979.30 | 6827.03 | +3932.57 | +6660.77 | +97.56 | +5 |

## CH4 upper, 270.60–298.81 s

Track `sha256:4890848ef49fb1f161057a3560781053da4915e98ff6108361484b8c34664b4b`; 29 observations; 474 nominal-time satellites scored. Training leader: **STARLINK-37359 (NORAD 69188)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-3182 (NORAD 51469): leader heldout RMS **192.71 Hz** versus **905.06 Hz**; gain **+712.36 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37359 | 69188 | 1 | 1 | 71.45 | 192.71 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-3182 | 51469 | 2 | 2 | 103.98 | 905.06 | +32.53 | +712.36 | +78.71 | -4 |
| STARLINK-3998 | 52610 | 3 | 3 | 190.66 | 2033.89 | +119.21 | +1841.19 | +90.53 | +4 |
| STARLINK-32189 | 60317 | 4 | 5 | 365.33 | 3847.06 | +293.88 | +3654.35 | +94.99 | +2 |
| STARLINK-33985 | 63943 | 5 | — | 472.63 | 4605.84 | +401.17 | +4413.13 | +95.82 | +5 |
| STARLINK-30114 | 56826 | — | 4 | 967.01 | 3490.08 | +895.55 | +3297.37 | +94.48 | +5 |

## CH4 lower, 271.10–299.32 s

Track `sha256:17cd3a6f3fb1abfda605e62f3bfce7b9ec6baa6d86a82e0c88d1eaabb6cb072c`; 29 observations; 474 nominal-time satellites scored. Training leader: **STARLINK-37359 (NORAD 69188)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-3182 (NORAD 51469): leader heldout RMS **116.61 Hz** versus **666.74 Hz**; gain **+550.13 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37359 | 69188 | 1 | 1 | 110.68 | 116.61 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-3182 | 51469 | 2 | 2 | 119.74 | 666.74 | +9.05 | +550.13 | +82.51 | -3 |
| STARLINK-3998 | 52610 | 3 | 3 | 193.32 | 2010.13 | +82.64 | +1893.52 | +94.20 | +5 |
| STARLINK-32189 | 60317 | 4 | 5 | 398.66 | 4109.68 | +287.98 | +3993.07 | +97.16 | +3 |
| STARLINK-33985 | 63943 | 5 | — | 530.66 | 4784.02 | +419.97 | +4667.41 | +97.56 | +5 |
| STARLINK-30114 | 56826 | — | 4 | 994.94 | 3461.70 | +884.25 | +3345.09 | +96.63 | +5 |

## CH2 lower, 279.04–299.19 s

Track `sha256:35a172746665615f517c6a9147bc316bc194acda5b535f760c0ed4469620263f`; 21 observations; 466 nominal-time satellites scored. Training leader: **STARLINK-3182 (NORAD 51469)**; heldout rank 2 in the full scored population.

Against the best other heldout candidate, STARLINK-37359 (NORAD 69188): leader heldout RMS **656.51 Hz** versus **38.95 Hz**; gain **-617.56 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-3182 | 51469 | 1 | 2 | 142.95 | 656.51 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-37359 | 69188 | 2 | 1 | 156.17 | 38.95 | +13.22 | -617.56 | -1585.55 | -2 |
| STARLINK-3998 | 52610 | 3 | 4 | 355.49 | 2052.40 | +212.54 | +1395.88 | +68.01 | +5 |
| STARLINK-32189 | 60317 | 4 | — | 732.51 | 3788.76 | +589.56 | +3132.25 | +82.67 | +1 |
| STARLINK-30114 | 56826 | 5 | 5 | 788.41 | 2613.25 | +645.46 | +1956.74 | +74.88 | +5 |
| STARLINK-11359 [DTC] | 61884 | — | 3 | 1698.52 | 2046.13 | +1555.57 | +1389.62 | +67.91 | +5 |

## CH3 upper, 74.50–118.37 s

Track `sha256:dad99294b8de308cd245ff73187c691b2c068aa4bdb5338ffbb87a3f42a0cc30`; 50 observations; 489 nominal-time satellites scored. Training leader: **STARLINK-35765 (NORAD 67041)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32182 (NORAD 60319): leader heldout RMS **87.62 Hz** versus **474.44 Hz**; gain **+386.81 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35765 | 67041 | 1 | 1 | 58.51 | 87.62 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-32182 | 60319 | 2 | 2 | 71.97 | 474.44 | +13.46 | +386.81 | +81.53 | -4 |
| STARLINK-37440 | 69189 | 3 | 4 | 445.64 | 3738.83 | +387.13 | +3651.21 | +97.66 | -3 |
| STARLINK-33989 | 63929 | 4 | 3 | 542.76 | 482.32 | +484.24 | +394.70 | +81.83 | +5 |
| STARLINK-2500 | 48485 | 5 | 5 | 1588.87 | 3777.54 | +1530.36 | +3689.92 | +97.68 | +5 |

## CH3 lower, 43.76–78.78 s

Track `sha256:1315f81420bf6a6eb7399fd78581b344ffae462b84f253bb3b8238884f3bc7e5`; 41 observations; 479 nominal-time satellites scored. Training leader: **STARLINK-33703 (NORAD 63418)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-1771 (NORAD 46384): leader heldout RMS **177.16 Hz** versus **3311.39 Hz**; gain **+3134.23 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33703 | 63418 | 1 | 1 | 74.88 | 177.16 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-5939 | 56015 | 2 | — | 698.78 | 7515.83 | +623.89 | +7338.67 | +97.64 | -5 |
| STARLINK-34721 | 65039 | 3 | 3 | 730.09 | 5132.03 | +655.20 | +4954.87 | +96.55 | +5 |
| STARLINK-2728 | 48478 | 4 | — | 1009.32 | 10495.43 | +934.44 | +10318.27 | +98.31 | +5 |
| STARLINK-5798 | 56040 | 5 | — | 2015.90 | 13573.70 | +1941.02 | +13396.54 | +98.69 | -5 |
| STARLINK-1771 | 46384 | — | 2 | 4287.92 | 3311.39 | +4213.04 | +3134.23 | +94.65 | +5 |
| STARLINK-4077 | 53154 | — | 4 | 3581.81 | 6667.91 | +3506.92 | +6490.75 | +97.34 | +5 |
| STARLINK-11419 [DTC] | 62883 | — | 5 | 6749.82 | 7076.83 | +6674.93 | +6899.67 | +97.50 | +5 |

## CH2 lower, 201.41–223.58 s

Track `sha256:4b3292aedcf64c37de3e22ff6f4800cba52bf1c9490516a004852298e0fe8fa0`; 26 observations; 467 nominal-time satellites scored. Training leader: **STARLINK-33980 (NORAD 63930)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32474 (NORAD 61260): leader heldout RMS **27.81 Hz** versus **1164.82 Hz**; gain **+1137.01 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33980 | 63930 | 1 | 1 | 112.74 | 27.81 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-3315 | 50848 | 2 | 3 | 306.67 | 2464.56 | +193.93 | +2436.75 | +98.87 | -5 |
| STARLINK-5834 | 57071 | 3 | 4 | 339.44 | 2682.75 | +226.70 | +2654.94 | +98.96 | -2 |
| STARLINK-31866 | 59668 | 4 | — | 560.37 | 4499.06 | +447.62 | +4471.25 | +99.38 | -5 |
| STARLINK-31325 | 59165 | 5 | — | 619.12 | 5296.59 | +506.37 | +5268.78 | +99.47 | +0 |
| STARLINK-32474 | 61260 | — | 2 | 1717.62 | 1164.82 | +1604.88 | +1137.01 | +97.61 | +5 |
| STARLINK-30958 | 58457 | — | 5 | 1374.08 | 3188.87 | +1261.34 | +3161.07 | +99.13 | +5 |
