# Canonical duplicate fits in Graph arbitration

This separate development experiment tests the ownership instability exposed by the two sealed DS30-0008 detector outputs. The competing proposals at the first changed row both fit degree four to exactly the same 79 observations on the same time basis. Their fitted coefficients differed by less than 6 × 10⁻¹¹ Hz. The lifted responses delivered to the least-squares fitter selected identical integer carrier branches in this witness. The absolute gauge difference was zero. [Original arbitration trace](graph-native-path.md#source-of-the-dense-membership-change) · [Captured fit and replay evidence](measurements/graph-canonical-alias.json)

The predeclared rule groups proposals only if their ordered observation indices, polynomial degree, reference time, scale, and relative integer carrier lifts agree exactly. It records the array that the fitter actually used. For each raw response `y`, it recovers the nearest integer `k` in `y + kP` from the lifted response. The reconstruction must lie within 32 binary64 epsilons of the largest magnitude among the raw value, lifted value and period `P`. This accounts for rounding in subtracting the prediction, translating, wrapping and adding the prediction back, plus the recovery arithmetic. The rounding interval must also be smaller than a quarter-period so it can certify a unique integer. Fits with a different gauge shift all recovered integers by the same constant. Subtracting the first integer therefore defines one equivalent regression with the first raw measurement as its gauge. The earliest proposal supplies the group's ordering. Stock finalization and polynomial gates consume the canonical fit. [Implementation](../../../tools/pipeline_eval/variants/experimental/graph_alias.py) · [Planted equality, carrier translations, distinct fits and fallback tests](../../../tests/pipeline_eval/test_graph_alias.py)

| Saved detection input | Collapsed groups | Graph owners, stock → canonical | Lost / gained / reassigned | Final tracks / curved keys |
|---|---:|---:|---:|---:|
| DS30-0008 deployed | 14 | 6,456 → 6,473 | 0 / 17 / 0 | 236 / 111 |
| DS30-0008 packed Q15 | 14 | 6,454 → 6,473 | 0 / 19 / 0 | 236 / 111 |
| Public north | 0 | 450 → 450 | 0 / 0 / 0 | 31 / 15 |
| Public south | 4 | 423 → 432 | 0 / 9 / 0 | 30 / 14 |

The two dense detector inputs now agree on every final Graph owner while retaining all three measured CFO differences. Each paired run uses the same saved detection bytes. The northern prepared output is byte-identical. The southern and physical memberships change relative to the original finalizer. In the dense witness, roundoff had split identical supports before the minimum-support and quality gates. The comparison establishes reproducibility under this particular detector perturbation. Ground-truth recovery and downstream position accuracy require separate checks.

The trial uses the sealed dense pair, the saved northern inside input from the native-path replay and the deployed detections from the published southern inside pair. Extend the Gauss command in the native-path replay with the southern path from the receipt, and replace the script with `graph_alias_trial.py`. Supply the four detection paths in table order. The trial alternates the reference-first and canonical-first order. Recorded CPU differences were small relative to the complete Graph stage. [Gauss replay environment](graph-native-path.md#reproduction) · [Input paths, timing and ownership receipts](measurements/graph-canonical-alias.json)

## Southern saved-solver check

The installed ALGO08 solver used the same saved southern detections and original capture-time orbital archive for both methods and both mirrored offers. The canonical rule was scoped to Graph preparation. The check alternated which method ran first. The scorer used the public simulated location after inference. [Saved-solver runner](graph_alias_solve.py) · [Input pins and complete receipt](measurements/graph-canonical-alias-south-solver.json) · [Earlier mirrored offers](mirrored-regions.md)

| Southern offer | Decision with either method | Horizontal error c = 0 / fitted c | Frequency RMS c = 0 / fitted c |
|---|---|---:|---:|
| 100 m inside | Correct keep | 0.816789 / 1.101409 km | 6.502299 / 6.391940 Hz |
| 100 m outside | False keep | 0.817172 / 1.102143 km | 6.502345 / 6.392003 Hz |

At each offer the methods produced identical positions, frequency RMS, objective replay, optimizer path, and all 137 diagnostic grid points. Both calibration arms retained the same 266 satellite owners over seven satellites. The nine new Graph members did not increase the final satellite owner count. Both methods still returned the omitted offer. Fitting `c` reduced frequency RMS and increased horizontal error for both offers. This comparison measured downstream effects at one public simulated site. The dense physical replay stopped at Graph ownership. [Fit and grid parity](measurements/graph-canonical-alias-south-solver.json)

Use the same Gauss lock and environment from the Graph replay. The arguments below bind the exact detector digest, original archive and stored mirrored offers. Use `--canonical-only` to reproduce only the candidate's diagnostic grids against the already published reference grids.

```bash
south=("$bench"/paired-full-signed-south-inside/baseline/fast-scan-automatic-work/*/detections.json)
"${locked[@]}" "$release/venv/bin/python" -B reports/ALGO08/single-core-2x/graph_alias_solve.py \
  "${south[0]}" 9ead12e735906a95066b77dfcaca54e9bdf68dc0a2c816a95fa3bca3419a3d49 \
  "$release/assets" /tmp/leo-regional-qZJKBw4W/public/tle \
  sha256:7aa06cab0502bcac70645a41a219bb6d53f1077f329e6f7ed79eb59a8794feec \
  reports/ALGO08/single-core-2x/measurements/region-mirrors.json.gz south
```
