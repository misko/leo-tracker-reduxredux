# Normalized latent-peak pilot

The fitted-c mixture changes requested coverage 192→194/293, while full original-winner coverage changes 6270→6239/7707. Major windows (at least 80% net restoration of originally missing support) remain 3→3 among 6 tested windows. Normalized group rotation-control associations change 1132→1139. This pilot does not justify expanding the uniform-peak model to all sources.

One likelihood contribution per probe group: `-log(mean(exp(-row_nll)))`, with uniform weight over all passed GLRT peaks. The original row density already contains clutter. Posterior peak probabilities weight both frequency and visibility/q normalizer gradients; physical priors appear once. Singleton groups exactly reproduce the original 125 Hz objective and every gradient. Actual support times and RF values are retained.

Tested 2/5 sources: S03, S04; 7707/20,084 original winners and 293/693 challenge observations. The CSV retains all 15 fixed window denominators; blank cells are untested. Nine synthetic tests pass. No production code or frozen report changed.

Every arm starts at the same sealed fixed-bank fitted-c profile endpoint. The c=0 arm changes only c before fitting. Both the original-winner continuation and peak-mixture continuation receive the same additional allowance of at most 1,000 complete objective calls and 120 seconds, with no proposal orbit projections. The reused upstream profile endpoint already had its separate 1,000-call/120-second allowance; it is shared by the paired continuations. Original band offsets, clock nodes, q budget, priors, candidate order and all existing bounds are preserved. Public frozen sequential calibration verifies analytic time/RF-center transport within 1e-6 Hz, without changing clock, q or timing coordinates.

| Source | c arm | Optimized density | Winner full | Challenge | New/lost vs original | New/lost vs seed | Reference km | Strict KKT | Calls |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| S03 | fitted-c | mixture | 3459/3988 | 136/138 | +421/−53 | +16/−24 | 3.391 | 2.58e-05 | 350 |
| S03 | fitted-c | winner | 3467/3988 | 136/138 | +423/−47 | +0/−0 | 3.282 | 0.000306 | 19 |
| S03 | zero-c | mixture | 2444/3988 | 120/138 | +350/−997 | +1042/−374 | 4.327 | 0.000772 | 399 |
| S03 | zero-c | winner | 2493/3988 | 120/138 | +345/−943 | +1050/−333 | 4.318 | 0.00016 | 405 |
| S04 | fitted-c | mixture | 2780/3719 | 58/155 | +549/−150 | +91/−114 | 259.460 | 0.00077 | 377 |
| S04 | fitted-c | winner | 2803/3719 | 56/155 | +548/−126 | +0/−0 | 260.094 | 0.000411 | 18 |
| S04 | zero-c | mixture | 2552/3719 | 63/155 | +550/−379 | +465/−219 | 258.647 | 0.000115 | 428 |
| S04 | zero-c | winner | 2630/3719 | 61/155 | +581/−332 | +524/−200 | 258.815 | 0.000215 | 412 |

The configured station is an uncertain external reference used only for measurement. In-sample likelihood gain does not establish improved localization. All original support losses remain visible in the JSON; the paired-seed columns measure the incremental change from the shared profile endpoint.

| Source | c arm | Optimized density | Winner RMS Hz | Winner NLL | Peak-set NLL | Group posterior associations | Rotation control |
|---|---|---|---:|---:|---:|---:|---:|
| S03 | fitted-c | mixture | 140.66 | 40715.94 | 40640.32 | 3515 | 587 |
| S03 | fitted-c | winner | 140.84 | 40676.09 | 40678.69 | 3509 | 592 |
| S03 | zero-c | mixture | 176.31 | 46044.04 | 45537.91 | 2654 | 585 |
| S03 | zero-c | winner | 178.71 | 45943.29 | 45617.18 | 2647 | 592 |
| S04 | fitted-c | mixture | 150.90 | 39925.74 | 39265.13 | 3006 | 552 |
| S04 | fitted-c | winner | 147.44 | 39820.65 | 39415.92 | 2982 | 540 |
| S04 | zero-c | mixture | 162.94 | 41410.77 | 40689.28 | 2820 | 549 |
| S04 | zero-c | winner | 163.79 | 41232.39 | 40803.72 | 2820 | 580 |

Winner NLL is always evaluated on the original fixed observations; peak-set NLL always uses the same all-peak groups. Values across these two columns are different observation likelihoods and are not comparable. Group counts use maximum satellite posterior **after summing over latent peaks**, compared with group clutter. No maximum-over-peaks count is credited as recovery. The fixed within-RX/channel half rotation preserves each lane’s CFO distribution while breaking its time links. It is one diagnostic negative control, not a calibrated significance test or a null-refitted comparison.

A possible next model would learn peak reliability from independent training evidence instead of assigning equal weight to every passed alternative. That would require a separate training-only calibration and new null checks; this pilot supplies no validated weights. More alternative opportunities alone have not restored a new major window.

![Matched original-winner coverage](pilot-coverage.png)

![Timing distributions with identical candidate counts](pilot-timing.png)

Reproduce with the pinned scientific Python environment: `python -m unittest discover -s reports/2026_10_17_dsx01_iteration4/peak_mixture -p "test_*.py" -v`, `python reports/2026_10_17_dsx01_iteration4/peak_mixture/run_pilot.py --source S03` (then S04), and `python reports/2026_10_17_dsx01_iteration4/peak_mixture/report_pilot.py`.
