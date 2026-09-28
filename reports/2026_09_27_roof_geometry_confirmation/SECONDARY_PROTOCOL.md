# Frozen secondary: RX-guided coverage, Doppler-only final ranking

Frozen before confirmation distance unblinding. This secondary does not replace
the primary `D_plus_geometry` selection and must be reported separately.

For each completed confirmation branch, take exactly the unique coordinates
whose `D_plus_geometry` arm trace records an `evaluate` event. Require this count
to equal that arm's declared evaluated-point count and require every coordinate
to have one finite entry in `branch.point_components`. Select the minimum frozen
robust Doppler score `D` within only that coordinate set, with deterministic
ties by east then north.

The D arm's coordinates and the union/common inventory are inadmissible. No new
orbit propagation, candidate fitting, reception scoring, search evaluation, or
GPS/reference coordinate is used. Reception evidence affects only which 160
coordinates the joint arm explored; Doppler likelihood alone chooses the final
coordinate among those points.

This distinguishes an RX search-guidance effect from a final joint-likelihood
ranking effect. It cannot establish either effect if source-topology coverage
fails, and it does not convert an incomplete primary cohort into a completed
confirmation.
