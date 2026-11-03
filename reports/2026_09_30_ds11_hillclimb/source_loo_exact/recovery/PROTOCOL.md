# Alternative solver diagnostic, before any wider-screen revision

The original source-holdout screen and the separate same-L-BFGS-B restart both
remain failures. This diagnostic tests exactly one SLSQP continuation of the
same saved index-4 t8/NORAD-65855 endpoint. No geographic errors may enter the
decision or execution.

First require a local precision diagnostic: finite, positive-definite loss
curvature; relative Hessian asymmetry and step-halving discrepancy each at
most 0.005; predicted Newton east/north displacement at most 0.01 metre and
timing displacement at most 1e-5 second. Failure of these checks means this
diagnostic must not run. These are numerical reliability checks, not position
accuracy bounds.

The saved failed fit must be interior and finite, with maximum gradient at
most 0.01 and finite-difference discrepancy at most 0.02. Start one SLSQP call
at that saved endpoint with the same retained objective, supplied gradient and
bounds; maxiter100, ftol1e-12, no new starts. Use the original success, finite,
boundary, gradient and finite-difference qualification. Retained objective may
not worsen by more than 1e-7 nats. One BLAS thread, one process, 90-second cap.

Report both the original failure and new outcome, endpoint displacement and
held-score change. A successful diagnostic is evidence of solver recovery only;
it cannot establish geographic improvement or silently resume the old screen.
A wider comparison requires its own frozen uniform execution rule.
