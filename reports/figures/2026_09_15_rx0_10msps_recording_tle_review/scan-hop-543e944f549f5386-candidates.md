# Candidate RMS comparisons: scan-hop-543e944f549f5386

[Ranked RMS plots for every track](scan-hop-543e944f549f5386-rms.md).

Recorded **2026-09-14T17:30:12.494100Z**, RX0, 10 MS/s.

[Recording assessment and plots](scan-hop-543e944f549f5386.md).

Each track has its own training-selected leader; there is no single satellite assignment for the whole recording. Lower RMS is better. The same observations and chronological split are used for all candidates within a track.

Gain = alternative RMS − training-leader RMS. Positive gain favors the leader; negative heldout gain means the alternative predicts better. Percent gain uses the alternative RMS as denominator; it is not identification confidence. Tau and carrier offset were selected on training data and remain frozen on heldout.

The archived screen retained the top five training candidates and top five heldout candidates, whose union is listed below. Candidate counts describe the full scored population; names/scores outside these retained lists were not archived. A blank rank means outside that top-five list. Catalogue exclusions and control results are in the linked recording assessment and evidence.

## CH1 upper, 0.53–25.35 s

Track `sha256:a2d95307dd8420daffe961cf247ad376a43f6855d56c7b37db5c8012619c070b`; 25 observations; 525 nominal-time satellites scored. Training leader: **STARLINK-38188 (NORAD 100233)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30941 (NORAD 58475): leader heldout RMS **424.09 Hz** versus **15020.00 Hz**; gain **+14595.91 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-38188 | 100233 | 1 | 1 | 101.53 | 424.09 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-30941 | 58475 | 2 | 2 | 5201.50 | 15020.00 | +5099.97 | +14595.91 | +97.18 | +0 |
| STARLINK-5769 | 55585 | 3 | 3 | 5421.60 | 15766.89 | +5320.07 | +15342.80 | +97.31 | +0 |
| STARLINK-11489 | 62271 | 4 | 4 | 7580.42 | 21639.58 | +7478.89 | +21215.49 | +98.04 | +5 |
| STARLINK-30987 | 58487 | 5 | — | 7994.03 | 26464.85 | +7892.50 | +26040.76 | +98.40 | -5 |
| STARLINK-37437 | 69170 | — | 5 | 8188.12 | 21909.30 | +8086.59 | +21485.21 | +98.06 | +5 |

## CH4 lower, 64.79–99.96 s

Track `sha256:53cefcf797b8027a3dd3931709038d8e7076c738ab9613ff13f06c681a07d6e3`; 38 observations; 527 nominal-time satellites scored. Training leader: **STARLINK-32810 (NORAD 63037)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11529 (NORAD 62599): leader heldout RMS **249.30 Hz** versus **446.33 Hz**; gain **+197.03 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32810 | 63037 | 1 | 1 | 144.55 | 249.30 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-11529 | 62599 | 2 | 2 | 321.54 | 446.33 | +176.99 | +197.03 | +44.14 | -5 |
| STARLINK-35021 | 65282 | 3 | 3 | 596.23 | 780.46 | +451.68 | +531.16 | +68.06 | -5 |
| STARLINK-36559 | 67555 | 4 | 4 | 856.49 | 8451.79 | +711.94 | +8202.49 | +97.05 | -5 |
| STARLINK-4591 | 53607 | 5 | — | 1570.07 | 11718.27 | +1425.52 | +11468.97 | +97.87 | -5 |
| STARLINK-35597 | 66493 | — | 5 | 2228.36 | 9443.98 | +2083.81 | +9194.68 | +97.36 | +5 |

## CH4 upper, 66.43–98.95 s

Track `sha256:80ec96e60448f3b9990e2fdfe46e386cdd664567c63dd37e53de0df65fd1ac72`; 35 observations; 526 nominal-time satellites scored. Training leader: **STARLINK-32810 (NORAD 63037)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11529 (NORAD 62599): leader heldout RMS **264.73 Hz** versus **412.37 Hz**; gain **+147.64 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32810 | 63037 | 1 | 1 | 116.23 | 264.73 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-11529 | 62599 | 2 | 2 | 247.03 | 412.37 | +130.79 | +147.64 | +35.80 | -5 |
| STARLINK-35021 | 65282 | 3 | 3 | 511.54 | 704.13 | +395.31 | +439.41 | +62.40 | -5 |
| STARLINK-36559 | 67555 | 4 | 4 | 996.39 | 7997.03 | +880.15 | +7732.30 | +96.69 | -5 |
| STARLINK-4591 | 53607 | 5 | — | 1815.99 | 11018.16 | +1699.75 | +10753.43 | +97.60 | -5 |
| STARLINK-35597 | 66493 | — | 5 | 2294.93 | 8764.36 | +2178.70 | +8499.63 | +96.98 | +5 |

