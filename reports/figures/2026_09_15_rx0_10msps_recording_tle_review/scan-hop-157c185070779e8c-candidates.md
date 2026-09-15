# Candidate RMS comparisons: scan-hop-157c185070779e8c

Recorded **2026-09-14T18:30:12.754513Z**, RX0, 10 MS/s.

[Recording assessment and plots](scan-hop-157c185070779e8c.md).

Each track has its own training-selected leader; there is no single satellite assignment for the whole recording. Lower RMS is better. The same observations and chronological split are used for all candidates within a track.

Gain = alternative RMS − training-leader RMS. Positive gain favors the leader; negative heldout gain means the alternative predicts better. Percent gain uses the alternative RMS as denominator; it is not identification confidence. Tau and carrier offset were selected on training data and remain frozen on heldout.

The archived screen retained the top five training candidates and top five heldout candidates, whose union is listed below. Candidate counts describe the full scored population; names/scores outside these retained lists were not archived. A blank rank means outside that top-five list. Catalogue exclusions and control results are in the linked recording assessment and evidence.

## CH4 lower, 53.31–73.71 s

Track `sha256:5a76adef43092e92f9137727658420d98f2e501bcaf4eaac8799c159fe6cf8a0`; 27 observations; 492 nominal-time satellites scored. Training leader: **STARLINK-35530 (NORAD 65921)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37824 (NORAD 69956): leader heldout RMS **42.12 Hz** versus **5281.14 Hz**; gain **+5239.02 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35530 | 65921 | 1 | 1 | 40.06 | 42.12 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-11519 | 62560 | 2 | 3 | 1118.94 | 5592.92 | +1078.88 | +5550.80 | +99.25 | -5 |
| STARLINK-37824 | 69956 | 3 | 2 | 1401.40 | 5281.14 | +1361.34 | +5239.02 | +99.20 | -2 |
| STARLINK-4298 | 53177 | 4 | — | 2799.79 | 10167.99 | +2759.73 | +10125.87 | +99.59 | -5 |
| STARLINK-6179 | 56910 | 5 | — | 2851.28 | 9654.08 | +2811.23 | +9611.96 | +99.56 | -5 |
| STARLINK-32949 | 63145 | — | 4 | 2996.17 | 7480.66 | +2956.11 | +7438.54 | +99.44 | +5 |
| STARLINK-3305 | 50166 | — | 5 | 3132.27 | 8762.95 | +3092.21 | +8720.83 | +99.52 | +5 |

## CH2 lower, 89.47–114.66 s

Track `sha256:33a73e9081729d58e0b8ae3b2b2ca622290593682827b2565bcffedf6a81dbf0`; 29 observations; 508 nominal-time satellites scored. Training leader: **STARLINK-30604 (NORAD 58075)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4676 (NORAD 53598): leader heldout RMS **114.48 Hz** versus **1383.12 Hz**; gain **+1268.64 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30604 | 58075 | 1 | 1 | 61.67 | 114.48 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-4676 | 53598 | 2 | 2 | 344.69 | 1383.12 | +283.02 | +1268.64 | +91.72 | -5 |
| STARLINK-31131 | 58673 | 3 | 5 | 440.80 | 3352.97 | +379.13 | +3238.49 | +96.59 | -5 |
| STARLINK-32949 | 63145 | 4 | — | 488.96 | 3781.08 | +427.29 | +3666.60 | +96.97 | +3 |
| STARLINK-11657 | 63558 | 5 | — | 1130.41 | 8202.61 | +1068.74 | +8088.14 | +98.60 | +0 |
| STARLINK-38323 | 100518 | — | 3 | 1511.80 | 2631.49 | +1450.13 | +2517.02 | +95.65 | +5 |
| STARLINK-30593 | 58112 | — | 4 | 1388.08 | 3330.01 | +1326.41 | +3215.53 | +96.56 | -5 |

## CH1 lower, 133.57–162.27 s

Track `sha256:b0bdd2007854d5a133ef9f97e22d272642868361ae99bf82d4ea6d9c99bc5e80`; 39 observations; 509 nominal-time satellites scored. Training leader: **STARLINK-36638 (NORAD 67594)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30141 (NORAD 57620): leader heldout RMS **69.30 Hz** versus **1347.54 Hz**; gain **+1278.24 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36638 | 67594 | 1 | 1 | 31.17 | 69.30 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-30141 | 57620 | 2 | 2 | 834.56 | 1347.54 | +803.39 | +1278.24 | +94.86 | +0 |
| STARLINK-38323 | 100518 | 3 | 3 | 1141.48 | 4064.29 | +1110.31 | +3994.99 | +98.29 | -5 |
| STARLINK-11733 | 64072 | 4 | 4 | 1434.83 | 4157.48 | +1403.66 | +4088.18 | +98.33 | -5 |
| STARLINK-30554 | 58048 | 5 | 5 | 1444.90 | 4835.68 | +1413.73 | +4766.37 | +98.57 | -5 |

