# Candidate RMS comparisons: scan-hop-499abcb9ca352397

Recorded **2026-09-14T16:40:12.231571Z**, RX0, 10 MS/s.

[Recording assessment and plots](scan-hop-499abcb9ca352397.md).

Each track has its own training-selected leader; there is no single satellite assignment for the whole recording. Lower RMS is better. The same observations and chronological split are used for all candidates within a track.

Gain = alternative RMS − training-leader RMS. Positive gain favors the leader; negative heldout gain means the alternative predicts better. Percent gain uses the alternative RMS as denominator; it is not identification confidence. Tau and carrier offset were selected on training data and remain frozen on heldout.

The archived screen retained the top five training candidates and top five heldout candidates, whose union is listed below. Candidate counts describe the full scored population; names/scores outside these retained lists were not archived. A blank rank means outside that top-five list. Catalogue exclusions and control results are in the linked recording assessment and evidence.

## CH3 lower, 30.02–58.99 s

Track `sha256:a194540efacfd217afba8903cb2c95c780b472179dd28186f14c287eee3db31b`; 38 observations; 605 nominal-time satellites scored. Training leader: **STARLINK-2420 (NORAD 47831)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-35437 (NORAD 66563): leader heldout RMS **125.35 Hz** versus **152.33 Hz**; gain **+26.98 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-2420 | 47831 | 1 | 1 | 24.08 | 125.35 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-35437 | 66563 | 2 | 2 | 25.56 | 152.33 | +1.48 | +26.98 | +17.71 | +0 |
| STARLINK-33792 | 63506 | 3 | 3 | 282.22 | 486.80 | +258.14 | +361.45 | +74.25 | -5 |
| STARLINK-33798 | 63449 | 4 | — | 338.24 | 2707.07 | +314.16 | +2581.72 | +95.37 | +5 |
| STARLINK-36744 | 67987 | 5 | 4 | 1023.87 | 1889.56 | +999.79 | +1764.21 | +93.37 | +5 |
| STARLINK-30858 | 58358 | — | 5 | 2547.58 | 1969.56 | +2523.51 | +1844.20 | +93.64 | +5 |

## CH4 upper, 60.00–82.79 s

Track `sha256:7864b0282d7c335c4133fd26f834dda7b8cd9535a78ea463d96b2a7078cec263`; 30 observations; 612 nominal-time satellites scored. Training leader: **STARLINK-2422 (NORAD 47832)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-35344 (NORAD 65656): leader heldout RMS **120.22 Hz** versus **2335.22 Hz**; gain **+2215.00 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-2422 | 47832 | 1 | 1 | 44.47 | 120.22 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-11166 | 60062 | 2 | 4 | 902.90 | 2894.36 | +858.43 | +2774.14 | +95.85 | +5 |
| STARLINK-38010 | 69727 | 3 | — | 953.57 | 8555.09 | +909.10 | +8434.87 | +98.59 | -5 |
| STARLINK-36744 | 67987 | 4 | — | 1190.34 | 4829.96 | +1145.87 | +4709.74 | +97.51 | -5 |
| STARLINK-11654 | 63265 | 5 | 3 | 1225.75 | 2777.63 | +1181.28 | +2657.40 | +95.67 | +5 |
| STARLINK-35344 | 65656 | — | 2 | 1653.56 | 2335.22 | +1609.10 | +2215.00 | +94.85 | +5 |
| STARLINK-32088 | 59693 | — | 5 | 2072.26 | 4245.77 | +2027.79 | +4125.55 | +97.17 | +5 |

## CH2 lower, 75.36–101.56 s

Track `sha256:54856449576e366f341aaef2c7dcdc014e216226ec7e4365379b1a8cd5770def`; 27 observations; 611 nominal-time satellites scored. Training leader: **STARLINK-32088 (NORAD 59693)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11654 (NORAD 63265): leader heldout RMS **35.30 Hz** versus **839.76 Hz**; gain **+804.46 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32088 | 59693 | 1 | 1 | 38.62 | 35.30 | +0.00 | +0.00 | +0.00 | +3 |
| STARLINK-11654 | 63265 | 2 | 2 | 143.64 | 839.76 | +105.02 | +804.46 | +95.80 | -3 |
| STARLINK-37390 | 68782 | 3 | 3 | 161.73 | 1778.80 | +123.12 | +1743.50 | +98.02 | +2 |
| STARLINK-35403 | 66081 | 4 | 4 | 194.68 | 2132.42 | +156.06 | +2097.12 | +98.34 | +2 |
| STARLINK-35344 | 65656 | 5 | — | 323.07 | 3303.74 | +284.46 | +3268.44 | +98.93 | -5 |
| STARLINK-31508 | 59503 | — | 5 | 909.74 | 3257.65 | +871.12 | +3222.35 | +98.92 | +3 |

