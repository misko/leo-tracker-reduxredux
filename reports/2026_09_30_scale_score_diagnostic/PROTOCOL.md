# Marginal versus joint held prediction under frozen scale models

Use the complete DS10 N24_h0 baseline location/timings and frozen original, matched-constant and variable track-scale models from the preceding weighting pilot. No parameters, weights, candidates, thresholds or geography change.

For every track, compare (a) joint held predictive log density, full-data log density minus training log density, and (b) the sum over held observations of individual conditional log densities, training-plus-one-held log density minus training log density. Each individual prediction conditions only on training data, never on other held outcomes. Use the same normalized q020 signal/background contrast mixture, training visibility and physical scale in both definitions.

Report both proper predictive targets separately: the sum of individual log scores is not the joint log density and cannot be substituted for it. Audit direct joint scores against the previous full model for all tracks and arms. Test one-held equivalence and single-versus-batch conditional prediction. This is a fixed-location explanatory diagnostic, not a new accuracy result or a promotion criterion. Cap at 180 seconds, no new RF, exports, propagation or fitting.
