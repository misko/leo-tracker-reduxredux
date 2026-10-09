# Independent reduced-Hessian prototype review

The algebra and synthetic qualification were reviewed before a recording fit.
Six synthetic tests pass. No new RF objective evaluation or position fit was
performed by this review.

In scaled free coordinates, let Q be an orthonormal null-space basis of the
selected active constraint normals, and S the physical scale matrix. The code's
physical direction basis is D=S*Q. Its reduced gradient D-transpose*g and central
gradient-difference Hessian columns D-transpose*(g(v+hD_j)−g(v−hD_j))/(2h) are
consistent derivatives in the same reduced coordinates. On the target's affine
satellite timing face, these coupled directions preserve the active shift. Every
probe and proposed Newton state is additionally checked against all unchanged
physical constraints before evaluation.

The symmetric reduced Hessian must be finite and positive definite above a
machine-precision threshold. Indefinite or unidentified directions produce an
explicit negative result; no fitted ridge, curvature floor or scan-specific
regularization is introduced. The solve uses the same reduced gradient, maps
back through D, and applies the fixed damping list. Acceptance retains full
independent KKT improvement and the original fixed128ULP objective ceiling;
projected-subproblem success does not replace the0.001 qualification gate.

The synthetic tests cover a coupled anisotropic active-face quadratic, recovery
of its known optimum in one round, indefinite and null-Hessian rejection, budget
limits, an empty active face with remaining interior descent, nonunit scales and
rejection of an infeasible original seed. They use a synthetic problem port,
not the RF mixture objective or its native interpolation kernel. These tests
prove the intended algebra and safeguards, not actual calibration or localization
improvement.

Two limitations remain explicit. Treating every near-active normal as an equality
is a conservative active-face search; a face with zero KKT multiplier might permit
an inward direction that this null space excludes. Also, central-probe feasibility
and positive definiteness after symmetrization do not themselves prove derivative
consistency. Raw Hessian asymmetry is retained as a diagnostic; an unexpectedly
large asymmetry or changing spectrum needs interpretation before attributing a
failure to physical nonidentifiability. Curved active disk constraints can reject
two-sided tangent probes at second order, although this target fixes position and
its binding timing face is affine.

The existing iteration99 negative result supports trying a coupled Hessian,
without guaranteeing it: four accepted steps reduced KKT to0.002408070987, then
all three final feasible dampings lowered objective while worsening full KKT.
Those rejections are consistent with the unchanged policy. A new separately
frozen iteration100 result is required before claiming a qualified postfit, and
downstream matched-c continuation remains necessary before any position claim.
