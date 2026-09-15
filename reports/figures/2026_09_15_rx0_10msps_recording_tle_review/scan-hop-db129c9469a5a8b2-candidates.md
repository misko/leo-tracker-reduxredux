# Candidate RMS comparisons: scan-hop-db129c9469a5a8b2

[Ranked RMS plots for every track](scan-hop-db129c9469a5a8b2-rms.md).

Recorded **2026-09-14T19:40:12.731860Z**, RX0, 10 MS/s.

[Recording assessment and plots](scan-hop-db129c9469a5a8b2.md).

Each track has its own training-selected leader; there is no single satellite assignment for the whole recording. Lower RMS is better. The same observations and chronological split are used for all candidates within a track.

Gain = alternative RMS − training-leader RMS. Positive gain favors the leader; negative heldout gain means the alternative predicts better. Percent gain uses the alternative RMS as denominator; it is not identification confidence. Tau and carrier offset were selected on training data and remain frozen on heldout.

The archived screen retained the top five training candidates and top five heldout candidates, whose union is listed below. Candidate counts describe the full scored population; names/scores outside these retained lists were not archived. A blank rank means outside that top-five list. Catalogue exclusions and control results are in the linked recording assessment and evidence.

## CH3 lower, 58.77–88.63 s

Track `sha256:4f86e4b3ec14533baa114a2a22d682bd1be7c739eab0cfa12bca3ee8e9407ece`; 49 observations; 505 nominal-time satellites scored. Training leader: **STARLINK-4055 (NORAD 53161)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-1500 (NORAD 45744): leader heldout RMS **69.88 Hz** versus **4009.03 Hz**; gain **+3939.15 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-4055 | 53161 | 1 | 1 | 40.00 | 69.88 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-1500 | 45744 | 2 | 2 | 343.27 | 4009.03 | +303.26 | +3939.15 | +98.26 | -1 |
| STARLINK-30566 | 58054 | 3 | 3 | 1644.12 | 8024.79 | +1604.11 | +7954.91 | +99.13 | -5 |
| STARLINK-32804 | 62846 | 4 | 4 | 3938.15 | 12498.05 | +3898.15 | +12428.17 | +99.44 | +5 |
| STARLINK-11438 [DTC] | 62888 | 5 | — | 4293.00 | 19018.45 | +4253.00 | +18948.57 | +99.63 | -5 |
| STARLINK-31773 | 59429 | — | 5 | 4490.02 | 15904.47 | +4450.02 | +15834.59 | +99.56 | +0 |

## CH3 upper, 59.03–88.38 s

Track `sha256:4a8044af028d3543b80fdac9c28529ad537b3636e7c2971fe36bb2cc89db06f2`; 47 observations; 505 nominal-time satellites scored. Training leader: **STARLINK-4055 (NORAD 53161)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-1500 (NORAD 45744): leader heldout RMS **49.64 Hz** versus **2963.68 Hz**; gain **+2914.04 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-4055 | 53161 | 1 | 1 | 62.61 | 49.64 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-1500 | 45744 | 2 | 2 | 344.62 | 2963.68 | +282.01 | +2914.04 | +98.33 | -3 |
| STARLINK-30566 | 58054 | 3 | 3 | 1721.01 | 7805.34 | +1658.40 | +7755.70 | +99.36 | -5 |
| STARLINK-32804 | 62846 | 4 | 4 | 3989.41 | 12093.91 | +3926.80 | +12044.27 | +99.59 | +5 |
| STARLINK-11438 [DTC] | 62888 | 5 | — | 4439.00 | 18477.85 | +4376.39 | +18428.21 | +99.73 | -5 |
| STARLINK-31773 | 59429 | — | 5 | 4573.02 | 15411.86 | +4510.41 | +15362.22 | +99.68 | +0 |

## CH3 lower, 118.98–148.83 s

