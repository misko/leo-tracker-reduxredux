# Candidate RMS comparisons: scan-hop-4d85ec3c4f985f42

[Ranked RMS plots for every track](scan-hop-4d85ec3c4f985f42-rms.md).

Recorded **2026-09-14T21:50:12.467072Z**, RX0, 10 MS/s.

[Recording assessment and plots](scan-hop-4d85ec3c4f985f42.md).

Each track has its own training-selected leader; there is no single satellite assignment for the whole recording. Lower RMS is better. The same observations and chronological split are used for all candidates within a track.

Gain = alternative RMS − training-leader RMS. Positive gain favors the leader; negative heldout gain means the alternative predicts better. Percent gain uses the alternative RMS as denominator; it is not identification confidence. Tau and carrier offset were selected on training data and remain frozen on heldout.

The archived screen retained the top five training candidates and top five heldout candidates, whose union is listed below. Candidate counts describe the full scored population; names/scores outside these retained lists were not archived. A blank rank means outside that top-five list. Catalogue exclusions and control results are in the linked recording assessment and evidence.

## CH4 lower, 60.11–81.30 s

Track `sha256:72037cd60e65102efed730a71a5247b62112d1db656a47d891cde9750b81524b`; 22 observations; 472 nominal-time satellites scored. Training leader: **STARLINK-30407 (NORAD 57823)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11690 (NORAD 64242): leader heldout RMS **56.01 Hz** versus **2608.79 Hz**; gain **+2552.78 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30407 | 57823 | 1 | 1 | 22.95 | 56.01 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-31018 | 58635 | 2 | 3 | 300.45 | 2762.72 | +277.50 | +2706.71 | +97.97 | +2 |
| STARLINK-32041 | 60202 | 3 | — | 435.23 | 4412.24 | +412.27 | +4356.23 | +98.73 | -5 |
| STARLINK-32237 | 60443 | 4 | 5 | 440.52 | 4178.93 | +417.56 | +4122.92 | +98.66 | +1 |
| STARLINK-37039 | 69361 | 5 | — | 734.76 | 5255.22 | +711.80 | +5199.22 | +98.93 | -5 |
| STARLINK-11690 | 64242 | — | 2 | 2530.17 | 2608.79 | +2507.22 | +2552.78 | +97.85 | +5 |
| STARLINK-32246 | 60432 | — | 4 | 889.18 | 3205.44 | +866.22 | +3149.43 | +98.25 | -5 |

## CH4 lower, 87.96–119.57 s

Track `sha256:9251a0dc198194e47e4639ff46947449eb23ee7a8aa3c954ef38a7f07343fa90`; 36 observations; 487 nominal-time satellites scored. Training leader: **STARLINK-31283 (NORAD 59174)**; heldout rank 2 in the full scored population.

Against the best other heldout candidate, STARLINK-32535 (NORAD 62119): leader heldout RMS **1525.08 Hz** versus **1069.56 Hz**; gain **-455.52 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31283 | 59174 | 1 | 2 | 127.99 | 1525.08 | +0.00 | +0.00 | +0.00 | +3 |
| STARLINK-30407 | 57823 | 2 | 3 | 668.12 | 7781.36 | +540.12 | +6256.28 | +80.40 | -5 |
| STARLINK-32246 | 60432 | 3 | 4 | 881.30 | 9863.81 | +753.30 | +8338.73 | +84.54 | -1 |
| STARLINK-32535 | 62119 | 4 | 1 | 941.37 | 1069.56 | +813.38 | -455.52 | -42.59 | -5 |
| STARLINK-36031 | 66593 | 5 | — | 2622.24 | 14993.31 | +2494.25 | +13468.23 | +89.83 | -5 |
| STARLINK-11680 | 63554 | — | 5 | 3728.39 | 11555.91 | +3600.40 | +10030.83 | +86.80 | +5 |

## CH1 upper, 89.97–131.41 s

