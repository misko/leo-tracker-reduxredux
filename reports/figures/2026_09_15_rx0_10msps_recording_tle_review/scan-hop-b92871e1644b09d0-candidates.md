# Candidate RMS comparisons: scan-hop-b92871e1644b09d0

[Ranked RMS plots for every track](scan-hop-b92871e1644b09d0-rms.md).

Recorded **2026-09-14T18:20:12.980561Z**, RX0, 10 MS/s.

[Recording assessment and plots](scan-hop-b92871e1644b09d0.md).

Each track has its own training-selected leader; there is no single satellite assignment for the whole recording. Lower RMS is better. The same observations and chronological split are used for all candidates within a track.

Gain = alternative RMS − training-leader RMS. Positive gain favors the leader; negative heldout gain means the alternative predicts better. Percent gain uses the alternative RMS as denominator; it is not identification confidence. Tau and carrier offset were selected on training data and remain frozen on heldout.

The archived screen retained the top five training candidates and top five heldout candidates, whose union is listed below. Candidate counts describe the full scored population; names/scores outside these retained lists were not archived. A blank rank means outside that top-five list. Catalogue exclusions and control results are in the linked recording assessment and evidence.

## CH2 lower, 22.20–60.87 s

Track `sha256:ca59a9e96635b9013362634e952b382b0a4dc9788c208db3595b6a68b069fe6a`; 40 observations; 557 nominal-time satellites scored. Training leader: **STARLINK-36641 (NORAD 67589)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4701 (NORAD 53727): leader heldout RMS **489.67 Hz** versus **12436.18 Hz**; gain **+11946.51 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36641 | 67589 | 1 | 1 | 548.63 | 489.67 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-31071 | 58602 | 2 | 3 | 3728.35 | 12549.40 | +3179.72 | +12059.73 | +96.10 | +5 |
| STARLINK-30166 | 57602 | 3 | 4 | 4254.49 | 13542.51 | +3705.86 | +13052.84 | +96.38 | +5 |
| STARLINK-2414 | 48095 | 4 | 5 | 5350.41 | 14658.42 | +4801.78 | +14168.76 | +96.66 | +5 |
| STARLINK-3959 | 52564 | 5 | — | 5355.19 | 25057.94 | +4806.56 | +24568.28 | +98.05 | -5 |
| STARLINK-4701 | 53727 | — | 2 | 6549.75 | 12436.18 | +6001.12 | +11946.51 | +96.06 | +5 |

## CH2 upper, 23.59–58.09 s

Track `sha256:fc3a866299d5fd73331e59d3793e204021ea049134992f7e8a1c90285c13ab62`; 37 observations; 553 nominal-time satellites scored. Training leader: **STARLINK-36641 (NORAD 67589)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-31071 (NORAD 58602): leader heldout RMS **371.49 Hz** versus **11591.87 Hz**; gain **+11220.39 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36641 | 67589 | 1 | 1 | 501.36 | 371.49 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-31071 | 58602 | 2 | 2 | 3341.51 | 11591.87 | +2840.16 | +11220.39 | +96.80 | +5 |
| STARLINK-30166 | 57602 | 3 | 4 | 3806.23 | 12558.31 | +3304.87 | +12186.82 | +97.04 | +5 |
| STARLINK-2414 | 48095 | 4 | 5 | 4772.37 | 13765.40 | +4271.01 | +13393.91 | +97.30 | +5 |
| STARLINK-3959 | 52564 | 5 | — | 4786.21 | 22671.17 | +4284.85 | +22299.68 | +98.36 | -5 |
| STARLINK-4701 | 53727 | — | 3 | 5823.28 | 12178.10 | +5321.93 | +11806.61 | +96.95 | +5 |

## CH1 lower, 119.69–144.89 s

