# Defer covariance changes; prioritize the full position comparison

All twelve consumed members completed with exact predecessor pair identity and
the required saved-objective, pair-score and shared-mass parity. No fitting or
position evaluation occurred. The diagnostic took 149.615340 seconds of summed
member runtime, or 358.894162 seconds including the preserved preceding audits.

On the same eligible fractional mass, the fitted-c raw product per mass was
0.088628 and the opposite-block-centered product was 0.505339. For c=0 the values
were 0.462366 and 0.388800. Eligible mass coverage exceeded 99.7% in both arms,
but this did not establish adequate information in the training block.

The [saved-moment root-cause analysis](SAVED_MOMENT_RCA.md) explains the inflated
fitted-c result: 91.68% of the centered total is the exact block-mean disagreement
term. Tiny satellite responsibility tails in one block were normalized into
large means and applied to the other block. The original result and every
member remain visible; the posthoc concentration calculation does not filter
the primary experiment.

This rules out treating this diagnostic as evidence for a covariance correction.
It does not rule out correlated measurement noise. Do not select rho or change
the production likelihood from these results. Prioritize the full 193-member
phase-versus-timestamp position comparison after the separately frozen ordinary
model reconstruction check. Any further overlap-aware residual diagnostic needs
its own predeclared protocol.

Parent review passed ten core/runner tests and four reporting tests. Reports
verified frozen source/input bindings and all result/claim hashes. The archive
preserves all 24 receipts with readback verification. Both visualizations were
inspected. Production remains unchanged; the latest full-cohort fitted-c mean
is still 1.254810 km and the 0.4 km goal remains unmet.
