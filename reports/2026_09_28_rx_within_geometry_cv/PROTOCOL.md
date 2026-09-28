# Within-sequence geometry: calibration recording-held-out comparison

This post-outcome diagnostic asks whether removing between-sequence geometry levels improves transfer between calibration recordings. It does not use the eight reused evaluation recordings, confirmation data, or any calibration-held-frequency outcome. It does not yet introduce persistent receiver-gain random effects; centering isolates the geometry-level contribution first.

## Fold isolation and feature definitions

Use the original six calibration recordings' 1,356 reception windows. In each of six folds, fit on five complete recordings and predict the omitted recording. Refit the already-selected `joint` empirical reference on the five training recordings, without reselecting its model family. Refit the original eight-feature mean/scale convention on those five recordings' reception forecasts, excluding the other component, including all nominees, both receivers and invisible forecasts without nominee-prior weighting. Preserve intercept center=0/scale=1 and set near-zero scales below1e-12 to1.

Absolute family uses those standardized features. Within family subtracts each exact lane × nominee × receiver reception mean from standardized columns3:8 only: up, north, east, signed-east tilt, signed-east×up tilt. Leave columns0:3 (intercept, RX, sample rate) exactly unchanged. Center the already-constructed interaction column, rather than constructing a product of centered variables.

For the omitted recording, centering uses its complete known reception forecast schedule, including invisible forecasts. It uses no observed counts, frequencies or detections. This is a covariate-conditional/transductive design: future predicted geometry is assumed available at the start of the recording's reception segment. It does not claim an unknown-future-covariate deployment result. All records' nominations and log priors remain frozen from their earlier prefix training. Sigma remains the historically chosen500Hz; this experiment is conditional on that prior research choice, not fresh nested selection of sigma.

## Fits and held scoring

Use the existing normalized empirical signal kernel and joint presence fitter, unchanged priors, bounds, exact-null competitor and D/E/S/T dimensions. Fit all four arms in both families. Both D starts use neutral beta[-2,0,0] and occupancy0.5/tau1; no coefficients learned from all six records may warm-start a fold. Within each family E/S/T may start from its immediately preceding nested arm. Save both starts and convergence outcomes; if an arm has no converged start, fail that fold without omitting it.

The identical D design is a hard invariant: absolute and within D arrays, fits and scores must agree. Score each lane of the omitted recording independently from its frozen conditional nomination prior, with actual timestamp gaps. Every reception window is scored before updating the filter. Report unpenalized predictive log density versus that fold's frozen reference and absolute density including the reference; calibration MAP penalties never enter held predictive scores.

Aggregate the six recording means equally. Primary diagnostic contrasts are within T−D and T−S; report every arm versus reference/D, paired within−absolute differences for E/S/T and per-record signs. Results select no deployment model in this stage. No new full-data fit or original evaluation-panel score is permitted here. A tilt claim would still require direction controls and independent evidence.

## Verification and bounded execution

Test geometry means near zero, D columns unchanged, fold background/scaler/start isolation, malformed excluded outcome isolation and score reconstruction. Independently audit the six folds' complete disjoint partition of1,356 source windows, optimizer outcomes, D identity and all aggregate arithmetic.

Freeze sources, tests, protocol and dataset hash before execution. First execution has one numerical thread, nice19,4GiB and a300-second wall limit. Persist each completed fold as an exclusive checkpoint. If the bound is reached, retain the run and completed folds; any continuation may execute only missing folds with identical frozen settings and a separate receipt. Never substitute a partial-fold mean for the complete result. No RF, raw IQ, QNAP mutation or multi-hour campaign is authorized.
