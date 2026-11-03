# Next controlled models after DSX01 iteration 3

The preceding iteration finds a higher window count (455/693) using broader
frequency widths during search, but still seven strongly restored windows,
several nonstationary endpoints, more displaced original support and large
configured-reference distances. The goal remains active. No validation station
coordinates or manually selected satellite IDs may enter any method.

Three SOL investigations continue in parallel, in separate directories:

1. `expanded_annealing/`: apply the same 1000→500→250→125 Hz continuation to
   the generically expanded bank. Compare with extra continuation entirely at
   125 Hz, with the same added 1,000-objective/120-second allowance. Preserve
   raw and numerical-finishing histories separately and evaluate one policy
   across all five recordings. Final selection/classification remains 125 Hz.
2. `peak_mixture/`: integrate all passed GLRT peaks with a normalized latent
   peak variable per original probe group. Start with uniform within-group
   weights, an explicit existing clutter alternative and once-only priors.
   A single peak must exactly reproduce the original likelihood and gradients;
   duplicating identical peaks must not increase evidence. All q/visibility
   normalizer derivatives must receive the peak posterior weights. Headline
   coverage remains on the original 693 winning observations. Any-peak coverage
   is a separate diagnostic with permutation controls, never credited recovery.
3. `frequency_bias/`: test an empirical constant-Hz residual b_s shared across
   receivers/channels for each satellite, with Gaussian shrinkage sigma 300 or
   1000 Hz and bounds ±4000 Hz. This tests whether constant frequency residuals
   are being forced into timing shifts; it does not assert an oscillator or
   ephemeris root cause. Exact all-point bias profiles must debit displaced
   support. Zero bias must exactly nest the original model. Constant-Hz biases
   add no new RF-dependent term; physical Doppler still uses actual RF.

For every model, preserve observation/probe identity and every missing outcome
in evaluation denominators. Use fitted-c/c=0 controls with matched candidate
sets, data, priors and search allowances. Keep frequency scores, paired RMS,
new/lost assignments, timing and configured-reference position separate.
Never combine per-window maxima or choose a variant from reference accuracy.
No new RF collection, production writes, contract changes or remote pushes.

These full-data warm fits are development evidence. Position-independent code
and held-CFO invariance tests are necessary but insufficient to prove predictive
generalization. Any successful development model still needs excluded-data
evaluation with correctly learned training-only calibration and an explicit
candidate-discovery/clock-extrapolation policy; the previous targeted-probe
holdout and whole-half holdout are different experiments.

The normalized-peak pilot has now stopped after eight strictly converged
S03/S04 outcomes: it gains two requested-window points but loses complete-scan
winning-point support in fitted-c and c=0. It does not justify a full campaign.
Its agent next builds a faithful training-only baseline in `cold_pipeline/`:
one S03 early→late pilot through the original public production entrypoint,
bounded at 480 seconds after testing whole-probe derivation and provenance.
Only training probe measurements enter discovery. Held-time propagation uses
only train-selected IDs, and frozen residual-clock boundary extension is
declared and tested. No full-data calibration or configured position supplies
a seed. This is a validation prerequisite rather than a fourth recovery model.
