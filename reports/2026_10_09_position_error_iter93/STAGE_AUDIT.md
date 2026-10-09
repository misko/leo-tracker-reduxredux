# ac11 stage audit: converged fits in an upstream wrong region

Persisted V3 `scan-fw-ac11ac00c0676d1b` completes both B7 arms. Fitted-c error is 55.685 km and c0 is 53.945 km. Both satisfy the independent 0.001 gate; this is a localization failure, not a final optimizer/convergence failure.

Reference coordinates are used only to evaluate already persisted stage positions. No new fit, seed, bank or operational winner is chosen by this audit.

![Persisted position, support and timing penalties](stage-audit.png)

| Stage | Arm | Error km | Satellites | Signal mass | RMS Hz | Timing prior | Stationarity |
|---|---|---:|---:|---:|---:|---:|---:|
| B3 | fitted-c | 59.468 | 41 | 2672.94 | 128.68 | 351.362 | 0.000113302 |
| B3 | zero-c | 57.806 | 41 | 2530.06 | 146.43 | 342.130 | 0.00095174 |
| B4 | fitted-c | 55.163 | 16 | 1019.85 | 149.90 | 11.087 | 0.000101704 |
| B4 | zero-c | 52.608 | 16 | 944.79 | 173.62 | 9.962 | 0.000608581 |
| B4W | fitted-c | 55.907 | 16 | 1040.25 | 137.15 | 10.241 | 6.89906e-05 |
| B4W | zero-c | 55.103 | 16 | 980.79 | 164.63 | 10.333 | 5.79774e-05 |
| B5 | fitted-c | 55.756 | 16 | 1040.91 | 136.40 | 10.176 | 1.40508e-06 |
| B5 | zero-c | 55.103 | 16 | 980.79 | 164.63 | 10.333 | 0.000312108 |
| C6 | fitted-c | 55.756 | 16 | 1040.91 | 136.40 | 10.176 | 1.40514e-06 |
| C6 | zero-c | 55.103 | 16 | 980.79 | 164.63 | 10.333 | 0.000209504 |
| B7 | fitted-c | 55.685 | 16 | 1042.28 | 136.46 | 10.139 | 1.18894e-05 |
| B7 | zero-c | 53.945 | 16 | 997.27 | 164.96 | 10.090 | 0.000233603 |

## What precedes the joint stages

All three ordinary region passes record a calibration prefit failure for `point:-47.5:-62.5`. Both final arms originate from the sep50 region's `point:-72.5:-137.5`. The joint ladder therefore begins inside that selected regional hypothesis; it does not revisit discarded/failed regions. The separate regional prefit replay isolates this earlier exclusion. Stage diagnostics alone do not prove that a discarded region would have produced a better final position.

## B3 to B4: large support loss, not a comparable-score decision

Production `reduce_bank` deletes satellites whose fitted relative timing magnitude exceeds 5 s, then projects the retained total timing shifts into a smaller zero-sum basis. Here it removes 25/41 satellites (61.0%). Fitted posterior signal mass drops 2672.94→1019.85 (61.8%) and c0 drops 2530.06→944.79 (62.7%). Timing penalties fall 351.362→11.087 and342.130→9.962, partly because the high-timing candidates are removed. This is not evidence that those candidates' timing errors were corrected.

The bank change alters mixture candidates and clutter/visibility terms, so B3/B4 objectives and posterior RMS are not controlled same-model comparisons. The objective increase 39830→45121 does not mean an optimizer converged to a worse point under one unchanged function. B4 is accepted because it independently qualifies within its own changed model, as prescribed by B7.

The actual fitted-c position error improves 59.468→55.163 km at pruning, and c0 improves 57.806→52.608 km. Therefore this receipt **does not establish pruning as a position-error amplifier**. It establishes substantial evidence/support loss in an already wrong region, potentially reducing recovery information. Proving a causal accuracy effect requires an unpruned/pruned same-start controlled replay.

## Later stages cannot undo the regional exclusion

B4W relaxes the existing clock prior, B5 adds RF-time flexibility, and B7 adds satellite slope flexibility; all remain independently stationary near the same bad regional solution. Fitted-c B5→B7 changes position error 55.756→55.685 km (about 71 m), and c0 C6→B7 changes 55.103→53.945 km (about 1.16 km). These are small changes relative to the 54–56 km failure; further frequency flexibility does not recover a missing regional hypothesis in this persisted run.

The B3 relative timing RMS is approximately 8.28 s fitted and 8.17 s c0. Thus the existing inference-only timing-strain concept would flag this case without reference error. A uniform bounded retry of a failed retained regional prefit is the more direct cause-oriented test; final-function extra time is not motivated by these strongly qualified B7 endpoints.

[Per-stage values, provenance and removed IDs](stage-audit.json). No deployment change or new RF collection occurred.
