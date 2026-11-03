# Frame-phase prediction beyond retained training support

This distinct feasibility test asks whether a physical-source/RF phase clock can
predict later detections without a simultaneous retained anchor. It does not
infer non-detection from a missing track, fit positions, or authenticate labels.
Use only existing family2 DS10 frame exports16/17. Pool fragments and receivers
by inferred NORAD and exact RF. Remove candidates owned by multiple such groups
and deduplicate candidate IDs within a group. Report all exclusions.

Within each group, set a time boundary at two thirds of its original training
time span. Fit one robust quadratic clock to original training points at or
before the boundary; evaluate only original held points later than the boundary.
Require at least6 fitting points,3 held points, and3 distinct fitting times.
Unwrap fitting phases only, using period1333.333...us. Use soft-L1 scale0.1us,
at most300 evaluations and optimality<1e-4. Keep failures. No orbit correction,
held phase, station coordinates or geographic error enters fitting or selection.

Calibrate the timing tolerance on donor16 as the median across eligible groups
of their95th-percentile held absolute circular error. Freeze it before loading
donor17. On donor17 report per-group hit fractions and their median, phase-shift
controls1/7,2/7,3/7 of a frame, and actual extrapolation time gaps. Feasibility
requires at least10 qualified groups in each recording, at least90% qualification
among eligible groups in both, tolerance less than1% of a frame, validation
median hit fraction>=80%, and each shifted-control median hit fraction<=5%.
These are correlated observations with inferred identities, not independent
trials or calibrated physical missed-detection probabilities. A pass licenses
only a later raw-opportunity census; it does not license DS11 position changes.
Do not alter thresholds or the split after inspecting the result. No new RF.
