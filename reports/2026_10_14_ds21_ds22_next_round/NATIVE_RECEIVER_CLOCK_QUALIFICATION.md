# Native receiver-clock numerical qualification

Both predetermined DS22 cases passed the zero-fit qualification. At all six original C starts plus its selected training endpoint, zero added clock coefficients reproduced the original objective, physical gradients, receiver-group gradients and posterior responsibilities exactly: maximum absolute difference **0** on both cases. The new 18-coefficient clock basis and prior match the original B model, while corrections are evaluated at C's native candidate timestamps.

| Case | States checked | Objective calls | Optimizer calls | Largest scaled clock gradient at original endpoint | Analytic directional derivative | Finite difference |
|---|---:|---:|---:|---:|---:|---:|
| DS22-001 | 7 | 16 | 0 | 31.856611031 | 0.637132221 | 0.637132198 |
| DS22-019 | 7 | 16 | 0 | 51.635521218 | -1.032710424 | -1.032710410 |

The additional directions have nonzero derivatives at the old stationary endpoints, so the augmented objective has local descent directions there. This establishes neither a physical receiver-clock cause nor improved position accuracy. The matched six-start fitted experiment remains necessary; no new localization result or incumbent replacement is claimed.

001 completed in 36.166527 seconds and 019 in 31.163286 seconds. Both were below the frozen 120-second qualification limit. Eight component/tool tests passed; Ruff passed. No reference or held observations were read. The next experiment is specified in `NATIVE_RECEIVER_CLOCK_PROTOCOL.md` and must preserve the original per-call budgets and both sealed training selections before reference reporting.

Frozen implementation and qualifier: `6e51a96c5`. Actual receipts: `local/ds22-native-clock-qualification-v1/DS22-{001,019}`. The original C implementation, original matrices and prior failed diagnostics remain unchanged.
