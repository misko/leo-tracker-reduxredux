# Free source drift removes substantial local position information

At the eight original IID training endpoints, projecting out a shared linear
drift per repeated conditional satellite leaves median generalized horizontal
information eigenvalues0.275 and0.559 relative to baseline. Projecting out one
drift per receiver leaves0.751 and0.993. Thus free source drift overlaps much
more strongly with the Doppler directions that identify position.

| Free nuisance model | Median lower retained-information eigenvalue | Median upper eigenvalue |
|---|---:|---:|
|One slope per receiver|0.751|0.993|
|One slope per repeated confident NORAD|0.275|0.559|

The audit uses489 tracks across eight scans. Source slopes cover425 tracks,
with11–18 repeated conditional identities per scan. Training-MAP candidate
Jacobians are computed in E/N/timing coordinates. Track constants are removed
by within-track centering, and timing is profiled in both baseline and modified
horizontal information. SVD removes the nuisance span without a tuned ridge.
All observation weights use the same expected Student-t information factor,
which cancels in the reported ratios.

These are conditional local design ratios, not posterior covariance estimates,
observed robust curvature, calibrated confidence bounds or predicted position
errors. Candidate identities remain uncertain. Free drift is an infinite-prior-
variance limit; finite calibrated source covariance could retain more position
information. The audit therefore argues against unrestricted residual-slope
subtraction, not against every correlated-error model. Earlier geographic
failures remain the relevant evidence about tested correction policies.

Two component tests pass for confounded/orthogonal nuisance directions, duplicate
columns, scaling invariance, empty nuisances and projection orthogonality.
The initial attempt failed before scan processing because it incorrectly
expected the identity sidecar hash in a flattened source map. The exact initial
script and failure record are preserved. The corrected version verifies the
sidecar through the nested binding in the already-verified CFO audit.
The completed single-thread run exits0 in2.90seconds under a90second cap.
An independent2x2 characteristic-polynomial calculation verifies all reported
generalized eigenvalues and summary medians; it does not replay Jacobians.
No held observations, reference error, position fit, IQ or orbit update is used.
