# Candidate RMS comparisons: scan-hop-99bee37023f62a10

[Ranked RMS plots for every track](scan-hop-99bee37023f62a10-rms.md).

Recorded **2026-09-14T17:00:12.924859Z**, RX0, 10 MS/s.

[Recording assessment and plots](scan-hop-99bee37023f62a10.md).

Each track has its own training-selected leader; there is no single satellite assignment for the whole recording. Lower RMS is better. The same observations and chronological split are used for all candidates within a track.

Gain = alternative RMS − training-leader RMS. Positive gain favors the leader; negative heldout gain means the alternative predicts better. Percent gain uses the alternative RMS as denominator; it is not identification confidence. Tau and carrier offset were selected on training data and remain frozen on heldout.

The archived screen retained the top five training candidates and top five heldout candidates, whose union is listed below. Candidate counts describe the full scored population; names/scores outside these retained lists were not archived. A blank rank means outside that top-five list. Catalogue exclusions and control results are in the linked recording assessment and evidence.

## CH1 lower, 6.71–32.53 s

Track `sha256:f1bc58c765b4cbfc962c5e64266eb5e241b3a8d25ea8b95b9438076f6be26c64`; 26 observations; 573 nominal-time satellites scored. Training leader: **STARLINK-3948 (NORAD 52546)**; heldout rank 2 in the full scored population.

Against the best other heldout candidate, STARLINK-34765 (NORAD 66506): leader heldout RMS **94.22 Hz** versus **85.37 Hz**; gain **-8.85 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-3948 | 52546 | 1 | 2 | 45.06 | 94.22 | +0.00 | +0.00 | +0.00 | +2 |
| STARLINK-34765 | 66506 | 2 | 1 | 48.19 | 85.37 | +3.13 | -8.85 | -10.37 | -1 |
| STARLINK-4534 | 53395 | 3 | 3 | 277.79 | 2861.41 | +232.73 | +2767.19 | +96.71 | -5 |
| STARLINK-5941 | 56013 | 4 | 5 | 501.07 | 4733.83 | +456.01 | +4639.61 | +98.01 | -4 |
| STARLINK-32090 | 59691 | 5 | 4 | 936.72 | 3560.24 | +891.66 | +3466.02 | +97.35 | +5 |

## CH1 upper, 8.72–31.90 s

Track `sha256:eaa4e88ba3e8adeb688c232daddb0f9cc15527b0c35b155ccb76c9dd82d946ea`; 24 observations; 572 nominal-time satellites scored. Training leader: **STARLINK-34765 (NORAD 66506)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-3948 (NORAD 52546): leader heldout RMS **86.19 Hz** versus **96.00 Hz**; gain **+9.81 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34765 | 66506 | 1 | 1 | 24.94 | 86.19 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-3948 | 52546 | 2 | 2 | 25.53 | 96.00 | +0.60 | +9.81 | +10.22 | +2 |
| STARLINK-4534 | 53395 | 3 | 3 | 305.67 | 2732.42 | +280.73 | +2646.23 | +96.85 | -5 |
| STARLINK-5941 | 56013 | 4 | 5 | 397.44 | 4137.15 | +372.51 | +4050.96 | +97.92 | -5 |
| STARLINK-32090 | 59691 | 5 | 4 | 896.17 | 3297.00 | +871.24 | +3210.81 | +97.39 | +5 |

## CH2 lower, 16.66–51.56 s

Track `sha256:8d2cf87d255f8d6c9720242f81e5b31d1b10501c305c38a4973142da9c6ee33a`; 36 observations; 585 nominal-time satellites scored. Training leader: **STARLINK-37949 (NORAD 69671)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11452 (NORAD 62511): leader heldout RMS **332.00 Hz** versus **6080.04 Hz**; gain **+5748.04 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37949 | 69671 | 1 | 1 | 78.22 | 332.00 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-11452 | 62511 | 2 | 2 | 1082.18 | 6080.04 | +1003.96 | +5748.04 | +94.54 | -5 |
| STARLINK-34765 | 66506 | 3 | 4 | 3550.32 | 11394.70 | +3472.10 | +11062.69 | +97.09 | +1 |
| STARLINK-3948 | 52546 | 4 | 5 | 3569.32 | 11457.33 | +3491.09 | +11125.33 | +97.10 | +4 |
| STARLINK-32090 | 59691 | 5 | — | 5447.67 | 16483.43 | +5369.45 | +16151.43 | +97.99 | +4 |
| STARLINK-34749 | 65675 | — | 3 | 5960.92 | 11307.47 | +5882.70 | +10975.47 | +97.06 | +5 |

