# TRAIN-only alternating epoch and association refinement

Frozen before running this refinement. Use the complete first 72-scan TRAIN
group and all tracks selected by its existing fixed 3 s minimum-span policy.
Start each of the six arms from its corresponding conditional shared-scan epoch
fit (Sacramento/Reno, scales 0.2/1/5 s). Do not select an arm by reference error.

At the current position and scan epoch, reconsider every retained causal
satellite for every track. Use the original visibility rule, training-only CFO,
and training RMS candidate ranking. Keep track support and weights fixed.
Then use the existing bound-aware coupled Schur polish to update the shared
position and one epoch per scan, with the same original prior disks, ±5 s epoch
bounds, capped-800-Hz loss and regularization. This introduces no per-track epoch
or extra frequency-slope parameters.

Perform at most three reassignment/polish cycles per arm. Reject any continuous
update that increases the exact penalized training objective beyond 1e-9 Hz
numerical tolerance; allow 1e-7 Hz replay tolerance when checking reassignment.
Record these tolerances and each cycle's signed gain. Stop when a cycle
changes no identities and improves objective by less than 0.001 Hz. Record all
identity changes, objective changes, solver traces and termination causes.
Keep every arm, including failures or stalls. This is local alternating
refinement from a blind baseline, not a globally optimal joint search. Explicitly
label cycle-limit arms; their identities need not be optimal after the final
continuous update. Even the stability/small-gain rule is not a stationarity
certificate.

Before fitting, verify the conditional source, inference seal, exact TRAIN group,
and cache bindings. Read only its sealed inference, not its post-seal error or
held metrics. Fit and seal all six arms before held-frequency and reference
scoring. Held scoring must retain fitted identities and training-only offsets.
No validation/test evidence, new RF collection, or production changes.

Compare with the conditional model on identical support and objective. A lower
frequency residual alone does not establish better positioning. This experiment
tests whether freezing baseline identities limits the structured timing model.
