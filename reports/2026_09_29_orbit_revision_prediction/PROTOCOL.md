# Fixed-position causal orbit-revision prediction

Freeze before execution. All 3,983 target residual cases and all nine panels from
the revision-support inventory. Reconstruct the baseline element choice from each
bank manifest's pinned provider snapshots: newest element epoch per object, then
collection time and digest, matching the baseline exporter. Propagate each selected
candidate at the two existing timing-grid nodes bracketing its inherited fitted
recording time. Reproduce stored positions within 1e-8 km, velocities within
1e-10 km/s and fitted frequency within 1e-6 Hz before scoring a revision.

Keep candidate, location, recording time, observation times and masks unchanged.
Replace only elements with the inventoried six-hour and 24-hour older Space-Track
records. Primary comparison is 24 hours; six hours is a limited-support control.
Use the same two-node interpolation as baseline, not a different propagator or
continuous-time evaluation. Recenter each residual on its own training mean;
score median absolute held residual. Record frequency revision training slope,
training-centered RMS, same-element identity, missing support and propagation
failures. Missing/failed revisions retain baseline error in all-case accounting.
Report supported and changed-element subsets separately; never choose by held
or geographic error. No position fit or orbit correction is estimated.

GP disagreement measures sensitivity, not calibrated uncertainty or independent
truth. Conditional candidate labels and fitted locations remain unverified.
Use pinned archive reader/parser/propagator, read-only access, one numerical
thread, one recording bank at a time and a 120-second run cap. No new RF or download.
