# Fixed-state correlation-time screen

The conditional added-observation diagnostic shows smaller residual magnitude but more sign persistence than simulations from the existing covariance model on all three pilots. This motivates a covariance-shape screen, not a geographic claim or a noise-scale reduction.

Before scoring, fix correlation times to 0.5 (control), 2, 10 and 60 seconds. Keep white-noise amplitude, correlated-noise amplitude and Student degrees of freedom unchanged. Keep the same eight-point fitted states, identities, checked signal tracks, original points and added points. No fitting, background relabelling, track deletion, timing-prior adjustment or reference scoring occurs.

Recompute the joint scale matrix and its exact eight-point marginal for each correlation time, then evaluate the normalized conditional density of added contrasts. The 0.5-second control must reproduce the sealed original conditional scores. Verify the conditional density against the joint-to-marginal density ratio for every track/arm.

For each target dataset, select the correlation time maximizing the equally weighted mean of the other two datasets' mean conditional log density per added observation. Break ties by listed order. Target added observations do not select its correlation time. Report every arm and all three target results, including losses. The target's fitted state is its existing eight-point state; this is covariance transfer at fixed fitted geometry, not held-out geographic inference or an untouched validation set.

This four-arm screen tests correlation shape alone. It cannot establish that stronger correlation or altered likelihood weighting improves geographic accuracy. Inspect the complete outcomes before proposing a separate bounded refit. The fixed identities, fitted-state uncertainty, detector/track selection and dependence across tracks limit interpretation.
