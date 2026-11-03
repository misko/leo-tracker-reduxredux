# Exact timing profiles with complete joint calibration

The adapter passes five component tests and a bounded qualification against the existing TRAIN-only joint-band endpoints. Twelve direct objective evaluations agree with profile columns within **2.15e-10 NLL**, in **13.22 seconds**. No optimization, proposal search, held scoring, station/reference read, new discovery or old-report change occurred. This establishes mathematical compatibility, not a recovery or localization result.

`timing_profiles.py` supplies a generic array port, `ResidualProfiles`, and the narrow scientific adapter `from_context(context, vector, nuisance)`. Its calibration input is the complete current-model wrapped residual. It never reconstructs a clock, band contrast, RF coefficient or another calibration term. For orbital prediction `d` and current residual `r`, a trial candidate uses

```
r_trial = wrap(r_current + d_current - d_trial)
```

This retains every current band/clock/RF correction implicitly. Each output column changes only that candidate's total timing; all other candidates and every nuisance coordinate remain fixed. The likelihood subtracts the old candidate contribution, adds the new Gaussian signal and visibility odds, and updates both numerator and selected-event normalizer. Signed evidence from every scored point includes lost support. A zero-signal candidate still changes the normalizer when its visibility changes.

The initial complete objective carries all non-timing penalties exactly once, including the current absolute band prior. Each timing trial adds the exact change in common-mean and zero-sum relative penalties after recentering all candidates. This version explicitly requires the unchanged 3 s common and 2 s relative prior; it rejects other widths. `timing_vector(vector, basis, total_times)` constructs a direct model trial in that same gauge. Feasibility, timing bounds, search policy and future fit budgets remain the caller's responsibility; this package implements no search or optimizer.

The five tests compare every profile column to direct `JointBandObjective` evaluations at nondefault band offsets, both fitted-c and c0 physical states, multiple timings, compact-horizon transitions and full-alias prediction jumps. They also test excluded-CFO invariance, the zero-signal visibility normalizer, exact prior recentering, preserved physical/nuisance seeds and projection accounting. No frozen model code changed.

The actual qualification uses only the existing 2073-observation training export and its 45 TRAIN-selected candidates. Both already frozen joint endpoints supply complete calibration states. Deterministic bank-order indices are chosen without candidate/window hypotheses. For each c arm, one construction objective plus five direct single-coordinate objectives consumes six checks; the total is twelve. Two trial timing vectors per arm score all columns. The current-timing nesting check adds a third profile vector. There are 270 vectorized column comparisons and eight explicit profile orbit-prediction/elevation projections, **in addition to** orbit work inside the twelve direct objective evaluations. Optimization/refit calls are zero. Conditional c0 remains downstream of fitted-c training discovery; no whole-pipeline c0 inference is claimed.

`protocol.json` was saved before tests and target context loading and binds code, sealed source endpoints and TRAIN input hashes. `qualification.json` records all ten trial comparisons, two construction objectives, actual errors, nondefault bands, counts and elapsed time. `manifest.json` seals this directory. The sealed `iteration5/joint_band_contrast` numerical ports and report remain unchanged.
