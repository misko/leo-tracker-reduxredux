# Full DSX01 joint-band policy gate

The full-cohort gate is negative: fitted-c joint calibration raises whole-recording coverage13784→14144/20084 but requested coverage falls422→420/693, with strict endpoints4/5→3/5. Median configured-reference distance remains132.472→132.415km. The c0 comparison similarly gains whole-recording coverage12180→13412 while losing requested coverage417→399 and strict endpoints5/5→1/5. No geographic recovery or model promotion follows the better training fit.

All20 outcomes and training-only selectors sealed before window or configured-position evaluation. One frozen policy applies to all five original candidate banks and all15 requested windows. No per-window/source choice, reference seeding, RF collection, held selection, original-label truth assumption or production change occurs.

## Complete-policy aggregate

| RF arm | Policy | Assigned/20084 | Requested/693 | New/lost vs original | Requested new/lost | Overall assigned RMS Hz | Selected strict | Raw strict | Calls |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| fitted-c | fixed | 13784 | 422 | 3304/742 | 337/11 | 155.819 | 4/5 | 4/5 | 93 |
| fitted-c | joint | 14144 | 420 | 3681/759 | 333/9 | 153.253 | 3/5 | 3/5 | 2626 |
| zero-c | fixed | 12180 | 417 | 3476/2518 | 349/28 | 171.585 | 5/5 | 5/5 | 2050 |
| zero-c | joint | 13412 | 399 | 3916/1726 | 335/32 | 166.114 | 1/5 | 1/5 | 3175 |

Summed fitted-c data NLL improves222582.028→220244.221 (−2337.808), while c0 improves231857.131→225353.196 (−6503.935). These are in-sample likelihood changes, not evidence of improved localization or predictive generalization. Overall assigned RMS uses a changing population; the intersection RMS below uses exactly retained pairs.

The original reference is the same saved fitted-c production outcome for both RF sensitivity arms. The c0 arm changes only the fitted-profile seed's c coordinate, and retains all other complete coordinates and constraints; upstream discovery and seed construction used fitted c. It is not an independent cold c0 pipeline.

## Matched-policy effects and paired residuals

| RF arm | Joint minus fixed full count | Joint new/lost vs fixed | Requested delta | Full intersection RMS fixed→joint Hz | Requested intersection RMS Hz |
|---|---:|---:|---:|---:|---:|
| fitted-c | +360 | 587/227 | -2 | 153.370→151.131 | 164.208→165.623 |
| zero-c | +1232 | 2505/1273 | -18 | 166.339→159.434 | 158.147→172.231 |

## Every source and RF arm

J is compared only within a target, and no lower-J feasible nonstationary point is silently filtered. Raw returned endpoints, profile seeds and original complete states remain in outcomes_seal.json. Selected labels and both strict flags expose selection or optimizer failures rather than claim they are model improvements.

