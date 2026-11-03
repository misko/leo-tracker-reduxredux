# Contemporaneous other-candidate residual transfer

Freeze before execution. Reuse all nine eight-scan target exports from
2026_09_29_donor_residual_transfer; no new fitting of position or association.
The candidate identities and residuals remain conditional on the existing
training-fitted model. This is a predictive diagnostic, not physical calibration.

For each target, exclude its track and candidate number from every donor.
Require same scan, exact RF, and at least 50% overlap of the target training-time
span. Refit each donor slope from its training points inside the target training
span, requiring five points spanning five seconds. Take a median within each
candidate number, then a median over at least three other distinct numbers.
Compare same-RX donors with opposite-RX donors and zero slope. Report separate
coverage and a matched subset with both donor predictors. No clipping or tuning.
Every arm uses the target's training-only residual/time means; score median
absolute held residual in canonical 11.2-GHz Hz. Noneligible cases use zero slope
for full-population accounting. Also report a target's own training slope as a
diagnostic comparator, not an independent receiver correction.

Report case and scan counts, per-dataset and per-panel paired gains, all failures,
and input hashes. Case counts are dependent, not independent replicates. Training
masks are inherited interleaved masks, not causal forecasting. No geographic
promotion solely from conditional residual gains. No new RF or production edits.
