# C053 complete free-chart Hessian qualification

The prior directional audit found smooth feasible descent and high positive curvature along three directions, but did not establish the full matrix. This zero-fit experiment measures the full51-coordinate native fixed-geography chart Hessian at the identical sealed best feasible state.

Central analytic-gradient differences use prespecified chart steps1e-4 and5e-5. Four independent units cover coordinates0–25 and26–50 at each step. One baseline objective is evaluated in unit0; totals are at most205 native objective/gradient evaluations. Each unit separately obtains the baseline native visibility mask and every feasible signed probe's visibility, for at most208 explicit native orbit calls. Infeasible probes are preserved as missing columns, never projected or replaced. All units share exact state, model, bank, priors, domain and chart.

Only complete matrices receive symmetrized spectra. Both raw symmetry defects and step-to-step matrix/eigenvalue differences are reported, together with all visibility changes and infeasible probes. A spectrum alone does not certify a smooth positive-definite Hessian if visibility changes or derivative instability occur. No global or uncertainty claim is made.

Each unit has120 seconds internal and135/140 seconds external TERM/KILL bounds, with at most four single-thread workers. Source and component tests freeze before preparation. No solver call, reference or held evidence is used. Any preconditioning or objective-scaling prototype requires separate review after this audit, with original acceptance and ftol implications accounted for.
