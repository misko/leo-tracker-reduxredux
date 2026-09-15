# Candidate RMS comparisons: scan-hop-aab019dd63812034

[Ranked RMS plots for every track](scan-hop-aab019dd63812034-rms.md).

Recorded **2026-09-14T20:00:12.557912Z**, RX0, 10 MS/s.

[Recording assessment and plots](scan-hop-aab019dd63812034.md).

Each track has its own training-selected leader; there is no single satellite assignment for the whole recording. Lower RMS is better. The same observations and chronological split are used for all candidates within a track.

Gain = alternative RMS − training-leader RMS. Positive gain favors the leader; negative heldout gain means the alternative predicts better. Percent gain uses the alternative RMS as denominator; it is not identification confidence. Tau and carrier offset were selected on training data and remain frozen on heldout.

The archived screen retained the top five training candidates and top five heldout candidates, whose union is listed below. Candidate counts describe the full scored population; names/scores outside these retained lists were not archived. A blank rank means outside that top-five list. Catalogue exclusions and control results are in the linked recording assessment and evidence.

## CH2 lower, 29.88–52.04 s

Track `sha256:ed6d6d809333bb69f028b97b8ecebc3bb27e6cd3425ccd18ac3976eb8ec22f04`; 24 observations; 467 nominal-time satellites scored. Training leader: **STARLINK-30989 (NORAD 58510)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30569 (NORAD 58068): leader heldout RMS **121.23 Hz** versus **1299.02 Hz**; gain **+1177.78 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30989 | 58510 | 1 | 1 | 60.57 | 121.23 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-30569 | 58068 | 2 | 2 | 112.00 | 1299.02 | +51.42 | +1177.78 | +90.67 | +4 |
| STARLINK-32553 | 62071 | 3 | 3 | 191.25 | 2046.33 | +130.68 | +1925.10 | +94.08 | -5 |
| STARLINK-31776 | 59603 | 4 | — | 395.79 | 3787.65 | +335.21 | +3666.41 | +96.80 | +5 |
| STARLINK-11726 [DTC] | 64067 | 5 | — | 486.82 | 5301.07 | +426.25 | +5179.84 | +97.71 | +5 |
| STARLINK-2581 | 48412 | — | 4 | 770.44 | 2445.15 | +709.86 | +2323.92 | +95.04 | -5 |
| STARLINK-1828 | 46725 | — | 5 | 927.75 | 2727.25 | +867.18 | +2606.02 | +95.55 | -5 |

## CH4 upper, 60.98–102.85 s

Track `sha256:8a3dd8b64c6354ae1bdbdbed4c876a533815f947330ec37c281c3a7f6c6f3ddc`; 48 observations; 488 nominal-time satellites scored. Training leader: **STARLINK-31592 (NORAD 59467)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-34677 (NORAD 65031): leader heldout RMS **120.51 Hz** versus **1097.94 Hz**; gain **+977.43 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31592 | 59467 | 1 | 1 | 56.24 | 120.51 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-30151 | 56827 | 2 | 3 | 155.59 | 1455.06 | +99.34 | +1334.55 | +91.72 | +3 |
| STARLINK-35469 | 65863 | 3 | 4 | 592.37 | 5611.45 | +536.12 | +5490.94 | +97.85 | -5 |
| STARLINK-30989 | 58510 | 4 | — | 1218.05 | 10116.57 | +1161.80 | +9996.06 | +98.81 | -5 |
| STARLINK-34677 | 65031 | 5 | 2 | 1284.92 | 1097.94 | +1228.68 | +977.43 | +89.02 | +5 |
| STARLINK-4082 | 52658 | — | 5 | 3079.85 | 10080.27 | +3023.61 | +9959.76 | +98.80 | +5 |

## CH4 lower, 61.35–96.15 s