Track `sha256:a2d766d3da0056d1977f123870ca09013ebfe66018a94056f99b8f34925e3112`; 36 observations; 498 nominal-time satellites scored. Training leader: **STARLINK-35464 (NORAD 65881)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4040 (NORAD 53151): leader heldout RMS **44.37 Hz** versus **2212.65 Hz**; gain **+2168.29 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35464 | 65881 | 1 | 1 | 176.86 | 44.37 | +0.00 | +0.00 | +0.00 | -4 |
| STARLINK-4040 | 53151 | 2 | 2 | 1366.37 | 2212.65 | +1189.51 | +2168.29 | +97.99 | +5 |
| STARLINK-31514 | 59187 | 3 | — | 2569.73 | 13095.53 | +2392.87 | +13051.16 | +99.66 | -5 |
| STARLINK-33664 | 63415 | 4 | — | 3364.72 | 13413.48 | +3187.86 | +13369.12 | +99.67 | -5 |
| STARLINK-35761 | 66961 | 5 | — | 3373.07 | 12896.57 | +3196.21 | +12852.20 | +99.66 | +5 |
| STARLINK-31768 | 59616 | — | 3 | 3690.12 | 10926.62 | +3513.26 | +10882.25 | +99.59 | +5 |
| STARLINK-32634 | 62313 | — | 4 | 4567.94 | 10983.82 | +4391.08 | +10939.46 | +99.60 | +5 |
| STARLINK-31262 | 58847 | — | 5 | 5220.05 | 12789.52 | +5043.19 | +12745.15 | +99.65 | +5 |

## CH4 lower, 143.03–169.37 s

Track `sha256:409cfdeaaf1e19e8173e256cefc96b1e2b199c3b523784c671fedeab74ed39d0`; 28 observations; 487 nominal-time satellites scored. Training leader: **STARLINK-32634 (NORAD 62313)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-31262 (NORAD 58847): leader heldout RMS **120.13 Hz** versus **138.91 Hz**; gain **+18.78 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32634 | 62313 | 1 | 1 | 19.21 | 120.13 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-31262 | 58847 | 2 | 2 | 54.66 | 138.91 | +35.45 | +18.78 | +13.52 | +0 |
| STARLINK-35464 | 65881 | 3 | — | 784.66 | 6269.79 | +765.44 | +6149.66 | +98.08 | +0 |
| STARLINK-31768 | 59616 | 4 | 5 | 1126.12 | 5629.08 | +1106.91 | +5508.95 | +97.87 | -1 |
| STARLINK-31660 | 59642 | 5 | 4 | 1131.89 | 2622.75 | +1112.68 | +2502.61 | +95.42 | +5 |
| STARLINK-4040 | 53151 | — | 3 | 1690.37 | 1260.48 | +1671.16 | +1140.34 | +90.47 | +5 |

## CH4 lower, 173.90–195.57 s

Track `sha256:97af68796b4272c3b014a873aec76fa1d8c457b8413d5b6efc6b3e1505e35a4d`; 23 observations; 475 nominal-time satellites scored. Training leader: **STARLINK-34607 (NORAD 64742)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-31660 (NORAD 59642): leader heldout RMS **61.10 Hz** versus **3361.35 Hz**; gain **+3300.25 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34607 | 64742 | 1 | 1 | 16.90 | 61.10 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-31660 | 59642 | 2 | 2 | 313.03 | 3361.35 | +296.13 | +3300.25 | +98.18 | +2 |
| STARLINK-32634 | 62313 | 3 | 4 | 363.53 | 4165.46 | +346.63 | +4104.36 | +98.53 | -5 |
| STARLINK-31262 | 58847 | 4 | 3 | 370.89 | 4050.42 | +353.98 | +3989.32 | +98.49 | -2 |
| STARLINK-4040 | 53151 | 5 | — | 1372.80 | 9138.50 | +1355.90 | +9077.40 | +99.33 | -5 |
| STARLINK-31381 | 59469 | — | 5 | 1426.69 | 4181.18 | +1409.79 | +4120.08 | +98.54 | +5 |

## CH2 upper, 180.07–200.12 s

