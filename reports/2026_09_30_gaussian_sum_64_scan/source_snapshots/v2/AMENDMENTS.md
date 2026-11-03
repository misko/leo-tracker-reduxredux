# Experiment amendments

## v1: frozen first smoke

The first regional DS9-F001 Gaussian-sum update retained more than
0.99999999999999 of the posterior mass, but the next factor failed when tiny
retained lineages queried outside four-knot orbit interpolation support. The
largest of these tiny lineages had probability 6.40e-13; the eight substantive
lineages had probabilities from 0.00238 to 0.281. The scalar implementation took
22.96 seconds for the first update. The greedy control reached its 85-second
internal budget after 12 factors. Neither is a completed single-scan estimate.
The prior-only control completed. Original receipts and source snapshots remain.

## v2: engineering retry, recorded before scoring

Set the posterior child weight floor to 1e-12, while preserving the 16-component
cap and explicit accounting of *all* discarded probability. Every child's
likelihood is still scored before pruning, and the 1% promotion threshold is
unchanged. This avoids maintaining negligible lineages outside interpolation
support without clipping or extrapolating their states. The proposed change was
independently reviewed before the retry; it uses no reference-coordinate score.

Vectorize orbit prediction while testing agreement against scalar interpolation
and finite differences. Drop exactly-zero floating-point posterior weights before
constructing positive-weight Gaussian components. These are numerical changes;
physical priors, observations, geometric support, covariance assumptions, resource
limits, and the selected panel are unchanged. Preserve v1 in the failure accounting
and write v2 to a separate output directory. Do not pool their scientific results.
