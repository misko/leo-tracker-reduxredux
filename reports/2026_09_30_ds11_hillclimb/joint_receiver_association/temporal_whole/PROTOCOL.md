# Time-correlated whole-source positioning with calibration fallback

Use the identical eleven-record panel from acquisition_position, without dropping
failed calibration settings. Families 2,4,6,7 use their temporal_acquisition tau
and fixed signed emission coefficients. Families 3,5 use the Doppler-only
objective because their temporal geometry screens failed. The two 2.5MS/s
settings remain Doppler fallback if this model proceeds to the full corpus.
This is a calibration-selected policy, not target-error-selected family tuning.

Sum all source assignments with the existing exact DP and raw observation
ownership alternatives. A source may explain multiple fragments on either RX.
Aggregate one RX state per source/window, then use the normalized refresh-state
filter across its complete detection-window sequence. Windows containing only
held detections advance the latent state but are unobserved during training;
00 windows remain outside this conditional model. Source/window timestamps
are observation-design covariates, not newly used held response labels.
Propagate analytic emission sensitivities through the filter. Keep original
causal orbital banks, CFO profiles and zero height. Do not freeze geometry or
candidate identities, prune candidates, add arbitrary evidence weights or
fit tau from DS11 errors.

Verify tau=0 parity against the existing whole-source model, arbitrary missing
windows against the scalar filter, exhaustive tiny assignment sums and finite
differences. Check real-scan derivatives and runtime on original index0 before
fitting. Every child ≤90 seconds; ≤3 single-thread workers. Preserve failures.

Fit 22 cells (Doppler control and calibration-selected candidate per recording)
from the original IID seeds. Bounds EN±12km/time±5s; L-BFGS-B maxiter100,
ftol1e-13, gtol0.001, maxls25. Qualification stays solver success, bound margin
≥0.001, raw gradient≤0.01, derivative discrepancy≤0.02. Read reference errors
only after all cells terminate. The unchanged cohort-separated accuracy gate
requires all fits qualified, ≥5% median reduction, strict majority wins and no
P90 increase against both original IID and refitted Doppler. Fallback records
stay in all denominators. Passing requires further controls/full-corpus
confirmation. Failure ends this variant, not the full DS11 objective.
