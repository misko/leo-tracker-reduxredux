# Shared position with separate receiver timings

Freeze all 18 consecutive DS7/DS8/DS9 four/eight panels from the published
consecutive-panels plan. Change only timing parameterization: one common E/N
position and two timings per recording, ordered all RX0 then all RX1. Keep
the zero-decay Student-t4/100 Hz shared-track-scale likelihood, weak offset
prior, candidate banks and training/held partitions. Partition each recording
exhaustively by software receiver using the previously tested filter.

Four starts per panel: generic E/N (0,0), (3,-3), (-3,3) km with zero timings,
and the prior both-RX selected position with its timings duplicated. This
nested start is training-derived and declared for every panel. No geographic
or held result chooses starts. Bounds E/N +/-12 km, timings +/-5 s;
L-BFGS-B maxiter140/maxfun200/ftol1e-14/gtol1e-8/maxls30. Qualify successful,
interior fits with gradient infinity norm <=0.01. Select greatest qualified
training score; preserve all failures, with no retries or gate changes.

At the nested start, verify the split objective reproduces the unsplit
training and held scores within 1e-7, every held row, and the tied timing
gradient (sum of receiver gradients) within 1e-7. Verify exhaustive disjoint
track membership. At selected fits replay training score within 1e-7;
audit E/N centered differences at 0.001/0.0005 km, tolerance0.002. Audit
every timing at 0.0000625/0.00003125 s: both intervals must avoid a 0.25 s
bank node, each analytic discrepancy and mutual finite-difference discrepancy
must be <0.002. Record failures explicitly; no alternate-step fallback.

Compare geography against the exposed unsurveyed reference only after
training selection. Report all panel errors, medians by dataset and size,
sub-km counts, matched held changes vs one-timing baseline, timing differences,
and first-four matched held changes for nested eight vs four. Separate the
three-generic-start result from the four-start selected result where possible
to expose optimizer-initialization effects. No new RF or provider access.

One scientific worker, BLAS1/nice19, 4 GiB address-space cap, 180 s per-process
cap and at least 5 GiB available memory. All process receipts and source/input
hashes retained. Existing completed output paths may not be overwritten.
