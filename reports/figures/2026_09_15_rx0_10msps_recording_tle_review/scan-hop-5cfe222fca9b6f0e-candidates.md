# Candidate RMS comparisons: scan-hop-5cfe222fca9b6f0e

[Ranked RMS plots for every track](scan-hop-5cfe222fca9b6f0e-rms.md).

Recorded **2026-09-14T21:10:12.525115Z**, RX0, 10 MS/s.

[Recording assessment and plots](scan-hop-5cfe222fca9b6f0e.md).

Each track has its own training-selected leader; there is no single satellite assignment for the whole recording. Lower RMS is better. The same observations and chronological split are used for all candidates within a track.

Gain = alternative RMS − training-leader RMS. Positive gain favors the leader; negative heldout gain means the alternative predicts better. Percent gain uses the alternative RMS as denominator; it is not identification confidence. Tau and carrier offset were selected on training data and remain frozen on heldout.

The archived screen retained the top five training candidates and top five heldout candidates, whose union is listed below. Candidate counts describe the full scored population; names/scores outside these retained lists were not archived. A blank rank means outside that top-five list. Catalogue exclusions and control results are in the linked recording assessment and evidence.

## CH3 lower, 41.99–62.91 s

Track `sha256:0259043fcb3f4a200de0d8dead3c6ad8ba11e3303c408c93b441cc5537b53407`; 22 observations; 483 nominal-time satellites scored. Training leader: **STARLINK-37103 (NORAD 68267)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-35873 (NORAD 67860): leader heldout RMS **41.39 Hz** versus **1639.54 Hz**; gain **+1598.15 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-37103 | 68267 | 1 | 1 | 28.55 | 41.39 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-30325 | 57717 | 2 | 3 | 953.21 | 2417.50 | +924.65 | +2376.11 | +98.29 | +5 |
| STARLINK-31544 | 59399 | 3 | 4 | 1101.77 | 4194.68 | +1073.22 | +4153.29 | +99.01 | -5 |
| STARLINK-35873 | 67860 | 4 | 2 | 1492.62 | 1639.54 | +1464.06 | +1598.15 | +97.48 | +5 |
| STARLINK-5945 | 56018 | 5 | 5 | 2569.85 | 7390.52 | +2541.30 | +7349.13 | +99.44 | +5 |

## CH1 lower, 93.78–119.00 s

Track `sha256:4fe2647e23ed58d5d7c1cb9fddea7a0be229759a1e189520d0a836655e4dd7f0`; 32 observations; 489 nominal-time satellites scored. Training leader: **STARLINK-30316 (NORAD 57673)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-33892 (NORAD 63783): leader heldout RMS **113.51 Hz** versus **3518.26 Hz**; gain **+3404.75 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30316 | 57673 | 1 | 1 | 66.76 | 113.51 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-33892 | 63783 | 2 | 2 | 1212.35 | 3518.26 | +1145.59 | +3404.75 | +96.77 | +5 |
| STARLINK-36950 | 67992 | 3 | 4 | 2034.65 | 9897.43 | +1967.89 | +9783.92 | +98.85 | -5 |
| STARLINK-36385 | 67717 | 4 | 3 | 2142.70 | 8391.62 | +2075.94 | +8278.11 | +98.65 | -1 |
| STARLINK-35873 | 67860 | 5 | — | 2159.43 | 12054.11 | +2092.67 | +11940.60 | +99.06 | -5 |
| STARLINK-32921 | 62920 | — | 5 | 2319.35 | 10354.12 | +2252.59 | +10240.61 | +98.90 | -5 |

## CH1 upper, 94.16–118.62 s

