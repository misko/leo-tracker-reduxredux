# C053 exact-coordinate preconditioning repairs fixed-profile stationarity

The diagonal-coordinate arm reached a strict stationary profile where the matched unscaled arm did not. Both began at exactly the same saved best feasible state with the same objective, priors, fixed geography, constraints and objective ftol. Original-scale independent KKT—not the transformed gradient—determined acceptance. No position was released or reference read.

| Arm | Strict profile J | Best feasible J | Best feasible original KKT | Actual objective calls | Completed iterations | Total fit/audit seconds |
|---|---:|---:|---:|---:|---:|---:|
| Original coordinates | unavailable | 50360.032179 | 747.683484 | 1569 | 345 | 55.057333 |
| Fixed diagonal coordinates | 50178.021759 | 50178.021759 | 0.000286369 | 1569 | 207 | 55.096886 |

Both optimizers hit the55 second optimization deadline and reported solver-success false. The scaled arm had nevertheless recorded a strict stationary point that passed independent acceptance within the shared60 second budget. Its NLL49849.814978 improves the source-state NLL50033.223085 by183.408107 while prior penalty increases1.397687, giving an objective improvement182.010420. It also improves on the earlier inferior strict profile J55704.855579. It still loses to the historical full-position incumbent J45613.177281; fixed-profile acceptance is not an accuracy or full-selector improvement.

The numerical intervention was the frozen affine chart `z = z_start + S*y`, using `S_i=1/sqrt(max(1,abs(H_ii)))` from the smaller-step Hessian. Bounds and constraint Jacobians were transformed exactly. Objective units, SLSQP ftol1e-11, physical/nuisance constraints, model evidence, priors and original-scale KKT were unchanged. Six negative Hessian eigenvalues remain; no statistical regularization or positive-definite Hessian assumption was introduced.

Actual oracle checks in both arms gave exactly matching J/NLL/prior and saved-source objective, physical-gradient difference4.75e-11, nuisance difference5.89e-15, inverse-chain gradient difference4.98e-11 and posterior difference1.96e-13. Four component tests and Ruff passed, including actual native gradient/constraint-Jacobian finite differences, exact bounds, and a real SLSQP test with original-scale KKT.

Each arm received60 seconds/600 iterations, with five seconds reserved for strict selection and independent audit. The baseline recorded1568 optimizer objectives plus one audit; scaling1567 plus two audits. There were two actual optimizer invocations, no releases. The four preceding actual oracle evaluations are outside the fitting counts. The source Hessian itself cost205 objectives and208 explicit native orbit calls in a prior diagnostic; this extra construction cost is disclosed, so the comparison is matched per-fit rather than a claim of equal end-to-end computational cost. The pair wave completed107.228 seconds including preparation/authority, using two single-thread workers and independent195/200 second external bounds.

Both outcomes are sealed, preserving the unavailable baseline. A free-geography experiment requires separate review; none is included here. No reference/held/locked evidence or accuracy selection was used. Source/protocole3b91fcab; namespace `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c053-precondition-control-v1`, global `seal.json` and original unit receipts.