Track `sha256:8953c4b59463613d186c5a779aa2b89e622d5a546d1b3a5b81d19a042a92c36d`; 28 observations; 528 nominal-time satellites scored. Training leader: **STARLINK-34041 (NORAD 63844)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4390 (NORAD 53653): leader heldout RMS **137.56 Hz** versus **2217.90 Hz**; gain **+2080.34 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34041 | 63844 | 1 | 1 | 21.78 | 137.56 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-3276 | 50189 | 2 | 3 | 1023.52 | 2502.76 | +1001.74 | +2365.20 | +94.50 | +5 |
| STARLINK-35516 | 65918 | 3 | 5 | 1050.25 | 3407.02 | +1028.46 | +3269.46 | +95.96 | +5 |
| STARLINK-5767 | 55586 | 4 | — | 1121.98 | 3660.70 | +1100.20 | +3523.14 | +96.24 | +0 |
| STARLINK-30580 | 58115 | 5 | — | 1439.10 | 7639.75 | +1417.32 | +7502.19 | +98.20 | -5 |
| STARLINK-4390 | 53653 | — | 2 | 2430.21 | 2217.90 | +2408.43 | +2080.34 | +93.80 | +5 |
| STARLINK-11112 | 60115 | — | 4 | 1669.62 | 3051.50 | +1647.83 | +2913.94 | +95.49 | +5 |

## CH1 upper, 119.94–145.14 s

Track `sha256:b34b003ac3c0496ceb1ee9090bfb4250cff4656d7b1e3e589c4f592c94be9528`; 28 observations; 527 nominal-time satellites scored. Training leader: **STARLINK-34041 (NORAD 63844)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4390 (NORAD 53653): leader heldout RMS **194.33 Hz** versus **1982.13 Hz**; gain **+1787.80 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34041 | 63844 | 1 | 1 | 34.19 | 194.33 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-3276 | 50189 | 2 | 3 | 1035.45 | 2426.32 | +1001.26 | +2232.00 | +91.99 | +5 |
| STARLINK-35516 | 65918 | 3 | 5 | 1081.32 | 3356.96 | +1047.13 | +3162.64 | +94.21 | +5 |
| STARLINK-5767 | 55586 | 4 | — | 1154.61 | 3609.25 | +1120.42 | +3414.92 | +94.62 | +0 |
| STARLINK-30580 | 58115 | 5 | — | 1548.16 | 7685.90 | +1513.97 | +7491.57 | +97.47 | -5 |
| STARLINK-4390 | 53653 | — | 2 | 2372.52 | 1982.13 | +2338.34 | +1787.80 | +90.20 | +5 |
| STARLINK-11112 | 60115 | — | 4 | 1662.18 | 2899.93 | +1627.99 | +2705.61 | +93.30 | +5 |

## CH2 upper, 134.17–186.59 s

Track `sha256:43166ce20900dd6bd03c2cd020de28cd8733218c2bbfd47d6c9ef510d08e13a4`; 72 observations; 554 nominal-time satellites scored. Training leader: **STARLINK-31388 (NORAD 59565)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-6185 (NORAD 56901): leader heldout RMS **158.60 Hz** versus **2689.44 Hz**; gain **+2530.84 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31388 | 59565 | 1 | 1 | 140.54 | 158.60 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-6185 | 56901 | 2 | 2 | 300.44 | 2689.44 | +159.91 | +2530.84 | +94.10 | +5 |
| STARLINK-11112 | 60115 | 3 | 4 | 848.26 | 6986.80 | +707.73 | +6828.20 | +97.73 | -5 |
| STARLINK-3276 | 50189 | 4 | — | 1657.24 | 13535.32 | +1516.70 | +13376.72 | +98.83 | -5 |
| STARLINK-34041 | 63844 | 5 | — | 2425.68 | 19917.16 | +2285.14 | +19758.56 | +99.20 | -5 |
| STARLINK-11742 | 64377 | — | 3 | 9004.96 | 6071.23 | +8864.43 | +5912.63 | +97.39 | +5 |
| STARLINK-32561 | 62026 | — | 5 | 3396.41 | 12357.27 | +3255.87 | +12198.67 | +98.72 | +5 |

## CH2 lower, 134.43–187.10 s

