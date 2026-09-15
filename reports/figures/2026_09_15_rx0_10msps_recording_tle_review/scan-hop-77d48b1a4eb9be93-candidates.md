# Candidate RMS comparisons: scan-hop-77d48b1a4eb9be93

[Ranked RMS plots for every track](scan-hop-77d48b1a4eb9be93-rms.md).

Recorded **2026-09-14T19:10:12.741503Z**, RX0, 10 MS/s.

[Recording assessment and plots](scan-hop-77d48b1a4eb9be93.md).

Each track has its own training-selected leader; there is no single satellite assignment for the whole recording. Lower RMS is better. The same observations and chronological split are used for all candidates within a track.

Gain = alternative RMS − training-leader RMS. Positive gain favors the leader; negative heldout gain means the alternative predicts better. Percent gain uses the alternative RMS as denominator; it is not identification confidence. Tau and carrier offset were selected on training data and remain frozen on heldout.

The archived screen retained the top five training candidates and top five heldout candidates, whose union is listed below. Candidate counts describe the full scored population; names/scores outside these retained lists were not archived. A blank rank means outside that top-five list. Catalogue exclusions and control results are in the linked recording assessment and evidence.

## CH2 lower, 68.69–94.29 s

Track `sha256:fdb2049e603a7e46c3ed541782727882ab53bf054cca0e91db959332c6f29e57`; 36 observations; 472 nominal-time satellites scored. Training leader: **STARLINK-35770 (NORAD 66977)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4081 (NORAD 52660): leader heldout RMS **141.92 Hz** versus **437.89 Hz**; gain **+295.97 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35770 | 66977 | 1 | 1 | 24.29 | 141.92 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-37037 | 68084 | 2 | 5 | 311.40 | 3436.37 | +287.10 | +3294.44 | +95.87 | +2 |
| STARLINK-4081 | 52660 | 3 | 2 | 450.32 | 437.89 | +426.02 | +295.97 | +67.59 | +5 |
| STARLINK-11669 [DTC] | 63548 | 4 | 3 | 681.11 | 2290.58 | +656.82 | +2148.66 | +93.80 | +5 |
| STARLINK-6225 | 57092 | 5 | 4 | 705.54 | 3284.03 | +681.25 | +3142.11 | +95.68 | +5 |

## CH1 lower, 142.15–167.71 s

Track `sha256:b6b2ab0d78d6f6527d394a5077c51febabef3e0ce122e5d7a34e8c7264fd29d3`; 31 observations; 470 nominal-time satellites scored. Training leader: **STARLINK-33992 (NORAD 64026)**; heldout rank 8 in the full scored population.

Against the best other heldout candidate, STARLINK-4732 (NORAD 53870): leader heldout RMS **4503.56 Hz** versus **1030.45 Hz**; gain **-3473.11 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33992 | 64026 | 1 | — | 116.98 | 4503.56 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-30292 | 57844 | 2 | — | 131.06 | 4660.78 | +14.08 | +157.21 | +3.37 | +1 |
| STARLINK-11240 [DTC] | 60929 | 3 | — | 139.86 | 5572.68 | +22.87 | +1069.12 | +19.18 | +0 |
| STARLINK-11695 [DTC] | 63551 | 4 | — | 295.85 | 5331.02 | +178.87 | +827.46 | +15.52 | -5 |
| STARLINK-33961 | 64047 | 5 | 3 | 493.88 | 1856.74 | +376.89 | -2646.82 | -142.55 | +4 |
| STARLINK-4732 | 53870 | — | 1 | 576.76 | 1030.45 | +459.78 | -3473.11 | -337.05 | +5 |
| STARLINK-32657 | 62475 | — | 2 | 736.68 | 1116.50 | +619.70 | -3387.06 | -303.36 | +5 |
| STARLINK-11730 [DTC] | 64074 | — | 4 | 2195.16 | 2362.55 | +2078.17 | -2141.01 | -90.62 | +5 |
| STARLINK-4299 | 53172 | — | 5 | 1717.39 | 2522.41 | +1600.41 | -1981.15 | -78.54 | +5 |

## CH4 lower, 143.53–164.19 s