## CH2 upper, 16.92–48.41 s

Track `sha256:452f02ca80a786f80274601db61f023dd361f29a99d9e194b560658b5e4f7b82`; 33 observations; 583 nominal-time satellites scored. Training leader: **STARLINK-37949 (NORAD 69671)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11452 (NORAD 62511): leader heldout RMS **280.64 Hz** versus **5225.84 Hz**; gain **+4945.19 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37949 | 69671 | 1 | 1 | 52.32 | 280.64 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-11452 | 62511 | 2 | 2 | 894.79 | 5225.84 | +842.47 | +4945.19 | +94.63 | -5 |
| STARLINK-34765 | 66506 | 3 | 3 | 3181.89 | 10481.69 | +3129.57 | +10201.05 | +97.32 | +1 |
| STARLINK-3948 | 52546 | 4 | 4 | 3197.98 | 10544.64 | +3145.66 | +10264.00 | +97.34 | +4 |
| STARLINK-32090 | 59691 | 5 | — | 4902.68 | 15514.05 | +4850.37 | +15233.41 | +98.19 | +5 |
| STARLINK-34749 | 65675 | — | 5 | 5539.17 | 11521.30 | +5486.85 | +11240.65 | +97.56 | +5 |

## CH2 lower, 59.26–84.73 s

Track `sha256:401e333a54192e4a72da3773de639585c2e00c2b612488af7c8722ff87a27e42`; 29 observations; 576 nominal-time satellites scored. Training leader: **STARLINK-31507 (NORAD 59401)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11525 (NORAD 62566): leader heldout RMS **207.00 Hz** versus **1437.68 Hz**; gain **+1230.68 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31507 | 59401 | 1 | 1 | 97.29 | 207.00 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-11525 | 62566 | 2 | 2 | 228.60 | 1437.68 | +131.31 | +1230.68 | +85.60 | +5 |
| STARLINK-30900 | 58423 | 3 | — | 376.49 | 3915.56 | +279.20 | +3708.56 | +94.71 | -1 |
| STARLINK-5698 | 55623 | 4 | — | 443.73 | 4569.09 | +346.44 | +4362.09 | +95.47 | +5 |
| STARLINK-3911 | 52565 | 5 | — | 495.59 | 5636.39 | +398.30 | +5429.39 | +96.33 | +5 |
| STARLINK-35518 | 66198 | — | 3 | 1003.42 | 3462.62 | +906.13 | +3255.62 | +94.02 | +5 |
| STARLINK-34749 | 65675 | — | 4 | 857.20 | 3631.87 | +759.91 | +3424.87 | +94.30 | +5 |
| STARLINK-35991 | 66861 | — | 5 | 679.53 | 3907.07 | +582.24 | +3700.07 | +94.70 | +5 |

## CH2 upper, 59.64–87.13 s

Track `sha256:c0fbd2a6f884144c72d2d564bc57880030776bc4c7a81bcc7273ba4e1ec4efde`; 31 observations; 577 nominal-time satellites scored. Training leader: **STARLINK-31507 (NORAD 59401)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11525 (NORAD 62566): leader heldout RMS **224.71 Hz** versus **1744.41 Hz**; gain **+1519.70 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31507 | 59401 | 1 | 1 | 58.78 | 224.71 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-11525 | 62566 | 2 | 2 | 216.00 | 1744.41 | +157.23 | +1519.70 | +87.12 | +5 |
| STARLINK-30900 | 58423 | 3 | 4 | 363.40 | 4355.52 | +304.63 | +4130.81 | +94.84 | -3 |
| STARLINK-5698 | 55623 | 4 | — | 443.47 | 5446.01 | +384.70 | +5221.30 | +95.87 | +4 |
| STARLINK-3911 | 52565 | 5 | — | 513.86 | 6625.97 | +455.08 | +6401.25 | +96.61 | +4 |
| STARLINK-35518 | 66198 | — | 3 | 1038.98 | 3730.72 | +980.20 | +3506.01 | +93.98 | +5 |
| STARLINK-35991 | 66861 | — | 5 | 743.09 | 4559.94 | +684.31 | +4335.23 | +95.07 | +5 |

## CH4 lower, 59.77–84.35 s

