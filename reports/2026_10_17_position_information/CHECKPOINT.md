# Position-information continuation checkpoint

Goal active, unachieved: merged-track satellite association on DSX01 and DS22,
ultimately verified position error below 0.5 km. This goal turn made progress
through a tested information kernel, six actual data audits, two independent
merged DS22 searches and two common-position searches. No external blocker.

All launched jobs are terminal: successful information run 83880; failed stdout
run 89056 (preserved source/data); DS22 merged c0/fc 84526/67248; common-position
c0/fc 7538/21547. The common-position outputs use only earlier blind families;
scan-local calibration remains independent. Common position is a declared
same-site hypothesis. Both arms error 5.55746 km, not a qualified success.

Conditional major axes with nuisance projection are 0.618 km S01 separate,
0.620/0.621 km S01 merged, 0.851 km DS22 separate. Ignoring nuisance terms
would give misleading 13–15 m conditional axes. These are Gaussian mean-model
diagnostics, not full-score Hessians or calibrated truth uncertainty. No bounds
are active in the audited endpoints. Actual errors remain 6.356, 6.479 and
2.139 km respectively. No new parameter defaults were adopted.

DS22 merged leaves the same 29 curved components and original 1,123 points;
1016 pass final checks, 1515 extended points / 47 merged tracks, error 2.139 km.
Do not call this an accuracy benefit from merging. Earlier best DS22-001 is
1.894662 km under a different noise-gated search. Whole DS22 is not validated.

Next: per-satellite score/position conflicts at existing blind assignments;
audit full causal orbital disagreement beyond scalar along-track phase before
introducing orbit parameters. No arbitrary component slopes. Learn blind
S02–S05 labels before a larger common-position experiment; never use their
known-GPS association output as a blind initializer. All c experiments require
identical points, candidate sets, other priors and budgets. Linear fragments may
associate only after curved-derived calibration is frozen.