Track `sha256:aa1c78e157e98dbafcb636fc5dae1c56db1a9f4c3e3b15f2008c024bb0fdb029`; 27 observations; 466 nominal-time satellites scored. Training leader: **STARLINK-33992 (NORAD 64026)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30292 (NORAD 57844): leader heldout RMS **33.58 Hz** versus **318.28 Hz**; gain **+284.70 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33992 | 64026 | 1 | 1 | 35.62 | 33.58 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-30292 | 57844 | 2 | 2 | 54.16 | 318.28 | +18.54 | +284.70 | +89.45 | +2 |
| STARLINK-11240 [DTC] | 60929 | 3 | 4 | 85.90 | 751.57 | +50.28 | +717.99 | +95.53 | +0 |
| STARLINK-11695 [DTC] | 63551 | 4 | 3 | 216.76 | 714.10 | +181.14 | +680.52 | +95.30 | -5 |
| STARLINK-33961 | 64047 | 5 | — | 365.45 | 3480.68 | +329.83 | +3447.10 | +99.04 | +2 |
| STARLINK-11730 [DTC] | 64074 | — | 5 | 1678.58 | 2104.03 | +1642.95 | +2070.44 | +98.40 | +5 |

## CH1 upper, 143.66–163.68 s

Track `sha256:cbcdd4a22cb804199d1de628655407923dbadf948c9517dad30f3fdd7a75f35c`; 26 observations; 465 nominal-time satellites scored. Training leader: **STARLINK-30292 (NORAD 57844)**; heldout rank 2 in the full scored population.

Against the best other heldout candidate, STARLINK-33992 (NORAD 64026): leader heldout RMS **317.71 Hz** versus **30.66 Hz**; gain **-287.05 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30292 | 57844 | 1 | 2 | 49.36 | 317.71 | +0.00 | +0.00 | +0.00 | +2 |
| STARLINK-33992 | 64026 | 2 | 1 | 65.69 | 30.66 | +16.32 | -287.05 | -936.26 | -1 |
| STARLINK-11240 [DTC] | 60929 | 3 | 3 | 98.24 | 698.73 | +48.88 | +381.02 | +54.53 | +0 |
| STARLINK-11695 [DTC] | 63551 | 4 | 4 | 183.58 | 703.74 | +134.22 | +386.02 | +54.85 | -5 |
| STARLINK-33961 | 64047 | 5 | — | 321.65 | 3568.03 | +272.29 | +3250.32 | +91.10 | +3 |
| STARLINK-11730 [DTC] | 64074 | — | 5 | 1586.83 | 1802.27 | +1537.47 | +1484.56 | +82.37 | +5 |

## CH3 lower, 173.52–223.24 s

Track `sha256:f1bb043dc425f6c10d743e3e5effb1396c21a285178d53fa7f1773c543144bda`; 57 observations; 486 nominal-time satellites scored. Training leader: **STARLINK-36152 (NORAD 66968)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-6245 (NORAD 57079): leader heldout RMS **215.10 Hz** versus **5733.95 Hz**; gain **+5518.85 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36152 | 66968 | 1 | 1 | 64.59 | 215.10 | +0.00 | +0.00 | +0.00 | -4 |
| STARLINK-6245 | 57079 | 2 | 2 | 1021.98 | 5733.95 | +957.39 | +5518.85 | +96.25 | +5 |
| STARLINK-11240 [DTC] | 60929 | 3 | — | 2430.06 | 15678.46 | +2365.47 | +15463.36 | +98.63 | -4 |
| STARLINK-30292 | 57844 | 4 | — | 2605.03 | 18894.90 | +2540.44 | +18679.79 | +98.86 | -5 |
| STARLINK-33992 | 64026 | 5 | — | 3405.07 | 22376.20 | +3340.48 | +22161.09 | +99.04 | -5 |
| STARLINK-3972 | 52669 | — | 3 | 6925.14 | 5812.90 | +6860.55 | +5597.80 | +96.30 | +5 |
| STARLINK-11160 [DTC] | 60125 | — | 4 | 6821.26 | 8653.88 | +6756.66 | +8438.78 | +97.51 | +5 |
| STARLINK-1152 | 45096 | — | 5 | 3618.83 | 10308.32 | +3554.24 | +10093.22 | +97.91 | -5 |

## CH3 upper, 176.04–221.23 s

