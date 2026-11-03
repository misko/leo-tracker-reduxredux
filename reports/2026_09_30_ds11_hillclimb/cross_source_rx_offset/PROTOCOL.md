# Conditional cross-source receiver-offset diagnostic

Use the frozen same-source CFO audit exports only. Orient all native frequency
differences RX1 minus RX0 and wrap modulo the native pilot alias period.
Require at least six shared training visits in each target receiver pair.
Donors must be from the same scan and exact RF, a different selected NORAD,
and share at least six of the target pair's common visits. Aggregate duplicate
donor pairs by NORAD using a circular medoid, then give each donor NORAD one
vote. At least three donor identities are required. Predict the target offset
with the donor circular medoid; compare absolute wrapped error against a zero
offset. Retain all unsupported cases and all errors, without threshold tuning.

This is a descriptive leave-source comparison of training-derived CFOs, not
held-observation validation: the original position endpoint and conditional
identities already used target observations. No position reference, new orbit,
IQ read, held observations or position fits are permitted. A positive result
would support examining a shared receiver-path constraint, not promote one.
