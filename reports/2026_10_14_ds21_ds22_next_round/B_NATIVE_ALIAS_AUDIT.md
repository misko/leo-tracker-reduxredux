# Wrapped-to-native receiver ambiguity explains poor direct-transfer scores

A training-only zero-fit diagnostic identifies a specific missing step in the new direct B-to-native-C transfer experiment. B's wrapped likelihood is invariant to integer receiver-offset shifts of 1/4.4 microseconds = 227272.727273 Hz. C's finite native-frequency branches are not. Copying the complete B state preserves its correction function but can carry the wrong representative of that wrapped ambiguity into C.

The existing training-only modal-confident receiver-branch rule selects integers **−1 for receiver 0 and +2 for receiver 1** on both predetermined cases. Applying these two shifts changes only physical receiver intercepts. Geography, RF-dependent fitted c, clock coefficients, band offsets, satellite timing, bank, observations and priors are unchanged; no optimizer or reference is used.

| Case/model | Unlifted seed objective | Explicitly lifted seed objective | Signal mass before → after |
|---|---:|---:|---:|
| 001 B | 40400.444399 | 40400.444399 | 2252.84 → 2252.84 |
| 001 native C | 51442.675541 | 40456.387114 | 270.64 → 2147.99 |
| 019 B | 40936.599243 | 40936.599243 | 1711.10 → 1711.10 |
| 019 native C | 49145.310121 | 41347.575196 | 450.69 → 1679.91 |

The wrapped B objective changes by only 1.4552e-11 in either case. These native objectives are at the initial B states, not the later unlifted-transfer endpoints. Signal mass is posterior mass, not verified satellite detections. No location-accuracy improvement can be inferred from this score-only diagnostic, since the positions have not moved.

On 001 the rule uses 1372/893 confident windows for receivers 0/1, with modal fractions 0.936589/0.784994. On 019 it uses 1238/453 windows, fractions 0.912763/0.849890. One integer applies to each whole receiver across both bands; no per-window or truth-selected ambiguity is introduced.

This identifies a transfer-procedure mismatch, not an omitted ambiguity correction in the original C initializer. The existing C path already applies this receiver-lifting rule to its original seeds. The new experiment had deliberately copied B's final state without changing any lifts. A new source-frozen paired control will compare lifted B-repeat and lifted native C from the same original B-selected state and domain; the unlifted experiment remains an immutable control. No position-based choice between them is permitted.

Both original unlifted case matrices were sealed before this diagnostic. Source `eba7ce2c1`; four receiver-integer/mutation tests and Ruff pass. Actual run: 66.323835 seconds, eight objective evaluations, two training assignment predictions and zero fits. Receipts: `local/ds22-b-native-alias-audit-v1`; report SHA256 `c2cb267736a0618db1a0a7bd701fc690de176314beeaa40759acc564b13092e1`.
