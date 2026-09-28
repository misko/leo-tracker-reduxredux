# Shared detection uncertainty did not improve overall location error

All four fixed-grid runs completed in 533.6–578.5 seconds. The same 289 coordinates per independent prior were evaluated for original geometry, candidate-mixture geometry, and mixture geometry with the accepted shared detection effect. All 2,312 points passed validation before reference distances were computed.

The reference is the operator-supplied roof coordinate, not surveyed GPS truth. This is an already-unblinded development cohort, not independent confirmation.

## Distance results

| Recording | Prior | Doppler-only, km | Original geometry, km | Mixture, km | Shared detection effect, km |
|---|---|---:|---:|---:|---:|
| 339af | Sacramento | 2.4237 | 1.9585 | 1.9585 | 1.9585 |
| 339af | Reno | 2.4662 | 1.6095 | 1.6095 | 1.6095 |
| 53ce | Sacramento | 5.5377 | 5.5132 | 6.5309 | 6.0323 |
| 53ce | Reno | 5.7088 | 5.7013 | 6.7316 | 6.2344 |
| e76c | Sacramento | 3.0003 | 3.0003 | 3.9510 | 4.4837 |
| e76c | Reno | 3.0138 | 3.0138 | 4.0054 | 4.0054 |
| c9db | Sacramento | 5.4166 | 5.4166 | 5.4166 | 5.4166 |
| c9db | Reno | 5.4218 | 5.4218 | 5.4218 | 5.4218 |

| Prior | Mean Doppler-only | Mean original geometry | Mean mixture | Mean shared effect |
|---|---:|---:|---:|---:|
| Sacramento | 4.094565 | 3.972148 | 4.464221 | 4.472775 |
| Reno | 4.152652 | 3.936606 | 4.442068 | 4.317748 |
| Combined | 4.123608 | 3.954377 | 4.453144 | 4.395262 |

Against Doppler-only, shared geometry improves two cases, worsens four, and ties two. Mean error is 9.24% worse for Sacramento and 3.98% worse for Reno, or 6.59% worse overall. Combined median also worsens, from 4.215211 to 4.950147 km.

Against the previous mixture, shared geometry improves two cases, worsens one, and leaves five unchanged. Against original geometry it improves none, worsens four, and leaves four unchanged. No selected point lies on a grid edge or prior boundary.

## What changed in the local ranking

Under the shared-effect objective, compare its chosen point to the previous mixture's chosen point. Negative score difference favors the new point:

| Case | Shift east/north, km | Doppler change | Detection increment change | Conditional ratio increment change | Joint change |
|---|---|---:|---:|---:|---:|
| 53ce Sacramento | -0.5 / 0 | -0.000639 | +0.000149 | +0.000004 | -0.000486 |
| 53ce Reno | -0.5 / 0 | -0.001302 | +0.000116 | +0.000001 | -0.001186 |
| e76c Sacramento | +0.5 / -0.5 | +0.000373 | +0.000278 | -0.001204 | -0.000553 |

The 53ce correction moves back toward the Doppler preference. The new e76c Sacramento regression is instead favored by the conditional ratio term, despite worse Doppler and detection terms. These are telescoping shared-candidate likelihood increments, not independent reception marginals or causal proof of incorrect satellite identity.

This is consistent with the unresolved ratio-model issue: its held-out track residual-sum dispersion was 5.7768 times expectation, and it remained unchanged in this detection-only prototype. That calibration evidence justifies investigating a correlated ratio model; the known geographic errors must not be used to select a downweighting factor or remove tracks.

## Validation and decision

- Old and mixture scores reproduce the frozen reference replay with maximum absolute difference 3.55e-15.
- Doppler-only scores remain identical across reception variants.
- Maximum 64-versus-128 quadrature discrepancy is 6.42e-7 candidate-track log-likelihood units, well below 0.001.
- All four replay hashes and recorded code hashes were independently verified.
- All 193 experiment-directory tests pass; the reporter rejects a corrupted binding before reading reference positions.
- No candidate sharing between priors, model tuning using distances, new RF, or production changes occurred.

Do not promote this model as improved location accuracy, and do not consume the unused confirmation cohort for this unsuccessful development model. Better held-out reception prediction did not establish better position discrimination. The active resolution goal remains unproven.

Artifacts: `shared-geometry-distances.json`, four `shared-geometry-replay-*.json` files, `SHARED_GEOMETRY_PROTOCOL.md`, and `score_shared_geometry.py`. `NEXT_CONFIRMATION_AVAILABILITY.md` is metadata-only preparation; none of those four recordings has been evaluated by this experiment.
