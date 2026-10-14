# Relative-phase cost and derivative audit

The zero-fit audit completed in 40.322 seconds. It reconstructed only training
inputs from the sealed DS21-039 phase experiment, verified its original source
and parent authority before and after evaluation, and performed no optimizer,
held projection, or reference lookup.

At the identical original all-band training winner, six evaluations per scorer
were alternated in order to reduce host-load drift. Median evaluation time was
31.555 ms for receive-epoch and 113.199 ms for relative-phase: **3.587 times
slower** for the new Python implementation. This is a measured comparison on
the concurrently loaded host, not a universal speed claim.

Central differences at two prespecified scales checked east, north, fitted c,
common timing, the first relative timing coordinate, and the first group offset.
Checks covered the original training winner and both rejected phase endpoints.
The maximum scaled analytic/finite-difference discrepancy across these probes
was 8.608e-6; endpoint maxima were 1.411e-6 and 8.764e-7. This checks those
coordinates locally, not every gradient component or all visibility boundaries.
No gross discrepancy appeared in the sampled derivatives.

Both previous combined-band fits exhausted 20 seconds after only 164/167
evaluations. The cost finding makes implementation overhead a concrete possible
contributor to nonconvergence. It does not prove that more iterations recover
the correct position or that the relative-phase mechanism is physically true.

Next: an isolated native implementation of the same phase predictions and
derivatives, checked against the frozen Python oracle on synthetic and actual
saved states. Only after numerical equivalence and measured improvement should
a separately frozen, matched-budget fitting control run. Keep all earlier
nonconverged results and their receipts unchanged.

Evidence namespace: `local/phase-cost-audit-v1` in this report directory.
Result SHA-256: `fbd6acca2574a348ba9c575acd42b4191eb11dcae122aa0e41d5d1b1a17f7f80`.
The audit recipe and five owned tests are committed separately from the report.