## CH2 lower, 75.63–98.69 s

Track `sha256:0e7af997abbb6199dfbddbef919913de66e9f93638804252a3b78ef0f980e725`; 25 observations; 518 nominal-time satellites scored. Training leader: **STARLINK-32810 (NORAD 63037)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-35021 (NORAD 65282): leader heldout RMS **104.25 Hz** versus **162.59 Hz**; gain **+58.33 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32810 | 63037 | 1 | 1 | 31.09 | 104.25 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-11529 | 62599 | 2 | 3 | 64.32 | 625.20 | +33.23 | +520.95 | +83.32 | -5 |
| STARLINK-35021 | 65282 | 3 | 2 | 231.53 | 162.59 | +200.43 | +58.33 | +35.88 | -5 |
| STARLINK-36559 | 67555 | 4 | — | 1750.21 | 7681.96 | +1719.11 | +7577.70 | +98.64 | -5 |
| STARLINK-35597 | 66493 | 5 | — | 2100.94 | 6953.06 | +2069.85 | +6848.81 | +98.50 | +5 |
| STARLINK-11231 | 61057 | — | 4 | 4310.85 | 6276.85 | +4279.76 | +6172.60 | +98.34 | +5 |
| STARLINK-30897 | 58360 | — | 5 | 2614.85 | 6865.55 | +2583.75 | +6761.29 | +98.48 | +5 |

## CH1 lower, 82.57–108.14 s

Track `sha256:0e09ddac785ef9b6073754044c77b16f7cf2103980eeb9cfcec61d95a290b474`; 29 observations; 523 nominal-time satellites scored. Training leader: **STARLINK-35021 (NORAD 65282)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32810 (NORAD 63037): leader heldout RMS **56.46 Hz** versus **198.65 Hz**; gain **+142.19 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35021 | 65282 | 1 | 1 | 31.78 | 56.46 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-32810 | 63037 | 2 | 2 | 78.42 | 198.65 | +46.63 | +142.19 | +71.58 | +5 |
| STARLINK-11529 | 62599 | 3 | 3 | 82.99 | 308.94 | +51.21 | +252.48 | +81.73 | -5 |
| STARLINK-11231 | 61057 | 4 | 4 | 2027.26 | 1165.89 | +1995.47 | +1109.43 | +95.16 | +5 |
| STARLINK-35597 | 66493 | 5 | — | 2299.49 | 5087.37 | +2267.71 | +5030.91 | +98.89 | -3 |
| STARLINK-30897 | 58360 | — | 5 | 2318.91 | 4376.71 | +2287.12 | +4320.25 | +98.71 | +5 |

## CH4 lower, 143.15–163.80 s

Track `sha256:9a4fe2dda0100112a45e835999af2f18a080ad9ebff3d7c387332a835f6909c9`; 22 observations; 520 nominal-time satellites scored. Training leader: **STARLINK-34511 (NORAD 65214)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-2419 (NORAD 47830): leader heldout RMS **153.64 Hz** versus **3176.03 Hz**; gain **+3022.40 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34511 | 65214 | 1 | 1 | 75.60 | 153.64 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-2419 | 47830 | 2 | 2 | 572.62 | 3176.03 | +497.02 | +3022.40 | +95.16 | -3 |
| STARLINK-4655 | 53613 | 3 | 5 | 841.48 | 4446.43 | +765.87 | +4292.80 | +96.54 | -5 |
| STARLINK-6195 | 56902 | 4 | — | 1139.61 | 4636.40 | +1064.00 | +4482.76 | +96.69 | +5 |
| STARLINK-34052 | 63874 | 5 | — | 1402.18 | 7700.48 | +1326.58 | +7546.84 | +98.00 | -5 |
| STARLINK-36317 | 67736 | — | 3 | 1788.26 | 3374.85 | +1712.65 | +3221.21 | +95.45 | +5 |
| STARLINK-11510 | 62516 | — | 4 | 3045.20 | 3573.06 | +2969.60 | +3419.43 | +95.70 | +5 |

