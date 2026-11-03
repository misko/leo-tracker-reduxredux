# Internal position/velocity consistency of two DS11 candidate banks

Stored satellite velocities agree closely with central finite differences of
the stored positions in scans0 and16. The check uses the zero timing-grid point
and the grid point nearest each original IID timing estimate, a0.5second
central-difference span, and every retained candidate/observation state at
those grid points.

| Scan | Timing points | Bank states per timing point | Median velocity discrepancy | Maximum discrepancy |
|---|---|---:|---:|---:|
|0|0,0.25seconds|37820|0.00859m/s|0.01508m/s|
|16|-1,0seconds|39272|0.00896m/s|0.01721m/s|

At11.2GHz, even the maximum vector discrepancy bounds the corresponding
line-of-sight Doppler difference below0.643Hz in these checks. This is much
smaller than the observed hundred-Hz residual structure. The stored velocity
versus finite-position-difference discrepancy therefore does not explain that
structure at the tested grid points.

This is an internal consistency check, not validation of absolute orbit
accuracy, inertial/terrestrial orientation, observation timing, satellite
identity, or geographic position. A coherent error in both state arrays would
remain. Counts include repeated satellite states across exported tracks and
must not be described as unique satellites.

The bounded runner exits0, verifies inherited input/source hashes, and retains
the full quantiles and source bindings in [outcome.json](outcome.json). No
position fit, geographic reference, IQ access or orbit-provider request occurs.
