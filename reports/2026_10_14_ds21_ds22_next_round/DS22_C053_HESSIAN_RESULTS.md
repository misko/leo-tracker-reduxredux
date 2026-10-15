# C053 full Hessian: stable nonconvex curvature, no visibility crossing

The full51-coordinate fixed-geography Hessian is indefinite at the stalled best feasible state. Both finite-difference steps produce six negative eigenvalues, with small raw symmetry defects and close step-to-step agreement. This is a nonstationary state with negative curvature, not a certified stationary saddle or positive-definite Newton basin.

| Chart step | Smallest eigenvalue | Largest eigenvalue | Negative eigenvalues | Raw relative symmetry defect |
|---|---:|---:|---:|---:|
| 1e-4 | −1913.836980 | 200248.776489 | 6 | 2.4693e-7 |
| 5e-5 | −1913.391417 | 200248.793112 | 6 | 6.1655e-8 |

The relative difference between symmetrized matrices is7.0481e-5. The largest absolute sorted-eigenvalue change is7.0995; the six negative signs persist. All204 signed coordinate perturbations were feasible without projection; there were zero native visibility changes across208 explicit orbit evaluations. No columns were missing. The raw matrices, symmetrized matrices, spectra, diagonals and all signed-probe receipts are preserved.

The smaller-step diagonal ranges from−1806.599 to165691.151 in the original scaled optimizer chart. The two group-offset diagonal values are165691.151 and123618.897, using original5000 Hz scales. This makes diagonal coordinate preconditioning a reasonable controlled numerical hypothesis, but high curvature alone does not explain all SLSQP behavior. The earlier three descent directions all had positive directional curvature and therefore could not characterize the complete matrix.

A next matched test can use the fixed smaller-step diagonal scaling `S_i = 1/sqrt(max(1, abs(H_ii)))`, preserving the exact objective, bounds, constraint Jacobian, ftol and original-coordinate KKT. The floor is inactive for these measured diagonal values. This is a coordinate transformation, not regularization of the statistical model or a claim that the Hessian is positive definite. No solve is part of this audit.

Actual cost205 native objective/gradient evaluations plus208 explicit native orbit calls, zero fits/reference/held. Four bounded single-thread units completed in48.768 seconds wall time; each had120 seconds internal and135/140 seconds external bounds. Three component tests and Ruff passed. Source/protocolf2cd5ba62; namespace `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c053-hessian-audit-v1`, globally sealed `report.json` and all four original units.
