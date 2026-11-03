# DS11 fixed-position predictive bridge for joint revision uncertainty

At the original scan0/16 IID training endpoints, evaluate all three previously
frozen joint-orbit variants: zero, actual revision direction, matched linear
direction. Use the existing groups, all common candidate hypotheses, singleton
supports and DS7/DS8-learned coefficient priors without modification.

For each candidate/coefficient hypothesis profile the track CFO on training
rows only. Use that fixed CFO to score held observations. Sum track scores
within a source before marginalizing candidate and coefficient; conditional
held score is joint minus training log normalizer. This is a normalized held
predictive mixture conditional on plug-in CFO estimates, not a fully integrated
CFO model. Require training-score replay within1e-6 of the numerical benchmark.

Report per-source and total held gains, retaining every source and observation.
Advance to bounded geographic fitting only if the actual-revision variant beats
BOTH zero and linear total held scores in BOTH scans. Do not pick a coefficient,
candidate or source subset using held observations. No position fits or
reference errors; one single-thread run under90seconds. Preserve failures.
