# Robust-curve reassociation checkpoint

All bounded jobs for this experiment completed. The full methods, tables and
figures are in README.md. No recording or QNAP mutation was performed.

- Radio-only partition: 676 DSX01 fragments / 18,338 Graph points; two explicit
  background points (S01 RX1 CH1 T009 endpoint and S02 RX1 CH4 T002). DS22-001:
  111 fragments / 3,510 Graph points, no membership changes. All IDs preserved.
- Fixed supplied GPS: S01 recovers 26 points in both c arms, 1,975 -> 2,001.
  Other scans retain baseline counts after a same-position state-pool safeguard.
  Totals c0/fitted-c: 10,397 / 10,378 of 20,084 raw GLRT detections.
- Important raw failure retained: repaired S02 fitted-c refit gives 98 points
  versus baseline 1,857. Old objective prefers the 98-point state: 227.35 vs
  282.67 million on identical repaired measurements. This is an objective/gate
  mismatch, not merely an optimizer choosing a worse scalar minimum.
- New research score requires every curved member's residual gates before
  ranking candidates. Failed components pay explicit clutter cost; priors and
  complexity remain. Linear/background tracks never rank calibration states.
  Saved-state audit prefers the original 1,857-point S02 state, 735.72 vs
  1,682.23 million. Only original/repaired proposals at the same known position
  enter this safeguard. No parameters are reoptimized under the new score.
- New score also prefers known-position states over the saved wrong-position
  S01 / DS22 states in both c arms. This is a diagnostic containing a known-GPS
  proposal, not a successful blind search or independent identity validation.
- Actual matched blind errors: S01 cold 41.733/41.734 km -> 41.595 km; sparse
  13-point grid retains one basin and misses a better known basin. S01 resumed
  local blind searches all end at identical 12.5298 km and 1,814 points.
  DS22-001 cold remains 14.8163 km. The <0.5 km goal remains unachieved.
- Twenty-eight current focused tests pass, with Ruff passing all changed
  experiment/component files. Additional earlier merger/experiment tests passed
  before the final score addition. All scientific job handles were polled to
  completion, including audit 26511 and report 61905 (the first report attempt
  failed due to a wrapper field; corrected renderer uses its saved consolidation).

Next bounded experiment: integrate feasible curved-track scoring into an
independent geographic proposal search, paired c0/fitted-c and conditional null
controls. Do not seed it from the known-position audit winner. Preserve old raw
results and code snapshots. Continue chronological track review at T013.

This directory is sealed with per-file SHA256 values after writing the report,
source snapshots and receipts. New runs must write new directories.
