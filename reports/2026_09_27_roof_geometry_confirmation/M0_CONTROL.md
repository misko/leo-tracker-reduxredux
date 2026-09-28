# Direction-free M0 reception control

Frozen as a post-hoc likelihood decomposition. It does not replace or rerun the
predeclared D or D+geometry searches and uses no new cohort or reference error.

`topology_m0_calibration.json` independently fits the direction-free detection
and conditional log-margin-ratio models on exactly the same six calibration
scans and topology-retained tracks as the amended M1 calibration. The ratio
variance is recomputed from M0 residuals using the same equal-track weights.
M1 nuisance coefficients or variance are not reused.

At confirmation scoring, use M0 predictions for each endpoint, set both east
slopes to zero, and pass those rows through the unchanged track-wide candidate
identity marginalization. Detection contributes for every available endpoint;
the ratio density contributes only when matched; the denominator remains every
reserved Doppler observation. Because M0 reception likelihood is independent
of candidate and location, it factors exactly into D plus a track-specific
constant. Therefore an M0-guided search must have the same ordering and trace as
D. Any coordinate difference is an implementation error.

The comparison is `D`, `D + RX_M0`, and `D + RX_M1`. Only the M1-minus-M0
profile isolates the incremental calibrated direction term on a matched point
inventory. This remains a conditional composite-likelihood diagnostic, not an
independent satellite-identity or surveyed-position claim.

The six calibration scans contain 2.5, 7.5, and 10 MHz sample rates. The fresh
cohort also contains 5 MHz, which is unseen during calibration. Under the frozen
feature encoder, unseen 5 MHz rows receive the reference-level sample-rate
effect. This limitation applies to M0 and M1 and must be reported rather than
silently interpreted as a calibrated 5 MHz nuisance correction.