Track `sha256:a6eb994ad28e2f792ffa2d060eddb16717142e68f1e8a9953e8a931c07d7a979`; 31 observations; 489 nominal-time satellites scored. Training leader: **STARLINK-30316 (NORAD 57673)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-33892 (NORAD 63783): leader heldout RMS **104.37 Hz** versus **3474.36 Hz**; gain **+3369.99 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30316 | 57673 | 1 | 1 | 76.26 | 104.37 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-33892 | 63783 | 2 | 2 | 1161.52 | 3474.36 | +1085.27 | +3369.99 | +97.00 | +5 |
| STARLINK-36950 | 67992 | 3 | 4 | 1936.04 | 9617.60 | +1859.79 | +9513.23 | +98.91 | -5 |
| STARLINK-35873 | 67860 | 4 | — | 2047.35 | 11689.20 | +1971.09 | +11584.83 | +99.11 | -5 |
| STARLINK-36385 | 67717 | 5 | 3 | 2047.80 | 8188.28 | +1971.54 | +8083.91 | +98.73 | -1 |
| STARLINK-32921 | 62920 | — | 5 | 2211.70 | 10071.83 | +2135.44 | +9967.46 | +98.96 | -5 |

## CH2 upper, 94.41–115.46 s

Track `sha256:34a55daf71a6bcb422bd39d5673ef4206aaa9b103c99516abc05e99dddf7125d`; 26 observations; 489 nominal-time satellites scored. Training leader: **STARLINK-30316 (NORAD 57673)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-33892 (NORAD 63783): leader heldout RMS **116.77 Hz** versus **3124.32 Hz**; gain **+3007.55 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30316 | 57673 | 1 | 1 | 89.32 | 116.77 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-33892 | 63783 | 2 | 2 | 966.79 | 3124.32 | +877.48 | +3007.55 | +96.26 | +5 |
| STARLINK-36950 | 67992 | 3 | 4 | 1432.81 | 7823.42 | +1343.49 | +7706.65 | +98.51 | -5 |
| STARLINK-35873 | 67860 | 4 | — | 1435.90 | 9313.47 | +1346.58 | +9196.70 | +98.75 | -5 |
| STARLINK-36385 | 67717 | 5 | 3 | 1603.77 | 7040.27 | +1514.45 | +6923.50 | +98.34 | +0 |
| STARLINK-32921 | 62920 | — | 5 | 1678.97 | 8325.94 | +1589.66 | +8209.17 | +98.60 | -5 |

## CH1 lower, 179.10–220.42 s

Track `sha256:64db4e1282866fbbf3e3faf4446d7012b6a74aeef70d5e2d62150510e677854e`; 49 observations; 499 nominal-time satellites scored. Training leader: **STARLINK-34017 (NORAD 64339)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-36889 (NORAD 68006): leader heldout RMS **54.84 Hz** versus **5478.02 Hz**; gain **+5423.18 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34017 | 64339 | 1 | 1 | 107.96 | 54.84 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-32271 | 60368 | 2 | 3 | 457.21 | 5494.67 | +349.24 | +5439.83 | +99.00 | +4 |
| STARLINK-36889 | 68006 | 3 | 2 | 642.33 | 5478.02 | +534.37 | +5423.18 | +99.00 | +5 |
| STARLINK-32085 | 59685 | 4 | 5 | 804.29 | 9609.38 | +696.33 | +9554.54 | +99.43 | -5 |
| STARLINK-31116 | 58947 | 5 | — | 1306.66 | 9799.44 | +1198.70 | +9744.60 | +99.44 | +4 |
| STARLINK-3392 | 51123 | — | 4 | 4285.30 | 7970.08 | +4177.34 | +7915.24 | +99.31 | +5 |

## CH1 upper, 179.22–219.67 s