| Source | RF | Policy | Selected | J / data NLL | Full / requested | KKT | Configured km | Common timing s | q change RMS | RX band updates Hz |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---|
| S01 | fitted-c | fixed | returned | 57682.156 / 56740.963 | 2517 / 90 | 0.00396825 | 132.472 | -3.367 | 0.02861 | [0.0, 0.0] |
| S01 | fitted-c | joint | returned | 57679.579 / 56742.711 | 2516 / 91 | 0.000617226 | 132.415 | -3.356 | 0.02869 | [8.17, -56.5] |
| S01 | zero-c | fixed | returned | 57829.755 / 56838.963 | 2530 / 91 | 5.39075e-05 | 132.385 | -3.060 | 0.02842 | [0.0, 0.0] |
| S01 | zero-c | joint | returned | 57813.968 / 56795.289 | 2544 / 92 | 0.000446198 | 133.636 | -2.831 | 0.02858 | [-234.73, -429.31] |
| S02 | fitted-c | fixed | profile-seed | 41448.507 / 40678.728 | 2102 / 74 | 0.000154213 | 135.377 | -1.875 | 0.01572 | [0.0, 0.0] |
| S02 | fitted-c | joint | returned | 41429.422 / 40661.013 | 2106 / 72 | 0.00142102 | 135.113 | -1.913 | 0.01560 | [-1.8, 242.88] |
| S02 | zero-c | fixed | returned | 43495.352 / 42815.274 | 1687 / 82 | 0.000519986 | 131.318 | -1.935 | 0.02399 | [0.0, 0.0] |
| S02 | zero-c | joint | returned | 42379.744 / 41650.393 | 1932 / 65 | 0.00433729 | 134.475 | -1.189 | 0.02149 | [-914.34, 225.02] |
| S03 | fitted-c | fixed | returned | 40821.325 / 40676.094 | 3467 / 136 | 0.000305534 | 3.282 | 0.877 | 0.02287 | [0.0, 0.0] |
| S03 | fitted-c | joint | returned | 40819.438 / 40675.836 | 3465 / 136 | 0.00374166 | 3.276 | 0.872 | 0.02280 | [7.88, -16.62] |
| S03 | zero-c | fixed | returned | 46119.461 / 45943.287 | 2493 / 120 | 0.000159856 | 4.318 | 0.857 | 0.02307 | [0.0, 0.0] |
| S03 | zero-c | joint | returned | 43881.276 / 43713.821 | 2964 / 118 | 0.00165139 | 3.584 | 1.109 | 0.01884 | [-1004.78, -814.66] |
| S04 | fitted-c | fixed | profile-seed | 40246.697 / 39820.651 | 2803 / 56 | 0.000634583 | 260.094 | 4.883 | 0.03984 | [0.0, 0.0] |
| S04 | fitted-c | joint | returned | 40137.526 / 39717.650 | 2810 / 49 | 0.000304153 | 259.787 | 4.854 | 0.03984 | [152.69, 265.33] |
| S04 | zero-c | fixed | returned | 41637.316 / 41232.390 | 2630 / 61 | 0.000215357 | 258.815 | 4.649 | 0.04158 | [0.0, 0.0] |
| S04 | zero-c | joint | returned | 41026.668 / 40580.159 | 2749 / 58 | 0.0026515 | 264.326 | 5.248 | 0.04110 | [-262.89, -432.7] |
| S05 | fitted-c | fixed | returned | 44912.730 / 44665.593 | 2895 / 66 | 0.0001126 | 4.709 | -0.647 | 0.02615 | [0.0, 0.0] |
| S05 | fitted-c | joint | returned | 42653.125 / 42447.011 | 3247 / 72 | 0.000480467 | 2.354 | -0.646 | 0.03722 | [-122.48, -1286.49] |
| S05 | zero-c | fixed | returned | 45270.798 / 45027.216 | 2840 / 63 | 0.000533543 | 5.595 | -0.583 | 0.02587 | [0.0, 0.0] |
| S05 | zero-c | joint | returned | 42822.063 / 42613.533 | 3223 / 66 | 0.00295502 | 2.786 | -0.561 | 0.03735 | [-305.53, -1468.61] |

Configured distances use the same five metadata-qualified operator-supplied roof references; survey and altitude uncertainty remain unknown. They enter only after the global outcome seal. Fit/NLL gains do not imply position gains. The position CDF keeps all five sources and marks nonstationary selectors with x. No best-of-truth position, window or RF-arm mixture is formed.

## All fifteen requested windows

| Window | Original/N | Fixed fitted c | Joint fitted c | Fixed c0 | Joint c0 |
|---|---:|---:|---:|---:|---:|
| DSX01-001 | 13/86 | 79 | 79 | 79 | 78 |
| DSX01-002 | 1/35 | 11 | 12 | 12 | 14 |
| DSX01-003 | 0/27 | 0 | 0 | 0 | 0 |
| DSX01-004 | 6/44 | 10 | 9 | 14 | 18 |
| DSX01-005 | 1/33 | 31 | 31 | 33 | 21 |
| DSX01-006 | 12/72 | 33 | 32 | 35 | 26 |
| DSX01-007 | 16/54 | 54 | 54 | 40 | 43 |
| DSX01-008 | 8/50 | 48 | 48 | 46 | 46 |
| DSX01-009 | 4/34 | 34 | 34 | 34 | 29 |
| DSX01-010 | 2/46 | 25 | 18 | 33 | 29 |
| DSX01-011 | 9/43 | 15 | 14 | 11 | 13 |
| DSX01-012 | 14/66 | 16 | 17 | 17 | 16 |
| DSX01-013 | 1/28 | 22 | 24 | 22 | 24 |
| DSX01-014 | 3/39 | 11 | 15 | 11 | 9 |
| DSX01-015 | 6/36 | 33 | 33 | 30 | 33 |