Track `sha256:a1f5a4b43ec0d09c5284c693da1080f61860d95a7bfb15103626b6795484e5e7`; 49 observations; 483 nominal-time satellites scored. Training leader: **STARLINK-36152 (NORAD 66968)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-6245 (NORAD 57079): leader heldout RMS **214.19 Hz** versus **5321.47 Hz**; gain **+5107.28 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36152 | 66968 | 1 | 1 | 79.59 | 214.19 | +0.00 | +0.00 | +0.00 | -4 |
| STARLINK-6245 | 57079 | 2 | 2 | 840.93 | 5321.47 | +761.33 | +5107.28 | +95.97 | +5 |
| STARLINK-11240 [DTC] | 60929 | 3 | — | 1782.51 | 14559.69 | +1702.92 | +14345.49 | +98.53 | -4 |
| STARLINK-30292 | 57844 | 4 | — | 2009.98 | 17567.41 | +1930.39 | +17353.22 | +98.78 | -5 |
| STARLINK-33992 | 64026 | 5 | — | 2777.18 | 20841.63 | +2697.59 | +20627.44 | +98.97 | -5 |
| STARLINK-3972 | 52669 | — | 3 | 5924.97 | 5927.41 | +5845.37 | +5713.22 | +96.39 | +5 |
| STARLINK-11160 [DTC] | 60125 | — | 4 | 5843.87 | 8508.72 | +5764.28 | +8294.52 | +97.48 | +5 |
| STARLINK-1152 | 45096 | — | 5 | 3152.52 | 9715.55 | +3072.93 | +9501.36 | +97.80 | -5 |

## CH4 lower, 176.29–208.52 s

Track `sha256:d05cf90a311599036c651a6b7e6e961f50c98f497879eb1418082b880b251a1d`; 35 observations; 473 nominal-time satellites scored. Training leader: **STARLINK-36152 (NORAD 66968)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-6245 (NORAD 57079): leader heldout RMS **42.78 Hz** versus **2581.52 Hz**; gain **+2538.74 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36152 | 66968 | 1 | 1 | 29.57 | 42.78 | +0.00 | +0.00 | +0.00 | -4 |
| STARLINK-6245 | 57079 | 2 | 2 | 349.17 | 2581.52 | +319.60 | +2538.74 | +98.34 | +5 |
| STARLINK-30292 | 57844 | 3 | 4 | 911.67 | 8399.76 | +882.11 | +8356.97 | +99.49 | -3 |
| STARLINK-33992 | 64026 | 4 | 5 | 932.88 | 9178.40 | +903.31 | +9135.61 | +99.53 | -5 |
| STARLINK-11240 [DTC] | 60929 | 5 | — | 1006.78 | 9526.02 | +977.21 | +9483.23 | +99.55 | +2 |
| STARLINK-1152 | 45096 | — | 3 | 2141.31 | 6839.35 | +2111.75 | +6796.57 | +99.37 | -5 |

## CH4 upper, 179.18–207.89 s

Track `sha256:1a272293fb32ee600b42ae66f3557ee41a5dc1956a0555f93950337cc1477ab3`; 31 observations; 471 nominal-time satellites scored. Training leader: **STARLINK-36152 (NORAD 66968)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-6245 (NORAD 57079): leader heldout RMS **53.14 Hz** versus **2467.26 Hz**; gain **+2414.12 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36152 | 66968 | 1 | 1 | 81.11 | 53.14 | +0.00 | +0.00 | +0.00 | -4 |
| STARLINK-6245 | 57079 | 2 | 2 | 407.99 | 2467.26 | +326.88 | +2414.12 | +97.85 | +5 |
| STARLINK-30292 | 57844 | 3 | 4 | 664.57 | 6851.13 | +583.46 | +6797.99 | +99.22 | -5 |
| STARLINK-11240 [DTC] | 60929 | 4 | 5 | 731.01 | 7032.42 | +649.90 | +6979.28 | +99.24 | -1 |
| STARLINK-33992 | 64026 | 5 | — | 995.52 | 8991.66 | +914.41 | +8938.51 | +99.41 | -5 |
| STARLINK-1152 | 45096 | — | 3 | 1879.94 | 6256.73 | +1798.83 | +6203.59 | +99.15 | -5 |

## CH1 upper, 273.93–297.63 s

Track `sha256:35a23bc66da558c11ec2c211fa10931368163f361d763edfe0966274d25bad64`; 27 observations; 473 nominal-time satellites scored. Training leader: **STARLINK-31567 (NORAD 59199)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-6351 (NORAD 57240): leader heldout RMS **126.03 Hz** versus **2525.23 Hz**; gain **+2399.20 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31567 | 59199 | 1 | 1 | 24.29 | 126.03 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-6351 | 57240 | 2 | 2 | 766.34 | 2525.23 | +742.06 | +2399.20 | +95.01 | -2 |
| STARLINK-36790 | 68095 | 3 | 5 | 1455.74 | 8071.89 | +1431.46 | +7945.86 | +98.44 | -5 |
| STARLINK-31646 | 59265 | 4 | 3 | 1576.06 | 6428.45 | +1551.77 | +6302.42 | +98.04 | -5 |
| STARLINK-4035 | 52690 | 5 | 4 | 2136.47 | 6799.25 | +2112.18 | +6673.22 | +98.15 | +5 |
