# Local differential-phase development protocol

This is one bounded development replay on the reused stream-1 28.200 s, 20 ms
snippet. It is not fresh validation, association evidence, or a geometric motion
measurement. Freeze this protocol, implementation, template source, frozen
nominees, and completed nesting result before opening saved IQ.

Retain the frozen nominees, epochs, aliases, and the training-selected independent
source-by-receiver residual CFOs from the completed nested comparison. Do not
impose a shared receiver CFO, common phase, or cross-receiver fit. Use absolute
snippet sample coordinates and 200 physical 100 microsecond groups with 16-sample
guards. Assign 100 whole groups to training with `seed=20260929`; the remainder
are held. All receivers, sources, tones, and model variants share this split.

For exact templates and two prespecified controls (symbol roll 17 and swapped
source epochs), jointly fit sixteen complex tone coefficients independently in
each physical group and receiver with CFO fixed. For each receiver and source,
derive a coefficient-vector reference by SVD of training-group coefficients
only. Project every group coefficient vector onto that reference. At common raw
sample times form each source's cross-receiver phase, then their source
difference. The arbitrary coefficient gauges affect the intercept but not the
held phase evolution.

Fit an affine circular phase trend using training groups only and score held
angular RMS and residual resultant. Also report constant-phase held error and
minimum normalized projection magnitude. Preserve both the residual coefficient
slope and the physical-frequency-restored slope obtained by adding the fixed
template double-difference frequency; neither has calibrated uncertainty. The prespecified descriptive condition
is exact held resultant at least 0.8 and exact held RMS below both controls.
Failure is useful negative evidence. Success is only local conditional phase
predictability after estimating and removing a local affine rate: source-dependent channels, timing/CFO alias error, reused-IQ
selection, and the roughly 2 microradian geometry residual after affine per-dwell
nuisance prevent a speed, direction, orbit, position, or identification claim.

One replay is allowed, bounded to five minutes and 20 ms of saved capture. No RF
collection and no tuning after viewing held outcomes. A favorable result gates a
new independently associated multi-dwell test; an unfavorable result redirects
work to association and channel calibration rather than further phase fitting.