Track `sha256:4177e04de54e9a22fcf7ddcbd424180b7fd0c7360e94df686eeb95d3eb518aaf`; 49 observations; 493 nominal-time satellites scored. Training leader: **STARLINK-31283 (NORAD 59174)**; heldout rank 2 in the full scored population.

Against the best other heldout candidate, STARLINK-32535 (NORAD 62119): leader heldout RMS **3984.08 Hz** versus **1752.71 Hz**; gain **-2231.37 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31283 | 59174 | 1 | 2 | 567.56 | 3984.08 | +0.00 | +0.00 | +0.00 | +4 |
| STARLINK-32535 | 62119 | 2 | 1 | 811.78 | 1752.71 | +244.22 | -2231.37 | -127.31 | -5 |
| STARLINK-32246 | 60432 | 3 | — | 2599.63 | 18169.12 | +2032.07 | +14185.04 | +78.07 | -5 |
| STARLINK-30407 | 57823 | 4 | — | 3001.30 | 18019.03 | +2433.74 | +14034.94 | +77.89 | -5 |
| STARLINK-11680 | 63554 | 5 | 3 | 5427.64 | 12996.52 | +4860.08 | +9012.44 | +69.35 | +5 |
| STARLINK-31898 | 59905 | — | 4 | 7191.47 | 16564.68 | +6623.92 | +12580.59 | +75.95 | +5 |
| STARLINK-32131 | 60153 | — | 5 | 7286.56 | 17154.81 | +6719.00 | +13170.73 | +76.78 | +5 |

## CH1 lower, 90.35–131.66 s

Track `sha256:4e4f6303cf7a57428c62fe8411a6f20cd8cfbcadf867234c139718d0cda42ebd`; 50 observations; 492 nominal-time satellites scored. Training leader: **STARLINK-31283 (NORAD 59174)**; heldout rank 2 in the full scored population.

Against the best other heldout candidate, STARLINK-32535 (NORAD 62119): leader heldout RMS **4053.43 Hz** versus **1819.87 Hz**; gain **-2233.56 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31283 | 59174 | 1 | 2 | 592.66 | 4053.43 | +0.00 | +0.00 | +0.00 | +4 |
| STARLINK-32535 | 62119 | 2 | 1 | 768.24 | 1819.87 | +175.58 | -2233.56 | -122.73 | -5 |
| STARLINK-32246 | 60432 | 3 | — | 2788.74 | 18419.65 | +2196.08 | +14366.21 | +77.99 | -5 |
| STARLINK-30407 | 57823 | 4 | — | 3193.55 | 18236.35 | +2600.89 | +14182.92 | +77.77 | -5 |
| STARLINK-11680 | 63554 | 5 | 3 | 5442.42 | 12983.98 | +4849.76 | +8930.55 | +68.78 | +5 |
| STARLINK-31898 | 59905 | — | 4 | 7202.06 | 16528.55 | +6609.40 | +12475.12 | +75.48 | +5 |
| STARLINK-32131 | 60153 | — | 5 | 7303.88 | 17125.45 | +6711.22 | +13072.02 | +76.33 | +5 |

## CH2 upper, 198.56–224.38 s

Track `sha256:135c9d081c4cd7135d9a597e154bd3bb6395fbf61d4f96cf7a4eb9467d6be710`; 35 observations; 489 nominal-time satellites scored. Training leader: **STARLINK-30770 (NORAD 58132)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37651 (NORAD 69353): leader heldout RMS **112.74 Hz** versus **545.91 Hz**; gain **+433.18 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30770 | 58132 | 1 | 1 | 46.51 | 112.74 | +0.00 | +0.00 | +0.00 | +2 |
| STARLINK-32241 | 60437 | 2 | 3 | 103.62 | 967.99 | +57.11 | +855.25 | +88.35 | +4 |
| STARLINK-37651 | 69353 | 3 | 2 | 153.24 | 545.91 | +106.73 | +433.18 | +79.35 | +5 |
| STARLINK-36388 | 68037 | 4 | 4 | 191.34 | 1867.57 | +144.84 | +1754.83 | +93.96 | -2 |
| STARLINK-5733 | 56925 | 5 | — | 667.96 | 3547.63 | +621.45 | +3434.89 | +96.82 | +5 |
| STARLINK-4436 | 53479 | — | 5 | 670.90 | 3322.90 | +624.39 | +3210.17 | +96.61 | -5 |

