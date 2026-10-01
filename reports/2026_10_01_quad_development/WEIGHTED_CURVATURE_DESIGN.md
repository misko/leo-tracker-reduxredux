# Candidate-weighted residual curvature: separate future optimizer experiment

The marginal single pilots required25and45iterations on DS9/DS10, versus2and5for the hard-model refinements. Their exact marginal objective and gradient currently use a leading-branch residual curvature approximation. Before changing any running experiment, prepare a separate direction computation that weights each candidate's residual curvature by its conditional probability.

For track t and signal branch i, form

`H_ti = p_ti * w_ti * J_ti.T * C_t^-1 * J_ti`,

where w is the Student-t4 IRLS weight. Add these contributions and the existing Gaussian prior precision. Background remains in the exact objective/gradient but supplies no residual curvature. This is still an approximate positive preconditioner: it omits visibility curvature and the branch-score covariance term of the exact marginal Hessian. It is not a posterior covariance or a change to the likelihood.

Each compact Jacobian touches only the shared position, its scan's clock and two drifts, and one satellite epoch. Consequently, all epoch-epoch off-diagonal elements of this approximation are zero. Partition the system into a small core of size `2 + 3 * scans` and a diagonal epoch block:

`H = [[A, B], [B.T, D]]`.

Eliminate epochs with `S = A - B D^-1 B.T`, solve S for the core step, then recover epoch steps. This retains the intended candidate-weighted curvature without building a dense all-epoch Hessian or a huge matrix over all candidate observations. Numerical conditioning still requires validation; reject nonpositive/singular systems rather than silently inserting a position prior.

The new `epoch_block_curvature.py` helper performs that assembly and solve from compact6-by-6candidate blocks. Two tests pass: a weighted two-scan example agrees with a dense full-state solve to1e-10, and absence of signal position geometry fails explicitly. No radio-model block assembly or optimizer integration has been performed yet. No current pilot uses this helper.

After the frozen six-window marginal pilot finishes, use its convergence and budget outcomes to decide whether this optimizer-only ablation is warranted. If pursued, validate block assembly against the existing Jacobians and a dense reference on bounded cases, then freeze the same-start/same-model/same-budget comparison. Preserve the marginal objective, complete gradient, line search and stopping criteria. Do not tune the direction or budgets inside the active pilot.
