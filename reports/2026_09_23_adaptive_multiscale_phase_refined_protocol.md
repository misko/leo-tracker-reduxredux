# Frozen protocol: adaptive 120/60/20 ms phase replay with train-only within-frame CFO refinement

Retrospective development replay of `scan-hop-28d7592ea614f624` visits 1065,
1077, 1109, 1113, and 1140: the fixed subset with at least two current
phase-blind receiver pairs in the previously raw-audited 20-visit cohort. Read
each 120 ms visit once (0.60 s total). Use the prior train-only raw receiver
offset recorded by that audit and the current public GLRT epochs/CFOs.
Order the two bound sources by RX0 acquired CFO, so DD is high minus low. Use
the manifest-bound lower-edge template and apply each source's fractional epoch
both to IQ interpolation and its carrier coordinate.

At the 60 ms visit center, process nested 120, 60, and 20 ms chunks. Compare
frozen GLRT timing with a train-frame local ±80-sample search. Use the same
seeded frame ordinal split for both sources. Fit receiver-product residual
frequency on training frames; measure held phase at the common center without
refitting. Restore each source's two coarse carrier coordinates exactly once,
then form ordinary-2π DD. Retain rolled-17 and +37-sample timing controls and
all failures. Treat 120 ms as an internal reference, not truth. Plot wrapped
per-visit points only; never unwrap or join retunes.

Before each 64-symbol coherent sum, estimate a separate within-frame residual
CFO for each receiver using training whole frames only, through the production
`coherent_pilot_frames` estimator. Apply that frozen residual to held exact and
control symbols. This corrects the known v1 frontend omission without searching
source aliases or changing the frozen cohort.
