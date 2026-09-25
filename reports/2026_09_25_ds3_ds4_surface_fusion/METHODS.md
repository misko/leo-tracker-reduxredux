# DS3/DS4 objective-surface fusion method contract

This experiment was specified before reference-position scoring. It consumes the
sealed Sacramento `diagnostics.evaluated_points` surfaces from
`scanner-adaptive-tle-position-v2`. Inference does not read the source
`reference_evaluation_only` object, source position-error fields, or the known
receiver coordinate.

Each scan has 400 adaptively selected points. Exact overlap is audited before
fusion. Because the full-set intersection contains only 48 points and does not
provide a useful local neighborhood, every scan is independently interpolated
onto the same 6.25 km grid inside a 243.75 km Sacramento-centered disk. The
interpolator is piecewise-linear over a Delaunay triangulation. Every unit uses
only grid points supported by every included scan, so the compared objective at
every cell has the same session membership.

Scans receive equal total weight. This prevents long or high-yield scans from
silently dominating a multi-scan position. The primary method averages capped
MSE. Three scale-robust sensitivity methods are also fixed before scoring:

1. `raw_mse`: arithmetic mean of squared capped RMS.
2. `delta_mse`: subtract each scan's sampled minimum, then average. Under equal
   weights this must select exactly the same result as raw MSE; it is retained
   as an explicit invariance check.
3. `robust_scaled_delta_mse`: divide each delta-MSE surface by its sampled MSE
   IQR (with a fixed 1 Hz² floor), then average.
4. `fractional_rank`: replace the 400 sampled MSE values with fractional ranks,
   interpolate those ranks, then average.

The grid minimum is refined with one quadratic fit to its nearest 25 common-grid
points. The continuous estimate is accepted only when the Hessian is positive
definite, the design is full rank, local R² is at least 0.80, the stationary
point remains inside both the local fit support and prior disk, and the discrete
minimum is interior. Otherwise the discrete grid point is reported.

Inference is sealed before the receiver reference coordinate is introduced.
Post-seal scoring evaluates every DS3 and DS4 single scan, the frozen
non-overlapping groups of eight, each full dataset, and the combined DS3+DS4
full unit. Curvature describes the fitted objective surface; it is not a
calibrated position uncertainty.