Track `sha256:163815586fdc6829615ce2eff26ab05675fb502a6362c39a02471c73cb689d83`; 28 observations; 576 nominal-time satellites scored. Training leader: **STARLINK-31507 (NORAD 59401)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11525 (NORAD 62566): leader heldout RMS **162.95 Hz** versus **1375.03 Hz**; gain **+1212.08 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31507 | 59401 | 1 | 1 | 59.27 | 162.95 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-11525 | 62566 | 2 | 2 | 142.59 | 1375.03 | +83.32 | +1212.08 | +88.15 | +5 |
| STARLINK-30900 | 58423 | 3 | — | 316.81 | 3997.98 | +257.54 | +3835.03 | +95.92 | +0 |
| STARLINK-5698 | 55623 | 4 | — | 386.01 | 4290.36 | +326.74 | +4127.41 | +96.20 | +5 |
| STARLINK-3911 | 52565 | 5 | — | 423.79 | 5289.23 | +364.52 | +5126.28 | +96.92 | +5 |
| STARLINK-35518 | 66198 | — | 3 | 894.75 | 3291.98 | +835.48 | +3129.04 | +95.05 | +5 |
| STARLINK-34749 | 65675 | — | 4 | 806.12 | 3417.65 | +746.85 | +3254.70 | +95.23 | +5 |
| STARLINK-35991 | 66861 | — | 5 | 587.70 | 3688.93 | +528.43 | +3525.99 | +95.58 | +5 |

## CH1 upper, 65.95–87.00 s

Track `sha256:891517851991d5251d9a44ca768a6dabf5bb23a6e323b98cc427795d5dc2d383`; 22 observations; 573 nominal-time satellites scored. Training leader: **STARLINK-31507 (NORAD 59401)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11525 (NORAD 62566): leader heldout RMS **41.67 Hz** versus **1666.33 Hz**; gain **+1624.67 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31507 | 59401 | 1 | 1 | 50.47 | 41.67 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-5698 | 55623 | 2 | 3 | 324.09 | 2804.73 | +273.62 | +2763.06 | +98.51 | -5 |
| STARLINK-3911 | 52565 | 3 | — | 340.13 | 3203.30 | +289.66 | +3161.63 | +98.70 | -5 |
| STARLINK-34749 | 65675 | 4 | 5 | 343.72 | 3119.73 | +293.25 | +3078.06 | +98.66 | -1 |
| STARLINK-11525 | 62566 | 5 | 2 | 379.51 | 1666.33 | +329.04 | +1624.67 | +97.50 | +5 |
| STARLINK-35518 | 66198 | — | 4 | 938.29 | 2840.19 | +887.82 | +2798.53 | +98.53 | +5 |

## CH1 lower, 66.46–86.62 s

Track `sha256:88d53f8121041a5d1e766509f461b8b41d1b5050dc801f11c95222c9c48eec95`; 20 observations; 573 nominal-time satellites scored. Training leader: **STARLINK-31507 (NORAD 59401)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11525 (NORAD 62566): leader heldout RMS **29.38 Hz** versus **1612.07 Hz**; gain **+1582.69 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31507 | 59401 | 1 | 1 | 42.42 | 29.38 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-34749 | 65675 | 2 | 4 | 348.79 | 2695.89 | +306.36 | +2666.51 | +98.91 | -2 |
| STARLINK-5698 | 55623 | 3 | 5 | 386.29 | 2755.52 | +343.87 | +2726.14 | +98.93 | -5 |
| STARLINK-3911 | 52565 | 4 | — | 403.69 | 3156.76 | +361.26 | +3127.39 | +99.07 | -5 |
| STARLINK-11525 | 62566 | 5 | 2 | 405.03 | 1612.07 | +362.61 | +1582.69 | +98.18 | +5 |
| STARLINK-35518 | 66198 | — | 3 | 951.24 | 2686.04 | +908.81 | +2656.66 | +98.91 | +5 |

## CH2 upper, 89.14–132.61 s

Track `sha256:99738e0871fb6d4e5fead0a642520119b7917c12ae6dff1d44e9fe4358605d15`; 49 observations; 596 nominal-time satellites scored. Training leader: **STARLINK-35419 (NORAD 66559)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4569 (NORAD 53687): leader heldout RMS **176.38 Hz** versus **2618.81 Hz**; gain **+2442.43 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35419 | 66559 | 1 | 1 | 62.90 | 176.38 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-37395 | 69148 | 2 | 4 | 611.56 | 4842.68 | +548.65 | +4666.30 | +96.36 | +5 |
| STARLINK-35518 | 66198 | 3 | — | 1318.82 | 10795.05 | +1255.91 | +10618.67 | +98.37 | -5 |
| STARLINK-31507 | 59401 | 4 | — | 1375.78 | 13068.93 | +1312.88 | +12892.55 | +98.65 | -5 |
| STARLINK-11525 | 62566 | 5 | — | 1594.34 | 13082.31 | +1531.43 | +12905.93 | +98.65 | -5 |
| STARLINK-4569 | 53687 | — | 2 | 3036.40 | 2618.81 | +2973.49 | +2442.43 | +93.26 | +5 |
| STARLINK-34341 | 64161 | — | 3 | 2077.64 | 3511.50 | +2014.73 | +3335.13 | +94.98 | +5 |
| STARLINK-2429 | 47838 | — | 5 | 3456.85 | 8492.19 | +3393.94 | +8315.81 | +97.92 | +5 |