Track `sha256:9e1323c507ed721a183d07ffd44fb16eea4b689299f4b7cf57fe229dd73e28ed`; 72 observations; 554 nominal-time satellites scored. Training leader: **STARLINK-31388 (NORAD 59565)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-6185 (NORAD 56901): leader heldout RMS **165.37 Hz** versus **2760.92 Hz**; gain **+2595.55 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31388 | 59565 | 1 | 1 | 143.59 | 165.37 | +0.00 | +0.00 | +0.00 | +1 |
| STARLINK-6185 | 56901 | 2 | 2 | 289.82 | 2760.92 | +146.23 | +2595.55 | +94.01 | +5 |
| STARLINK-11112 | 60115 | 3 | 4 | 834.82 | 7115.55 | +691.23 | +6950.18 | +97.68 | -5 |
| STARLINK-3276 | 50189 | 4 | — | 1629.65 | 13762.10 | +1486.06 | +13596.73 | +98.80 | -5 |
| STARLINK-34041 | 63844 | 5 | — | 2378.35 | 20242.91 | +2234.76 | +20077.54 | +99.18 | -5 |
| STARLINK-11742 | 64377 | — | 3 | 8803.77 | 6442.24 | +8660.18 | +6276.88 | +97.43 | +5 |
| STARLINK-32561 | 62026 | — | 5 | 3371.08 | 12464.22 | +3227.49 | +12298.86 | +98.67 | +5 |

## CH4 lower, 214.22–238.79 s

Track `sha256:87590df91e69df122a4b2d2a104be4dddec8404e83a7031354d9ad1ccc8b7870`; 31 observations; 518 nominal-time satellites scored. Training leader: **STARLINK-33958 (NORAD 63850)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-5752 (NORAD 55577): leader heldout RMS **207.73 Hz** versus **1204.58 Hz**; gain **+996.85 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33958 | 63850 | 1 | 1 | 56.76 | 207.73 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-5752 | 55577 | 2 | 2 | 99.18 | 1204.58 | +42.42 | +996.85 | +82.76 | +2 |
| STARLINK-3286 | 50171 | 3 | — | 275.89 | 3342.90 | +219.13 | +3135.18 | +93.79 | -1 |
| STARLINK-37621 | 69830 | 4 | 3 | 360.77 | 1617.42 | +304.01 | +1409.70 | +87.16 | +5 |
| STARLINK-30257 | 57526 | 5 | — | 630.00 | 6011.52 | +573.24 | +5803.80 | +96.54 | -5 |
| STARLINK-35112 | 65520 | — | 4 | 632.58 | 2064.81 | +575.82 | +1857.08 | +89.94 | -5 |
| STARLINK-35261 | 65595 | — | 5 | 1501.87 | 3250.44 | +1445.11 | +3042.71 | +93.61 | -5 |

## CH4 upper, 217.62–238.54 s

Track `sha256:f0f8a6cca0d0e758b9f39d5609859ac232aac34d8ae14cf1a5f69ac8121b2a01`; 26 observations; 516 nominal-time satellites scored. Training leader: **STARLINK-33958 (NORAD 63850)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-5752 (NORAD 55577): leader heldout RMS **172.53 Hz** versus **1023.21 Hz**; gain **+850.68 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33958 | 63850 | 1 | 1 | 58.95 | 172.53 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-5752 | 55577 | 2 | 2 | 85.38 | 1023.21 | +26.44 | +850.68 | +83.14 | +3 |
| STARLINK-37621 | 69830 | 3 | 3 | 357.58 | 1474.30 | +298.64 | +1301.77 | +88.30 | +5 |
| STARLINK-3286 | 50171 | 4 | — | 409.81 | 3523.13 | +350.87 | +3350.60 | +95.10 | +1 |
| STARLINK-35112 | 65520 | 5 | 4 | 557.43 | 1747.36 | +498.49 | +1574.83 | +90.13 | -5 |
| STARLINK-35261 | 65595 | — | 5 | 1157.08 | 2421.73 | +1098.14 | +2249.20 | +92.88 | -5 |

## CH2 lower, 254.53–283.77 s

Track `sha256:c9d9a334569a12b290730e970e4265b6ea7c2804d5eede4752bd30bb425156e3`; 32 observations; 517 nominal-time satellites scored. Training leader: **STARLINK-36281 (NORAD 67605)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37886 (NORAD 69943): leader heldout RMS **291.91 Hz** versus **7943.31 Hz**; gain **+7651.40 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36281 | 67605 | 1 | 1 | 134.35 | 291.91 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-37886 | 69943 | 2 | 2 | 2731.04 | 7943.31 | +2596.69 | +7651.40 | +96.33 | +5 |
| STARLINK-30323 | 57634 | 3 | 3 | 3114.96 | 9398.08 | +2980.61 | +9106.17 | +96.89 | +5 |
| STARLINK-31854 | 59671 | 4 | 4 | 3200.16 | 9723.00 | +3065.81 | +9431.09 | +97.00 | +5 |
| STARLINK-35112 | 65520 | 5 | — | 3756.68 | 15902.62 | +3622.33 | +15610.71 | +98.16 | -5 |
| STARLINK-35524 | 65914 | — | 5 | 4824.21 | 10381.77 | +4689.86 | +10089.86 | +97.19 | +5 |

