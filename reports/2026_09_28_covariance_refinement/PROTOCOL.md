# Numerical refinement of covariance source positions

Preserve the published covariance-transfer experiment unchanged. For each of
its eight model/source units, choose the highest training-score returned fit
with optimizer success and interior parameters, irrespective of its previous
gradient qualification. Refine that one point with the identical model/data,
L-BFGS-B maxiter60/maxfun100, ftol1e-14, gtol1e-8, maxls30. No new starts or
geographic/reference-based selection. Require success, interior parameters,
and gradient infinity norm <=0.01 for qualification. Archive the source seed
and previous qualified selection separately; do not erase prior outcomes.

At each qualified refined donor position rerun target timing/frequency-offset
adaptation at starts0,-2,+2, with fixed donor geography and the tighter stopping
criteria. Maxiter100/maxfun160 for target adaptation. Select by target training
likelihood only. Recompute all source/target held scores; check source position
gradients against full objective differences at1m/0.5m, tolerance0.002.

Source and target fits and scoring each capped90 seconds/4GiB, one BLAS thread,
at most two concurrent workers. No automatic retry. Failure remains visible.
The Student-t4 scale100 Hz, decay0/10 seconds, nugget0.2, original weak offset
prior, retained banks, full-catalogue normalization and whole-visit split are
unchanged. No new IQ, RF or catalogue propagation. Report changes from the
previous qualified positions and scores, plus the same-model separate-panel
and iid comparisons. One refinement seed is not a new multistart robustness
test. A polished solution does not establish global optimality or accuracy
against independent surveyed truth.