Track `sha256:17b28f308480efcd7851067928b54816b58bd8ef77ec6bb701927e5e06f21f2d`; 48 observations; 498 nominal-time satellites scored. Training leader: **STARLINK-34017 (NORAD 64339)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32271 (NORAD 60368): leader heldout RMS **87.45 Hz** versus **5253.91 Hz**; gain **+5166.46 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34017 | 64339 | 1 | 1 | 114.95 | 87.45 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-32271 | 60368 | 2 | 2 | 451.88 | 5253.91 | +336.93 | +5166.46 | +98.34 | +4 |
| STARLINK-36889 | 68006 | 3 | 3 | 622.85 | 5276.61 | +507.90 | +5189.16 | +98.34 | +5 |
| STARLINK-32085 | 59685 | 4 | 5 | 763.12 | 9160.42 | +648.17 | +9072.96 | +99.05 | -5 |
| STARLINK-31116 | 58947 | 5 | — | 1237.64 | 9437.96 | +1122.69 | +9350.51 | +99.07 | +4 |
| STARLINK-3392 | 51123 | — | 4 | 4197.55 | 8166.79 | +4082.60 | +8079.34 | +98.93 | +5 |

## CH2 lower, 179.35–217.90 s

Track `sha256:b91913b48d41b21a38cec0f07d83ea560ecfc471d4fdec33f34db1e908b6aaba`; 45 observations; 498 nominal-time satellites scored. Training leader: **STARLINK-34017 (NORAD 64339)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32271 (NORAD 60368): leader heldout RMS **94.81 Hz** versus **4838.89 Hz**; gain **+4744.08 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34017 | 64339 | 1 | 1 | 78.83 | 94.81 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-32271 | 60368 | 2 | 2 | 355.21 | 4838.89 | +276.39 | +4744.08 | +98.04 | +4 |
| STARLINK-36889 | 68006 | 3 | 3 | 516.61 | 4919.11 | +437.78 | +4824.30 | +98.07 | +5 |
| STARLINK-32085 | 59685 | 4 | 5 | 629.29 | 8436.03 | +550.46 | +8341.22 | +98.88 | -5 |
| STARLINK-31116 | 58947 | 5 | — | 1082.26 | 9136.81 | +1003.44 | +9042.00 | +98.96 | +5 |
| STARLINK-3392 | 51123 | — | 4 | 4012.49 | 8316.19 | +3933.67 | +8221.38 | +98.86 | +5 |

## CH2 upper, 180.10–203.54 s

Track `sha256:0daed154f02f337209d688fd6351c6ade476d047ba35617e09bcfec67ad14441`; 30 observations; 489 nominal-time satellites scored. Training leader: **STARLINK-34017 (NORAD 64339)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32271 (NORAD 60368): leader heldout RMS **102.42 Hz** versus **1300.60 Hz**; gain **+1198.18 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34017 | 64339 | 1 | 1 | 56.46 | 102.42 | +0.00 | +0.00 | +0.00 | -3 |
| STARLINK-32271 | 60368 | 2 | 2 | 117.37 | 1300.60 | +60.90 | +1198.18 | +92.13 | +2 |
| STARLINK-36889 | 68006 | 3 | 3 | 163.97 | 1627.08 | +107.51 | +1524.67 | +93.71 | +5 |
| STARLINK-32085 | 59685 | 4 | 5 | 329.03 | 3400.60 | +272.56 | +3298.18 | +96.99 | +1 |
| STARLINK-31116 | 58947 | 5 | 4 | 385.98 | 3242.57 | +329.52 | +3140.16 | +96.84 | +5 |

## CH4 upper, 209.58–239.56 s

Track `sha256:d20b10179110b6633d8dc3b4cb7775ec03a27657d9c7967c9cc7d53fc0b64675`; 35 observations; 495 nominal-time satellites scored. Training leader: **STARLINK-33842 (NORAD 63782)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-3354 (NORAD 51146): leader heldout RMS **57.66 Hz** versus **1775.65 Hz**; gain **+1717.99 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33842 | 63782 | 1 | 1 | 41.62 | 57.66 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-3354 | 51146 | 2 | 2 | 210.92 | 1775.65 | +169.30 | +1717.99 | +96.75 | -3 |
| STARLINK-3375 | 51114 | 3 | 4 | 445.37 | 3842.93 | +403.75 | +3785.26 | +98.50 | +5 |
| STARLINK-34017 | 64339 | 4 | 5 | 819.42 | 7023.62 | +777.80 | +6965.96 | +99.18 | -2 |
| STARLINK-3392 | 51123 | 5 | 3 | 847.89 | 1839.21 | +806.27 | +1781.54 | +96.86 | -5 |

