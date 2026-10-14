# Reviewed C endpoint checkpoint control

The additional-budget control separates two failures. On DS22-001, the previously rejected lower- and upper-anchor paths now converge, but the original full-band model still ranks both below its original solution. On DS22-003, the rejected upper-anchor profile stops almost immediately with the same residual nonstationarity. Neither case changes the selected solution in this control.

All distances below are to the configured, unconfirmed DS22 reference. They are not verified accuracy. The two case selections were sealed before this reporting join.

| Case / stationary release | Configured distance, km | Training objective | Likelihood NLL | Selected |
|---|---:|---:|---:|---|
| 001 / original-full control | 21.266493 | 41863.551059 | 41529.962579 | Yes |
| 001 / lower anchor | 9.481242 | 42032.596044 | 41779.457003 | No |
| 001 / upper anchor | 3.404501 | 43618.874533 | 43404.248856 | No |
| 003 / original-full control | 2.827544 | 33448.986949 | 33162.958700 | Yes |

The 001 lower/upper release stationarity values are 0.000085843 and 0.000094535, both below the unchanged 0.001 threshold. Their final positions are closer to the configured reference, but both their objectives and likelihood NLLs are worse than the selected original. Therefore initialization/timeout alone cannot explain the 001 discrepancy for these tested paths. Removing the prior from the final ranking would not reverse it. This does not prove that every other basin or candidate assignment is exhausted.

On 003, the upper-anchor profile returned solver success after 0.634 seconds with objective 32749.329539 and stationarity 0.002929311. This reproduces the previous near-stationary failure without exhausting runtime. It remains excluded and no release was run. Simply extending runtime or repeating this continuation is not supported. Investigating numerical stopping criteria is distinct from weakening the independent acceptance threshold. The previously accepted lower-anchor release at 2.709445 km belongs to the earlier experiment and was not part of this predetermined failed-endpoint control; this control does not replace that result.

Nine calls were made: six on 001 and three on 003. Each retained the original 20-second/600-iteration limit, model, fitted c, observations, bank and 25 km anchor disk. The 001 run completed in 81.226726 seconds; 003 in 41.409333 seconds. All calls returned, with the single nonstationary profile retained. This experiment deliberately adds budget to the original run. No further checkpoint continuation is authorized by its frozen protocol, and no production/incumbent model was replaced.

Source `f5d8233ba`, evaluator `a4f4cafa7`: five component tests pass and Ruff passes. Parent endpoint objective replays and original qualified-start equality were checked before the new calls. The paired evaluator checks both seals, exact call inventories and training selections before reference access.

Receipts: `local/ds22-c-anchor-checkpoint-v1/DS22-{001,003}`; comparison: `local/ds22-c-checkpoint-comparison-v1/report.json`. Original failed endpoints and derivative audits remain immutable in their earlier namespaces.
