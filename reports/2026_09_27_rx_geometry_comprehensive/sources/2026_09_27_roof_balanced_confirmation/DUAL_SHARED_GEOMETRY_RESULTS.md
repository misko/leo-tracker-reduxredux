# Shared detection and ratio uncertainty: partial repair, no accuracy gain

All four frozen replays completed successfully in 816.0–870.5 seconds. Each
evaluated the same 289 saved coordinates per independent Sacramento/Reno prior.
All 2,312 points passed whole-cohort validation before new reference distances
were computed. The scientific scorer, model parameters, candidate-search policy,
and grid inventories were unchanged during execution.

The reference is the operator-supplied roof coordinate, not surveyed GPS truth.
This is already-unblinded development evidence, not independent confirmation.

## Every distance result

Distances are kilometres. "Detection" is the preceding shared-detection model;
"Dual" additionally integrates the accepted shared matched-ratio offset.

| Scan | Prior | Doppler-only | Original geometry | Detection | Dual |
|---|---|---:|---:|---:|---:|
| 339af | Sacramento | 2.4237 | 1.9585 | 1.9585 | 2.3884 |
| 339af | Reno | 2.4662 | 1.6095 | 1.6095 | 2.5797 |
| 53ce | Sacramento | 5.5377 | 5.5132 | 6.0323 | 6.0323 |
| 53ce | Reno | 5.7088 | 5.7013 | 6.2344 | 5.7013 |
| e76c | Sacramento | 3.0003 | 3.0003 | 4.4837 | 3.0003 |
| e76c | Reno | 3.0138 | 3.0138 | 4.0054 | 3.0138 |
| c9db | Sacramento | 5.4166 | 5.4166 | 5.4166 | 5.4166 |
| c9db | Reno | 5.4218 | 5.4218 | 5.4218 | 5.4218 |

| Mean error | Doppler-only | Original geometry | Detection | Dual |
|---|---:|---:|---:|---:|
| Sacramento | 4.094565 | 3.972148 | 4.472775 | 4.209401 |
| Reno | 4.152652 | 3.936606 | 4.317748 | 4.179155 |
| Combined | 4.123608 | 3.954377 | 4.395262 | 4.194278 |

Against Doppler-only, dual improves two cases, worsens two, and ties four.
Mean error is 2.80% worse for Sacramento, 0.64% worse for Reno, and 1.71% worse
combined. Combined median is unchanged at 4.215211 km.

Against shared detection alone, dual improves three cases, worsens two, and ties
three; combined mean improves 4.57%. In particular, both e76c positions return
to their Doppler-only/original-geometry selections, and 53ce Reno returns to its
original-geometry selection. However, both 339af cases regress and 53ce
Sacramento remains worse than Doppler-only.

Against original geometry, dual improves none, worsens three, and ties five.
No selected coordinate lies on a grid edge or prior boundary. Eight prior cases
represent only four recordings, not eight independent samples. Small radial
error changes on a half-kilometre grid do not establish metre-scale resolution.

## Validation

- All source replay and code hashes independently match the report receipts.
- Every original-geometry and shared-detection score reproduces its frozen
  source score exactly (maximum absolute difference zero).
- Doppler-only scores are identical across variants (maximum difference zero).
- Maximum 64/128 detection quadrature discrepancy is 6.4143e-7 candidate-track
  log-likelihood units, below the frozen 0.001 threshold.
- The reporting-only code-hash inventory was corrected to include two existing
  producer dependencies. Its regression test now reads the producer's actual
  receipt expression. No file imported by a live replay was edited.
- The report validates all four scans and both priors before opening reference
  metadata. No candidates or proposed coordinates were shared between priors.
- All 225 experiment-directory tests pass after replay completion, including
  the corrected producer-inventory regression test.

## Scientific conclusion and next decision

Adding shared uncertainty improves held-out reception prediction and removes
some geographic regressions, but **does not establish better position accuracy
or resolution**. Do not promote the dual model or consume the unused
confirmation cohort for this unsuccessful development model. Do not select
per-scan model variants, ratio weights, or exclusions using these errors.

The calibration-only `RX_SPATIAL_SENSITIVITY_AUDIT.md` provides a useful next
diagnostic direction: reception direction evidence survives within-track
centering in all six calibration scans, but small position displacements cause
much smaller directional changes than switching satellite candidates. A next
bounded diagnostic should distinguish fixed-identity local sensitivity from
association-driven changes, rather than assume better predictive likelihood
implies more geographic information. Measured antenna angles and a confirmed
physical/software RX mapping remain useful missing inputs for a physical model.

The active tracking-resolution goal remains unproven. No production changes,
new RF recording, or writes to source recordings occurred.

Artifacts: `dual-shared-geometry-distances.json`, all four
`dual-shared-geometry-replay-*.json` files, `DUAL_SHARED_GEOMETRY_PROTOCOL.md`,
`score_dual_shared_geometry.py`, and `RX_SPATIAL_SENSITIVITY_AUDIT.md`.