Track `sha256:a244216ec00282f10127910008a49877c90b637cdce292f54da1c2f01a878a50`; 42 observations; 479 nominal-time satellites scored. Training leader: **STARLINK-31592 (NORAD 59467)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30151 (NORAD 56827): leader heldout RMS **64.98 Hz** versus **933.40 Hz**; gain **+868.42 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31592 | 59467 | 1 | 1 | 32.75 | 64.98 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-30151 | 56827 | 2 | 2 | 119.46 | 933.40 | +86.72 | +868.42 | +93.04 | +3 |
| STARLINK-35469 | 65863 | 3 | 4 | 481.50 | 3643.09 | +448.76 | +3578.11 | +98.22 | -5 |
| STARLINK-30989 | 58510 | 4 | 5 | 1018.35 | 8403.78 | +985.60 | +8338.80 | +99.23 | -2 |
| STARLINK-1828 | 46725 | 5 | — | 1175.20 | 9438.92 | +1142.45 | +9373.94 | +99.31 | -4 |
| STARLINK-34677 | 65031 | — | 3 | 1191.01 | 1062.45 | +1158.27 | +997.47 | +93.88 | +5 |

## CH4 lower, 106.39–144.29 s

Track `sha256:23597cd9bc4bc77438fc10fe7159aa93149623e5cf0a6bb0929d8b7732bf04a5`; 50 observations; 484 nominal-time satellites scored. Training leader: **STARLINK-32194 (NORAD 60315)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37424 (NORAD 69192): leader heldout RMS **117.07 Hz** versus **7964.20 Hz**; gain **+7847.13 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32194 | 60315 | 1 | 1 | 127.08 | 117.07 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-34677 | 65031 | 2 | 4 | 1150.61 | 12378.31 | +1023.53 | +12261.25 | +99.05 | -5 |
| STARLINK-37424 | 69192 | 3 | 2 | 2596.59 | 7964.20 | +2469.51 | +7847.13 | +98.53 | +5 |
| STARLINK-5843 | 57072 | 4 | — | 2743.40 | 14702.02 | +2616.32 | +14584.95 | +99.20 | -5 |
| STARLINK-34587 | 64735 | 5 | 5 | 2897.46 | 13700.21 | +2770.38 | +13583.14 | +99.15 | +5 |
| STARLINK-30962 | 58458 | — | 3 | 4482.32 | 12324.63 | +4355.24 | +12207.56 | +99.05 | +5 |

## CH4 upper, 107.14–143.16 s

Track `sha256:78c0112328fc277bd3b96ff723f089156c791dac0dd0762dfacb4432c7d27a8f`; 48 observations; 482 nominal-time satellites scored. Training leader: **STARLINK-32194 (NORAD 60315)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37424 (NORAD 69192): leader heldout RMS **111.37 Hz** versus **7708.73 Hz**; gain **+7597.36 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32194 | 60315 | 1 | 1 | 118.22 | 111.37 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-34677 | 65031 | 2 | 3 | 924.27 | 11431.08 | +806.04 | +11319.72 | +99.03 | -5 |
| STARLINK-37424 | 69192 | 3 | 2 | 2331.08 | 7708.73 | +2212.85 | +7597.36 | +98.56 | +5 |
| STARLINK-5843 | 57072 | 4 | — | 2410.60 | 13856.48 | +2292.38 | +13745.11 | +99.20 | -5 |
| STARLINK-34587 | 64735 | 5 | 5 | 2566.00 | 12972.70 | +2447.77 | +12861.33 | +99.14 | +5 |
| STARLINK-30962 | 58458 | — | 4 | 4061.35 | 12001.41 | +3943.12 | +11890.04 | +99.07 | +5 |

## CH1 lower, 150.48–180.34 s

Track `sha256:083aa8c28e166ad411fd9a26be502948e0859c17e3ba32112db71b6425955f72`; 33 observations; 478 nominal-time satellites scored. Training leader: **STARLINK-30962 (NORAD 58458)**; heldout rank 5 in the full scored population.

