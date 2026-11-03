# Frame evolution feasibility audit

Use DS10 family2 donors16/17, already selected by hardware metadata, and their
availability-correct calibration geometry. No DS11 reference or observations
enter this audit. Retain every donor track with an inferred training Doppler
source assignment; these are not authenticated satellite identities.

Extract fractional frame epochs from public raw metadata and exact device
counter differences. Reduce integer counter differences modulo the750Hz frame
period before adding fractions. Compare phase evolution with simultaneous
orbital range/c from the original causal bank, linearly transported from the
support center to the measured frame epoch using bank velocity. This ignores
light-time and clock physics and is only a feasibility approximation, not a
ranging model ready for position fitting.

For each track use only training visits to unwrap phase residuals and fit a
constant plus linear clock term. Compare range coefficient+1 with0 (clock-only)
and-1 (reversed curvature). The finite nuisance fit uses robust soft-L1 loss
with fixed0.1 microsecond scale; no DS11 tuning. Evaluate held visits by circular
residual to each training fit. Preserve large phase jumps, insufficient support,
nonconvergence and all track-level results. Report results by recording; repeated
tracks or receiver copies are not independent experiments. Stop short of a
position model unless orbital curvature yields reproducible held-data benefit.

Read metadata only, no RF collection or IQ reprocessing. Export children<=90s,
at most three single-thread workers. Keep original source bindings immutable.
