# Responsibility changes after optimizer continuation

The same observations, satellite set, model, and priors are evaluated at the saved original and continued solutions. Satellite responsibilities are reconstructed from the likelihood; clutter probability is one minus their sum. The most probable state includes clutter. These diagnostic state changes are not a rerun of greedy association.

Only initially unconverged cases with saved continuation results are included. A small change in position error can conceal a substantial change in soft associations. Posterior RMS changes can also reflect changed responsibilities rather than improvement on a fixed set of hard satellite owners.

| Scan | Measurements | Model | Cone | RF | Windows | Changed states | Sat to sat | Sat to clutter | Clutter to sat | Mean TV | RMS before Hz | RMS after Hz | Error before m | Error after m |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R025-01 | original | V16 | on | fitted-c | 2655 | 88 | 12 | 5 | 71 | 0.033158 | 123.42 | 122.25 | 2207.9 | 2267.4 |
| R025-01 | original | V16 | on | zero-c | 2655 | 0 | 0 | 0 | 0 | 0.000070 | 122.95 | 122.94 | 2140.8 | 2139.2 |
| R025-01 | refined | V16 | on | fitted-c | 2643 | 0 | 0 | 0 | 0 | 0.000050 | 121.51 | 121.52 | 1951.0 | 1950.7 |
| R025-05 | original | T1AT | off | fitted-c | 2847 | 1 | 1 | 0 | 0 | 0.000037 | 135.33 | 135.33 | 2497.7 | 2497.3 |
| R025-05 | original | T1AT | off | zero-c | 2847 | 4 | 3 | 1 | 0 | 0.001165 | 136.10 | 136.05 | 2361.3 | 2327.0 |
| R025-05 | original | T1AT | on | fitted-c | 2847 | 0 | 0 | 0 | 0 | 0.000120 | 136.09 | 136.08 | 4000.0 | 4000.0 |
| R025-05 | original | T1AT | on | zero-c | 2847 | 4 | 2 | 1 | 1 | 0.001242 | 137.42 | 137.40 | 4000.0 | 4000.0 |
| R025-05 | original | V16 | off | fitted-c | 2847 | 0 | 0 | 0 | 0 | 0.000023 | 116.84 | 116.84 | 4000.0 | 4000.0 |
| R025-05 | original | V16 | off | zero-c | 2847 | 0 | 0 | 0 | 0 | 0.000001 | 125.04 | 125.04 | 3470.6 | 3470.7 |
| R025-05 | original | V16 | on | fitted-c | 2847 | 0 | 0 | 0 | 0 | 0.000017 | 121.71 | 121.71 | 4000.0 | 4000.0 |
| R025-05 | original | V16 | on | zero-c | 2847 | 0 | 0 | 0 | 0 | 0.000005 | 121.62 | 121.62 | 4000.0 | 4000.0 |
| R025-05 | refined | V16 | off | fitted-c | 3398 | 0 | 0 | 0 | 0 | 0.000000 | 88.16 | 88.16 | 4000.0 | 4000.0 |
| R025-05 | refined | V16 | on | zero-c | 3398 | 0 | 0 | 0 | 0 | 0.000000 | 88.21 | 88.21 | 4000.0 | 4000.0 |
| R025-06 | original | T1AT | off | fitted-c | 2253 | 0 | 0 | 0 | 0 | 0.000001 | 144.95 | 144.95 | 4000.0 | 4000.0 |
| R025-06 | original | T1AT | on | fitted-c | 2253 | 3 | 3 | 0 | 0 | 0.002293 | 143.40 | 143.29 | 4000.0 | 4000.0 |
| R025-06 | original | T1AT | on | zero-c | 2253 | 273 | 226 | 11 | 36 | 0.117990 | 143.15 | 125.14 | 4000.0 | 3688.3 |
| R025-06 | original | V16 | on | fitted-c | 2253 | 0 | 0 | 0 | 0 | 0.000005 | 138.30 | 138.30 | 1633.9 | 1633.9 |
| R025-06 | original | V16 | on | zero-c | 2253 | 0 | 0 | 0 | 0 | 0.000000 | 161.96 | 161.96 | 1525.3 | 1525.3 |
| R025-07 | refined | T1AT | off | zero-c | 2518 | 0 | 0 | 0 | 0 | 0.000019 | 137.88 | 137.88 | 3518.6 | 3518.8 |
| R025-07 | refined | T1AT | on | fitted-c | 2518 | 0 | 0 | 0 | 0 | 0.000005 | 95.20 | 95.20 | 3879.6 | 3879.6 |
| R025-07 | refined | T1AT | on | zero-c | 2518 | 0 | 0 | 0 | 0 | 0.000026 | 138.13 | 138.13 | 3418.5 | 3418.9 |
| R025-07 | refined | V16 | on | fitted-c | 2518 | 0 | 0 | 0 | 0 | 0.000001 | 90.64 | 90.64 | 3275.7 | 3275.7 |
| R025-07 | refined | V16 | on | zero-c | 2518 | 0 | 0 | 0 | 0 | 0.000000 | 146.99 | 146.99 | 303.1 | 303.1 |
| R025-08 | original | V16 | off | fitted-c | 3643 | 0 | 0 | 0 | 0 | 0.000003 | 94.19 | 94.20 | 1820.6 | 1820.6 |
| R025-08 | original | V16 | off | zero-c | 3643 | 0 | 0 | 0 | 0 | 0.000003 | 139.16 | 139.16 | 4000.0 | 4000.0 |
| R025-08 | original | V16 | on | fitted-c | 3643 | 11 | 3 | 3 | 5 | 0.003582 | 93.39 | 93.18 | 1905.5 | 1825.5 |
| R025-08 | original | V16 | on | zero-c | 3643 | 0 | 0 | 0 | 0 | 0.000004 | 139.56 | 139.56 | 4000.0 | 4000.0 |
| R025-08 | refined | V16 | off | fitted-c | 3643 | 7 | 7 | 0 | 0 | 0.001591 | 92.35 | 92.35 | 2366.4 | 2369.6 |
| R025-08 | refined | V16 | off | zero-c | 3643 | 0 | 0 | 0 | 0 | 0.000001 | 140.89 | 140.89 | 4000.0 | 4000.0 |
| R025-08 | refined | V16 | on | zero-c | 3643 | 0 | 0 | 0 | 0 | 0.000001 | 141.66 | 141.66 | 4000.0 | 4000.0 |
| R100-02 | original | T1AT | off | fitted-c | 2714 | 325 | 177 | 70 | 78 | 0.084044 | 168.59 | 168.36 | 4000.0 | 3999.3 |
| R100-02 | original | T1AT | off | zero-c | 2714 | 743 | 320 | 150 | 273 | 0.215792 | 176.17 | 159.24 | 4000.0 | 3997.9 |
| R100-02 | original | T1AT | on | fitted-c | 2714 | 556 | 273 | 131 | 152 | 0.174977 | 166.82 | 163.66 | 4000.0 | 3999.9 |
| R100-02 | original | T1AT | on | zero-c | 2714 | 645 | 305 | 120 | 220 | 0.192428 | 174.16 | 159.76 | 4000.0 | 4000.0 |
| R100-02 | original | V16 | off | fitted-c | 2714 | 89 | 21 | 16 | 52 | 0.031548 | 161.14 | 161.55 | 1968.5 | 1611.1 |
| R100-02 | original | V16 | off | zero-c | 2714 | 0 | 0 | 0 | 0 | 0.000009 | 160.23 | 160.23 | 2296.8 | 2296.6 |
| R100-02 | original | V16 | on | fitted-c | 2714 | 0 | 0 | 0 | 0 | 0.000171 | 160.40 | 160.39 | 3673.3 | 3667.4 |
| R100-02 | original | V16 | on | zero-c | 2714 | 0 | 0 | 0 | 0 | 0.000019 | 161.63 | 161.63 | 2235.4 | 2235.1 |
| R100-03 | refined | T1AT | off | fitted-c | 2835 | 20 | 13 | 2 | 5 | 0.006809 | 109.60 | 109.06 | 1566.2 | 1600.5 |
| R100-03 | refined | T1AT | off | zero-c | 2835 | 34 | 25 | 2 | 7 | 0.011714 | 111.98 | 111.54 | 1485.0 | 1536.7 |
| R100-03 | refined | T1AT | on | fitted-c | 2835 | 0 | 0 | 0 | 0 | 0.000200 | 106.81 | 106.83 | 1281.0 | 1281.9 |
| R100-03 | refined | T1AT | on | zero-c | 2835 | 1 | 1 | 0 | 0 | 0.000014 | 109.38 | 109.38 | 1166.0 | 1166.0 |
| R100-03 | refined | V16 | off | fitted-c | 2835 | 0 | 0 | 0 | 0 | 0.000000 | 129.99 | 129.99 | 2018.4 | 2018.4 |
| R100-03 | refined | V16 | off | zero-c | 2835 | 495 | 88 | 58 | 349 | 0.169462 | 119.28 | 104.82 | 617.7 | 756.3 |
| R100-03 | refined | V16 | on | fitted-c | 2835 | 0 | 0 | 0 | 0 | 0.000001 | 124.20 | 124.20 | 947.3 | 947.4 |
| R100-03 | refined | V16 | on | zero-c | 2835 | 3 | 1 | 2 | 0 | 0.001072 | 131.91 | 131.88 | 417.7 | 419.9 |
| R100-04 | refined | V16 | on | fitted-c | 2895 | 0 | 0 | 0 | 0 | 0.000096 | 98.19 | 98.20 | 521.9 | 519.8 |
| R100-04 | refined | V16 | on | zero-c | 2895 | 6 | 6 | 0 | 0 | 0.002580 | 98.40 | 98.29 | 509.5 | 573.6 |

Mean TV is the average total-variation distance between each window's before/after satellite-plus-clutter probability vectors. Zero means unchanged responsibilities. Reproduce with `audit_continuation.py` in the scientific Python environment. The companion JSON contains exact source hashes and unrounded statistics.
