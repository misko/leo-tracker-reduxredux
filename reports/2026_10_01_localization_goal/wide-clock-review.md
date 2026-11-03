# Wider shared-clock Gaussian prior

The fixed 12-scan DS9/DS10/DS11 development panel does not support widening the shared clock prior. Retain the 1 s baseline; no full-64 expansion or deployment change was made.

| Prior standard deviation | Accepted | Median horizontal error | 90th percentile | Within 3 km |
|---|---:|---:|---:|---:|
| 1 s control | 12/12 | 1,892 m | 3,998 m | 10/12 |
| 2 s | 12/12 | 1,897 m | 3,998 m | 8/12 |
| 5 s | 12/12 | 1,935 m | 4,000 m | 8/12 |

Both wider arms improve only 5/12 scans. Maximum absolute change in the fitted shared clock is 0.078 s at sigma=2 s and 0.100 s at sigma=5 s. The largest error regression is 289 m at 5 s. This suggests that shared-clock shrinkage is not the main accuracy bottleneck within the tested modes. It does not exclude timing errors or different behavior after fresh acquisition and association.

Only the clock penalty changed, from c²/2 to c²/(2 sigma²), with sigma=1,2,5 s. Satellite epoch priors remain N(0,0.5² s²), receiver drift priors N(0,0.5² (Hz/s)²), height 30.48 m MSL, and Sacramento regional support unchanged. Position and all active nuisance parameters were jointly refitted from saved baseline states. Satellite identities were fixed. This is a warm conditional sensitivity study, not a new cold full-pipeline benchmark. The 12 scans are previously exposed development data; reference coordinates are unsurveyed operator coordinates and were accessed only after numerical acceptance decisions.

The shared c and satellite-specific e_s enter as c+e_s. Relaxing c changes both common timing regularization and the decomposition of effective offsets. It does not by itself identify physical clock error. Gaussian normalization constants, which do not affect each arm's optimum, remain omitted; objectives must not be compared across arms as model evidence.

Four isolated tests passed for prior penalty, gradient, curvature, preservation of other coordinates, and invalid-arm rejection. All 36 fits passed source/input binding, support, monotonic objective, stationarity, full finite-difference gradient and matched-control audits. At most two fits ran concurrently with 25 s internal / 30 s external limits. Median warm runtimes were 2.29, 2.46 and 2.37 s; these exclude original acquisition work.

Artifacts: [sealed evaluation](wide-clock-v1-evaluation.json), [source freeze and receipts](wide-clock-v1/sources.json), [plot](wide-clock-v1.png). The evaluator completed and wrote a verified hash-sealed result; its subsequent redundant stdout copy to /tmp hit a disk quota. The saved result and generated plot were successfully read and checked.

![Per-scan errors and shared-clock offsets](wide-clock-v1.png)
