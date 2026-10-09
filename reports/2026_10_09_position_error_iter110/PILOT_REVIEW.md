# Proposed conditional pilot progression rule

Freeze the literal random seed, sampling algorithm and sorted membership authority
before selecting four whole recordings from each of DS16, DS17 and DS18. This is
a 12-recording consumed-data mechanism screen, not unseen validation. Selection
must use labels only: no reference errors, readiness, categorical confidence or
failure outcomes. Record all selected members including input failures.

Use global rho=0 versus rho=0.5, unchanged 125 Hz likelihood width, matched bank,
observations, priors and starts. Both arms begin from the same archived fitted-B7
start, with static c and the final two RF clock coefficients locked in c=0.
Report the archived endpoints separately to distinguish refitting from changing
the likelihood. No cross-rho score winner or reference-guided fallback is allowed.
Reuse the unchanged independent KKT threshold 0.001 and physical bounds.

The proposed progression rule to a separately frozen full148 study requires all
of the following, computed after every selected member has a terminal receipt:

- All 48 fit attempts (12 recordings × two c arms × two rho values) complete
  and independently qualify; no failed candidate is hidden through fallback.
- Fitted-c mean position error improves by at least 5% relative to rho=0,
  and its median does not worsen.
- Neither arm has a paired position regression greater than 1 km or an increased
  worst error; c=0 mean error is no more than 5% worse than its control.
- Every fit remains within the identical absolute 90-second budget, with a
  maximum of 600 optimizer iterations. Publish actual fit time, objective
  evaluations, iterations, reconstruction time separately and measured peak memory.

Sequence likelihood, signal RMS and categorical confidence are descriptive only;
they cannot satisfy or override these position and cost gates. Publish every paired
counterexample, terminal qualification and fallback result even if a gate fails.
Full148 progression is authorization to investigate, not proof of generalization
or deployment readiness. With four members per dataset, these thresholds are a
coarse screening convention, not statistically powered population guarantees.

The control starts at an already qualified B7 optimum, while the changed model
must move. Consequently a candidate/control runtime ratio is not an embedded
feasibility criterion and is not a progression gate. The absolute budget is a
research bound, not evidence of fast embedded operation. The 600 limit means
optimizer iterations, not an objective-evaluation cap; actual evaluations remain
reportable even when they exceed 600. Do not claim measured optimizer iterations
if the backend exposes only evaluations; mark unavailable fields explicitly.

No recording job, sampling draw or rho tuning was performed for this review.