## CH1 lower, 89.64–120.27 s

Track `sha256:95b562275b7e1d2db280d46aa55d464feefb248c80447bd9d9ec2ac063633220`; 36 observations; 584 nominal-time satellites scored. Training leader: **STARLINK-35419 (NORAD 66559)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37395 (NORAD 69148): leader heldout RMS **51.18 Hz** versus **1266.66 Hz**; gain **+1215.47 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35419 | 66559 | 1 | 1 | 46.77 | 51.18 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-35518 | 66198 | 2 | 5 | 507.72 | 4937.83 | +460.95 | +4886.65 | +98.96 | -5 |
| STARLINK-11525 | 62566 | 3 | — | 624.46 | 5974.39 | +577.69 | +5923.21 | +99.14 | -5 |
| STARLINK-37395 | 69148 | 4 | 2 | 629.21 | 1266.66 | +582.43 | +1215.47 | +95.96 | +5 |
| STARLINK-31507 | 59401 | 5 | — | 765.87 | 6419.10 | +719.09 | +6367.92 | +99.20 | -3 |
| STARLINK-34341 | 64161 | — | 3 | 1645.55 | 3793.16 | +1598.77 | +3741.98 | +98.65 | +5 |
| STARLINK-4569 | 53687 | — | 4 | 2675.04 | 3969.86 | +2628.26 | +3918.68 | +98.71 | +5 |

## CH2 lower, 89.77–127.57 s

Track `sha256:27b710890132df96ac393863de4fc9921d104c360341b426d6bc6ef86a588569`; 43 observations; 590 nominal-time satellites scored. Training leader: **STARLINK-35419 (NORAD 66559)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4569 (NORAD 53687): leader heldout RMS **127.42 Hz** versus **2626.19 Hz**; gain **+2498.77 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35419 | 66559 | 1 | 1 | 86.18 | 127.42 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-37395 | 69148 | 2 | 3 | 592.81 | 3153.25 | +506.63 | +3025.83 | +95.96 | +5 |
| STARLINK-35518 | 66198 | 3 | — | 905.77 | 8064.23 | +819.59 | +7936.82 | +98.42 | -5 |
| STARLINK-31507 | 59401 | 4 | — | 967.98 | 9438.49 | +881.80 | +9311.07 | +98.65 | -5 |
| STARLINK-11525 | 62566 | 5 | — | 1092.53 | 9783.09 | +1006.35 | +9655.67 | +98.70 | -5 |
| STARLINK-4569 | 53687 | — | 2 | 2847.98 | 2626.19 | +2761.80 | +2498.77 | +95.15 | +5 |
| STARLINK-34341 | 64161 | — | 4 | 1872.55 | 3694.88 | +1786.37 | +3567.47 | +96.55 | +5 |
| STARLINK-2429 | 47838 | — | 5 | 3042.26 | 7904.00 | +2956.08 | +7776.59 | +98.39 | +5 |

## CH1 upper, 90.02–123.67 s

Track `sha256:a4dbea3a399b56763209e8b7fcb7193771c3ed8a10a5c4b17aab9c248825f559`; 38 observations; 586 nominal-time satellites scored. Training leader: **STARLINK-35419 (NORAD 66559)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37395 (NORAD 69148): leader heldout RMS **67.12 Hz** versus **2026.54 Hz**; gain **+1959.42 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35419 | 66559 | 1 | 1 | 51.78 | 67.12 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-37395 | 69148 | 2 | 2 | 588.33 | 2026.54 | +536.56 | +1959.42 | +96.69 | +5 |
| STARLINK-35518 | 66198 | 3 | 5 | 618.46 | 6211.89 | +566.68 | +6144.77 | +98.92 | -5 |
| STARLINK-11525 | 62566 | 4 | — | 747.22 | 7529.49 | +695.44 | +7462.37 | +99.11 | -5 |
| STARLINK-31507 | 59401 | 5 | — | 795.47 | 7611.84 | +743.69 | +7544.72 | +99.12 | -4 |
| STARLINK-4569 | 53687 | — | 3 | 2681.48 | 3423.43 | +2629.71 | +3356.31 | +98.04 | +5 |
| STARLINK-34341 | 64161 | — | 4 | 1693.55 | 3785.70 | +1641.77 | +3718.58 | +98.23 | +5 |