## CH4 lower, 209.83–240.57 s

Track `sha256:b045b6c1e652847171351614e0ddb910c2a00cd7fb681491bebcb72ef318bcf3`; 35 observations; 497 nominal-time satellites scored. Training leader: **STARLINK-33842 (NORAD 63782)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-3392 (NORAD 51123): leader heldout RMS **43.92 Hz** versus **1822.26 Hz**; gain **+1778.34 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33842 | 63782 | 1 | 1 | 27.72 | 43.92 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-3354 | 51146 | 2 | 3 | 185.27 | 1856.90 | +157.54 | +1812.99 | +97.63 | -3 |
| STARLINK-3375 | 51114 | 3 | 4 | 491.86 | 3962.35 | +464.13 | +3918.43 | +98.89 | +5 |
| STARLINK-34017 | 64339 | 4 | 5 | 830.83 | 6704.70 | +803.11 | +6660.79 | +99.34 | -3 |
| STARLINK-3392 | 51123 | 5 | 2 | 831.84 | 1822.26 | +804.12 | +1778.34 | +97.59 | -5 |

## CH1 upper, 249.88–283.28 s

Track `sha256:093c39aa8c2f9a976a4134c15f8f3822a77c63558da0cf933c8478b09cf22712`; 37 observations; 498 nominal-time satellites scored. Training leader: **STARLINK-31251 (NORAD 58836)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-36040 (NORAD 66614): leader heldout RMS **95.38 Hz** versus **4171.52 Hz**; gain **+4076.14 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31251 | 58836 | 1 | 1 | 63.42 | 95.38 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-36040 | 66614 | 2 | 2 | 1222.53 | 4171.52 | +1159.11 | +4076.14 | +97.71 | +5 |
| STARLINK-31694 | 60140 | 3 | 3 | 1464.16 | 4757.60 | +1400.74 | +4662.23 | +98.00 | +5 |
| STARLINK-3354 | 51146 | 4 | — | 2393.10 | 12308.25 | +2329.68 | +12212.87 | +99.23 | -5 |
| STARLINK-36000 | 66807 | 5 | — | 3569.09 | 10529.10 | +3505.68 | +10433.73 | +99.09 | -4 |
| STARLINK-31977 | 59892 | — | 4 | 5086.08 | 9215.99 | +5022.67 | +9120.61 | +98.97 | +5 |
| STARLINK-30303 | 57677 | — | 5 | 5997.51 | 9242.43 | +5934.10 | +9147.05 | +98.97 | +5 |

## CH1 lower, 250.01–283.53 s

Track `sha256:d1ccca69a4d610af3e77232f798753fc34f31a83a94ad18a985ef4c19afaff21`; 39 observations; 498 nominal-time satellites scored. Training leader: **STARLINK-31251 (NORAD 58836)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-36040 (NORAD 66614): leader heldout RMS **275.83 Hz** versus **4320.17 Hz**; gain **+4044.35 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31251 | 58836 | 1 | 1 | 43.48 | 275.83 | +0.00 | +0.00 | +0.00 | +1 |
| STARLINK-36040 | 66614 | 2 | 2 | 1240.49 | 4320.17 | +1197.01 | +4044.35 | +93.62 | +5 |
| STARLINK-31694 | 60140 | 3 | 3 | 1482.13 | 4920.76 | +1438.65 | +4644.93 | +94.39 | +5 |
| STARLINK-3354 | 51146 | 4 | — | 2432.07 | 12830.64 | +2388.60 | +12554.82 | +97.85 | -5 |
| STARLINK-36000 | 66807 | 5 | — | 3584.03 | 10866.01 | +3540.55 | +10590.18 | +97.46 | -4 |
| STARLINK-30303 | 57677 | — | 4 | 5963.01 | 9299.39 | +5919.54 | +9023.56 | +97.03 | +5 |
| STARLINK-31977 | 59892 | — | 5 | 5066.68 | 9353.99 | +5023.20 | +9078.16 | +97.05 | +5 |

