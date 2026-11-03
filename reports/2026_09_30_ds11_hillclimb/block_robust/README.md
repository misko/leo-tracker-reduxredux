# Time-block robustness protocol (prepared; no corpus results)

This family tests an intermediate contamination model between the original IID
Student-t likelihood and one shared-scale multivariate Student-t density for an
entire track.  The three frozen variants use block widths of 1, 3, and 10
seconds.  All retain df=4, the normalized 100 Hz spherical base scale, the
original catalogue mixture, and exactly one profiled constant CFO per track and
catalogue candidate.  There are no slopes, mean corrections, or extra fitted
parameters.

For each track, take the first training timestamp as the anchor.  Width `w`
defines half-open bins `[anchor + k*w, anchor + (k+1)*w)`.  Empty bins contribute
nothing.  All training observations in an occupied bin form one spherical
multivariate t4 vector and share that bin's latent scale; occupied bins have
independent scales.  Held observations do not select the anchor, populate bins,
or affect the training objective.  The product of block densities includes the
dimension-specific multivariate-t normalizers.

The constant CFO is profiled against the product of all block densities plus
the original Gaussian prior with variance `1e12 Hz^2`.  Batched quantile-seeded
IRLS fixed points propose basins, stationary roots are then bracketed, and the
lowest located positive-curvature stationary loss is retained.  Position and
timing gradients use the envelope theorem at that profiled CFO.

No screen or real-data fit has been launched.  If authorized, the existing
hill-climb harness should run variants `block1,block3,block10` under family
`block_robust`, preserving its 90-second per-process cap and append-only run
receipts.