## CH2 lower, 198.68–223.75 s

Track `sha256:979b7932d2939be2f6884ed5d9e63f1160c502fda74dd6d0c11d22d058e47df2`; 34 observations; 487 nominal-time satellites scored. Training leader: **STARLINK-30770 (NORAD 58132)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37651 (NORAD 69353): leader heldout RMS **57.31 Hz** versus **480.93 Hz**; gain **+423.62 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30770 | 58132 | 1 | 1 | 16.28 | 57.31 | +0.00 | +0.00 | +0.00 | +2 |
| STARLINK-32241 | 60437 | 2 | 3 | 76.58 | 945.66 | +60.31 | +888.36 | +93.94 | +4 |
| STARLINK-37651 | 69353 | 3 | 2 | 147.62 | 480.93 | +131.35 | +423.62 | +88.08 | +5 |
| STARLINK-36388 | 68037 | 4 | 4 | 185.85 | 1752.35 | +169.57 | +1695.05 | +96.73 | -2 |
| STARLINK-4436 | 53479 | 5 | — | 599.52 | 3236.48 | +583.24 | +3179.17 | +98.23 | -5 |
| STARLINK-5733 | 56925 | — | 5 | 669.64 | 3162.83 | +653.37 | +3105.52 | +98.19 | +5 |

## CH4 lower, 201.96–224.12 s

Track `sha256:044747143f88488c0dbe1d189a02b6c47287d214c8fc92a4a5a39f646765c84a`; 28 observations; 485 nominal-time satellites scored. Training leader: **STARLINK-30770 (NORAD 58132)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37651 (NORAD 69353): leader heldout RMS **50.28 Hz** versus **443.29 Hz**; gain **+393.01 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30770 | 58132 | 1 | 1 | 25.81 | 50.28 | +0.00 | +0.00 | +0.00 | +2 |
| STARLINK-32241 | 60437 | 2 | 3 | 93.29 | 587.35 | +67.47 | +537.06 | +91.44 | +3 |
| STARLINK-37651 | 69353 | 3 | 2 | 141.15 | 443.29 | +115.34 | +393.01 | +88.66 | +5 |
| STARLINK-36388 | 68037 | 4 | 4 | 182.77 | 2007.16 | +156.95 | +1956.88 | +97.49 | -2 |
| STARLINK-5733 | 56925 | 5 | — | 342.08 | 3556.69 | +316.27 | +3506.41 | +98.59 | +4 |
| STARLINK-4436 | 53479 | — | 5 | 738.91 | 3170.66 | +713.10 | +3120.38 | +98.41 | -5 |

## CH4 upper, 203.09–224.00 s

Track `sha256:e95992375e5367cd3b88d93a88e2f9fa84ce6572aee98aa295d911791acb6593`; 27 observations; 482 nominal-time satellites scored. Training leader: **STARLINK-30770 (NORAD 58132)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37651 (NORAD 69353): leader heldout RMS **17.42 Hz** versus **401.99 Hz**; gain **+384.57 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30770 | 58132 | 1 | 1 | 23.19 | 17.42 | +0.00 | +0.00 | +0.00 | +2 |
| STARLINK-32241 | 60437 | 2 | 3 | 66.17 | 620.55 | +42.97 | +603.13 | +97.19 | +3 |
| STARLINK-36388 | 68037 | 3 | 4 | 135.52 | 1465.49 | +112.33 | +1448.06 | +98.81 | -3 |
| STARLINK-37651 | 69353 | 4 | 2 | 137.07 | 401.99 | +113.88 | +384.57 | +95.67 | +5 |
| STARLINK-5733 | 56925 | 5 | 5 | 282.42 | 1824.30 | +259.22 | +1806.88 | +99.04 | -5 |