## CH2 lower, 135.13–170.05 s

Track `sha256:c16da5294d37085f70c3691644214c9bdc914c180cd18087dfb8c96d45be438b`; 37 observations; 586 nominal-time satellites scored. Training leader: **STARLINK-35927 (NORAD 66624)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30885 (NORAD 58361): leader heldout RMS **65.70 Hz** versus **3469.64 Hz**; gain **+3403.94 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35927 | 66624 | 1 | 1 | 84.12 | 65.70 | +0.00 | +0.00 | +0.00 | -4 |
| STARLINK-30885 | 58361 | 2 | 2 | 319.42 | 3469.64 | +235.29 | +3403.94 | +98.11 | -5 |
| STARLINK-37014 | 68216 | 3 | 4 | 329.54 | 4080.83 | +245.42 | +4015.13 | +98.39 | -2 |
| STARLINK-11181 | 60059 | 4 | — | 721.75 | 8755.24 | +637.63 | +8689.55 | +99.25 | -1 |
| STARLINK-4615 | 53620 | 5 | 3 | 759.96 | 3652.48 | +675.84 | +3586.78 | +98.20 | +5 |
| STARLINK-32260 | 61522 | — | 5 | 3423.81 | 5565.20 | +3339.69 | +5499.50 | +98.82 | +5 |

## CH4 lower, 172.69–201.76 s

Track `sha256:310f78a9d267cdda77d151cece7179292348f91afa97774632d29f59ce78d288`; 30 observations; 580 nominal-time satellites scored. Training leader: **STARLINK-35988 (NORAD 66615)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4492 (NORAD 53410): leader heldout RMS **102.98 Hz** versus **1011.16 Hz**; gain **+908.18 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35988 | 66615 | 1 | 1 | 37.70 | 102.98 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-3139 | 49425 | 2 | 3 | 129.04 | 1239.83 | +91.34 | +1136.85 | +91.69 | -5 |
| STARLINK-32776 | 63032 | 3 | — | 394.04 | 3798.80 | +356.34 | +3695.83 | +97.29 | +4 |
| STARLINK-30954 | 58407 | 4 | — | 599.17 | 5673.53 | +561.47 | +5570.55 | +98.18 | -5 |
| STARLINK-4492 | 53410 | 5 | 2 | 612.59 | 1011.16 | +574.89 | +908.18 | +89.82 | -5 |
| STARLINK-11181 | 60059 | — | 4 | 4058.90 | 2562.04 | +4021.20 | +2459.07 | +95.98 | +5 |
| STARLINK-32260 | 61522 | — | 5 | 2997.75 | 2634.94 | +2960.05 | +2531.96 | +96.09 | +5 |

## CH4 upper, 175.84–195.85 s

Track `sha256:f0d295a401d6295fb43f7913fd7150c115f6fbf93b92f36d362369a3bdf0b577`; 21 observations; 572 nominal-time satellites scored. Training leader: **STARLINK-35988 (NORAD 66615)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4492 (NORAD 53410): leader heldout RMS **66.61 Hz** versus **324.00 Hz**; gain **+257.39 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35988 | 66615 | 1 | 1 | 54.84 | 66.61 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-3139 | 49425 | 2 | 3 | 75.69 | 534.97 | +20.85 | +468.36 | +87.55 | -4 |
| STARLINK-32776 | 63032 | 3 | 5 | 203.74 | 2148.53 | +148.90 | +2081.92 | +96.90 | +5 |
| STARLINK-30954 | 58407 | 4 | — | 259.27 | 2977.12 | +204.42 | +2910.51 | +97.76 | -5 |
| STARLINK-4615 | 53620 | 5 | — | 342.33 | 3576.26 | +287.48 | +3509.65 | +98.14 | -5 |
| STARLINK-4492 | 53410 | — | 2 | 389.15 | 324.00 | +334.31 | +257.39 | +79.44 | -5 |
| STARLINK-5719 | 55609 | — | 4 | 502.66 | 1918.09 | +447.81 | +1851.48 | +96.53 | +5 |

## CH2 upper, 179.11–208.32 s

