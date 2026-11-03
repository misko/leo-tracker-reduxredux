# Approximate independently calibrated height pilot

Use the operator's newly confirmed 10 ft antenna height above ground plus terrain
at the unchanged stored antenna coordinates. Use GEOID18 to form25.142628571m
ellipsoidal height, explicitly approximating the NAD83/WGS84 frame difference.
This limitation is frozen in evidence.json before fitting; no claim of exact
datum conversion. The invalid phone elevation and visually estimated300ft are
not used. Do not fit height, tune it to geographic error, or move reference truth.

Reuse diagnostic scans0 and16, original causal banks and full candidate mixtures.
For both zero-height control and fixed-height arm fit original IID and center
seeds with the existing bounded height_robustness implementation. Retain its
optimizer/gradient/boundary qualification gates. Eight jobs, each<=90s, <=3
single-thread workers. Select within each scan/arm by qualified training score;
seal all selections before loading the original geographic evaluator.

Report both scans, all failures, and paired horizontal errors. Extend to broader
confirmation only if both calibrated estimates qualify and improve over their
refitted controls. Passing this screen alone does not achieve the DS11 goal.
Failing does not establish the physical antenna estimate is wrong. No new RF,
offline orbit data, production-default changes or golden-fixture edits.