## CH3 lower, 253.16–276.48 s

Track `sha256:b6dfb59772b7a8f1907321a9c3af44dfb24d26b9005fa4f339255a71e96c17bc`; 25 observations; 488 nominal-time satellites scored. Training leader: **STARLINK-36040 (NORAD 66614)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-31694 (NORAD 60140): leader heldout RMS **126.39 Hz** versus **638.22 Hz**; gain **+511.83 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36040 | 66614 | 1 | 1 | 35.55 | 126.39 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-31694 | 60140 | 2 | 2 | 66.30 | 638.22 | +30.75 | +511.83 | +80.20 | +3 |
| STARLINK-31251 | 58836 | 3 | 3 | 595.42 | 2425.69 | +559.87 | +2299.30 | +94.79 | -5 |
| STARLINK-3354 | 51146 | 4 | — | 678.45 | 5533.75 | +642.90 | +5407.36 | +97.72 | -5 |
| STARLINK-36000 | 66807 | 5 | 4 | 1436.31 | 5208.35 | +1400.76 | +5081.96 | +97.57 | -4 |
| STARLINK-31977 | 59892 | — | 5 | 2493.08 | 5425.81 | +2457.53 | +5299.42 | +97.67 | +5 |

## CH1 upper, 207.06–229.74 s

Track `sha256:47e1673448a072c3065b13cd1a583d0c7b2c0cd469378ddad0237a9b134ca409`; 24 observations; 490 nominal-time satellites scored. Training leader: **STARLINK-33842 (NORAD 63782)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-3354 (NORAD 51146): leader heldout RMS **67.78 Hz** versus **673.64 Hz**; gain **+605.86 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33842 | 63782 | 1 | 1 | 16.57 | 67.78 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-3354 | 51146 | 2 | 2 | 81.57 | 673.64 | +65.00 | +605.86 | +89.94 | -2 |
| STARLINK-3375 | 51114 | 3 | 3 | 128.89 | 1172.07 | +112.32 | +1104.30 | +94.22 | +1 |
| STARLINK-36889 | 68006 | 4 | — | 439.40 | 4003.26 | +422.83 | +3935.48 | +98.31 | +3 |
| STARLINK-32271 | 60368 | 5 | — | 448.92 | 4286.70 | +432.35 | +4218.92 | +98.42 | +1 |
| STARLINK-3392 | 51123 | — | 4 | 644.66 | 1724.98 | +628.09 | +1657.20 | +96.07 | -5 |
| STARLINK-34017 | 64339 | — | 5 | 724.15 | 3352.94 | +707.58 | +3285.16 | +97.98 | +5 |

## CH1 lower, 212.98–239.94 s

Track `sha256:0e726c48ed07ebaa9a770b999c6e5302a9e3426b8d4d9a241819aa36844c4fab`; 29 observations; 494 nominal-time satellites scored. Training leader: **STARLINK-33842 (NORAD 63782)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-3354 (NORAD 51146): leader heldout RMS **54.07 Hz** versus **1463.58 Hz**; gain **+1409.52 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33842 | 63782 | 1 | 1 | 25.44 | 54.07 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-3354 | 51146 | 2 | 2 | 157.69 | 1463.58 | +132.25 | +1409.52 | +96.31 | -4 |
| STARLINK-3375 | 51114 | 3 | 4 | 476.63 | 3902.99 | +451.19 | +3848.92 | +98.61 | +5 |
| STARLINK-34017 | 64339 | 4 | 5 | 494.46 | 5705.79 | +469.02 | +5651.72 | +99.05 | -5 |
| STARLINK-3392 | 51123 | 5 | 3 | 655.26 | 1594.45 | +629.81 | +1540.38 | +96.61 | -5 |
