# Candidate RMS comparisons: scan-hop-c385aedb1181e285

[Ranked RMS plots for every track](scan-hop-c385aedb1181e285-rms.md).

Recorded **2026-09-14T22:50:12.764263Z**, RX0, 10 MS/s.

[Recording assessment and plots](scan-hop-c385aedb1181e285.md).

Each track has its own training-selected leader; there is no single satellite assignment for the whole recording. Lower RMS is better. The same observations and chronological split are used for all candidates within a track.

Gain = alternative RMS − training-leader RMS. Positive gain favors the leader; negative heldout gain means the alternative predicts better. Percent gain uses the alternative RMS as denominator; it is not identification confidence. Tau and carrier offset were selected on training data and remain frozen on heldout.

The archived screen retained the top five training candidates and top five heldout candidates, whose union is listed below. Candidate counts describe the full scored population; names/scores outside these retained lists were not archived. A blank rank means outside that top-five list. Catalogue exclusions and control results are in the linked recording assessment and evidence.

## CH3 upper, 78.26–104.99 s

Track `sha256:a2c18d48e26325932c93eda7667a50f4bff2ece83afbf9bba41b17f792294c17`; 32 observations; 502 nominal-time satellites scored. Training leader: **STARLINK-34312 (NORAD 64711)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32437 (NORAD 63001): leader heldout RMS **148.01 Hz** versus **915.95 Hz**; gain **+767.94 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34312 | 64711 | 1 | 1 | 49.46 | 148.01 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-37742 | 69241 | 2 | 3 | 170.93 | 1666.79 | +121.47 | +1518.78 | +91.12 | +0 |
| STARLINK-32437 | 63001 | 3 | 2 | 366.09 | 915.95 | +316.63 | +767.94 | +83.84 | -5 |
| STARLINK-32370 | 61635 | 4 | 4 | 402.04 | 3752.43 | +352.57 | +3604.42 | +96.06 | -5 |
| STARLINK-32683 | 62445 | 5 | — | 465.63 | 4658.54 | +416.16 | +4510.53 | +96.82 | -5 |
| STARLINK-30258 | 57608 | — | 5 | 949.66 | 3806.41 | +900.19 | +3658.40 | +96.11 | +5 |

## CH3 lower, 78.89–103.85 s

Track `sha256:0b22cc7f1a01f6f8a1b59bea0cb031aba794da82155128a7a2b8f2cf17011edc`; 31 observations; 500 nominal-time satellites scored. Training leader: **STARLINK-34312 (NORAD 64711)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-32437 (NORAD 63001): leader heldout RMS **132.81 Hz** versus **887.83 Hz**; gain **+755.02 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-34312 | 64711 | 1 | 1 | 40.78 | 132.81 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-37742 | 69241 | 2 | 3 | 129.43 | 1437.53 | +88.65 | +1304.72 | +90.76 | +0 |
| STARLINK-32437 | 63001 | 3 | 2 | 364.02 | 887.83 | +323.24 | +755.02 | +85.04 | -5 |
| STARLINK-32370 | 61635 | 4 | 5 | 368.65 | 3311.28 | +327.87 | +3178.47 | +95.99 | -5 |
| STARLINK-32683 | 62445 | 5 | — | 384.42 | 4158.36 | +343.63 | +4025.54 | +96.81 | -5 |
| STARLINK-30258 | 57608 | — | 4 | 957.26 | 3217.81 | +916.48 | +3085.00 | +95.87 | +5 |

## CH4 lower, 197.55–221.35 s

Track `sha256:60985ff4ec50a2b16cc96c8d2339ea08d7164c29195f122f2ae111ae18395d09`; 28 observations; 494 nominal-time satellites scored. Training leader: **STARLINK-35074 (NORAD 65422)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-35095 (NORAD 65425): leader heldout RMS **75.46 Hz** versus **1189.10 Hz**; gain **+1113.65 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-35074 | 65422 | 1 | 1 | 17.53 | 75.46 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-35095 | 65425 | 2 | 2 | 662.59 | 1189.10 | +645.06 | +1113.65 | +93.65 | +5 |
| STARLINK-32880 | 62955 | 3 | 4 | 1737.09 | 8418.83 | +1719.56 | +8343.38 | +99.10 | -5 |
| STARLINK-37021 | 68105 | 4 | 3 | 1834.80 | 7550.43 | +1817.27 | +7474.97 | +99.00 | -5 |
| STARLINK-32770 | 62741 | 5 | 5 | 2432.87 | 8865.28 | +2415.34 | +8789.83 | +99.15 | -5 |

## CH3 lower, 249.95–285.45 s

Track `sha256:c9c733ae2ef86133265d7687d5845a7bcaf5b776e3faf8a1d0466e3715192322`; 42 observations; 499 nominal-time satellites scored. Training leader: **STARLINK-33888 (NORAD 63860)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-3126 (NORAD 49444): leader heldout RMS **128.85 Hz** versus **5428.27 Hz**; gain **+5299.42 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33888 | 63860 | 1 | 1 | 64.35 | 128.85 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-3126 | 49444 | 2 | 2 | 542.53 | 5428.27 | +478.18 | +5299.42 | +97.63 | -5 |
| STARLINK-5111 | 56146 | 3 | — | 916.10 | 10335.09 | +851.75 | +10206.23 | +98.75 | +2 |
| STARLINK-5528 | 56890 | 4 | — | 1123.41 | 9494.50 | +1059.05 | +9365.65 | +98.64 | -5 |
| STARLINK-11540 | 62564 | 5 | 5 | 1313.28 | 9162.47 | +1248.93 | +9033.62 | +98.59 | +1 |
| STARLINK-37680 | 69240 | — | 3 | 4000.22 | 7970.24 | +3935.87 | +7841.38 | +98.38 | +5 |
| STARLINK-3450 | 51734 | — | 4 | 3044.40 | 8223.95 | +2980.05 | +8095.10 | +98.43 | +5 |

## CH3 upper, 251.21–286.08 s

Track `sha256:a30e39f698f8c26161a4f7178617f85bc66efe18ff626d8cea613e642101dfee`; 40 observations; 497 nominal-time satellites scored. Training leader: **STARLINK-33888 (NORAD 63860)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-3126 (NORAD 49444): leader heldout RMS **147.73 Hz** versus **5988.15 Hz**; gain **+5840.42 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-33888 | 63860 | 1 | 1 | 85.16 | 147.73 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-3126 | 49444 | 2 | 2 | 497.53 | 5988.15 | +412.37 | +5840.42 | +97.53 | -5 |
| STARLINK-5111 | 56146 | 3 | — | 869.18 | 9775.93 | +784.02 | +9628.20 | +98.49 | +0 |
| STARLINK-5528 | 56890 | 4 | — | 1302.01 | 10114.30 | +1216.85 | +9966.57 | +98.54 | -5 |
| STARLINK-11540 | 62564 | 5 | 5 | 1460.81 | 9445.10 | +1375.65 | +9297.37 | +98.44 | +0 |
| STARLINK-37680 | 69240 | — | 3 | 3840.76 | 7484.68 | +3755.60 | +7336.95 | +98.03 | +5 |
| STARLINK-3450 | 51734 | — | 4 | 2983.89 | 8092.01 | +2898.72 | +7944.28 | +98.17 | +5 |