Track `sha256:55ecb2f30f8aa8132a169d523ec8bf69cb351e4b74fa665d7744f39160959481`; 30 observations; 576 nominal-time satellites scored. Training leader: **STARLINK-33799 (NORAD 63447)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32260 (NORAD 61522): leader heldout RMS **30.71 Hz** versus **2147.49 Hz**; gain **+2116.77 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33799 | 63447 | 1 | 1 | 53.09 | 30.71 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-32260 | 61522 | 2 | 2 | 315.67 | 2147.49 | +262.58 | +2116.77 | +98.57 | -5 |
| STARLINK-11181 | 60059 | 3 | — | 968.31 | 8332.28 | +915.22 | +8301.57 | +99.63 | +1 |
| STARLINK-37014 | 68216 | 4 | — | 1437.04 | 9451.36 | +1383.95 | +9420.64 | +99.68 | -5 |
| STARLINK-35988 | 66615 | 5 | 3 | 1719.87 | 4727.92 | +1666.78 | +4697.20 | +99.35 | +5 |
| STARLINK-3139 | 49425 | — | 4 | 2320.63 | 7466.22 | +2267.54 | +7435.51 | +99.59 | +2 |
| STARLINK-4492 | 53410 | — | 5 | 2362.23 | 7620.01 | +2309.14 | +7589.29 | +99.60 | -5 |

## CH2 lower, 179.99–208.20 s

Track `sha256:577b121ef0652c5424fb79ed798cbcde4ef93cf6b81aefbfdd14e08224c1269a`; 29 observations; 574 nominal-time satellites scored. Training leader: **STARLINK-33799 (NORAD 63447)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32260 (NORAD 61522): leader heldout RMS **19.96 Hz** versus **2135.54 Hz**; gain **+2115.58 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33799 | 63447 | 1 | 1 | 60.12 | 19.96 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-32260 | 61522 | 2 | 2 | 267.87 | 2135.54 | +207.76 | +2115.58 | +99.07 | -5 |
| STARLINK-11181 | 60059 | 3 | 4 | 844.80 | 7229.99 | +784.69 | +7210.03 | +99.72 | +0 |
| STARLINK-37014 | 68216 | 4 | — | 1436.29 | 9315.94 | +1376.17 | +9295.98 | +99.79 | -5 |
| STARLINK-35988 | 66615 | 5 | 3 | 1624.34 | 4554.45 | +1564.22 | +4534.49 | +99.56 | +5 |
| STARLINK-3139 | 49425 | — | 5 | 2210.32 | 7238.19 | +2150.20 | +7218.23 | +99.72 | +2 |

## CH3 upper, 202.39–239.44 s

Track `sha256:7d508a9586ba38e06fe82ce09bc3b20cd0d3ddccd926e28dce323561522f6bdf`; 40 observations; 584 nominal-time satellites scored. Training leader: **STARLINK-35814 (NORAD 66576)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-31308 (NORAD 59153): leader heldout RMS **181.55 Hz** versus **1038.70 Hz**; gain **+857.15 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35814 | 66576 | 1 | 1 | 78.28 | 181.55 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-31308 | 59153 | 2 | 2 | 135.29 | 1038.70 | +57.01 | +857.15 | +82.52 | -2 |
| STARLINK-34078 | 64012 | 3 | 4 | 686.74 | 6882.84 | +608.46 | +6701.29 | +97.36 | -5 |
| STARLINK-35988 | 66615 | 4 | — | 1104.31 | 9547.67 | +1026.04 | +9366.12 | +98.10 | +0 |
| STARLINK-33799 | 63447 | 5 | — | 1391.80 | 11857.50 | +1313.53 | +11675.94 | +98.47 | -1 |
| STARLINK-3965 | 52550 | — | 3 | 1510.39 | 6477.45 | +1432.12 | +6295.90 | +97.20 | +5 |
| STARLINK-37851 | 69658 | — | 5 | 4778.98 | 6910.17 | +4700.71 | +6728.62 | +97.37 | +5 |

## CH3 lower, 202.52–241.84 s

Track `sha256:6febf383bb9f491108d665b6d32630bca7a12fc1968f1808f71df8154656f9a6`; 44 observations; 586 nominal-time satellites scored. Training leader: **STARLINK-35814 (NORAD 66576)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-31308 (NORAD 59153): leader heldout RMS **205.25 Hz** versus **1204.43 Hz**; gain **+999.18 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35814 | 66576 | 1 | 1 | 94.00 | 205.25 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-31308 | 59153 | 2 | 2 | 146.50 | 1204.43 | +52.50 | +999.18 | +82.96 | -2 |
| STARLINK-34078 | 64012 | 3 | 5 | 683.88 | 8040.78 | +589.88 | +7835.54 | +97.45 | -5 |
| STARLINK-35988 | 66615 | 4 | — | 1080.99 | 11246.77 | +986.98 | +11041.52 | +98.18 | +0 |
| STARLINK-33799 | 63447 | 5 | — | 1365.03 | 13906.63 | +1271.03 | +13701.38 | +98.52 | -1 |
| STARLINK-37851 | 69658 | — | 3 | 4668.15 | 6302.51 | +4574.15 | +6097.26 | +96.74 | +5 |
| STARLINK-3965 | 52550 | — | 4 | 1494.50 | 7075.42 | +1400.50 | +6870.17 | +97.10 | +5 |