## CH3 lower, 143.40–173.49 s

Track `sha256:34d860d5bc664ae9ed41f024a8b99254b0b434b4bf22c73d552cd820974eeb49`; 30 observations; 533 nominal-time satellites scored. Training leader: **STARLINK-34511 (NORAD 65214)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-36317 (NORAD 67736): leader heldout RMS **75.67 Hz** versus **2038.62 Hz**; gain **+1962.95 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34511 | 65214 | 1 | 1 | 77.50 | 75.67 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-2419 | 47830 | 2 | 4 | 1137.04 | 5567.13 | +1059.54 | +5491.45 | +98.64 | -5 |
| STARLINK-4655 | 53613 | 3 | — | 1645.41 | 8258.82 | +1567.90 | +8183.15 | +99.08 | -5 |
| STARLINK-6195 | 56902 | 4 | — | 1884.80 | 7625.41 | +1807.30 | +7549.74 | +99.01 | +5 |
| STARLINK-36317 | 67736 | 5 | 2 | 2086.48 | 2038.62 | +2008.97 | +1962.95 | +96.29 | +5 |
| STARLINK-11510 | 62516 | — | 3 | 3037.42 | 3435.39 | +2959.92 | +3359.71 | +97.80 | +5 |
| STARLINK-2399 | 47816 | — | 5 | 3607.88 | 7143.29 | +3530.38 | +7067.62 | +98.94 | +5 |

## CH3 upper, 144.54–165.69 s

Track `sha256:0699eb7ed38f7c41088d8dd3b7c9048a662fe10de7b4ec9678bb7454c731d20b`; 22 observations; 524 nominal-time satellites scored. Training leader: **STARLINK-34511 (NORAD 65214)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11510 (NORAD 62516): leader heldout RMS **132.32 Hz** versus **1854.69 Hz**; gain **+1722.37 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34511 | 65214 | 1 | 1 | 69.97 | 132.32 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-2419 | 47830 | 2 | 4 | 731.89 | 3608.48 | +661.92 | +3476.16 | +96.33 | -4 |
| STARLINK-4655 | 53613 | 3 | — | 1062.95 | 5157.76 | +992.98 | +5025.44 | +97.43 | -5 |
| STARLINK-6195 | 56902 | 4 | 5 | 1288.87 | 5096.17 | +1218.90 | +4963.85 | +97.40 | +5 |
| STARLINK-36317 | 67736 | 5 | 3 | 1623.98 | 2705.08 | +1554.01 | +2572.76 | +95.11 | +5 |
| STARLINK-11510 | 62516 | — | 2 | 2503.92 | 1854.69 | +2433.95 | +1722.37 | +92.87 | +5 |

## CH4 lower, 192.76–233.08 s

Track `sha256:86ee1436cab88b46d0ed68a1e477c6ebb13d1072f5c8c0b794cd488e63d263bb`; 44 observations; 550 nominal-time satellites scored. Training leader: **STARLINK-32590 (NORAD 63047)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-33812 (NORAD 63879): leader heldout RMS **65.22 Hz** versus **3757.12 Hz**; gain **+3691.90 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32590 | 63047 | 1 | 1 | 25.19 | 65.22 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-33812 | 63879 | 2 | 2 | 475.49 | 3757.12 | +450.30 | +3691.90 | +98.26 | -5 |
| STARLINK-30979 | 58485 | 3 | 4 | 855.16 | 5957.67 | +829.97 | +5892.46 | +98.91 | +2 |
| STARLINK-31434 | 59215 | 4 | 5 | 1535.63 | 11868.73 | +1510.43 | +11803.52 | +99.45 | -5 |
| STARLINK-36317 | 67736 | 5 | — | 1885.75 | 12994.10 | +1860.55 | +12928.89 | +99.50 | -4 |
| STARLINK-11536 | 62563 | — | 3 | 6195.01 | 5080.10 | +6169.81 | +5014.88 | +98.72 | +5 |

## CH4 upper, 206.63–232.95 s

