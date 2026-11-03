# Causal orbit-revision shape diagnostic

This diagnostic uses the existing DS7–DS9 older-minus-current predicted Doppler
curves and training residual exports. It adds no orbit propagation, IQ reads,
position fits, geographic reference use, or offline orbit replacement.
Input digests, identities, masks and residual agreement are checked. Only
training samples enter the statistics; complete arrays are read for integrity
checks. Results are descriptive, not a calibrated orbit covariance.

After removing each curve's mean, the audit measures the fraction of revision
energy explained by a linear time trend. It also compares revision RMS with
median-absolute centered residual scale. Track quantities are pooled by median
within dataset/session/NORAD/RF occasions before dataset summaries, limiting
duplicate receiver/track representation.

| Dataset | Source occasions | Nonzero revisions | Median linear fraction | Revision size/residual scale Spearman |
|---|---:|---:|---:|---:|
| DS7 |843|836|0.931|0.083|
| DS8 |818|789|0.953|0.077|
| DS9 |851|504|0.962|0.093|

Only 33%, 32% and 37% of nonzero source directions, respectively, have at least
99% linear energy. Revision curves therefore contain some nonlinear shape,
but their magnitude has little rank association with the observed residual
scale. This weakens a simple revision-size-based noise weighting proposal.
It does not rule out a properly calibrated source-shared orbit uncertainty
model, and the earlier rejection of a universal mean correction is not a test
of such a covariance model. Unconstrained trend corrections remain hazardous
because those same trends carry position information.

The runner completed in approximately 0.96 seconds. One component test covers
linear, quadratic and constant direction behavior. `outcome.json` binds source
and test hashes and retains all row and source summaries. No DS11 model is
promoted and no position improvement is claimed.
