# Complete DS9 shared-scale localization

Use all 105 validated DS9 manifest recordings from full-manifest input
checkpoint 09-full-ready. Refuse preparation unless its DS9 group is complete
and its ordered identities match the frozen manifest. Preserve all track
eligibility exclusions and the separately validated DS9-F028 recovery. Never
remove or substitute a recording based on fit outcome. Freeze the checkpoint's
track, training, held and exclusion counts in the input plan.

Use the unchanged shared-track-scale likelihood (decay 0), candidate banks,
weak offset prior, catalogue normalization and whole-visit partition. The
runner and launcher are byte-for-byte copies of complete DS7/DS8 execution.
Three generic E/N starts are (0,0), (3,-3), (-3,3) km, with all 105 timings zero.
No earlier fitted position or timing vector initializes or replaces a fit.

L-BFGS-B uses maxiter 140/maxfun 200, ftol 1e-14, gtol 1e-8, maxls 30; bounds
are +/-12 km and +/-5 seconds. Qualification requires optimizer success,
interior parameters and gradient infinity norm <= 0.01. Select the greatest
training score among qualified starts. Retain every failure; no automatic
retries, relaxed gates or earlier-fit fallback.

Seal source fits before the selected-point held audit. Require training replay
within 1e-7, E/N finite-difference gradient checks at 1 m and 0.5 m within 0.002,
exact identity/track/count accounting, and an independent spherical-distance
check. Compare matched original30 held scores with their prior combined30 fit,
separately for union15 and outside15. The additional75 have no prior shared-
scale geographic baseline: report absolute scores and counts only.

Use the exposed unsurveyed operator reference only for post-fit evaluation.
Report errors and qualifications for all starts, not just the winner. No
surveyed accuracy, blind validation, independent emitter identity, calibrated
confidence radius or new-site accuracy claim.

One model worker at a time, BLAS1/nice19, 12 GiB address-space cap, 300 seconds
per process, and MemAvailable >= 14 GiB before launch. No simultaneous input
pool or other scientific modeling worker. Observed peak RSS was 5,981,068 KiB
for complete DS7 (88 records) and 4,335,612 KiB for complete DS8 (65 records).
This larger 105-record run retains the same limits; failures remain explicit.
No waveform reads, exports, new propagation, provider fetch, RF collection,
component changes or golden-fixture changes occur within this model experiment.
