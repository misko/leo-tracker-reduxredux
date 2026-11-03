# Iteration 4 interim checkpoint

The objective remains active: recover a larger fraction of the same 15 GLRT
windows with position-independent modeling and verify useful prediction.
Iteration 3 is sealed: 361 files, with 600 previous sealed files hash-verified
unchanged. See its [checkpoint](../2026_10_17_dsx01_iteration3/CHECKPOINT.md).

## New empirical frequency-residual lead

The constant-Hz satellite residual model, sigma_b=1000 Hz, now has complete
fitted-c/c=0 profile results on all five recordings. For fitted-c:

| Method | Window associations /693 | ≥80% net-restored windows /15 | Full associations /20084 | Lost original full support |
|---|---:|---:|---:|---:|
| Original | 96 | 0 | 11,222 | 0 |
| Fixed exact profile | 422 | 6 | 13,784 | 742 |
| Expanded exact profile | 434 | 7 | 14,248 | 791 |
| Fixed profile + width continuation | 455 | 7 | 14,173 | 1,037 |
| Constant-Hz residual, sigma_b=1000 | 462 | 8 | 14,372 | 779 |

The new model has five strict numerical endpoints. Independent source-ordered
NPZ comparison against the ORIGINAL published fitted-c observations gives
3,929 new / 779 lost assignments, net +3,150. On observations assigned by both
original and variant, RMS is 156.884→144.034 Hz (identities may change).
The model's own report additionally compares against the fixed-profile seed;
those new/lost counts use a different baseline and must be labelled accordingly.

Strongly restored windows are 001/005/007/008/009/010/013/015. Window003 remains
0/27 and window014 only12/39. This is one fixed global width/algorithm, not a
per-window hybrid. Other predeclared widths and continuation controls remain
visible; cross-width total objectives are not Bayesian model evidence.

This is not a localization success. Configured-reference distances for
S01–S05 are approximately130.55,137.70,3.94,258.43,5.38 km. Some biases reach
their 4000 Hz bound. The added term is an empirical residual hypothesis, not
proof of satellite oscillator error, correct identities or geographic truth.
It must earn predictive support before any promotion.

The completed conditional residual test rejects stable temporal prediction:
39/40 fits worsen excluded-half likelihood. Pooling both directions, fitted-c
assigned support falls from 13,784/20,084 to 10,789 with sigma_b=300 Hz or 8,307
with sigma_b=1000 Hz. Requested support falls from 422/693 to 287 or 262.
Only new b_s is learned on each training half; the same saved physical baseline,
calibration and q remain fixed. The baseline itself is full-data conditioned,
so this is a conditional diagnostic rather than end-to-end cold validation.
The descriptive 462/693 result must not be promoted. The frequency-bias report
is sealed with 106 files and nine passing tests.

## Other work

- `peak_mixture/`: eight strict S03/S04 pilot outcomes are sealed with nine
  passing tests and actual-data singleton equivalence. Fitted-c requested
  coverage192→194/293 comes with complete winning-point support6270→6239/7707
  and normalized permutation support1132→1139. No full-five campaign follows.
- `expanded_annealing/`: all 20 outcomes are complete and the 87-file report is
  sealed. Fitted-c full support rises 14,248→14,455/20,084 but requested support
  falls 434→429/693. All five endpoints are numerically strict, yet configured
  position errors remain large on S01/S02/S04. This is a negative recovery result.
- `cold_pipeline/`: faithful original-policy S03 early-half discovery completed
  in 77.659 seconds under its 480-second cap. The train-selected bank has 25 IDs;
  training support is 1571/2006 (RMS 151.11 Hz), held support only 165/1982
  (8.325%, RMS 173.73 Hz). Train KKT is 0.000223167. Complete selected-ID
  propagation and constant residual-clock extension preserve exact training
  closure; no held knots are fitted. Cost audit and final report are underway.
  This capture-midpoint split differs from the earlier 1994/1994 split.
- `../2026_10_17_dsx01_iteration5/age_timing/`: testing whether per-object element
  age and historical same-provider consistency support heterogeneous relative
  timing priors. Calibration uses snapshots before the earliest DSX recording;
  no target fitted timings or configured position tune prior widths. Common
  recording-clock uncertainty remains separate. No success claim yet.

All current changes are research-only on the existing corpus. No RF acquisition,
production deployment, public-contract change or remote push has occurred.