## CH2 upper, 76.12–98.42 s

Track `sha256:f961bf159253374576a1c0487ac5778e0c0742f4405408b3afdf34fd062c563d`; 23 observations; 608 nominal-time satellites scored. Training leader: **STARLINK-32088 (NORAD 59693)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11654 (NORAD 63265): leader heldout RMS **38.45 Hz** versus **744.68 Hz**; gain **+706.24 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32088 | 59693 | 1 | 1 | 54.07 | 38.45 | +0.00 | +0.00 | +0.00 | +3 |
| STARLINK-11654 | 63265 | 2 | 2 | 86.02 | 744.68 | +31.95 | +706.24 | +94.84 | -2 |
| STARLINK-37390 | 68782 | 3 | 3 | 132.85 | 1302.31 | +78.79 | +1263.86 | +97.05 | +3 |
| STARLINK-35403 | 66081 | 4 | 4 | 163.19 | 1429.24 | +109.12 | +1390.79 | +97.31 | +2 |
| STARLINK-35344 | 65656 | 5 | 5 | 211.49 | 2274.02 | +157.42 | +2235.57 | +98.31 | -5 |

## CH2 lower, 120.47–144.67 s

Track `sha256:fccf1f66a163fac485127a5764474828c27dd58042cd9ae1bdcf0a8286e3ddb9`; 25 observations; 603 nominal-time satellites scored. Training leader: **STARLINK-36126 (NORAD 66866)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32104 (NORAD 59695): leader heldout RMS **110.95 Hz** versus **722.26 Hz**; gain **+611.31 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36126 | 66866 | 1 | 1 | 17.81 | 110.95 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-32104 | 59695 | 2 | 2 | 151.33 | 722.26 | +133.52 | +611.31 | +84.64 | -4 |
| STARLINK-36168 | 68677 | 3 | — | 301.51 | 2518.20 | +283.70 | +2407.25 | +95.59 | -3 |
| STARLINK-35129 | 66077 | 4 | 4 | 790.34 | 1942.35 | +772.53 | +1831.40 | +94.29 | +5 |
| STARLINK-11484 | 62277 | 5 | — | 916.11 | 9293.52 | +898.30 | +9182.57 | +98.81 | -4 |
| STARLINK-35868 | 66579 | — | 3 | 970.53 | 1733.10 | +952.72 | +1622.16 | +93.60 | +5 |
| STARLINK-35542 | 66064 | — | 5 | 1405.89 | 2149.95 | +1388.08 | +2039.00 | +94.84 | +5 |

## CH1 lower, 178.18–217.13 s

Track `sha256:8a03a56c2858e3a6490651b4812d51716dcc3a045592f912d9156a99e2c068b3`; 45 observations; 608 nominal-time satellites scored. Training leader: **STARLINK-33846 (NORAD 63780)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-33807 (NORAD 63518): leader heldout RMS **131.23 Hz** versus **2279.58 Hz**; gain **+2148.34 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33846 | 63780 | 1 | 1 | 113.31 | 131.23 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-37030 | 68220 | 2 | 3 | 338.19 | 3025.05 | +224.88 | +2893.82 | +95.66 | +4 |
| STARLINK-33807 | 63518 | 3 | 2 | 629.10 | 2279.58 | +515.79 | +2148.34 | +94.24 | +5 |
| STARLINK-5367 | 55501 | 4 | 4 | 643.43 | 4714.21 | +530.12 | +4582.97 | +97.22 | +5 |
| STARLINK-30888 | 58370 | 5 | — | 800.79 | 7111.74 | +687.48 | +6980.50 | +98.15 | -5 |
| STARLINK-38007 | 69723 | — | 5 | 3442.64 | 4925.15 | +3329.34 | +4793.92 | +97.34 | +5 |

## CH4 lower, 178.56–219.54 s

Track `sha256:f4109860ad11fecb21e01f4ddc5117fa33e1221aaa388a68b6a04be4903c6762`; 47 observations; 611 nominal-time satellites scored. Training leader: **STARLINK-33846 (NORAD 63780)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-33807 (NORAD 63518): leader heldout RMS **134.67 Hz** versus **2920.46 Hz**; gain **+2785.79 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33846 | 63780 | 1 | 1 | 75.12 | 134.67 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-37030 | 68220 | 2 | 3 | 380.99 | 3510.06 | +305.87 | +3375.39 | +96.16 | +4 |
| STARLINK-33807 | 63518 | 3 | 2 | 555.15 | 2920.46 | +480.03 | +2785.79 | +95.39 | +5 |
| STARLINK-5367 | 55501 | 4 | 5 | 748.11 | 5331.67 | +672.98 | +5197.00 | +97.47 | +5 |
| STARLINK-30888 | 58370 | 5 | — | 875.56 | 8411.37 | +800.44 | +8276.70 | +98.40 | -5 |
| STARLINK-38007 | 69723 | — | 4 | 3425.09 | 4265.74 | +3349.96 | +4131.06 | +96.84 | +5 |

