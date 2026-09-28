# Numerical completion after the original pooled attempts

The initial DS7 augmented arm reports relative-loss convergence but its selected
maximum absolute gradient is 0.019526, above the frozen 0.01 qualification
threshold. All three starts fail that screen. The control qualifies. This was
observed before new geographic scoring. Do not relax the threshold or replace
the original result, starts, receipts or qualification.

This is an explicitly additional numerical follow-up, outside the original
no-retry trial. Apply one deterministic polishing attempt to **each** completed,
successful interior selected arm for DS7/DS8/DS9, including already-qualified
controls. Do not condition polishing on geographic or held improvement. Start
only at the previously selected point; introduce no new search start, parameter,
prior, bound, likelihood, observation, partition or candidate. Failed/missing or
boundary-selected arms remain ineligible and retain their original status.

Use the same L-BFGS-B objective and bounds with maxiter40, maxfun60, ftol1e-13,
gtol1e-6, maxls30. Cap each attempt at 90 seconds/4 GiB, one numerical thread,
nice19, with no retry. Keep original and refined outputs separately. A refined
point must succeed, remain interior, pass the original gradient <=0.01 screen,
and not reduce training score by more than 1e-7 to qualify. Always report its
displacement from the original point and original qualification. Missing or
failed refinement does not erase the original fit or silently qualify it.

Seal outputs before geographic scoring. Use a qualified refined augmented
point for the previously specified curvature audit; otherwise use the original
only if it independently qualified. Report original and refined geographic
and held comparisons as different execution stages. This extra computation
is not part of the original 300-second per-arm budget and must be itemized.
