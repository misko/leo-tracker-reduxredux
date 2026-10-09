# Active-face reduced-Hessian Newton qualification

Iteration99 reduced the saved postfit's independent stationarity residual from
0.01640097 to0.00240807 but did not meet0.001. Four scalar tangent steps improved
it; subsequent scalar Newton trials lowered score while worsening the infinity
norm of the full KKT residual. A scalar direction cannot account for all coupled
curvatures simultaneously.

This separate prototype keeps the same scaled active-face nullspace and obtains
its reduced Hessian by central differences of exact gradients, one1e-5 probe in
each nullspace coordinate. Symmetrize the result and solve a Newton system only
when positive definite above the floating-point rank threshold. No ridge,
eigenvalue clipping, pseudoinverse or additional model parameter is introduced.

Retain the same1,1/2,1/4 dampings, full physical feasibility, unchanged0.001 KKT
qualification and fixed128ULP initial objective ceiling. Budget at most2rounds
and100evaluations. Do not start a Hessian sweep without enough remaining budget
for all central probes and at least one Newton trial. Preserve all probes,
curvature eigenvalues/asymmetry, accepted steps and failures. No active-face
release or special per-scan numerical choices.

Starts the exact saved unqualified99 postfit after verifying its objective on
the identical reconstructed receiver-corrected likelihood. No position reference
or alternate seed enters inference. A qualified result would enable the separate
matched-c downstream continuation, not establish a position improvement itself.
Preparation and synthetic tests only until parent review/freeze/publication.
