# Frozen bounded eight-versus-sixteen fitting pilot

Units: DS9-B01-S1, DS10-B01-S1, DS11-B01-S1, selected by metadata order before denser fitting. Run eight then sixteen points for each unit, sequentially under the shared lock. Both arms start from the identical original three-start winner with all nuisance coordinates retained; neither inherits the other arm's output. This tests local evidence sensitivity, not new acquisition or the one-start search policy.

Use the unchanged `fit_localization_fast`, 64 iterations, Student-t4 model, original priors, uniform 250 km Sacramento disk and fixed 30.48 m MSL height. Build ports with the verified nested selector. The total budget is 90 seconds including the original cold launch and each arm's extra launch. Subtract original elapsed work, retain a five-second internal margin, and reject admission if less than ten seconds remain. Audit separately in a fresh process capped at 90 seconds. No retries or post-result tolerance changes.

The numerical audit reconstructs nested ports independently and retains the original objective/assignment, monotonicity, support, finite-difference gradient and stationarity checks. Additional checks bind the point limit, selected IDs, parent receipt and initial state; the eight-point control must reproduce the parent's starting objective. Only accepted outputs receive reference errors. Process, input or numerical failures remain in the planned denominators with their receipts/logs preserved.

Report matched acceptance, geographic error and charged/incremental costs. Raw objective values across observation dimensions are not comparable. No improvement claim follows merely from higher point count or successful convergence. These three exposed singles do not establish broad generalization, uncertainty calibration or cold runtime. Pair/quad and thirty-two-point extensions require inspecting the complete pilot first.

Prerequisite gates are the sealed `denser-track-port-check-v1.json` and `denser-scan-objective-check-v1.json`. Sources and inputs are reverified before and after each process. Existing frozen helpers and original outcomes remain unchanged.