Against the best other heldout candidate, STARLINK-30069 (NORAD 56834): leader heldout RMS **5385.52 Hz** versus **730.00 Hz**; gain **-4655.51 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30962 | 58458 | 1 | 5 | 1118.99 | 5385.52 | +0.00 | +0.00 | +0.00 | -5 |
| STARLINK-37424 | 69192 | 2 | — | 1224.23 | 8099.07 | +105.25 | +2713.55 | +33.50 | -5 |
| STARLINK-33847 | 63685 | 3 | 2 | 1252.39 | 3430.53 | +133.41 | -1954.99 | -56.99 | +5 |
| STARLINK-11619 [DTC] | 63272 | 4 | — | 1315.46 | 13532.01 | +196.48 | +8146.49 | +60.20 | -5 |
| STARLINK-30069 | 56834 | 5 | 1 | 1371.97 | 730.00 | +252.98 | -4655.51 | -637.74 | +0 |
| STARLINK-35726 | 66280 | — | 3 | 2029.18 | 4701.71 | +910.19 | -683.80 | -14.54 | -5 |
| STARLINK-11436 [DTC] | 62887 | — | 4 | 1777.35 | 5168.55 | +658.36 | -216.97 | -4.20 | +5 |

## CH1 upper, 150.98–180.47 s

Track `sha256:dd0e9176c5e6068c3a524ae9ba5d6eb79d89d277aa3d997480c34c1a9f32db54`; 33 observations; 478 nominal-time satellites scored. Training leader: **STARLINK-30069 (NORAD 56834)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-35726 (NORAD 66280): leader heldout RMS **78.56 Hz** versus **3714.50 Hz**; gain **+3635.94 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30069 | 56834 | 1 | 1 | 67.38 | 78.56 | +0.00 | +0.00 | +0.00 | +1 |
| STARLINK-30962 | 58458 | 2 | 5 | 543.26 | 5884.85 | +475.88 | +5806.29 | +98.66 | -5 |
| STARLINK-33847 | 63685 | 3 | 4 | 550.31 | 4073.89 | +482.93 | +3995.33 | +98.07 | +5 |
| STARLINK-11436 [DTC] | 62887 | 4 | 3 | 785.46 | 4029.83 | +718.08 | +3951.26 | +98.05 | +5 |
| STARLINK-37424 | 69192 | 5 | — | 937.37 | 8497.12 | +869.98 | +8418.55 | +99.08 | -5 |
| STARLINK-35726 | 66280 | — | 2 | 1176.05 | 3714.50 | +1108.66 | +3635.94 | +97.88 | -5 |

## CH4 lower, 213.11–253.55 s

Track `sha256:bcaff321ebbf68573103fb146fb84f9dec056a42c3a51d0ca78e6ad853722f7b`; 49 observations; 473 nominal-time satellites scored. Training leader: **STARLINK-31770 (NORAD 59601)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-2642 (NORAD 48437): leader heldout RMS **496.47 Hz** versus **3517.06 Hz**; gain **+3020.59 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31770 | 59601 | 1 | 1 | 127.20 | 496.47 | +0.00 | +0.00 | +0.00 | +1 |
| STARLINK-2642 | 48437 | 2 | 2 | 464.92 | 3517.06 | +337.72 | +3020.59 | +85.88 | -5 |
| STARLINK-4095 | 53170 | 3 | 3 | 975.90 | 4854.61 | +848.70 | +4358.14 | +89.77 | +5 |
| STARLINK-32447 | 61261 | 4 | 4 | 1283.24 | 6564.95 | +1156.03 | +6068.48 | +92.44 | +5 |
| STARLINK-31278 | 59163 | 5 | — | 2304.59 | 15086.08 | +2177.39 | +14589.61 | +96.71 | -5 |
| STARLINK-5518 | 56469 | — | 5 | 4210.72 | 9676.99 | +4083.52 | +9180.52 | +94.87 | +5 |

## CH4 upper, 213.23–253.68 s