## CH1 lower, 239.06–268.53 s

Track `sha256:3f93a22cebc7f1ebe01751a37835556f4af9d35fc126b9fbb9721c586c19cf12`; 32 observations; 571 nominal-time satellites scored. Training leader: **STARLINK-35897 (NORAD 66501)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-36278 (NORAD 68685): leader heldout RMS **37.45 Hz** versus **1700.13 Hz**; gain **+1662.69 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35897 | 66501 | 1 | 1 | 104.40 | 37.45 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-36278 | 68685 | 2 | 2 | 219.05 | 1700.13 | +114.65 | +1662.69 | +97.80 | +0 |
| STARLINK-31308 | 59153 | 3 | 4 | 733.19 | 7005.33 | +628.79 | +6967.88 | +99.47 | -5 |
| STARLINK-34951 | 65293 | 4 | 3 | 904.50 | 4780.63 | +800.10 | +4743.18 | +99.22 | +5 |
| STARLINK-35814 | 66576 | 5 | 5 | 989.35 | 8124.81 | +884.95 | +8087.36 | +99.54 | -5 |

## CH1 upper, 239.95–268.28 s

Track `sha256:8b8ca5c99d9db5f9fa821100b821f710fa981f66351296a08b654e1a11e6b25c`; 31 observations; 570 nominal-time satellites scored. Training leader: **STARLINK-35897 (NORAD 66501)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-36278 (NORAD 68685): leader heldout RMS **30.42 Hz** versus **1653.33 Hz**; gain **+1622.91 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35897 | 66501 | 1 | 1 | 87.16 | 30.42 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-36278 | 68685 | 2 | 2 | 162.56 | 1653.33 | +75.40 | +1622.91 | +98.16 | +0 |
| STARLINK-31308 | 59153 | 3 | 4 | 706.17 | 6899.56 | +619.01 | +6869.15 | +99.56 | -5 |
| STARLINK-34951 | 65293 | 4 | 3 | 881.68 | 4690.83 | +794.51 | +4660.41 | +99.35 | +5 |
| STARLINK-35814 | 66576 | 5 | 5 | 974.36 | 7986.81 | +887.19 | +7956.39 | +99.62 | -5 |

## CH2 lower, 246.37–281.51 s

Track `sha256:d860211a88547557db0509a522eb4efebb1b67e500c362f4be83ef38448a397a`; 37 observations; 578 nominal-time satellites scored. Training leader: **STARLINK-37851 (NORAD 69658)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-36278 (NORAD 68685): leader heldout RMS **217.96 Hz** versus **5607.02 Hz**; gain **+5389.06 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37851 | 69658 | 1 | 1 | 51.15 | 217.96 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-36278 | 68685 | 2 | 2 | 2234.56 | 5607.02 | +2183.41 | +5389.06 | +96.11 | +5 |
| STARLINK-35897 | 66501 | 3 | 3 | 3423.01 | 10914.43 | +3371.87 | +10696.47 | +98.00 | +3 |
| STARLINK-34951 | 65293 | 4 | 4 | 5490.99 | 16400.19 | +5439.84 | +16182.23 | +98.67 | +0 |
| STARLINK-31308 | 59153 | 5 | — | 6774.32 | 25646.77 | +6723.18 | +25428.81 | +99.15 | -5 |
| STARLINK-35220 | 65661 | — | 5 | 7651.75 | 16636.68 | +7600.61 | +16418.72 | +98.69 | +5 |

## CH4 upper, 246.88–270.30 s

