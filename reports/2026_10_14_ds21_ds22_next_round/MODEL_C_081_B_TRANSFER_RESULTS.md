# C081 complete B-to-native-C transfer: valid transport, no localization gain

The complete training-selected B state can be transported exactly into C's
native receiver-clock model, but its matched native refit loses to the current
C incumbent. Selected error stays12.785305 km. This is a negative transfer
result, not evidence that every possible B initializer has been exhausted.

The source-modal receiver alias shifts are−1 and+2, with modal fractions
0.856041 and0.767802 among778 and323 confident windows. The audit verifies
unchanged original wrapped likelihood, all four orbital outputs, full native
time/RF correction, receiver-clock priors and normalized native window scores.
Maximum correction discrepancy is1.1642e-10 Hz; orbital discrepancies are zero.
The native donor starts with objective27850.282697,1806.999379 above C's current
winner. Both source states satisfy their original25 km domains with zero
initializer adjustment. No reference is read during qualification.

| Matched native refit | Objective | NLL | Prior | KKT | Error (km) |
|---|---:|---:|---:|---:|---:|
| Complete lifted B donor | 27074.589422 | 26669.227653 | 405.361769 | 0.000077785 | 21.460507 |
| Current C incumbent repeat, selected | 26043.283318 | 25638.756309 | 404.527009 | 0.000311220 | 12.785305 |

Both fits pass independent stationarity checks. They use the same native model,
20-second/600-iteration budgets and their respective original search centres.
The unchanged accepted C incumbent is retained in the training selector.
The pair is sealed before reference evaluation. No cross-model raw objective
ranking is used and no new prior, candidate or likelihood is introduced.

The zero-fit qualification takes9.455 seconds (4 objectives); the matched pair
takes28.193 seconds (2 fits). Three new component tests and Ruff pass; exact
transport uses the previously tested native-state component unchanged.

Sources: audit `b543631b8`, fit `1836fd481`, evaluator `dba9cb54e`.
Bulk root `/srv/bulk/leo-research-ds21-ds22/2026_10_14`.
Audit namespace `model-c-b-transfer-audit-081-v1`; result SHA256
`dca0fcfe7619ebd3cfa10f127cdf6942c8054ccf9d568678fcfb03b605342679`.
Fit namespace `model-c-b-transfer-fit-081-v1`; terminal SHA256
`e0100d78364205783c2860830a203062627267555660492c396291dba8d7f9e8`.
Fit seal SHA256 `4273cca9ed9f918cb07d42346407ead2b8f54ee205739f2ec8c4efc7cd887e6c`.
