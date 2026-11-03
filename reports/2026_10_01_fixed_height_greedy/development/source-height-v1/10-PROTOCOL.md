# Fixed sea-level height and greedy recovery

Objective: obtain converged, useful single-scan horizontal location estimates,
starting with the greedy algorithm. User specified receiver height 100 ft above
mean sea level (30.48 m). Convert to ellipsoid height at each candidate location
using an independently sourced geoid; never initialize from receiver GPS.

Preserve all previous source-bound experiments. Reuse the identical 64 recording
selection, Sacramento 250 km intended uniform prior, causal satellite catalogue,
physical observation IDs, overlap exclusion, and original RF noise model.
Each recording starts independently. These previously inspected scans are a
regression panel, not an unseen validation set.

First isolate fixed-height greedy from subsequent changes. Remove height from
the estimated state rather than imposing an artificial tiny variance. Preserve
the other priors and physical support diagnostics. Record every attempt and
every failed prefix. A completed fit is not automatically a correct location.
Evaluate horizontal error only after predictions are sealed.

Development begins with DS9-F001, DS10-F001, DS11-F001, then extends to at most
eight scans per reviewed batch. Real fits use at most two simultaneous workers,
one numerical thread each, initially 90 seconds per attempt. No RF collection
or raw-IQ processing. Large state files remain in the SSD user cache.

Subsequent experiments may improve orbit coverage, nonlinear conditioning,
bounded multiple-hypothesis search, and joint refitting. Changes must have
component-owned tests and be isolated in separately named, source-bound runs.
Numerical convergence, support validity, empirical accuracy, and uncertainty
calibration are separate outcomes. No reference-error tuning of individual
scans and no acceptance obtained merely by deleting failed scientific checks.