## CH3 lower, 214.92–251.77 s

Track `sha256:e351e4eacde537bc83274002f5a68bfa666ecc7f48a587f934b6e150aa2ee91b`; 39 observations; 493 nominal-time satellites scored. Training leader: **STARLINK-36388 (NORAD 68037)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-4436 (NORAD 53479): leader heldout RMS **331.27 Hz** versus **4248.96 Hz**; gain **+3917.68 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36388 | 68037 | 1 | 1 | 38.60 | 331.27 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-4436 | 53479 | 2 | 2 | 468.53 | 4248.96 | +429.94 | +3917.68 | +92.20 | -2 |
| STARLINK-32241 | 60437 | 3 | 3 | 1892.72 | 8408.95 | +1854.12 | +8077.68 | +96.06 | +5 |
| STARLINK-2140 | 47730 | 4 | — | 3018.95 | 16803.81 | +2980.35 | +16472.54 | +98.03 | -5 |
| STARLINK-30770 | 58132 | 5 | 5 | 3159.87 | 13572.62 | +3121.27 | +13241.35 | +97.56 | +3 |
| STARLINK-37651 | 69353 | — | 4 | 3295.26 | 13188.33 | +3256.67 | +12857.06 | +97.49 | +5 |

## CH4 lower, 276.60–296.62 s

Track `sha256:f5dea1b615f4475af0c196edae54abe7a11ef0e88499952937a5b47f07fb157f`; 21 observations; 474 nominal-time satellites scored. Training leader: **STARLINK-30757 (NORAD 58131)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-3819 (NORAD 52349): leader heldout RMS **145.25 Hz** versus **613.27 Hz**; gain **+468.02 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30757 | 58131 | 1 | 1 | 59.32 | 145.25 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-3819 | 52349 | 2 | 2 | 73.77 | 613.27 | +14.45 | +468.02 | +76.32 | -3 |
| STARLINK-31399 | 59416 | 3 | 4 | 110.34 | 1245.83 | +51.03 | +1100.59 | +88.34 | +5 |
| STARLINK-11072 | 58705 | 4 | 3 | 188.55 | 1137.34 | +129.23 | +992.10 | +87.23 | -5 |
| STARLINK-30578 | 58093 | 5 | — | 323.32 | 3695.04 | +264.01 | +3549.80 | +96.07 | -5 |
| STARLINK-32226 | 60426 | — | 5 | 1852.56 | 1317.97 | +1793.24 | +1172.72 | +88.98 | +5 |

## CH2 lower, 49.28–70.58 s

Track `sha256:e625d8ccbaf8305ff990c76e5fa192a4eea7f345c2a5c250dc741c3d1ea03c23`; 23 observations; 472 nominal-time satellites scored. Training leader: **STARLINK-30407 (NORAD 57823)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-36436 (NORAD 67626): leader heldout RMS **23.61 Hz** versus **1396.78 Hz**; gain **+1373.17 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-30407 | 57823 | 1 | 1 | 82.17 | 23.61 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-36436 | 67626 | 2 | 2 | 245.79 | 1396.78 | +163.62 | +1373.17 | +98.31 | -5 |
| STARLINK-36031 | 66593 | 3 | — | 285.39 | 2244.06 | +203.22 | +2220.45 | +98.95 | +5 |
| STARLINK-32246 | 60432 | 4 | 4 | 412.33 | 2078.08 | +330.16 | +2054.47 | +98.86 | -5 |
| STARLINK-32626 | 62123 | 5 | — | 465.13 | 5825.86 | +382.96 | +5802.25 | +99.59 | -5 |
| STARLINK-32041 | 60202 | — | 3 | 1358.26 | 1482.01 | +1276.10 | +1458.40 | +98.41 | +5 |
| STARLINK-37039 | 69361 | — | 5 | 871.35 | 2092.24 | +789.18 | +2068.63 | +98.87 | +5 |
