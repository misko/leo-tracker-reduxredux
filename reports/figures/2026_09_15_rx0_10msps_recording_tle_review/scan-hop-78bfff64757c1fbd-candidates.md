# Candidate RMS comparisons: scan-hop-78bfff64757c1fbd

Recorded **2026-09-14T21:30:12.462465Z**, RX0, 10 MS/s.

[Recording assessment and plots](scan-hop-78bfff64757c1fbd.md).

Each track has its own training-selected leader; there is no single satellite assignment for the whole recording. Lower RMS is better. The same observations and chronological split are used for all candidates within a track.

Gain = alternative RMS − training-leader RMS. Positive gain favors the leader; negative heldout gain means the alternative predicts better. Percent gain uses the alternative RMS as denominator; it is not identification confidence. Tau and carrier offset were selected on training data and remain frozen on heldout.

The archived screen retained the top five training candidates and top five heldout candidates, whose union is listed below. Candidate counts describe the full scored population; names/scores outside these retained lists were not archived. A blank rank means outside that top-five list. Catalogue exclusions and control results are in the linked recording assessment and evidence.

## CH2 lower, 74.53–95.94 s

Track `sha256:e432f215778ffdb1bf46439d90e4dbbc4dff33697e2c448473ad56170061d622`; 27 observations; 494 nominal-time satellites scored. Training leader: **STARLINK-31942 (NORAD 59899)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11423 (NORAD 61950): leader heldout RMS **26.85 Hz** versus **1705.53 Hz**; gain **+1678.68 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31942 | 59899 | 1 | 1 | 20.84 | 26.85 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-36344 | 67710 | 2 | 4 | 349.27 | 3501.88 | +328.43 | +3475.03 | +99.23 | +3 |
| STARLINK-33890 | 65332 | 3 | 3 | 531.16 | 2779.04 | +510.31 | +2752.19 | +99.03 | -5 |
| STARLINK-33867 | 63795 | 4 | 5 | 1201.22 | 3892.86 | +1180.37 | +3866.00 | +99.31 | +1 |
| STARLINK-32108 | 59682 | 5 | — | 1433.45 | 6165.01 | +1412.61 | +6138.16 | +99.56 | -5 |
| STARLINK-11423 | 61950 | — | 2 | 2249.57 | 1705.53 | +2228.72 | +1678.68 | +98.43 | +5 |

## CH2 upper, 74.79–95.31 s

Track `sha256:d6ed853b4ac3c161d04f594167a786fc2991264a0785e8e313c954085fc9cdd0`; 28 observations; 493 nominal-time satellites scored. Training leader: **STARLINK-31942 (NORAD 59899)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-11423 (NORAD 61950): leader heldout RMS **19.15 Hz** versus **1689.50 Hz**; gain **+1670.35 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-31942 | 59899 | 1 | 1 | 20.95 | 19.15 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-36344 | 67710 | 2 | 4 | 361.97 | 3333.95 | +341.03 | +3314.80 | +99.43 | +3 |
| STARLINK-33890 | 65332 | 3 | 3 | 558.55 | 2681.33 | +537.61 | +2662.18 | +99.29 | -5 |
| STARLINK-33867 | 63795 | 4 | 5 | 1231.31 | 3690.67 | +1210.37 | +3671.52 | +99.48 | +0 |
| STARLINK-32108 | 59682 | 5 | — | 1480.16 | 5962.72 | +1459.21 | +5943.57 | +99.68 | -5 |
| STARLINK-11423 | 61950 | — | 2 | 2229.77 | 1689.50 | +2208.82 | +1670.35 | +98.87 | +5 |

## CH3 upper, 145.87–166.15 s

Track `sha256:29023df09d14b670975480b01640328c672f561b0480ec5a0f2b5094d76c9cfe`; 20 observations; 492 nominal-time satellites scored. Training leader: **STARLINK-5947 (NORAD 55989)**; heldout rank 1 in the full scored population.

Against the best other heldout candidate, STARLINK-37165 (NORAD 68287): leader heldout RMS **80.10 Hz** versus **754.54 Hz**; gain **+674.44 Hz**. This alternative is selected on heldout data for diagnosis, not used to refit the leader.

| Satellite | NORAD | Train rank | Heldout rank | Train RMS Hz | Heldout RMS Hz | Leader train gain Hz | Leader heldout gain Hz | Leader heldout gain % | Tau s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| STARLINK-5947 | 55989 | 1 | 1 | 28.93 | 80.10 | +0.00 | +0.00 | +0.00 | +0 |
| STARLINK-4132 | 53252 | 2 | 3 | 94.61 | 763.05 | +65.68 | +682.94 | +89.50 | +4 |
| STARLINK-30799 | 58121 | 3 | 4 | 694.52 | 951.10 | +665.58 | +871.00 | +91.58 | +0 |
| STARLINK-37165 | 68287 | 4 | 2 | 696.47 | 754.54 | +667.54 | +674.44 | +89.38 | +5 |
| STARLINK-35158 | 66381 | 5 | — | 1668.09 | 3860.38 | +1639.16 | +3780.27 | +97.92 | -5 |
| STARLINK-11448 | 63005 | — | 5 | 2865.45 | 2585.42 | +2836.51 | +2505.32 | +96.90 | +5 |
