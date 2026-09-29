# Complete DS8 shared-scale localization

Use all 65 validated DS8 manifest recordings from full-manifest input checkpoint
08-pool-ds8-ready. Refuse preparation unless its DS8 group is complete and its
ordered identities match the frozen manifest. Preserve track eligibility
exclusions; never remove or substitute a recording based on fit outcome.
Freeze the checkpoint's track, training and held counts in the input plan.

Use the unchanged shared-track-scale likelihood (decay 0), candidate banks,
weak offset prior, catalogue normalization and whole-visit partition. The runner
and launcher are byte-for-byte copies of the complete-DS7 experiment. Three
generic E/N starts are (0,0), (3,-3), (-3,3) km, with all 65 timings zero. No
previous fitted position or timing vector initializes or replaces a fit.

L-BFGS-B uses maxiter 140/maxfun 200, ftol 1e-14, gtol 1e-8, maxls 30; bounds
are +/-12 km and +/-5 seconds. Qualification requires optimizer success,
interior parameters and gradient infinity norm <= 0.01. Select the greatest
training score among qualified starts. Retain every failure; no automatic
retries, relaxed gates or earlier-fit fallback.

Seal source fits before the selected-point held audit. Require training replay
within 1e-7, E/N finite-difference gradient checks at 1 m and 0.5 m within 0.002,
exact identity/track/count accounting, and an independent spherical-distance
check. Compare matched original30 held scores with their prior combined30 fit,
separately for its union15 and outside15 panels. The additional35 have no prior
shared-scale geographic baseline: report absolute scores and counts only.

Use the exposed unsurveyed operator reference only for post-fit evaluation.
Report errors and qualifications for all starts, not just the winner. No
surveyed accuracy, blind validation, independent emitter identity, calibrated
confidence radius or new-site accuracy claim.

One model worker at a time, BLAS1/nice19, 12 GiB address-space cap, 300 seconds
per process, and MemAvailable >= 14 GiB before launch. No simultaneous input
pool or other scientific modeling worker. Complete DS7's maximum observed RSS
was 5,981,068 KiB across 88 records; this experiment has 65 records. These are
execution limits, not changes to scientific settings. No waveform reads,
exports, new propagation, provider fetch, RF collection or component changes.
