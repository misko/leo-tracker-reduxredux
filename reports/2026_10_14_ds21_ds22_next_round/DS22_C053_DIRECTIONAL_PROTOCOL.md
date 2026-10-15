# C053 best-feasible constrained directional audit

This zero-fit diagnostic uses the identical best feasible state saved by both sealed matched solver arms. It checks the original fixed-geography native model, full physical/nuisance constraints, scaled-chart gradient blocks and strict KKT without changing the state or objective.

Three directions are prespecified: active-cone projected full negative gradient, timing-only projected negative gradient, and receiver/RF/group-only projected negative gradient. Projection applies only to construction of a tangent direction, not to a perturbed state. Each direction is normalized by its maximum absolute chart component. Every positive and negative perturbation at steps1e-3,1e-4,1e-5 is checked for original-domain feasibility; infeasible probes are reported and skipped. No smaller step is chosen adaptively.

Feasible probes compare analytic directional derivatives with objective differences and gradient-derived directional curvature. An independent native orbit evaluation records visibility changes relative to baseline. This is not a full Hessian, positive-definiteness certificate, uncertainty estimate or global optimality claim. The report records scaled coordinate units, active constraint names/rank, all constraint values and bounded/unbounded chart limits.

At most19 native objectives and19 explicit native orbit calls occur, including baseline, with no localization fits, reference or held evidence. The source is frozen before preparation. One worker has120 seconds internal and135/140 seconds independent external TERM/KILL limits. All original scientific results remain immutable.
