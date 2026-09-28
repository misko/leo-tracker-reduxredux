# Complete DS7 shared-scale localization

Use every one of the88 validated DS7 manifest recordings from full-manifest
input checkpoint02. No recording substitution/exclusion based on fit outcome.
Use unchanged shared track scale likelihood (decay0), candidate banks, weak
offset prior, catalogue normalization and whole-visit partition. This extends
the30-record geographic result; DS8/DS9 complete inputs are still pending.

Three generic starts E/N(0,0), (3,-3), (-3,3)km; all88 timings zero. No complete-
or partial-dataset solution used as initialization or fallback. L-BFGS-B settings
maxiter140/maxfun200, ftol1e-14, gtol1e-8, maxls30; bounds +/-12km and +/-5s.
Qualify optimizer success, interior parameters and gradient infinity norm<=0.01.
Select highest training score among qualified starts. Retain all failures.
No automatic retries or relaxed gates.

Seal fits before held audit. Training replay tolerance1e-7; E/N gradient checks
at1m/0.5m, full-objective discrepancy tolerance0.002. Reconcile all5131 eligible
tracks,143207 training and95894 held observations. Keep11 track exclusions
explicit; all88 recordings remain. Compare held scores on the original30 tracks
against the prior combined30 fit, separately for its union/outside constituents.
The additional58 have no prior shared-scale geographic fit baseline: report
their absolute scores/counts without inventing a change statistic.

Use the same exposed unsurveyed operator reference only after sealed execution
and numerical checks. Report all three errors and qualifications, not just the
winner. No surveyed accuracy or independent new-site validation claim.

One modeling worker, BLAS1/nice19,12GiB address-space cap and300s per process.
Require MemAvailable>=14GiB before each job. The previous45-record model peaked
near3.2GiB RSS; increased cap supports88 records without changing the optimizer.
May overlap one independent serial input-export worker; no more than two
scientific jobs total. No waveform reads, exports, propagation, provider fetch,
RF collection or component changes within this modeling experiment.
