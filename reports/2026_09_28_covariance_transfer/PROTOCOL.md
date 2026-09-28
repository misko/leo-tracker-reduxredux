# Pooled and leave-one-dataset-out covariance positions

Use the exact first-eight DS7/DS8/DS9 panels and both fixed published covariance
models: Student-t4, scale100 Hz, nugget0.2, decay0 or10 seconds. Reuse the verified
global stationary-offset profiler and envelope gradient without modification.

For each model fit one shared position and per-record timings to all24, then
to each pair of datasets (16 records). Source starts use each included dataset's
published same-model position, concatenating only included datasets' timings.
Thus each all24 fit has three starts and each donor fit two. Excluded dataset
positions, observations and offsets never enter donor fitting or its starts.
Select maximum training score among numerically qualified successful interior
fits. Require gradient infinity norm <=0.01; bounds +/-12km and +/-5seconds.
L-BFGS-B maxiter140/maxfun200, ftol1e-12, gtol1e-6, maxls30.

For each excluded dataset, freeze the donor geographic position and adapt only
its eight timings and stationary offsets on its own training observations.
Three fixed timing starts:0,-2,+2 seconds. Same qualification, maxiter100,
maxfun160. Select on target training likelihood. This target nuisance
adaptation is explicit; target position never moves.

Each source/target worker capped180 seconds/4GiB, one BLAS thread, at most two
concurrent. No retries. Preserve all failures and qualifications. After
selection, recompute training/held scores with exact joint-minus-training
mixture density. Check source position gradients against complete-objective
central differences at1m and0.5m, tolerance0.002 nats/km. Held outcomes and
the exposed unsurveyed site reference remain outside fitting and selection.

Report shared-position error for each source unit and target transfer held
changes against both the original iid panel and same-model separate-panel
fit. Report source held changes similarly and all start separations. No
post-hoc choice of covariance model by geographic error. This exploratory
24-record panel does not establish full-dataset or independently surveyed
sub-kilometer accuracy even if the nominal threshold is crossed.
