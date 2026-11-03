# Hypothetical height robustness diagnostic

This is distinct from adopting a calibrated antenna height. No height is
estimated, chosen, or promoted. The uncertain Compass report remains unresolved.
Fix scenarios at -50, 0, +50 metres WGS84 ellipsoidal height; these are stress
points, not confidence limits or alternative interpretations of the phone.
Reuse diagnostic scans 0 and 16, their causal candidate banks, full mixtures,
training masks, CFO treatment, and original east/north/time bounds. Fit from
the original qualified IID seed and zero in every scenario. Select within
each scenario by qualified training score only. Never rank height scenarios.

Report displacement relative to the refitted zero-height scenario, timing
shift and changed training MAP candidate indices. Do not load the geographic
error evaluator, compute distance to truth, or claim accuracy improvement.
This tests whether height uncertainty causes material position/association
instability beyond the previous local linear projection. Failure to qualify
is retained. Qualification: optimizer success, finite score/coordinates,
at least .001 from bounds, max gradient <= .01 and independent central
finite-difference discrepancy <= .02. Limits: 100 iterations, 160 function
evaluations, 90 seconds per child, at most three single-thread workers.

No new RF, production defaults, capture metadata, or golden fixtures change.
