# Conditional element-age residual audit

This read-only diagnostic asks whether residual scale at the frozen original-IID
endpoint is associated with the age of the exact orbital element used by the
candidate bank.  It performs no position fit and reads no reference error.

The join reconstructs each bank's actual newest-per-object rule from its two
pinned provider snapshots.  For every training-selected candidate it chooses
the greatest `(element epoch, collection time, snapshot digest)` tuple, then
computes age from that element epoch to capture start.  Candidate catalogue
rows are mapped to physical NORAD numbers through the digest-bound DS11 identity
sidecar.  Repeated tracks and receiver views are collapsed to one
`(scan, NORAD, exact RF)` source occasion before association statistics are
computed.

There is a weak, monotone positive relationship.  Across 1,295 source occasions,
element age ranges from 0.345 to 3.047 days.  Spearman correlations are 0.201
for training median absolute residual, 0.195 for held median absolute residual,
0.176 for training RMS, and 0.180 for held RMS.  After subtracting each scan's
mean rank, the corresponding correlations remain 0.193, 0.187, 0.169, and
0.169.  Aggregating repeated occasions to 692 unique NORAD numbers gives similar
correlations of 0.186–0.220.

The freshest age quartile has median training/held absolute residuals of
80.24/82.85 Hz and training/held RMS of 139.29/144.42 Hz.  The oldest quartile
has 122.61/142.50 Hz and 256.47/265.37 Hz.  All four residual summaries increase
monotonically across the four age quartiles.

This is evidence that element age can mark conditional model uncertainty, but
it does not establish orbit error as the cause.  Candidate identities are
training-selected and unverified; orbit age can correlate with satellite cohort,
geometry, signal quality, RF occupancy, or element-update behavior.  Tracks
share scans and physical sources, and P-values therefore do not represent an
independent-sample causal test.  No age cutoff, fitted scale law, correction,
or geographic result is selected here.

The next admissible step, if pursued, is a small predeclared sensitivity model
whose scale depends monotonically on exact element age, with the original model
as its nested control.  It should keep the candidate mixture and source
denominator unchanged, test training-only calibration against held residuals,
and require a separately frozen geographic screen.  These data do not justify
an orbit displacement nuisance or an age-based candidate correction.

Machine-readable aggregates and provenance are in `summary.json`.