## CH1 upper, 134.07–161.51 s

Track `sha256:1e430a0ac5340bb100d5fe37e878210f46f76df1564716d129add0cc55c65dc7`; 38 observations; 506 nominal-time satellites scored. Training leader: **STARLINK-36638 (NORAD 67594)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30141 (NORAD 57620): leader heldout RMS **45.88 Hz** versus **1279.78 Hz**; gain **+1233.90 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36638 | 67594 | 1 | 1 | 62.62 | 45.88 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-30141 | 57620 | 2 | 2 | 792.61 | 1279.78 | +729.99 | +1233.90 | +96.42 | +0 |
| STARLINK-38323 | 100518 | 3 | 3 | 1101.68 | 3785.54 | +1039.05 | +3739.67 | +98.79 | -5 |
| STARLINK-11733 | 64072 | 4 | 4 | 1375.87 | 3900.77 | +1313.25 | +3854.89 | +98.82 | -5 |
| STARLINK-30554 | 58048 | 5 | 5 | 1390.28 | 4515.68 | +1327.66 | +4469.81 | +98.98 | -5 |

## CH2 lower, 187.72–215.71 s

Track `sha256:863a506e4d69538398cd83e828a6a214022fceed250baceecb9626a122144b22`; 31 observations; 513 nominal-time satellites scored. Training leader: **STARLINK-30081 (NORAD 57515)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-1470 (NORAD 45772): leader heldout RMS **33.05 Hz** versus **1311.13 Hz**; gain **+1278.08 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30081 | 57515 | 1 | 1 | 59.54 | 33.05 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-4640 | 53728 | 2 | 3 | 301.29 | 2623.89 | +241.75 | +2590.84 | +98.74 | -5 |
| STARLINK-31124 | 58674 | 3 | 5 | 1176.93 | 7818.26 | +1117.40 | +7785.21 | +99.58 | -5 |
| STARLINK-1470 | 45772 | 4 | 2 | 1385.07 | 1311.13 | +1325.53 | +1278.08 | +97.48 | +5 |
| STARLINK-34708 | 65062 | 5 | — | 2554.76 | 9392.76 | +2495.22 | +9359.71 | +99.65 | -1 |
| STARLINK-34011 | 63845 | — | 4 | 2717.27 | 5792.52 | +2657.74 | +5759.47 | +99.43 | +5 |

## CH4 lower, 198.31–223.52 s

Track `sha256:c749321cab23b49442a7d62e5b805677f0d3bddc80ed5a8a0b923602f0cc1298`; 31 observations; 511 nominal-time satellites scored. Training leader: **STARLINK-34011 (NORAD 63845)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30081 (NORAD 57515): leader heldout RMS **183.56 Hz** versus **1832.58 Hz**; gain **+1649.02 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34011 | 63845 | 1 | 1 | 63.12 | 183.56 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-37520 | 69819 | 2 | — | 497.48 | 4452.26 | +434.36 | +4268.70 | +95.88 | +5 |
| STARLINK-33663 | 63652 | 3 | 4 | 525.02 | 3736.27 | +461.91 | +3552.71 | +95.09 | +5 |
| STARLINK-4640 | 53728 | 4 | — | 617.57 | 6183.28 | +554.45 | +5999.72 | +97.03 | +5 |
| STARLINK-34708 | 65062 | 5 | — | 665.04 | 5682.97 | +601.92 | +5499.40 | +96.77 | -5 |
| STARLINK-30081 | 57515 | — | 2 | 2159.38 | 1832.58 | +2096.26 | +1649.02 | +89.98 | +5 |
| STARLINK-11096 | 59719 | — | 3 | 3865.60 | 2555.21 | +3802.49 | +2371.65 | +92.82 | +5 |
| STARLINK-1470 | 45772 | — | 5 | 810.18 | 3951.31 | +747.06 | +3767.74 | +95.35 | -5 |

## CH1 upper, 200.07–230.32 s

