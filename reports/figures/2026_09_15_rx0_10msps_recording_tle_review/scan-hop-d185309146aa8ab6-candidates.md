# Candidate RMS comparisons: scan-hop-d185309146aa8ab6

Recorded **2026-09-14T20:30:12.780413Z**, RX0, 10 MS/s.

[Recording assessment and plots](scan-hop-d185309146aa8ab6.md).

Each track has its own training-selected leader; there is no single satellite assignment for the whole recording. Lower RMS is better. The same observations and chronological split are used for all candidates within a track.

Gain = alternative RMS − training-leader RMS. Positive gain favors the leader; negative heldout gain means the alternative predicts better. Percent gain uses the alternative RMS as denominator; it is not identification confidence. Tau and carrier offset were selected on training data and remain frozen on heldout.

The archived screen retained the top five training candidates and top five heldout candidates, whose union is listed below. Candidate counts describe the full scored population; names/scores outside these retained lists were not archived. A blank rank means outside that top-five list. Catalogue exclusions and control results are in the linked recording assessment and evidence.

## CH3 lower, 72.44–125.20 s

Track `sha256:63f042f1e1ede9d3a8bf0f2c245f7427db39b48f2ed78f3a8c616da3e7a67b77`; 61 observations; 494 nominal-time satellites scored. Training leader: **STARLINK-35979 (NORAD 66809)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-2697 (NORAD 48474): leader heldout RMS **76.62 Hz** versus **481.17 Hz**; gain **+404.56 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35979 | 66809 | 1 | 1 | 63.09 | 76.62 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-2697 | 48474 | 2 | 2 | 67.73 | 481.17 | +4.64 | +404.56 | +84.08 | +1 |
| STARLINK-30961 | 58445 | 3 | 3 | 168.20 | 1559.32 | +105.11 | +1482.71 | +95.09 | -5 |
| STARLINK-4111 | 53159 | 4 | — | 897.09 | 7956.17 | +834.00 | +7879.55 | +99.04 | -5 |
| STARLINK-35103 | 65633 | 5 | — | 1381.24 | 9608.59 | +1318.15 | +9531.98 | +99.20 | -5 |
| STARLINK-31346 | 58943 | — | 4 | 1908.43 | 1860.54 | +1845.34 | +1783.92 | +95.88 | +5 |
| STARLINK-35776 | 66282 | — | 5 | 1699.52 | 7667.17 | +1636.43 | +7590.55 | +99.00 | +5 |

## CH3 upper, 75.09–97.63 s

Track `sha256:5106b52fbde7c35ee041c64a4eb058e1513fe16250acfc67150beeab1071d4f9`; 28 observations; 473 nominal-time satellites scored. Training leader: **STARLINK-35979 (NORAD 66809)**; heldout rank 2 in the full scored population.

Against the best other heldout candidate, STARLINK-2697 (NORAD 48474): leader heldout RMS **103.95 Hz** versus **59.69 Hz**; gain **-44.26 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35979 | 66809 | 1 | 2 | 52.93 | 103.95 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-2697 | 48474 | 2 | 1 | 62.45 | 59.69 | +9.52 | -44.26 | -74.16 | +1 |
| STARLINK-30961 | 58445 | 3 | 3 | 72.16 | 394.39 | +19.22 | +290.43 | +73.64 | -4 |
| STARLINK-35103 | 65633 | 4 | 5 | 103.35 | 1566.70 | +50.42 | +1462.75 | +93.36 | -5 |
| STARLINK-4111 | 53159 | 5 | 4 | 265.24 | 734.16 | +212.31 | +630.21 | +85.84 | -5 |

## CH3 upper, 139.82–171.21 s

Track `sha256:b70d3dd01e1772fd7359cb7b55f64a9ebda3de9102a2b51371b3f510568ffcfc`; 41 observations; 478 nominal-time satellites scored. Training leader: **STARLINK-2525 (NORAD 48482)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-36968 (NORAD 67995): leader heldout RMS **82.05 Hz** versus **4479.95 Hz**; gain **+4397.90 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-2525 | 48482 | 1 | 1 | 96.37 | 82.05 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-36968 | 67995 | 2 | 2 | 401.80 | 4479.95 | +305.43 | +4397.90 | +98.17 | +5 |
| STARLINK-33711 | 63404 | 3 | 3 | 473.56 | 4981.33 | +377.19 | +4899.28 | +98.35 | -3 |
| STARLINK-32651 | 62314 | 4 | — | 755.19 | 7764.71 | +658.82 | +7682.65 | +98.94 | -5 |
| STARLINK-3181 | 51461 | 5 | 5 | 817.94 | 7708.61 | +721.57 | +7626.56 | +98.94 | +5 |
| STARLINK-4185 | 53139 | — | 4 | 1117.40 | 6349.21 | +1021.02 | +6267.16 | +98.71 | +5 |

