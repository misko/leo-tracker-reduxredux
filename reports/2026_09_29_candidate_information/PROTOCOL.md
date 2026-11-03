# Candidate-slope position-information diagnostic

Frozen before execution. Use the 1,847 supported target cases from the completed
candidate cross-RX transfer experiment, retaining all nine panels separately.
At the inherited fitted location and per-record timing, differentiate the frozen
candidate Doppler predictions in east/north (km) and time (seconds). Use central
steps 0.001 km and 0.0001 s, then halve both; record timing-grid proximity.
Verify every case's prediction reproduces its exported residual and masks/times.

Center each track's training derivative columns to remove its constant. Weight
by frozen candidate weight times signal responsibility and a common precision
5/(7*100^2). This is optimistic complete-data linearized information conditional
on selected assignments, not observed mixture curvature or calibrated uncertainty.

Compare: (1) position and eight recording times only; (2) add one shared residual
slope per scan/candidate-number/exact-RF cell, shared across RX; (3) one slope per
track. All three use exactly the same supported subset. Center slope time columns
within each track. Profile slopes analytically, then the eight timing columns
using a relative-eigenvalue 1e-10 pseudoinverse. Compute generalized retained
position-information eigenvalues relative to the no-slope baseline. Report ranks,
matrices and finite-difference sensitivity; no confidence ellipses or accuracy
claims. No position, identity, timing or slope optimization is performed.

Use existing numerical state banks only; verify their declared artifact hashes.
Read one recording bank at a time, one numerical thread, 120-second total run cap.
No new orbit propagation, RF collection, production edits or geographic refits.