## CH4 upper, 178.68–218.91 s

Track `sha256:228b2876808a59d1421811f27ba055680c2e0ec34804adaa65cead86d2f62ea8`; 46 observations; 609 nominal-time satellites scored. Training leader: **STARLINK-33846 (NORAD 63780)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-33807 (NORAD 63518): leader heldout RMS **135.13 Hz** versus **2742.45 Hz**; gain **+2607.32 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33846 | 63780 | 1 | 1 | 71.31 | 135.13 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-37030 | 68220 | 2 | 3 | 354.99 | 3367.03 | +283.68 | +3231.90 | +95.99 | +4 |
| STARLINK-33807 | 63518 | 3 | 2 | 549.33 | 2742.45 | +478.02 | +2607.32 | +95.07 | +5 |
| STARLINK-5367 | 55501 | 4 | 5 | 696.14 | 5141.11 | +624.83 | +5005.98 | +97.37 | +5 |
| STARLINK-30888 | 58370 | 5 | — | 822.25 | 8032.99 | +750.94 | +7897.86 | +98.32 | -5 |
| STARLINK-38007 | 69723 | — | 4 | 3365.54 | 4416.85 | +3294.23 | +4281.72 | +96.94 | +5 |

## CH1 upper, 179.19–218.27 s

Track `sha256:1c96cf17ebf24f992590f229ad4e8826847c9ab47e198945e0383614a0d23b36`; 44 observations; 608 nominal-time satellites scored. Training leader: **STARLINK-33846 (NORAD 63780)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-33807 (NORAD 63518): leader heldout RMS **159.03 Hz** versus **2656.87 Hz**; gain **+2497.83 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33846 | 63780 | 1 | 1 | 78.39 | 159.03 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-37030 | 68220 | 2 | 3 | 385.66 | 3268.47 | +307.27 | +3109.44 | +95.13 | +4 |
| STARLINK-33807 | 63518 | 3 | 2 | 538.62 | 2656.87 | +460.23 | +2497.83 | +94.01 | +5 |
| STARLINK-5367 | 55501 | 4 | 5 | 753.13 | 4987.94 | +674.73 | +4828.91 | +96.81 | +5 |
| STARLINK-30888 | 58370 | 5 | — | 839.19 | 7792.12 | +760.80 | +7633.08 | +97.96 | -5 |
| STARLINK-38007 | 69723 | — | 4 | 3372.79 | 4282.10 | +3294.40 | +4123.06 | +96.29 | +5 |

## CH2 lower, 186.26–209.56 s

Track `sha256:c2db5df08e95504900c5e8318274be1693db6456fb8994869e36a6f0f4b94992`; 25 observations; 588 nominal-time satellites scored. Training leader: **STARLINK-34980 (NORAD 65258)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-34862 (NORAD 65180): leader heldout RMS **62.85 Hz** versus **663.57 Hz**; gain **+600.72 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34980 | 65258 | 1 | 1 | 51.70 | 62.85 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-34862 | 65180 | 2 | 2 | 433.70 | 663.57 | +382.00 | +600.72 | +90.53 | +5 |
| STARLINK-32566 | 61958 | 3 | 4 | 2017.29 | 7050.70 | +1965.60 | +6987.85 | +99.11 | -5 |
| STARLINK-11397 | 62590 | 4 | — | 2181.12 | 9336.84 | +2129.42 | +9274.00 | +99.33 | -5 |
| STARLINK-33846 | 63780 | 5 | 5 | 2581.66 | 7210.74 | +2529.96 | +7147.89 | +99.13 | +5 |
| STARLINK-33807 | 63518 | — | 3 | 3055.90 | 6407.07 | +3004.20 | +6344.23 | +99.02 | +5 |

## CH2 upper, 186.77–209.06 s