## CH2 upper, 255.29–283.52 s

Track `sha256:dd01067ccfb3c254531d4fbb77b5e857ba50fc143b65ec19a78cf6fc0b72da25`; 31 observations; 516 nominal-time satellites scored. Training leader: **STARLINK-36281 (NORAD 67605)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37886 (NORAD 69943): leader heldout RMS **304.52 Hz** versus **7682.06 Hz**; gain **+7377.54 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36281 | 67605 | 1 | 1 | 179.82 | 304.52 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-37886 | 69943 | 2 | 2 | 2673.44 | 7682.06 | +2493.63 | +7377.54 | +96.04 | +5 |
| STARLINK-30323 | 57634 | 3 | 3 | 3043.72 | 9089.00 | +2863.91 | +8784.48 | +96.65 | +5 |
| STARLINK-31854 | 59671 | 4 | 4 | 3126.11 | 9403.51 | +2946.29 | +9098.99 | +96.76 | +5 |
| STARLINK-35112 | 65520 | 5 | — | 3725.33 | 15455.01 | +3545.52 | +15150.50 | +98.03 | -5 |
| STARLINK-35524 | 65914 | — | 5 | 4619.56 | 9970.65 | +4439.74 | +9666.13 | +96.95 | +5 |

## CH2 upper, 2.67–23.59 s

Track `sha256:fdb5660283081be66b3afb524de4728034a132f30c693f53eea2eb72929b2e3c`; 25 observations; 543 nominal-time satellites scored. Training leader: **STARLINK-30166 (NORAD 57602)**; heldout rank 2 in the full scored population.

Against the best other heldout candidate, STARLINK-31071 (NORAD 58602): leader heldout RMS **411.23 Hz** versus **140.26 Hz**; gain **-270.98 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30166 | 57602 | 1 | 2 | 104.14 | 411.23 | +0.00 | +0.00 | +0.00 | +2 |
| STARLINK-31071 | 58602 | 2 | 1 | 107.29 | 140.26 | +3.16 | -270.98 | -193.20 | +1 |
| STARLINK-36578 | 67571 | 3 | 3 | 142.92 | 766.48 | +38.78 | +355.25 | +46.35 | +1 |
| STARLINK-3195 | 49762 | 4 | 4 | 177.06 | 906.27 | +72.93 | +495.04 | +54.62 | -5 |
| STARLINK-31078 | 58638 | 5 | — | 186.07 | 1402.24 | +81.94 | +991.00 | +70.67 | +3 |
| STARLINK-5503 | 57257 | — | 5 | 951.54 | 1029.04 | +847.40 | +617.81 | +60.04 | -5 |

## CH2 lower, 104.05–134.43 s

Track `sha256:6d5f63158af33a2613f10d0ed6470ab6bcaff2e25aaa33c0b139fad735540013`; 34 observations; 536 nominal-time satellites scored. Training leader: **STARLINK-34041 (NORAD 63844)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-5767 (NORAD 55586): leader heldout RMS **161.58 Hz** versus **2752.44 Hz**; gain **+2590.85 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34041 | 63844 | 1 | 1 | 82.06 | 161.58 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-5767 | 55586 | 2 | 2 | 241.37 | 2752.44 | +159.31 | +2590.85 | +94.13 | +5 |
| STARLINK-11742 | 64377 | 3 | — | 545.14 | 9016.65 | +463.08 | +8855.07 | +98.21 | +0 |
| STARLINK-35516 | 65918 | 4 | 3 | 633.02 | 3130.87 | +550.96 | +2969.29 | +94.84 | +5 |
| STARLINK-37894 | 69966 | 5 | — | 763.76 | 9578.49 | +681.71 | +9416.91 | +98.31 | -4 |
| STARLINK-3276 | 50189 | — | 4 | 1190.43 | 3999.02 | +1108.38 | +3837.44 | +95.96 | +5 |
| STARLINK-30580 | 58115 | — | 5 | 1033.00 | 5920.33 | +950.95 | +5758.75 | +97.27 | +5 |
