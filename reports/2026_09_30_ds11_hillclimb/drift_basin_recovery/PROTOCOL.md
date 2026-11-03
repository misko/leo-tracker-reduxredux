# Return corrected-model basins to the unchanged baseline

This is an optimizer diagnostic, not advancement of the failed drift policy.
Use every qualified endpoint from the frozen eight-scan drift geographic test
as a possible initializer for the original, uncorrected IID objective. Never
use geographic error to select seeds. Iterate previous job order; within each
scan retain a seed unless it is within1m EN and1ms timing of a retained seed.
Bind the previous plan, selection and all source hashes. Keep original bounds,
likelihood, causal banks, timestamps, masks, observations and qualification.

Optimize each retained seed once with the existing L-BFGS-B settings,90second
process cap, at most three single-thread workers. Include the already-qualified
original endpoint in final selection; replace it only with a qualified result
whose original training score is greater by more than1e-6 nats. Keep all
failures, and do not retry. Seal all eight training selections before scoring
positions. Report score gains and any geographic effects, including worsening.
No new measurement, orbit, correction model, or cross-scan pooling is allowed.
A null result closes this particular basin-recovery path without more starts.
