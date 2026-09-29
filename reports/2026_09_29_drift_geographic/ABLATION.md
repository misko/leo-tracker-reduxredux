# Completed differential-drift geographic ablation

All 54 declared combinations are terminal. No allocation is selected by reference error.
Each median requires all three early/middle/late panel audits. Missing medians are explicit.

| Model | DS7 / 4 m | DS7 / 8 m | DS8 / 4 m | DS8 / 8 m | DS9 / 4 m | DS9 / 8 m |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 2,196.1 | 2,023.6 | 2,473.8 | 1,721.1 | 1,173.9 | 876.1 |
| symmetric | 2,191.6 | 2,022.1 | 2,473.8 | 1,679.1 | 1,173.9 | 907.7 |
| rx0_anchor | 2,190.1 | 2,025.4 | 2,470.8 | 1,643.9 | 1,173.9 | 862.5 |
| rx1_anchor | 2,194.5 | 2,020.8 | 2,477.1 | 1,757.6 | 1,173.9 | 977.7 |

| Allocation | Audited / 18 | Lower error | Error tie | Better held | Held tie | Sub-km | Worst error m |
|---|---:|---:|---:|---:|---:|---:|---:|
| symmetric | 18 | 11 | 1 | 8 | 1 | 3 | 3675.6 |
| rx0_anchor | 18 | 10 | 1 | 3 | 1 | 3 | 3658.2 |
| rx1_anchor | 18 | 9 | 1 | 14 | 1 | 3 | 3688.5 |

Tie tolerances are 1e-6 m and 1e-7 nats for numerical reporting only.
Counts use audited results; nested panels and donor corrections are dependent.
These previously explored, unsurveyed-reference errors are not blind accuracy or calibrated resolution.

![Median errors](ablation.png)

[Every panel, start and audit status](all-complete/README.md). [Machine-readable comparison](ablation.json).
