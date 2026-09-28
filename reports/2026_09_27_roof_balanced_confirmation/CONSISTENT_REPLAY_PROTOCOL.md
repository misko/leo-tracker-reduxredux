# Paired fixed-grid calibration consistency diagnostic

This is development evidence on the four already-unblinded second-cohort roof recordings. It is not prospective validation and cannot establish surveyed accuracy or a general tracking-resolution improvement.

Compare the original reception calibration with the separately saved robust-direction-consistent calibration. Use each prior's exact existing 289-point local grid, with no recentering, added points, orientation choice, regularization tuning, or location-dependent model selection. Sacramento and Reno retain independent candidate associations; neither may use the other's fitted candidates or locations.

Compute each point's original zero-timing robust frequency shortlist once and apply both reception models to it. Keep source-topology filtering, occupied-second track weights, frequency parameters, track observations, nuisance features, and likelihood normalization unchanged. Each reception model uses its own calibration-only fitted ratio variance. The initial comparison uses the original reception contributions, not the reciprocal-pair sensitivity.

Before accepting a result, verify the old reception model matches the frozen original numerically, and reproduce every original grid point's saved objective scores within absolute tolerance 1e-7. Require old/new frequency scores to agree within 1e-12. Reject missing, duplicate, nonfinite, or unexpected grid points. Preserve source artifacts; refuse output overwrite and bind calibration, source grid, input, protocol, and implementation hashes.

Report distances only after all four paired runs pass these gates. Select each model's minimum joint score with deterministic east/north tie-breaking. Include Doppler-only selection as the common control, all eight scan/prior rows, separate prior means, improve/worsen/tie counts, and boundary flags. Do not attribute a difference in distance to a calibrated confidence interval or to improved physical resolution. The operator-supplied roof position is a reference, not surveyed ground truth.

The known remaining model limitation is unchanged: calibration uses weighted-mean candidate directions, whereas geographic scoring marginalizes candidate likelihoods. This experiment isolates association-feature consistency; it does not also fix that nonlinear modeling mismatch.