Track `sha256:49598b01b6e7e4982b2b5b22a791c180196df34d9a87a20b5ab2270e67bf77fb`; 26 observations; 587 nominal-time satellites scored. Training leader: **STARLINK-34980 (NORAD 65258)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-34862 (NORAD 65180): leader heldout RMS **91.55 Hz** versus **643.04 Hz**; gain **+551.49 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34980 | 65258 | 1 | 1 | 49.55 | 91.55 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-34862 | 65180 | 2 | 2 | 385.44 | 643.04 | +335.89 | +551.49 | +85.76 | +5 |
| STARLINK-32566 | 61958 | 3 | 4 | 1792.20 | 6785.79 | +1742.65 | +6694.24 | +98.65 | -5 |
| STARLINK-11397 | 62590 | 4 | — | 1947.72 | 8998.57 | +1898.17 | +8907.02 | +98.98 | -5 |
| STARLINK-33846 | 63780 | 5 | 5 | 2321.17 | 6987.26 | +2271.62 | +6895.71 | +98.69 | +5 |
| STARLINK-33807 | 63518 | — | 3 | 2775.13 | 6279.86 | +2725.58 | +6188.31 | +98.54 | +5 |

## CH2 upper, 120.10–140.25 s

Track `sha256:a495291569c6d48136bb61596c7e16fd1de3541fd2d39396d6377abd3fe771ed`; 21 observations; 601 nominal-time satellites scored. Training leader: **STARLINK-36126 (NORAD 66866)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32104 (NORAD 59695): leader heldout RMS **217.03 Hz** versus **289.80 Hz**; gain **+72.77 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36126 | 66866 | 1 | 1 | 54.62 | 217.03 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-32104 | 59695 | 2 | 2 | 216.91 | 289.80 | +162.28 | +72.77 | +25.11 | -4 |
| STARLINK-36168 | 68677 | 3 | — | 220.18 | 1888.27 | +165.55 | +1671.24 | +88.51 | -2 |
| STARLINK-11484 | 62277 | 4 | — | 581.10 | 6288.35 | +526.48 | +6071.32 | +96.55 | -2 |
| STARLINK-35129 | 66077 | 5 | 5 | 625.01 | 1802.31 | +570.39 | +1585.28 | +87.96 | +5 |
| STARLINK-35868 | 66579 | — | 3 | 1094.77 | 756.15 | +1040.14 | +539.12 | +71.30 | +5 |
| STARLINK-35542 | 66064 | — | 4 | 1541.47 | 1163.06 | +1486.85 | +946.03 | +81.34 | +5 |

## CH1 lower, 188.03–208.43 s

Track `sha256:f79ccc89382519a453a791d973529bd92b2bcf631ceede70d1eec9703f80be15`; 23 observations; 587 nominal-time satellites scored. Training leader: **STARLINK-34980 (NORAD 65258)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-34862 (NORAD 65180): leader heldout RMS **66.92 Hz** versus **600.20 Hz**; gain **+533.28 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34980 | 65258 | 1 | 1 | 35.42 | 66.92 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-34862 | 65180 | 2 | 2 | 337.19 | 600.20 | +301.77 | +533.28 | +88.85 | +5 |
| STARLINK-32566 | 61958 | 3 | 4 | 1588.11 | 6295.11 | +1552.70 | +6228.19 | +98.94 | -5 |
| STARLINK-11397 | 62590 | 4 | — | 1721.62 | 8346.86 | +1686.20 | +8279.94 | +99.20 | -5 |
| STARLINK-33846 | 63780 | 5 | 5 | 2026.96 | 6469.37 | +1991.54 | +6402.45 | +98.97 | +5 |
| STARLINK-33807 | 63518 | — | 3 | 2391.19 | 5808.14 | +2355.77 | +5741.22 | +98.85 | +5 |

## CH1 upper, 186.39–209.44 s

Track `sha256:e57c42d4ea48709afbda80fd5591b15fa513307e47dd197bc67f4e210122d6d1`; 27 observations; 588 nominal-time satellites scored. Training leader: **STARLINK-34980 (NORAD 65258)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-34862 (NORAD 65180): leader heldout RMS **91.34 Hz** versus **662.01 Hz**; gain **+570.67 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34980 | 65258 | 1 | 1 | 73.25 | 91.34 | +0.00 | +0.00 | +0.00 | -2 |
| STARLINK-34862 | 65180 | 2 | 2 | 420.43 | 662.01 | +347.18 | +570.67 | +86.20 | +5 |
| STARLINK-32566 | 61958 | 3 | 4 | 1910.58 | 7032.25 | +1837.33 | +6940.91 | +98.70 | -5 |
| STARLINK-11397 | 62590 | 4 | — | 2068.46 | 9324.24 | +1995.20 | +9232.90 | +99.02 | -5 |
| STARLINK-33846 | 63780 | 5 | 5 | 2473.93 | 7218.82 | +2400.68 | +7127.48 | +98.73 | +5 |
| STARLINK-33807 | 63518 | — | 3 | 2958.33 | 6451.16 | +2885.07 | +6359.83 | +98.58 | +5 |