Track `sha256:a4f9959ba0de750b73237a900e71bb2281c47a631ca6c3140b1183241292377e`; 33 observations; 515 nominal-time satellites scored. Training leader: **STARLINK-34011 (NORAD 63845)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30081 (NORAD 57515): leader heldout RMS **206.64 Hz** versus **3032.13 Hz**; gain **+2825.49 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34011 | 63845 | 1 | 1 | 73.81 | 206.64 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-4640 | 53728 | 2 | — | 655.87 | 8757.03 | +582.06 | +8550.39 | +97.64 | +0 |
| STARLINK-33663 | 63652 | 3 | 4 | 815.27 | 6140.79 | +741.46 | +5934.15 | +96.63 | +5 |
| STARLINK-37520 | 69819 | 4 | — | 876.58 | 7543.61 | +802.77 | +7336.97 | +97.26 | +4 |
| STARLINK-1470 | 45772 | 5 | 3 | 1032.46 | 5924.51 | +958.66 | +5717.86 | +96.51 | -5 |
| STARLINK-30081 | 57515 | — | 2 | 1717.63 | 3032.13 | +1643.82 | +2825.49 | +93.18 | +5 |
| STARLINK-11096 | 59719 | — | 5 | 2850.52 | 7312.10 | +2776.71 | +7105.46 | +97.17 | +5 |

## CH1 lower, 201.08–230.45 s

Track `sha256:56f261936d56923bcc76f7b7b3949000ae0302e5b4a8f6b0c3b0486adc35d9ea`; 35 observations; 515 nominal-time satellites scored. Training leader: **STARLINK-34011 (NORAD 63845)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30081 (NORAD 57515): leader heldout RMS **136.05 Hz** versus **3554.79 Hz**; gain **+3418.74 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34011 | 63845 | 1 | 1 | 116.05 | 136.05 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-4640 | 53728 | 2 | 5 | 734.40 | 7055.01 | +618.35 | +6918.97 | +98.07 | -4 |
| STARLINK-33663 | 63652 | 3 | 4 | 1129.99 | 6283.39 | +1013.94 | +6147.34 | +97.83 | +5 |
| STARLINK-37520 | 69819 | 4 | — | 1273.17 | 7631.43 | +1157.12 | +7495.38 | +98.22 | +3 |
| STARLINK-1470 | 45772 | 5 | 3 | 1288.41 | 5996.17 | +1172.36 | +5860.13 | +97.73 | -5 |
| STARLINK-30081 | 57515 | — | 2 | 1433.60 | 3554.79 | +1317.55 | +3418.74 | +96.17 | +5 |

## CH2 lower, 241.93–276.20 s

Track `sha256:3202c6efa7e260525b0f3f0d525b013d60f48dd5cec6f5d176ac477ba34194fe`; 35 observations; 520 nominal-time satellites scored. Training leader: **STARLINK-30605 (NORAD 58101)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-6205 (NORAD 56898): leader heldout RMS **2156.54 Hz** versus **3408.32 Hz**; gain **+1251.78 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30605 | 58101 | 1 | 1 | 38.17 | 2156.54 | +0.00 | +0.00 | +0.00 | +1 |
| STARLINK-6205 | 56898 | 2 | 2 | 1176.40 | 3408.32 | +1138.23 | +1251.78 | +36.73 | +5 |
| STARLINK-31751 | 59574 | 3 | 3 | 2212.91 | 6901.13 | +2174.74 | +4744.60 | +68.75 | +5 |
| STARLINK-1470 | 45772 | 4 | — | 2286.83 | 13246.80 | +2248.66 | +11090.26 | +83.72 | -5 |
| STARLINK-37896 | 69970 | 5 | — | 3406.10 | 10591.12 | +3367.92 | +8434.58 | +79.64 | -5 |
| STARLINK-34249 | 65376 | — | 4 | 5898.52 | 9293.28 | +5860.35 | +7136.74 | +76.79 | +5 |
| STARLINK-2466 | 48125 | — | 5 | 6170.81 | 10256.71 | +6132.64 | +8100.18 | +78.97 | +5 |

## CH3 upper, 254.67–274.82 s

Track `sha256:df7d4e23a0417d86ca63b6f608e0a8ff1bae0d07df79f520d5c636ac6749ced4`; 21 observations; 509 nominal-time satellites scored. Training leader: **STARLINK-31751 (NORAD 59574)**; heldout rank 3 in the full scored population.

