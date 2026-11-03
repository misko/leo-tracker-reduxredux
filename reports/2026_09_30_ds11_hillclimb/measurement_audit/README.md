# Original-IID measurement audit

This bounded, read-only audit traces the 32 frozen DS11 original-IID results
through their observation exports and candidate banks.  It does not refit a
position, select a model using reference error, read IQ, or change an input.

The strongest mismatch is a tail of poorly explained whole tracks.  Across
1,923 bank-eligible tracks, the training and held median absolute residuals at
the training-selected IID endpoint are 93.04 and 101.57 Hz.  The training RMS
is much more dispersed: its median is 160.35 Hz, P90 is 683.97 Hz, and P99 is
2,642.31 Hz.  Training median absolute residual reaches 256.39 Hz at P90 and
791.85 Hz at P99.  A simple diagnostic residual slope reaches 29.50 Hz/s at
P90 and 98.11 Hz/s at P99.  These slopes are descriptions at conditional MAP
satellite candidates, not fitted physical clock terms.

This supports an explicit smooth unassociated-track alternative as the next
bounded model test.  Independent Student-t observations can suppress isolated
points, but the original likelihood still forces every retained track to exert
satellite-dependent geographic force.  A fixed-prior trend alternative tests a
coherent whole-track failure without adding a free geographic slope.

## Conventions checked

- Exported `times_s` exactly equal each public trajectory point's
  `support_center_utc_ns - start_utc_ns`.  The bank propagates at these same
  times and interpolates only the fitted recording offset on the frozen
  quarter-second timing grid.
- Measurements are deliberately represented at the canonical 11.2 GHz
  convention.  The preceding 3,983-case RF-center audit found a median
  training-shape change of only 0.488 Hz when substituting nominal pilot
  centers, with mixed held effects.
- Earlier full-catalogue audits covered nine selected DS7–DS9 tracks using
  the contrast likelihood, not this DS11 IID objective. They retained at least
  99.999863% of training mass at the tested fitted locations, but the minimum
  over local corner settings was 94.673240%. No leading candidate was omitted
  at those sampled local settings. These results do not establish DS11
  shortlist completeness under the IID model's multi-root CFO profile; the
  exporter uses a separate approximate CFO score to form its shortlists.
  Full-catalogue prior normalization and omitted numerator mass are distinct
  questions. A direct DS11 IID audit is still needed before excluding missing
  candidate support as a cause of DS11 error.
- The 1 MHz CFO prior contributes a median 0.0695 log units per conditional MAP
  track and a median 8.13 log units per scan.  Removing only that penalty at the
  frozen endpoints changes zero of 1,923 MAP candidates.  It is active but does
  not explain the current candidate selections.
- RX0 has training/held median absolute residuals of 97.14/108.24 Hz; RX1 has
  88.55/96.50 Hz.  This modest receiver-width difference agrees with earlier
  constant-scale calibration.  Wider-scale and degrees-of-freedom DS11 arms
  improved tails while worsening the all-32 median geographic error.

All residuals subtract the candidate's training-profiled constant CFO.  The
candidate is the maximum training-score visible component at the frozen IID
position and timing.  Held rows never select the candidate or CFO.  Candidate
identities are conditional likelihood assignments, not decoded satellite truth.

Machine-readable counts, quantiles, and source bindings are in `summary.json`.