Track `sha256:55191935c1d93590b997654783226214c294573686435f31f1eb7f72b3b0bffe`; 30 observations; 544 nominal-time satellites scored. Training leader: **STARLINK-32590 (NORAD 63047)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30979 (NORAD 58485): leader heldout RMS **105.59 Hz** versus **3379.08 Hz**; gain **+3273.48 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32590 | 63047 | 1 | 1 | 30.08 | 105.59 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-33812 | 63879 | 2 | 3 | 936.41 | 3770.85 | +906.33 | +3665.25 | +97.20 | -5 |
| STARLINK-11536 | 62563 | 3 | 5 | 1024.64 | 7326.33 | +994.57 | +7220.74 | +98.56 | +3 |
| STARLINK-30979 | 58485 | 4 | 2 | 1186.84 | 3379.08 | +1156.76 | +3273.48 | +96.88 | -5 |
| STARLINK-31434 | 59215 | 5 | — | 2976.00 | 11052.67 | +2945.92 | +10947.07 | +99.04 | -5 |
| STARLINK-30510 | 57981 | — | 4 | 3146.65 | 5876.22 | +3116.57 | +5770.62 | +98.20 | +5 |

## CH2 lower, 207.01–230.81 s

Track `sha256:9b6d7c2c22ace870650c15f7fea7dc32a007ee482e6324494880c70531155a42`; 27 observations; 542 nominal-time satellites scored. Training leader: **STARLINK-32590 (NORAD 63047)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30979 (NORAD 58485): leader heldout RMS **65.94 Hz** versus **3044.99 Hz**; gain **+2979.05 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32590 | 63047 | 1 | 1 | 76.35 | 65.94 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-33812 | 63879 | 2 | 3 | 809.21 | 3248.06 | +732.85 | +3182.12 | +97.97 | -5 |
| STARLINK-11536 | 62563 | 3 | 5 | 835.94 | 5778.44 | +759.59 | +5712.49 | +98.86 | +3 |
| STARLINK-30979 | 58485 | 4 | 2 | 1068.90 | 3044.99 | +992.55 | +2979.05 | +97.83 | -5 |
| STARLINK-31434 | 59215 | 5 | — | 2589.78 | 9687.49 | +2513.43 | +9621.55 | +99.32 | -5 |
| STARLINK-30510 | 57981 | — | 4 | 2902.06 | 5767.57 | +2825.71 | +5701.63 | +98.86 | +5 |

## CH2 upper, 209.15–230.69 s

Track `sha256:c82ec090db4db82ab3c3e1441a6f3784af8342633270bdb607e3f8d16738dc88`; 25 observations; 540 nominal-time satellites scored. Training leader: **STARLINK-32590 (NORAD 63047)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30979 (NORAD 58485): leader heldout RMS **76.19 Hz** versus **2826.83 Hz**; gain **+2750.64 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32590 | 63047 | 1 | 1 | 70.89 | 76.19 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-11536 | 62563 | 2 | 5 | 683.23 | 5136.31 | +612.33 | +5060.12 | +98.52 | +2 |
| STARLINK-33812 | 63879 | 3 | 3 | 823.72 | 3141.34 | +752.82 | +3065.15 | +97.57 | -5 |
| STARLINK-30979 | 58485 | 4 | 2 | 979.58 | 2826.83 | +908.69 | +2750.64 | +97.30 | -5 |
| STARLINK-30510 | 57981 | 5 | 4 | 2465.24 | 4975.17 | +2394.34 | +4898.98 | +98.47 | +5 |

## CH3 lower, 244.17–266.96 s

Track `sha256:ca09ffde373cb6f1dad61f6220f9ff6075b32b10636cd783c0b25b6797a41ad4`; 25 observations; 546 nominal-time satellites scored. Training leader: **STARLINK-35027 (NORAD 65466)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4660 (NORAD 53609): leader heldout RMS **110.63 Hz** versus **1046.89 Hz**; gain **+936.26 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35027 | 65466 | 1 | 1 | 55.29 | 110.63 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-31568 | 59412 | 2 | 3 | 192.02 | 2401.22 | +136.72 | +2290.59 | +95.39 | +2 |
| STARLINK-4409 | 53203 | 3 | 5 | 647.58 | 2933.47 | +592.29 | +2822.84 | +96.23 | +5 |
| STARLINK-32590 | 63047 | 4 | — | 689.22 | 7656.54 | +633.93 | +7545.90 | +98.56 | -5 |
| STARLINK-30510 | 57981 | 5 | — | 796.81 | 3914.89 | +741.51 | +3804.26 | +97.17 | +5 |
| STARLINK-4660 | 53609 | — | 2 | 1157.09 | 1046.89 | +1101.80 | +936.26 | +89.43 | -5 |
| STARLINK-36585 | 67540 | — | 4 | 1052.44 | 2705.79 | +997.14 | +2595.16 | +95.91 | +5 |
