# Combined 30-record separate-dataset fits

Combine every recording from the disjoint union and outside-union panels:
30 records each for DS7, DS8 and DS9. No outcome-based exclusion, replacement,
new export, candidate propagation or RF collection. Sort each dataset by capture
time and session ID; verify exact manifest, pose and artifact hashes.

Use the unchanged shared track scale model (decay0), selected as the leading
geographic model by prior experiments. This is an exposed-data follow-up, not
blind model selection. Fit datasets separately; no observations from another
dataset enter its estimate. No pooled or leave-dataset-out fit in this experiment.

Three generic starts per dataset: E/N(0,0), (3,-3), (-3,3)km, all timings zero.
Use unchanged L-BFGS-B maxiter140/maxfun200, ftol1e-14, gtol1e-8, maxls30;
bounds +/-12km and +/-5s. Qualify optimizer success, interior parameters and
gradient infinity norm <=0.01. Select the greatest training score among qualified
starts. No previous-fit fallback, retries or relaxed gates.

Seal fits before held evaluation. Replay selected training scores within1e-7;
check full-objective E/N gradients at1m/0.5m, tolerance0.002. Compare held scores
separately on the union and outside-union tracks against their own previous
15-record selected fits. Use the original union result and latest timing-grid
outside result; reconcile exact track identities/counts. These are descriptive
likelihood comparisons with different fitted geographic/timing parameters.
Only after sealed execution calculate errors against the same unsurveyed,
previously exposed reference. Retain all start errors, not just the winner.

Nine fit processes plus up to three selected-point audits, each capped180s/
4GiB, BLAS1/nice19, at most two concurrent workers. No component changes.
