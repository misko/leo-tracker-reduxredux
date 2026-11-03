# Raw-detection conditional-geometry pilot

Freeze `raw_visibility/fit.json` after its independent donor17 validation pass.
Use the existing family2 DS11 pilot records original0 and additional1. Compare
unchanged Doppler and the signed raw-match event model at identical original IID
initializations. Keep causal orbit banks, original candidates, masks and CFO
profiling. No DS11 error-based tuning or hard timing/source identity constraints.

For each physical-source assignment and candidate-ownership alternative, collect
its owned training detections by window. Select the same SHA256-minimum raw
anchor as in calibration. Use its observed opposite-RX epoch-match event and
candidate line of sight in the calibrated conditional Bernoulli model. Subtract
the receiver-only event log likelihood at that anchor. Average this log ratio
over the source's nonempty training windows: one effective composite observation
per source limits serial duplication. Exactly sum candidate/source assignments
and ownership alternatives. This composite geometry factor is not a complete
physical visibility, clutter or temporal generative model.

Zero strength must match Doppler score, gradient and expected source count.
Test subset anchors, duplicates, empty subsets, scalar enumeration and numerical
derivatives. Each fit must finish<=90seconds, at most three single-thread workers.
Qualify with optimizer success, interior bound margin>=.001, gradient<=.01 and
finite-difference discrepancy<=.02. Seal every fit before geographic scoring.
Both timing-geometry fits must reduce both original and refitted Doppler errors
by>=5% to advance beyond this pilot. Preserve all failures; no broader accuracy
claim follows from two records or from earlier calibration scores.
