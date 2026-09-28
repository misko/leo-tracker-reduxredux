# Fixed-model validation outside the successful union

Use every recording in the published outside-union proposal, exactly15 per
DS7/DS8/DS9 with no overlap with the45-record union. Require all three input
panels to finish validation before any geographic fit. No substitutions or
outcome-based exclusions. These recordings are not certified research-blind.

Retain both unchanged multivariate Student-t4 models at100Hz: shared track
scale with a diagonal scale matrix, and10-second correlation/20% nugget.
Keep the original offset prior, visibility, full-catalogue normalization and
whole-visit split. No model selection or tuning using these geographic errors.

Fit each separate15-record panel, all45 jointly, and each30-record pool excluding
one dataset. Every source unit uses three generic E/N starts: (0,0), (3,-3),
(-3,3)km, with all record timings initially zero. Do not seed from the previous
union or an excluded dataset. The geographic origin remains inherited and
previously exposed. Generic starts differ from the union experiment's starts.

Bounds +/-12km and timings +/-5s; L-BFGS-B maxiter140/maxfun200, ftol1e-14,
gtol1e-8, maxls30. Qualify only optimizer-successful interior fits with raw
gradient infinity norm <=0.01. Select by training likelihood. No retries or
relaxed gates. At each qualified donor position, hold geography fixed and adapt
target timing/offsets with timing starts0,-2,+2, selecting by target training.

Replay all training and exact held scores. Verify matching track sets/counts
against each same-model separate15-record panel. Check source E/N gradients by
full-objective differences at1m/0.5m, tolerance0.002. Geographic scoring follows
sealed fits and held checks and uses the same exposed unsurveyed reference.
Report every unit/model, alternative start, failure, and comparison with the
union. Do not replace the earlier panel failures with only favourable results.

Each scientific worker capped180s/4GiB, BLAS1/nice19; at most two concurrent
workers. No waveform/IQ reads, RF collection, provider fetch or new propagation
in the modeling stage.
