# Conditional reception LOSO with fixed numerical refinement

The full-six numerical review passed before these folds: all three arms and all nine deterministic-start results reached gradient below 1e-10 after one Newton step. The prior protocols, model definitions, thresholds, inputs, and advancement rule remain unchanged.

Run the six original calibration sessions as held-out reception folds. For each, use the existing immutable runner to create a separate raw artifact for M0, same-objective mean-direction M1, and candidate-mixture M1. Feature levels and scales are learned only from that fold's five training sessions. Retain the fixed all-six frequency identities and log probabilities; call this conditional reception LOSO, not fully nested frequency validation.

Apply the unchanged bounded Newton refinement to every raw start using only that fold's training objective. Reproduce the saved raw objectives first. No heldout reception likelihood may select starts, optimizer settings, model form, or refinement stopping. Retain raw and refined artifacts separately. Do not change the three deterministic starts or convergence/curvature/stability thresholds after observing a fold.

Score the held-out session only with the training-derived schema and fitted coefficients. Report detection-marginal NLL plus conditional-ratio increment, their sum joint NLL, and track counts. Keep training scores explicitly separate. No ground-truth geographic error, evaluation grid, or recording from the location-test cohort enters fitting or advancement.

The aggregate requires the complete polished full-six result and all six polished fold results, exact partition/track counts, and matching immutable input/code/protocol/raw-artifact bindings. It independently applies `mixture_advancement.evaluate_gate` to the held-out track-normalized likelihood sums. A geographic replay is permitted only if full-fit and fold numerical checks pass and the predeclared calibration advancement gate passes. Failed folds or negative findings are retained, not replaced.

This stage tests predictive reception likelihood, not geographic accuracy. A later claim that RX geometry improves location resolution still requires a frozen geographic estimator and independent confirmation.