Track `sha256:31d65e18a8fc7c924e6de092341f0e1fa99ee98e1148626305896fb9e4edb036`; 26 observations; 566 nominal-time satellites scored. Training leader: **STARLINK-37851 (NORAD 69658)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-36278 (NORAD 68685): leader heldout RMS **46.89 Hz** versus **4368.28 Hz**; gain **+4321.39 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37851 | 69658 | 1 | 1 | 117.16 | 46.89 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-36278 | 68685 | 2 | 2 | 1590.50 | 4368.28 | +1473.35 | +4321.39 | +98.93 | +5 |
| STARLINK-35897 | 66501 | 3 | 3 | 2220.42 | 7462.44 | +2103.27 | +7415.55 | +99.37 | +5 |
| STARLINK-34951 | 65293 | 4 | 4 | 3681.16 | 11684.50 | +3564.01 | +11637.61 | +99.60 | +3 |
| STARLINK-31308 | 59153 | 5 | — | 4098.46 | 15447.36 | +3981.30 | +15400.47 | +99.70 | -5 |
| STARLINK-35551 | 66200 | — | 5 | 4989.89 | 13725.34 | +4872.73 | +13678.45 | +99.66 | +5 |

## CH2 upper, 247.25–274.08 s

Track `sha256:78dd8140fd75dc5e5fcd81dd2b5b1c90f5ad63816d9f96d0aa5ddda1cc1b5ef3`; 30 observations; 572 nominal-time satellites scored. Training leader: **STARLINK-37851 (NORAD 69658)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-36278 (NORAD 68685): leader heldout RMS **127.55 Hz** versus **4748.24 Hz**; gain **+4620.69 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37851 | 69658 | 1 | 1 | 39.79 | 127.55 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-36278 | 68685 | 2 | 2 | 1895.83 | 4748.24 | +1856.04 | +4620.69 | +97.31 | +5 |
| STARLINK-35897 | 66501 | 3 | 3 | 2808.24 | 8520.16 | +2768.45 | +8392.62 | +98.50 | +4 |
| STARLINK-34951 | 65293 | 4 | 4 | 4546.22 | 13011.92 | +4506.43 | +12884.37 | +99.02 | +1 |
| STARLINK-31308 | 59153 | 5 | — | 5398.94 | 18534.35 | +5359.15 | +18406.81 | +99.31 | -5 |
| STARLINK-35551 | 66200 | — | 5 | 5902.22 | 14810.46 | +5862.43 | +14682.92 | +99.14 | +5 |

## CH4 lower, 255.06–280.88 s

Track `sha256:4a3d636f8bcd34c908f4f776b037614a15fcb044f9a4ff86782e44a07526a2fe`; 28 observations; 572 nominal-time satellites scored. Training leader: **STARLINK-37851 (NORAD 69658)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-36278 (NORAD 68685): leader heldout RMS **88.32 Hz** versus **3863.96 Hz**; gain **+3775.64 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37851 | 69658 | 1 | 1 | 13.45 | 88.32 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-36278 | 68685 | 2 | 2 | 1463.34 | 3863.96 | +1449.89 | +3775.64 | +97.71 | +5 |
| STARLINK-35897 | 66501 | 3 | 3 | 2437.47 | 6862.60 | +2424.02 | +6774.28 | +98.71 | -2 |
| STARLINK-34951 | 65293 | 4 | 5 | 3874.25 | 11063.56 | +3860.81 | +10975.24 | +99.20 | -5 |
| STARLINK-35551 | 66200 | 5 | — | 4565.40 | 12147.87 | +4551.95 | +12059.55 | +99.27 | +5 |
| STARLINK-35220 | 65661 | — | 4 | 4650.58 | 10665.67 | +4637.13 | +10577.35 | +99.17 | +5 |

## CH4 lower, 179.62–208.83 s

Track `sha256:a4f291d697678b64f94314afe3e8be78839ebde4539589e34ee31fdec83803cc`; 30 observations; 576 nominal-time satellites scored. Training leader: **STARLINK-33799 (NORAD 63447)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32260 (NORAD 61522): leader heldout RMS **19.49 Hz** versus **2290.21 Hz**; gain **+2270.72 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33799 | 63447 | 1 | 1 | 23.30 | 19.49 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-32260 | 61522 | 2 | 2 | 282.97 | 2290.21 | +259.68 | +2270.72 | +99.15 | -5 |
| STARLINK-11181 | 60059 | 3 | — | 939.76 | 7689.33 | +916.46 | +7669.85 | +99.75 | +0 |
| STARLINK-37014 | 68216 | 4 | — | 1589.12 | 9775.90 | +1565.82 | +9756.41 | +99.80 | -5 |
| STARLINK-35988 | 66615 | 5 | 3 | 1741.82 | 4679.41 | +1718.53 | +4659.92 | +99.58 | +5 |
| STARLINK-3139 | 49425 | — | 4 | 2368.50 | 7475.95 | +2345.20 | +7456.47 | +99.74 | +2 |
| STARLINK-4492 | 53410 | — | 5 | 2410.78 | 7631.77 | +2387.48 | +7612.29 | +99.74 | -5 |
