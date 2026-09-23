# Frozen sixteen-scan comparison protocol

This experiment extends `../2026_09_23_sixteen_scan_position_resolution`.
The sixteen session IDs selected there remain fixed. No additional recording is required.
All 553 eligible tracks and 14,043 observations remain in the accounting, including
unmatched tracks. Raw observation counts are not independent-information counts.

## Parallel work

| Owner | Experiments | Owned outputs |
|---|---|---|
| SOL joint search | Shared stationary position; retained multiple spatial basins; finer location refinement; 1/2/4/8/16 scan accumulation | `joint/` |
| SOL timing and robust loss | Integer versus fractional timing; duration versus robust/error-floor weighting; nuisance-bound diagnostics | `timing_robust/` |
| Terra association and orbit | Hard versus soft identity with null support; shared orbit-correction feasibility/ablation | `soft_orbit/` |
| Coordinator | Evidence/validation audit, common comparison figures, limitations and final report | top-level report |

## Comparison rules

1. Sacramento radius 250 km and Reno radius 500 km retain the existing prior centres.
   Known receiver coordinates must not enter candidate generation, seed selection,
   optimization, loss tuning or model selection. Evaluate geographic error afterwards.
2. Preserve the pipeline's fixed randomized observation partitions. Do not substitute
   a chronological suffix. Scores used to choose identities or locations are selection
   scores, even if legacy code names them held-out scores.
3. Use identical observations, candidate support and trial-point support for a direct
   ablation. Report differences in candidate universes and search support explicitly.
   A shortlist-conditioned refinement is not a new full-catalogue blind search.
4. Do not sum interpolated independent score maps and call that an exact joint fit.
   Recompute location-dependent receiver geometry; reuse satellite states where valid.
5. Preserve coarse incumbents during spatial refinement. Smaller spacing establishes
   numerical resolution, not physical accuracy. Report remaining alternative basins.
6. Keep track duration and unmatched support in the objective. Estimate any uncertainty
   weights from training observations, with a stated error floor. Avoid counting the
   same satellite, dual-RX support or adjacent samples as independent evidence.
7. Compare validation and stability as well as optimized residual. If a genuinely
   untouched outer evaluation cannot be executed, state that limitation explicitly.
8. Report timing/orbit nuisance bounds and identifiability. An unsupported correction
   or phase constraint is a failure/feasibility result, not a manufactured position.

## Deliverables

Machine-readable per-method estimates, objectives, candidate scope, evidence counts,
timings and diagnostics; reproduction commands; a common location/error comparison;
residual-versus-position-error plots; accumulation and sensitivity plots where measured.
Include methods that cannot be supported in a clearly marked limitations table.
Completed research artifacts may be committed and pushed to main under the user's
existing authorization. This experiment does not authorize a production deployment.