The≥80% net-original-missing restoration label is descriptive coverage only. All labels and complete per-window new/lost/retained, row-NLL sums, paired RMS and unchanged denominators are in evaluation.json; no identity truth is inferred. The separate recovery_identity_audit demonstrates why point counts and dominant model-ID support must remain distinct.

## Method, constraints and cost

Seeds are the exact iteration2 fixed-profile fitted-c complete states for every source. Both policies retain the original shared likelihood, original ordered candidates, q, visibility, timing priors2s/3s, clocks and physical priors/bounds. Both use the broad regional research disk; extra original-production25km disks are not imposed. Original production KKT/local-domain flags are not copied into new audits. Each original point and profile seed was independently replayed under each current target and RF arm.

Joint offsets are absolute RX-specific high-band constants, bounded±ALIAS/2 with the same50000Hz prior replacing the frozen constant exactly once. Original physical, clock and q coordinates remain free. Updates are in the same source frame but remain coupled with other calibration/timing/geography; they are not hardware offset measurements.

Each new policy receives1000 objective/density calls and120 active seconds. The joint policy charges159 finite profile calls plus2 exact runtime qualifiers and≤839 refit calls. Profiles precomputed from the exact same complete states were requalified before reuse and their active calls/time charged; no free profile optimization is hidden. Fixed controls get1000 common.refit calls from the same complete seeds. This is a profile-plus-joint policy comparison, not a parameter-count-only causal experiment.

Each family reuses one immutable public preparation with fresh parameter copies and bank/observation/design fingerprint checks. Family preparation seconds and case wall times are separately retained in family_seal_Sxx.json. At most two families run under 540s TERM/545s KILL caps; per-case inference limits remain unchanged. Independent terminal audits, actual qualification and public source preparation are additional to inference. Post-seal scoring makes45 explicit model-classification calls plus public original-source replay/preparation. No hidden retry or endpoint polish is applied.

Version1 schema failure and original source/protocol/logs are retained. It required an optional mode field missing in every canonical historical seed. Version2 verifies exact path/source/job/input/terminal/TLE/method/arm authority and independently replays each fitted seed's full-observation J/NLL. This changes no scientific threshold or data. The earlier absent-cache preflight was corrected before source freeze with public reconstruction from the same original pinned local TLE; no provider or candidate changes.

Thirteen harness/shared-model tests, three family tests and two paired-metric tests pass. Actual ten source/RF qualifications pass exact nesting/profile J/NLL, original gradient and posterior closure, both new-band derivatives and unchanged classification; their source/profile/incumbent receipts are sealed before fits. Full-data development results do not substitute for blocked predictive evaluation. No production/DS21/DS22 promotion is authorized by this report alone.

## Measured execution costs

| Source | One preparation seconds | Four-case family seconds | Fixed charged calls (both RF arms) | Joint charged calls (both RF arms) |
|---|---:|---:|---:|---:|
| S01 | 19.414 | 66.121 | 454 | 1145 |
| S02 | 16.248 | 60.748 | 508 | 1333 |
| S03 | 17.930 | 49.833 | 424 | 1132 |
| S04 | 17.443 | 51.562 | 430 | 1130 |
| S05 | 16.937 | 38.175 | 327 | 1061 |

The two-worker matrix completed in156.126s. Charged inference totals7944 objective/density calls, including1590 actual profile calls computed once during qualification and re-used with their original costs. Additional declared actual qualification is110 model objectives plus public replay preparation, followed by20 independent terminal audits. Failed-v1 preparation, ten successful qualification preparations and five fit-family preparations are separate from the fitting allowance; post-seal evaluation performs five additional public preparations and45 explicit classification objectives. Public preparation's internal source audits are additional and were not instrumented as zero cost.
