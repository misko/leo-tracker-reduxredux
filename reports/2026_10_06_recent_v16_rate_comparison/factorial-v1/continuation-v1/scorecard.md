# Position scorecard after optimizer continuation

This comparison uses only scans with all 16 continuation configurations saved. Every configuration therefore has the same scan denominator. The original fixed-budget results remain unchanged. Continuation changes optimization effort, not observations, satellite sets, likelihoods, priors, or the 4 km constraint.

Complete scans (12/16): R025-01, R025-02, R025-03, R025-04, R025-05, R025-06, R025-07, R025-08, R100-01, R100-02, R100-03, R100-04.

Saved-error medians retain boundary and unconverged results; they describe the saved outputs, not a verified ranking of minima. The convergence-qualified success count uses the full complete-scan denominator and does not credit an unconverged low-error result. Boundary counts are reported independently of convergence.

| Measurements | Model | Cone | RF | Scans | Saved median m | Unconverged | Boundary | Converged within 1 km | Common converged median m |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| original | T1AT | off | fitted-c | 12 | 1745.9 | 1 | 1 | 1/12 | 1516.6 |
| original | T1AT | off | zero-c | 12 | 2052.6 | 1 | 1 | 1/12 | 1573.8 |
| original | T1AT | on | fitted-c | 12 | 1734.4 | 2 | 2 | 1/12 | 1517.1 |
| original | T1AT | on | zero-c | 12 | 2248.1 | 2 | 2 | 1/12 | 1580.8 |
| original | V16 | off | fitted-c | 12 | 1766.4 | 0 | 1 | 1/12 | 1865.0 |
| original | V16 | off | zero-c | 12 | 2087.0 | 1 | 1 | 1/12 | 1451.2 |
| original | V16 | on | fitted-c | 12 | 2038.5 | 0 | 1 | 1/12 | 1850.4 |
| original | V16 | on | zero-c | 12 | 1813.9 | 1 | 2 | 1/12 | 1438.1 |
| refined | T1AT | off | fitted-c | 12 | 1481.9 | 0 | 0 | 2/12 | 1387.9 |
| refined | T1AT | off | zero-c | 12 | 1570.6 | 0 | 0 | 2/12 | 1396.5 |
| refined | T1AT | on | fitted-c | 12 | 1318.6 | 0 | 0 | 2/12 | 1223.4 |
| refined | T1AT | on | zero-c | 12 | 1443.2 | 0 | 0 | 2/12 | 1216.3 |
| refined | V16 | off | fitted-c | 12 | 1966.9 | 1 | 1 | 2/12 | 1714.8 |
| refined | V16 | off | zero-c | 12 | 1767.2 | 1 | 2 | 3/12 | 1393.3 |
| refined | V16 | on | fitted-c | 12 | 1862.9 | 0 | 1 | 3/12 | 1421.4 |
| refined | V16 | on | zero-c | 12 | 1650.6 | 1 | 2 | 4/12 | 1002.7 |

The final column uses the same 8 scans for every row, requiring convergence in all 16 configurations: R025-01, R025-02, R025-03, R025-04, R025-07, R100-01, R100-03, R100-04. This removes numerical failures but selects an easier subset, so it cannot replace the full-cohort results. Boundary solutions remain constrained rather than global certificates.

All fits use the full associated data. These are descriptive development results, not held-out localization validation. No per-scan best configuration is selected using known position. Sample-rate groups are different captures, not randomized treatments. The c = 0 arm disables the final RF coefficient while preserving the fitted-c upstream receiver baseline.

[Per-case continuation results](report.md) · [Fixed-budget comparison](../report.md). Reproduce with `continuation_scorecard.py` in the scientific Python environment. The companion JSON contains exact values and source hashes.