Against the best other heldout candidate, STARLINK-4007 (NORAD 52707): leader heldout RMS **1826.74 Hz** versus **1011.04 Hz**; gain **-815.70 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31751 | 59574 | 1 | 3 | 14.56 | 1826.74 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-6205 | 56898 | 2 | — | 554.10 | 4254.47 | +539.53 | +2427.72 | +57.06 | -5 |
| STARLINK-4007 | 52707 | 3 | 1 | 746.29 | 1011.04 | +731.73 | -815.70 | -80.68 | -1 |
| STARLINK-34249 | 65376 | 4 | — | 749.51 | 2892.91 | +734.95 | +1066.16 | +36.85 | +5 |
| STARLINK-37896 | 69970 | 5 | 4 | 895.12 | 1879.00 | +880.56 | +52.25 | +2.78 | -5 |
| STARLINK-4405 | 53201 | — | 2 | 2092.18 | 1680.64 | +2077.62 | -146.10 | -8.69 | +5 |
| STARLINK-35887 | 66959 | — | 5 | 1252.24 | 2207.40 | +1237.68 | +380.65 | +17.24 | +4 |

## CH2 upper, 254.79–277.96 s

Track `sha256:ed1cfb6665a555ee0b2b389d81740364707b45ed1846c9a924751d7dacc9e275`; 24 observations; 512 nominal-time satellites scored. Training leader: **STARLINK-31751 (NORAD 59574)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-6205 (NORAD 56898): leader heldout RMS **648.69 Hz** versus **1008.54 Hz**; gain **+359.85 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31751 | 59574 | 1 | 1 | 669.19 | 648.69 | +0.00 | +0.00 | +0.00 | -5 |
| STARLINK-34249 | 65376 | 2 | — | 837.42 | 2383.05 | +168.23 | +1734.37 | +72.78 | +5 |
| STARLINK-6205 | 56898 | 3 | 2 | 952.05 | 1008.54 | +282.86 | +359.85 | +35.68 | +5 |
| STARLINK-2466 | 48125 | 4 | 3 | 1018.96 | 1730.95 | +349.77 | +1082.26 | +62.52 | +5 |
| STARLINK-4007 | 52707 | 5 | 5 | 1096.63 | 2324.71 | +427.44 | +1676.02 | +72.10 | -3 |
| STARLINK-4405 | 53201 | — | 4 | 2192.32 | 1968.26 | +1523.13 | +1319.58 | +67.04 | +5 |

## CH1 lower, 274.06–299.76 s

Track `sha256:98630ad987193e0832be525d7316c12e7af7f3bec69770f5ad2b10ee8b07bcdb`; 33 observations; 518 nominal-time satellites scored. Training leader: **STARLINK-34249 (NORAD 65376)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-38277 (NORAD 100507): leader heldout RMS **58.10 Hz** versus **771.38 Hz**; gain **+713.28 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34249 | 65376 | 1 | 1 | 28.55 | 58.10 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-2466 | 48125 | 2 | 3 | 169.45 | 1139.72 | +140.90 | +1081.62 | +94.90 | +4 |
| STARLINK-38277 | 100507 | 3 | 2 | 257.13 | 771.38 | +228.58 | +713.28 | +92.47 | +5 |
| STARLINK-4405 | 53201 | 4 | 4 | 410.47 | 3010.96 | +381.92 | +2952.86 | +98.07 | -1 |
| STARLINK-30605 | 58101 | 5 | 5 | 1710.71 | 8147.52 | +1682.16 | +8089.42 | +99.29 | -5 |

## CH1 upper, 275.70–300.01 s

Track `sha256:d486d4f8eba18132db6909264f3d2e7d028ff9a16f58a179ffcf09afec6ecc32`; 31 observations; 515 nominal-time satellites scored. Training leader: **STARLINK-34249 (NORAD 65376)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-38277 (NORAD 100507): leader heldout RMS **63.57 Hz** versus **954.35 Hz**; gain **+890.78 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34249 | 65376 | 1 | 1 | 107.66 | 63.57 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-2466 | 48125 | 2 | 3 | 166.26 | 1108.29 | +58.60 | +1044.72 | +94.26 | +4 |
| STARLINK-38277 | 100507 | 3 | 2 | 199.35 | 954.35 | +91.69 | +890.78 | +93.34 | +5 |
| STARLINK-4405 | 53201 | 4 | 4 | 407.70 | 2887.05 | +300.03 | +2823.48 | +97.80 | -2 |
| STARLINK-30605 | 58101 | 5 | — | 1742.38 | 8173.45 | +1634.72 | +8109.88 | +99.22 | -5 |
| STARLINK-32520 | 62021 | — | 5 | 4197.64 | 8151.27 | +4089.98 | +8087.70 | +99.22 | +5 |