## CH3 lower, 141.58–168.56 s

Track `sha256:87fb6d88a62c97f7be6dbb2fe68ce70d3a457f6dfa261e423bbe5d10ca65a24c`; 35 observations; 476 nominal-time satellites scored. Training leader: **STARLINK-2525 (NORAD 48482)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-36968 (NORAD 67995): leader heldout RMS **19.99 Hz** versus **3733.23 Hz**; gain **+3713.24 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-2525 | 48482 | 1 | 1 | 32.88 | 19.99 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-36968 | 67995 | 2 | 2 | 389.55 | 3733.23 | +356.67 | +3713.24 | +99.46 | +5 |
| STARLINK-33711 | 63404 | 3 | 3 | 478.78 | 4163.34 | +445.89 | +4143.35 | +99.52 | -3 |
| STARLINK-32651 | 62314 | 4 | — | 581.16 | 6449.38 | +548.28 | +6429.39 | +99.69 | -5 |
| STARLINK-3181 | 51461 | 5 | 5 | 590.92 | 5826.58 | +558.03 | +5806.59 | +99.66 | +4 |
| STARLINK-4185 | 53139 | — | 4 | 754.80 | 5188.93 | +721.92 | +5168.94 | +99.61 | +5 |

## CH2 upper, 181.03–205.87 s

Track `sha256:462fda81d90b6c559354894ff6927c1311cc8edf3c39b68dee617368dc0f4522`; 26 observations; 476 nominal-time satellites scored. Training leader: **STARLINK-31858 (NORAD 59658)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4174 (NORAD 53276): leader heldout RMS **70.03 Hz** versus **1025.83 Hz**; gain **+955.80 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31858 | 59658 | 1 | 1 | 24.19 | 70.03 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-4174 | 53276 | 2 | 2 | 87.38 | 1025.83 | +63.19 | +955.80 | +93.17 | -5 |
| STARLINK-11447 | 62418 | 3 | 3 | 187.58 | 2189.23 | +163.38 | +2119.21 | +96.80 | -3 |
| STARLINK-34693 | 64793 | 4 | — | 418.13 | 4012.01 | +393.94 | +3941.98 | +98.25 | -2 |
| STARLINK-35732 | 67037 | 5 | — | 529.68 | 5337.67 | +505.49 | +5267.64 | +98.69 | +5 |
| STARLINK-3230 | 50845 | — | 4 | 842.87 | 2452.78 | +818.68 | +2382.75 | +97.15 | -5 |
| STARLINK-4050 | 53274 | — | 5 | 966.92 | 3514.14 | +942.73 | +3444.11 | +98.01 | +5 |

## CH2 lower, 184.18–224.13 s

Track `sha256:241297c8338eb0f762a49493fbda8cd8155a2481f755c8dc75e2886533db27a3`; 42 observations; 487 nominal-time satellites scored. Training leader: **STARLINK-31858 (NORAD 59658)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-3230 (NORAD 50845): leader heldout RMS **77.74 Hz** versus **3593.88 Hz**; gain **+3516.14 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31858 | 59658 | 1 | 1 | 56.84 | 77.74 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-4174 | 53276 | 2 | 3 | 441.88 | 4434.89 | +385.05 | +4357.14 | +98.25 | -1 |
| STARLINK-3230 | 50845 | 3 | 2 | 1283.41 | 3593.88 | +1226.58 | +3516.14 | +97.84 | -5 |
| STARLINK-11447 | 62418 | 4 | — | 1333.07 | 8866.37 | +1276.23 | +8788.62 | +99.12 | -1 |
| STARLINK-35732 | 67037 | 5 | — | 1611.38 | 13648.79 | +1554.54 | +13571.05 | +99.43 | -5 |
| STARLINK-36846 | 67894 | — | 4 | 1975.62 | 6029.44 | +1918.78 | +5951.70 | +98.71 | +5 |
| STARLINK-4050 | 53274 | — | 5 | 1872.63 | 6706.09 | +1815.79 | +6628.34 | +98.84 | +5 |

## CH4 lower, 185.82–211.53 s

