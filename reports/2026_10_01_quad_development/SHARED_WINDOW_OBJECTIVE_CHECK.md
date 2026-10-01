# Complete shared-threshold objectives pass directional checks

The experimental objective now combines all track scores and Gaussian nuisance priors in a window, using explicit local-to-global column maps. Position is shared and each scan retains its independent clock, drifts and satellite epochs. A synthetic test verifies shared-position accumulation, disjoint nuisance columns and rejection of duplicated physical observations.

Four recorded fixed-state cases pass: DS9-B01-S1 (single), DS10-B01-D1 (pair), DS11-B01-Q (quad), and the rejected DS11-B03-D2 pair state. For each, the new-model assignments are selected once, then held fixed while checking east, north and three deterministic nuisance directions at two step sizes. Maximum absolute derivative discrepancies are 1.49e-7, 1.33e-7, 2.97e-7 and 3.12e-7, respectively, below the predeclared 0.002 threshold. These are directional checks, not exhaustive coordinate or global differentiability proofs.

The [sealed objective check](shared-window-objective-check-v1.json) includes the actual objective, gradient norm, directions' derivative values, timing and input bindings. It performs no optimization or geographic scoring.

A separate limited-memory BFGS prototype now uses the full score gradient, including visibility-dependent background terms. Two synthetic tests verify monotone recovery of a coupled quadratic optimum and an explicit unresolved outcome after an expired deadline. This does not establish convergence on the radio model. A line search and a stopping test alone are not an independent scientific audit.

The [pilot plan](SHARED_VISIBILITY_PILOT_PLAN.md) fixes three single-scan cases, the illustrative 0.1-degree width, original-state warm initialization, charged 90-second budget, solver settings and post-fit checks before fitting. A supervised runner and independent evaluator are still required. No new-model position result is claimed. Existing published benchmark outcomes and the continued-baseline reference remain unchanged.
