# Paired position/timing/slope refits on eight DS7 records

Fit all first eight chronological records from the sealed full88 request.
Compare the original zero-slope model with one shared native Hz/s slope per
recording. Both arms jointly fit east/north position and recording timing.
Keep likelihood, full candidate mixtures, offset profiling, track membership,
visit masks and native/canonical scaling unchanged. No spatial penalty is added.

Both arms use identical position/timing starting points: the previously sealed
independent estimate, with timing perturbations 0, -0.25 and +0.25 seconds,
clipped to the original [-5,5] timing bounds. The augmented arm starts slope at
zero in all three cases, bounded to [-20,20] native Hz/s. Position bounds remain
[-12,12] km per axis. This is a paired local warm-start comparison, not a new
global search. Historical baseline results are retained separately.

Use L-BFGS-B, analytic/envelope gradients (prediction derivatives numerically
checked previously), maxiter100, maxfun180, ftol1e-10, gtol1e-5, maxls30.
Persist every start before selecting maximum training score among successful
starts. Do not choose a different solution because of held score, known roof
error, a boundary or the gradient check. If no start succeeds, retain failure.
Qualification requires selected-start success, no parameter within 1e-3 of its
bound, and maximum absolute fitted-coordinate score gradient <=0.01. Report
the gradient, boundaries and all returned estimates even when unqualified.

Replay the historical independent training and held scores before fitting.
After each arm, preserve its full-mixture held score, track contributions,
candidate weights, estimate and optimizer receipts. A per-record timeout must
not erase an already completed arm. All eight records remain in denominators;
failures are not retried or replaced. Report paired qualified and all returned
results separately. Primary comparison is geographic error for individual
records; secondary measures are median paired change, below-1km count, held
gain per observation and sensitivity of selected solutions across starts.

Seal all fit outputs before a separate coordinator reads the unchanged DS7
operator-supplied roof reference. Geographic errors never enter fitting or
selection. This is an exposed, unsurveyed single-site development comparison;
no blind/generalized accuracy claim follows. DS8/DS9 transfer remains later.

Each record is sequentially limited to 180 seconds and 4 GiB, one numerical
thread and nice19, with all launch sources bound. No new propagation, IQ, RF
or source-store mutation. Retain failures; do not silently extend execution caps.
