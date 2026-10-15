# C053 strict-profile geographic admission audit

Before a free-geography solver comparison, this zero-fit audit checks the exact accepted scaled fixed profile against its original25 km disk and unchanged full native model. It records the full geographic gradient, original free-physical KKT, nuisance gradient, domain feasibility and any initializer canonicalization delta without applying that delta.

Two prespecified directions are the inward radial unit vector and the unit negative geographic gradient projected onto the disk's first-order feasible half-space. Each gets1 m and10 m probes with every non-geographic parameter fixed. Perturbed states are never projected: any infeasible probe is explicitly recorded and skipped. Native visibility changes are recorded for all evaluated states. A baseline objective plus at most four probes gives at most five objectives and five explicit orbit calls.

No fit, reference or held evidence is used. Source/tests freeze before genuine preparation. One worker has120 seconds internal and135/140 seconds independent external TERM/KILL limits. This audit does not authorize a larger disk or a free release; its measured feasible descent will be reviewed first.