Track `sha256:bbc62de12f03c7ca6c4166546b10ffd442eafa235550d9843273216f49739039`; 28 observations; 474 nominal-time satellites scored. Training leader: **STARLINK-34693 (NORAD 64793)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37380 (NORAD 69182): leader heldout RMS **34.76 Hz** versus **1334.79 Hz**; gain **+1300.04 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34693 | 64793 | 1 | 1 | 44.97 | 34.76 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-35732 | 67037 | 2 | 4 | 187.73 | 2225.59 | +142.77 | +2190.83 | +98.44 | +4 |
| STARLINK-4050 | 53274 | 3 | — | 258.01 | 2876.77 | +213.04 | +2842.01 | +98.79 | +5 |
| STARLINK-2525 | 48482 | 4 | — | 315.07 | 3491.81 | +270.10 | +3457.05 | +99.00 | -3 |
| STARLINK-36846 | 67894 | 5 | — | 319.20 | 2896.21 | +274.23 | +2861.46 | +98.80 | +5 |
| STARLINK-37380 | 69182 | — | 2 | 1292.39 | 1334.79 | +1247.42 | +1300.04 | +97.40 | +5 |
| STARLINK-35447 | 66589 | — | 3 | 1357.07 | 1907.78 | +1312.11 | +1873.02 | +98.18 | +5 |
| STARLINK-34666 | 64794 | — | 5 | 462.72 | 2437.36 | +417.76 | +2402.60 | +98.57 | -5 |

## CH1 lower, 229.54–253.62 s

Track `sha256:f8e66db6ebc262d9735ab9c04a9beff1241a6730753fb83b99963e2222f158dc`; 28 observations; 469 nominal-time satellites scored. Training leader: **STARLINK-33760 (NORAD 63764)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37380 (NORAD 69182): leader heldout RMS **73.63 Hz** versus **3112.63 Hz**; gain **+3039.00 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33760 | 63764 | 1 | 1 | 87.75 | 73.63 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-37380 | 69182 | 2 | 2 | 616.44 | 3112.63 | +528.69 | +3039.00 | +97.63 | -5 |
| STARLINK-11623 | 63276 | 3 | 4 | 640.21 | 5777.27 | +552.45 | +5703.63 | +98.73 | +4 |
| STARLINK-11138 | 59949 | 4 | — | 1105.94 | 7676.37 | +1018.19 | +7602.74 | +99.04 | -5 |
| STARLINK-36846 | 67894 | 5 | 5 | 1899.04 | 7298.04 | +1811.29 | +7224.41 | +98.99 | -5 |
| STARLINK-33652 | 63400 | — | 3 | 2693.29 | 5608.06 | +2605.54 | +5534.43 | +98.69 | +5 |

## CH4 upper, 265.70–298.95 s

Track `sha256:30a111c1f0b069bef98a3f41978a3e4a92f8689ca307d33ced832fec017986d6`; 44 observations; 480 nominal-time satellites scored. Training leader: **STARLINK-32209 (NORAD 60590)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11623 (NORAD 63276): leader heldout RMS **79.87 Hz** versus **3384.37 Hz**; gain **+3304.50 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32209 | 60590 | 1 | 1 | 89.11 | 79.87 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-36991 | 68011 | 2 | 5 | 967.31 | 7232.85 | +878.19 | +7152.98 | +98.90 | -4 |
| STARLINK-33652 | 63400 | 3 | — | 1661.69 | 11237.35 | +1572.58 | +11157.48 | +99.29 | -5 |
| STARLINK-32886 | 62807 | 4 | 3 | 1847.66 | 5273.89 | +1758.55 | +5194.03 | +98.49 | +5 |
| STARLINK-6237 | 57055 | 5 | 4 | 2258.68 | 6307.96 | +2169.57 | +6228.09 | +98.73 | +5 |
| STARLINK-11623 | 63276 | — | 2 | 4286.89 | 3384.37 | +4197.78 | +3304.50 | +97.64 | +5 |

## CH4 lower, 265.83–299.96 s

Track `sha256:5736c21f5b6461e5737f003cd5b4ae462a2a8dfe78c46df54f104892dea4270b`; 45 observations; 481 nominal-time satellites scored. Training leader: **STARLINK-32209 (NORAD 60590)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11623 (NORAD 63276): leader heldout RMS **82.09 Hz** versus **3843.48 Hz**; gain **+3761.39 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32209 | 60590 | 1 | 1 | 89.70 | 82.09 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-36991 | 68011 | 2 | 5 | 1085.82 | 7740.06 | +996.12 | +7657.97 | +98.94 | -4 |
| STARLINK-33652 | 63400 | 3 | — | 1841.95 | 11970.10 | +1752.25 | +11888.00 | +99.31 | -5 |
| STARLINK-32886 | 62807 | 4 | 3 | 1898.66 | 5355.31 | +1808.96 | +5273.22 | +98.47 | +5 |
| STARLINK-6237 | 57055 | 5 | 4 | 2319.61 | 6392.95 | +2229.91 | +6310.86 | +98.72 | +5 |
| STARLINK-11623 | 63276 | — | 2 | 4210.98 | 3843.48 | +4121.28 | +3761.39 | +97.86 | +5 |
