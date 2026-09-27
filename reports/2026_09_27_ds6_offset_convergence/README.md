# DS6 track-offset convergence audit

The existing 12-iteration Student-t offset profiler is not numerically
converged for all candidate residuals. At the 43 fixed corrected baseline
locations, increasing the iteration budget to 2000 with a 1e-7 Hz change
criterion changes total training log score by +82.622 and held log score by
+105.643. Eight scans change training score by more than one; two tracks change
their training-MAP candidate. These are score changes, not geographic gains.

The largest scan changes are `a38d2f57a8974b96` (+30.972 training, +41.331 held)
and `496d3fcd69534bc7` (+21.132 training, +77.929 held). The covariance-sensitive
scan `a077447f07d9f81f` changes by +8.479 training and +9.826 held. This gives a
concrete numerical reason to revisit the local likelihood and fits before
interpreting their fine curvature.

One visible candidate still does not meet the convergence criterion after
2000 iterations, in track `87984823a6aeb8b8909fe5e0ff844b7e2a13e604c4ef142573b66533483c6fd1`
of `scan-fw-53ce822d78d476ba`. The track mixture score barely changes, but this
does not excuse calling every candidate converged. The complete-real-data
test deliberately fails its zero-unconverged-candidates gate; two synthetic
tests pass. This failure is preserved rather than loosening the gate or
silently excluding the candidate. No new estimator is accepted from this
audit. A stationary scalar solve with explicit local-mode checks is the next
numerical step, followed by matched position refits and geographic assessment.

Both arms retain the same median initialization, fixed 100 Hz scale, candidate
visibility, inherited mixtures, training masks, position and timing. The
longer iteration centers residuals to reduce cancellation and fits using
training observations only. The existing tiny offset prior penalty remains
post-fit, so the convergence target is the unpenalized offset likelihood,
not the exact penalized objective. A stationary IRLS point is not guaranteed
to be the global Student-t optimum; that limitation is explicit.

The audit uses all 43 sealed DS6 scans and corrected causal elements. It never
loads ground truth. The two synthetic tests verify translation behavior,
explicit iteration-limit failure, held-data isolation and simple residual
recovery. All completed results and source dependencies are bound by hashes.
The old estimator is unmodified and remains reproducible. No production
deployment or new RF occurred; the broader sub-kilometre objective is active.