Track `sha256:8ddf41f9d1e9c25a54f6d9467a1e809eb16a6861851c847ba85ba64182c78fd8`; 49 observations; 473 nominal-time satellites scored. Training leader: **STARLINK-31770 (NORAD 59601)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-2642 (NORAD 48437): leader heldout RMS **480.28 Hz** versus **3531.90 Hz**; gain **+3051.62 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31770 | 59601 | 1 | 1 | 144.25 | 480.28 | +0.00 | +0.00 | +0.00 | +1 |
| STARLINK-2642 | 48437 | 2 | 2 | 478.91 | 3531.90 | +334.66 | +3051.62 | +86.40 | -5 |
| STARLINK-4095 | 53170 | 3 | 3 | 1035.17 | 4850.71 | +890.92 | +4370.43 | +90.10 | +5 |
| STARLINK-32447 | 61261 | 4 | 4 | 1346.77 | 6248.50 | +1202.52 | +5768.22 | +92.31 | +4 |
| STARLINK-31278 | 59163 | 5 | — | 2396.14 | 15156.54 | +2251.89 | +14676.26 | +96.83 | -5 |
| STARLINK-5518 | 56469 | — | 5 | 4248.01 | 9612.01 | +4103.76 | +9131.73 | +95.00 | +5 |

## CH1 lower, 220.79–253.94 s

Track `sha256:4624e9c01c4c4f1fe278c57ac49f49022108f0d5f0418357b15035c893b52aa0`; 40 observations; 468 nominal-time satellites scored. Training leader: **STARLINK-31770 (NORAD 59601)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4095 (NORAD 53170): leader heldout RMS **572.42 Hz** versus **3727.48 Hz**; gain **+3155.07 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31770 | 59601 | 1 | 1 | 106.05 | 572.42 | +0.00 | +0.00 | +0.00 | +1 |
| STARLINK-2642 | 48437 | 2 | 3 | 642.03 | 3981.86 | +535.98 | +3409.44 | +85.62 | -5 |
| STARLINK-4095 | 53170 | 3 | 2 | 1136.29 | 3727.48 | +1030.24 | +3155.07 | +84.64 | +2 |
| STARLINK-32447 | 61261 | 4 | 4 | 1432.40 | 4653.64 | +1326.35 | +4081.22 | +87.70 | +0 |
| STARLINK-11535 [DTC] | 62595 | 5 | — | 3039.39 | 7456.66 | +2933.34 | +6884.24 | +92.32 | +5 |
| STARLINK-5518 | 56469 | — | 5 | 3194.71 | 6916.50 | +3088.66 | +6344.08 | +91.72 | +5 |

## CH1 upper, 224.45–254.19 s

Track `sha256:b369178de507c37899ca8f86b636c1379a0efd1a10db6e86754b311b56d5f4dc`; 37 observations; 467 nominal-time satellites scored. Training leader: **STARLINK-31770 (NORAD 59601)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4095 (NORAD 53170): leader heldout RMS **340.49 Hz** versus **3050.39 Hz**; gain **+2709.90 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31770 | 59601 | 1 | 1 | 131.09 | 340.49 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-2642 | 48437 | 2 | 4 | 769.01 | 4033.63 | +637.92 | +3693.14 | +91.56 | -5 |
| STARLINK-4095 | 53170 | 3 | 2 | 1074.48 | 3050.39 | +943.39 | +2709.90 | +88.84 | +0 |
| STARLINK-32447 | 61261 | 4 | 3 | 1344.20 | 3908.54 | +1213.11 | +3568.05 | +91.29 | -2 |
| STARLINK-11535 [DTC] | 62595 | 5 | — | 2702.49 | 6676.09 | +2571.40 | +6335.60 | +94.90 | +5 |
| STARLINK-11239 [DTC] | 60924 | — | 5 | 3100.63 | 5962.43 | +2969.53 | +5621.94 | +94.29 | +5 |
