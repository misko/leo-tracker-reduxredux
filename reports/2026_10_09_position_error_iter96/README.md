# Curvature-aware qualification preparation

Pure solver and synthetic tests only; parent owns the separate single-case freeze
and runner. No real recording is evaluated by this preparation.

Keep the original feasible vector, existing physical constraints and independent
0.001 stationarity gate. Choose the largest scaled projected KKT component and
estimate positive scalar curvature from gradient differences at scaled step1e-5,
using central probes when feasible and a feasible one-sided probe otherwise.
Try raw-gradient Newton steps with fixed damping1,0.5,0.25. Retain every probe,
candidate, infeasibility and error; cap ten rounds and100 objective evaluations.

Every accepted state must stay below **initial objective plus128ULP of that initial
objective**, preventing cumulative tolerance drift. Outside numerical equivalence,
objective has priority; inside it, prefer lower full independent KKT then objective.
Advance only with strict full-KKT improvement. Finite-precision cost equivalence
does not weaken the qualification gate or permit a material score increase.

This is a bounded diagnostic for tiny local refinement, not a general optimizer,
position correction or global-minimum claim. No reference coordinate/error enters
the algorithm. Frozen93/94 and production remain unchanged.
