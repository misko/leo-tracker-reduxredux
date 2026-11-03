# Complete receiver holdout

Freeze before outcomes. Nine existing DS7/8/9 eight-scan panels, two directions:
train on RX0 and evaluate RX1, then reverse. Keep all original candidate banks,
measurements, and per-track masks. Only the source receiver's training samples
fit parameters or define groups. The target receiver's entire tracks are scored
under the ORIGINAL q020 model at source-fitted E/N and recording times. No target
receiver values initialize, select, or refit parameters. This is a fixed-model
geographic-transfer score, not the full predictive distribution of a shared
slope model across both receivers. Candidate banks remain conditional existing
exports, so do not claim fully blind RF identification.

Source baseline: three starts at (E,N)=(-2,0),(0,0),(2,0)km relative to configured
origin, all times zero. Select maximum training score among qualified fits.
Do not initialize from the combined-RX optimum. Fit bounds E/N+/-12km,
recording time+/-5sec, max100 iterations/160 evaluations per start. Qualify
optimizer success, no boundary, max gradient<=0.01, finite-difference gradient
discrepancy<=0.02. Log all failures; if no baseline qualifies, stop that direction.

Shared-slope arms use the source baseline's MAP assignments, probability>=0.5,
groups of at least two source tracks by recording/candidate. Fit fixed SD0.5
and2 Hz/s priors as in the preceding report, starting at the source-only
baseline. Use128 quadrature nodes, audit256 with score/held/gradient differences
<=0.01. Evaluate source interleaved held improvement and target complete-track
score improvement separately. Geographic reference is applied only after fits.
Wall cap120seconds per panel/direction, three local CPU workers maximum.

This is receiver separation within the same scans/site, not new-site validation.
Do not promote an arm merely because it improves the source interleaved score.