Track `sha256:d7ea0ad7f6e1d3be172a40fbcbedd1ab20c5752c2b0a99aee2b23851004b4e0a`; 22 observations; 477 nominal-time satellites scored. Training leader: **STARLINK-34607 (NORAD 64742)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-31381 (NORAD 59469): leader heldout RMS **69.30 Hz** versus **3823.85 Hz**; gain **+3754.56 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34607 | 64742 | 1 | 1 | 31.32 | 69.30 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-31660 | 59642 | 2 | 4 | 584.29 | 4027.27 | +552.97 | +3957.98 | +98.28 | -5 |
| STARLINK-31262 | 58847 | 3 | — | 977.42 | 6201.02 | +946.10 | +6131.72 | +98.88 | -5 |
| STARLINK-31381 | 59469 | 4 | 2 | 1370.58 | 3823.85 | +1339.26 | +3754.56 | +98.19 | +5 |
| STARLINK-32634 | 62313 | 5 | — | 1381.24 | 7666.90 | +1349.92 | +7597.61 | +99.10 | -5 |
| STARLINK-4054 | 53158 | — | 3 | 1742.44 | 3910.17 | +1711.12 | +3840.87 | +98.23 | +5 |
| STARLINK-30254 | 57533 | — | 5 | 1711.33 | 5068.58 | +1680.01 | +4999.29 | +98.63 | +5 |

## CH4 upper, 269.54–298.76 s

Track `sha256:1bb5b6783920c5b02cdd41d399301dcb5a9ce02ed6ace5c3197319e841da1d4d`; 44 observations; 482 nominal-time satellites scored. Training leader: **STARLINK-30553 (NORAD 58056)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11649 [DTC] (NORAD 64069): leader heldout RMS **41.46 Hz** versus **2640.04 Hz**; gain **+2598.58 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30553 | 58056 | 1 | 1 | 89.28 | 41.46 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-36141 | 67057 | 2 | 3 | 315.01 | 3411.98 | +225.73 | +3370.52 | +98.78 | -5 |
| STARLINK-5536 | 57062 | 3 | 5 | 470.88 | 5855.42 | +381.59 | +5813.96 | +99.29 | -1 |
| STARLINK-33998 | 63951 | 4 | — | 1370.27 | 6362.21 | +1280.99 | +6320.75 | +99.35 | +5 |
| STARLINK-11461 [DTC] | 62421 | 5 | 4 | 1421.15 | 4140.76 | +1331.87 | +4099.30 | +99.00 | +5 |
| STARLINK-11649 [DTC] | 64069 | — | 2 | 3408.90 | 2640.04 | +3319.62 | +2598.58 | +98.43 | +5 |

## CH4 lower, 270.17–298.51 s

Track `sha256:da29a4c6534c39322a443ed89012bfa1c30826eb91da7f32d90a7f4a3778ae1c`; 40 observations; 482 nominal-time satellites scored. Training leader: **STARLINK-30553 (NORAD 58056)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11649 [DTC] (NORAD 64069): leader heldout RMS **135.76 Hz** versus **2134.53 Hz**; gain **+1998.78 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30553 | 58056 | 1 | 1 | 21.73 | 135.76 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-36141 | 67057 | 2 | 3 | 292.82 | 3534.74 | +271.08 | +3398.98 | +96.16 | -5 |
| STARLINK-5536 | 57062 | 3 | 5 | 452.56 | 4936.87 | +430.83 | +4801.11 | +97.25 | -3 |
| STARLINK-11461 [DTC] | 62421 | 4 | 4 | 1283.64 | 4315.94 | +1261.91 | +4180.18 | +96.85 | +5 |
| STARLINK-33998 | 63951 | 5 | — | 1509.94 | 6268.42 | +1488.21 | +6132.66 | +97.83 | +5 |
| STARLINK-11649 [DTC] | 64069 | — | 2 | 3168.36 | 2134.53 | +3146.63 | +1998.78 | +93.64 | +5 |
