# C053 matched best-feasible restart: negative numerical result

A budget-matched restart from the best feasible LOW-to-full fixed-profile trajectory did not produce a strict endpoint. The uninterrupted control again selected the much worse stationary trajectory point. Both methods preserved the same better feasible state, which remained strongly nonstationary; it is not selectable. No geography was released and no reference or held evidence was read.

| Arm | Strict selected J | Best feasible J | Best feasible KKT | Actual objective calls | Completed iterations | Total fit/audit seconds |
|---|---:|---:|---:|---:|---:|---:|
| Uninterrupted | 55704.855579 | 50360.032179 | 747.683484 | 1554 | 354 | 55.083939 |
| Best-feasible restart | unavailable | 50360.032179 | 747.683484 | 1565 | 191 | 55.074353 |

Each arm had a shared60 second/600 iteration budget, with five seconds reserved for independent acceptance audits. The uninterrupted optimizer ran to55 seconds. Restart phase1 ran30 seconds/102 completed iterations and phase2 used the remaining25 seconds/89 iterations, with the shared remaining iteration cap498. Both restart phases stopped on the time bound. The actual two-arm wave completed in96.170 seconds including source authority/preparation; independent external195/200 second unit limits were present. There were three SLSQP invocations total.

The original complete initializer objective was50365.838662. Both methods found a feasible improvement of5.806483, but its independent KKT747.683484 is far above0.001. The uninterrupted selected endpoint J55704.855579 has independent KKT6.036602e-5 and is exactly the preceding inferior profile result. Its NLL55450.409517 is worse than the best feasible NLL50033.223085. Strict stationarity and low objective remain distinct requirements; neither this endpoint nor the failed restart demonstrates a good profile optimum.

Both actual native oracle checks passed before optimization: J/NLL/prior and fixed geography differences exactly zero, physical gradient difference3.65e-9, nuisance gradient6.09e-13, and posterior difference1.67e-12. Same model, priors, native evidence, complete seed, fixed geography and original25 km disk were used. All strict acceptance decisions were independently reevaluated within the shared budget. Seven component tests and Ruff passed, including a real SLSQP run and a regression proving audit deadline exhaustion cannot accept an unchecked trajectory. The uninterrupted arm recorded1552 optimizer calls plus two audits; restart recorded1564 plus one audit. These are objective calls, not iterations.

Both outcomes are sealed, including the unavailable restart. Original failed/accepted results remain unchanged; no retry occurred in the previous namespace. There is no accuracy result or model promotion from this numerical control. A subsequent diagnostic should inspect constrained descent, gradient consistency and visibility/branch changes at the training-selected best feasible state before prescribing another solver continuation.

Source/protocol7dbb1a73c. Namespace `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c053-best-feasible-control-v1`; wave `ds22-c053-best-feasible-wave-v1`. Exact terminal and source archives are bound by `seal.json`. The prior experiment and positional comparison remain in `DS22_C053_HALF_TRANSPORT_RESULTS.md`.
