# Candidate RMS comparisons: scan-hop-ccd4ff7d73b8e12e

Recorded **2026-09-14T23:20:12.558941Z**, RX0, 10 MS/s.

[Recording assessment and plots](scan-hop-ccd4ff7d73b8e12e.md).

Each track has its own training-selected leader; there is no single satellite assignment for the whole recording. Lower RMS is better. The same observations and chronological split are used for all candidates within a track.

Gain = alternative RMS − training-leader RMS. Positive gain favors the leader; negative heldout gain means the alternative predicts better. Percent gain uses the alternative RMS as denominator; it is not identification confidence. Tau and carrier offset were selected on training data and remain frozen on heldout.

The archived screen retained the top five training candidates and top five heldout candidates, whose union is listed below. Candidate counts describe the full scored population; names/scores outside these retained lists were not archived. A blank rank means outside that top-five list. Catalogue exclusions and control results are in the linked recording assessment and evidence.

## CH2 lower, 30.01–60.75 s

Track `sha256:14a14da793d7b50df0eb49df5723f81333476ddefed79c479c96a0fed70e4a77`; 33 observations; 501 nominal-time satellites scored. Training leader: **STARLINK-32935 (NORAD 63202)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30363 (NORAD 57744): leader heldout RMS **104.86 Hz** versus **947.42 Hz**; gain **+842.56 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32935 | 63202 | 1 | 1 | 34.29 | 104.86 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-30363 | 57744 | 2 | 2 | 112.53 | 947.42 | +78.24 | +842.56 | +88.93 | +2 |
| STARLINK-5211 | 54086 | 3 | 5 | 654.37 | 4837.58 | +620.08 | +4732.72 | +97.83 | +5 |
| STARLINK-6185 | 56901 | 4 | — | 918.60 | 7853.30 | +884.30 | +7748.43 | +98.66 | -5 |
| STARLINK-11657 | 63558 | 5 | — | 1413.58 | 11951.94 | +1379.29 | +11847.08 | +99.12 | -4 |
| STARLINK-11455 | 62463 | — | 3 | 3236.06 | 2928.77 | +3201.76 | +2823.91 | +96.42 | +5 |
| STARLINK-37187 | 68399 | — | 4 | 2238.45 | 4364.43 | +2204.16 | +4259.56 | +97.60 | +5 |

## CH2 upper, 40.49–62.13 s

Track `sha256:4194f824d0661b82e411170595a237f00893d9ae4063816ef01d32c5640a4256`; 25 observations; 494 nominal-time satellites scored. Training leader: **STARLINK-32935 (NORAD 63202)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-30363 (NORAD 57744): leader heldout RMS **68.91 Hz** versus **1261.52 Hz**; gain **+1192.61 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32935 | 63202 | 1 | 1 | 60.20 | 68.91 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-30363 | 57744 | 2 | 2 | 207.14 | 1261.52 | +146.94 | +1192.61 | +94.54 | +5 |
| STARLINK-11455 | 62463 | 3 | 5 | 727.10 | 3253.73 | +666.90 | +3184.82 | +97.88 | +5 |
| STARLINK-37187 | 68399 | 4 | 3 | 1131.73 | 1597.85 | +1071.53 | +1528.94 | +95.69 | +5 |
| STARLINK-5211 | 54086 | 5 | — | 1182.00 | 3967.10 | +1121.79 | +3898.19 | +98.26 | -2 |
| STARLINK-34715 | 64931 | — | 4 | 1649.08 | 2806.21 | +1588.87 | +2737.29 | +97.54 | +5 |

## CH2 lower, 117.69–160.40 s

Track `sha256:95bd0d124724f72a37a192d73ad153c1ea8b22d081937e31500af4f78a302826`; 53 observations; 510 nominal-time satellites scored. Training leader: **STARLINK-36182 (NORAD 67192)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-6357 (NORAD 56783): leader heldout RMS **299.39 Hz** versus **666.30 Hz**; gain **+366.92 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-36182 | 67192 | 1 | 1 | 39.95 | 299.39 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-6357 | 56783 | 2 | 2 | 66.45 | 666.30 | +26.50 | +366.92 | +55.07 | -5 |
| STARLINK-36173 | 67210 | 3 | 3 | 281.58 | 1789.95 | +241.63 | +1490.56 | +83.27 | -5 |
| STARLINK-37572 | 69448 | 4 | — | 398.36 | 4477.19 | +358.40 | +4177.80 | +93.31 | -4 |
| STARLINK-30323 | 57634 | 5 | — | 1223.40 | 5429.46 | +1183.45 | +5130.08 | +94.49 | -5 |
| STARLINK-32484 | 62160 | — | 4 | 3552.40 | 3229.58 | +3512.45 | +2930.19 | +90.73 | +5 |
| STARLINK-34482 | 64782 | — | 5 | 3936.80 | 3641.18 | +3896.84 | +3341.79 | +91.78 | +5 |

## CH1 upper, 240.57–268.29 s

Track `sha256:2bdb851234bcfbedb95ada48b43e0d242ed58bbf34e9db4e28b11fdadceb0b21`; 38 observations; 480 nominal-time satellites scored. Training leader: **STARLINK-32403 (NORAD 61629)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-1215 (NORAD 45225): leader heldout RMS **108.77 Hz** versus **501.71 Hz**; gain **+392.95 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32403 | 61629 | 1 | 1 | 53.48 | 108.77 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-1215 | 45225 | 2 | 2 | 112.47 | 501.71 | +58.99 | +392.95 | +78.32 | +5 |
| STARLINK-5037 | 53896 | 3 | 3 | 202.26 | 1207.45 | +148.78 | +1098.69 | +90.99 | -5 |
| STARLINK-35046 | 65701 | 4 | 5 | 568.42 | 1343.12 | +514.94 | +1234.35 | +91.90 | +5 |
| STARLINK-38054 | 100007 | 5 | — | 646.18 | 5334.47 | +592.70 | +5225.70 | +97.96 | +5 |
| STARLINK-3814 | 52335 | — | 4 | 964.38 | 1338.72 | +910.90 | +1229.95 | +91.88 | +5 |

## CH1 lower, 242.09–268.42 s

Track `sha256:0c2815d59bf4765455c79690634acc899bf6a05459cb0f0a3854d49c2b681ede`; 32 observations; 481 nominal-time satellites scored. Training leader: **STARLINK-32403 (NORAD 61629)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-1215 (NORAD 45225): leader heldout RMS **122.93 Hz** versus **478.79 Hz**; gain **+355.86 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-32403 | 61629 | 1 | 1 | 33.51 | 122.93 | +0.00 | +0.00 | +0.00 | -1 |
| STARLINK-1215 | 45225 | 2 | 2 | 126.04 | 478.79 | +92.53 | +355.86 | +74.32 | +5 |
| STARLINK-5037 | 53896 | 3 | 3 | 225.28 | 1172.87 | +191.76 | +1049.94 | +89.52 | -5 |
| STARLINK-35046 | 65701 | 4 | 4 | 553.21 | 1195.36 | +519.70 | +1072.43 | +89.72 | +5 |
| STARLINK-38054 | 100007 | 5 | — | 614.99 | 4054.91 | +581.48 | +3931.98 | +96.97 | +3 |
| STARLINK-3814 | 52335 | — | 5 | 768.31 | 1495.76 | +734.80 | +1372.83 | +91.78 | +5 |
