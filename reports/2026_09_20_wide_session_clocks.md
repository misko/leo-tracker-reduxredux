# Recording-specific UTC corrections after the wide search

Allowing each recording a separate UTC correction reduces horizontal error
below one kilometre in both tested cohorts. This is a preliminary numerical
result, not yet a validated accuracy guarantee: several fitted corrections
reach the existing −0.5 s bound.

The parent is the [fresh Denver-centred 9,000-mile search](2026_09_20_fresh_wide_position.md).
Satellite identities, source observations, randomized partitions, and quality
selection are frozen from that run. No antenna coordinate enters inference.
Each source retains its own constant frequency offset. Only recording UTC
corrections replace the shared UTC parameter; no frequency slopes are added.

| Cohort | Latitude | Longitude | Horizontal error | Fitting RMS | Random evaluation RMS |
|---|---:|---:|---:|---:|---:|
| All retained episodes | 37.8561638963 | −122.4799792474 | 936.5 m | 135.88 Hz | 161.93 Hz |
| Previously quality-selected episodes | 37.8563500658 | −122.4802758995 | 940.8 m | 75.31 Hz | 88.31 Hz |

Errors are spherical great-circle distances with radius 6,371,008.8 m to the
user-supplied evaluation coordinate 37.84903264307456, −122.4856541910174,
computed after inference. The corresponding shared-clock errors were 2,051.0
and 1,067.7 m. Both optimizations converge. Seven of 24 all-cohort clocks and
one of 23 selected-cohort clocks reach the negative bound. The clocks may
absorb orbit or model errors; this does not measure firmware timing error.

Exact SGP4 propagation at every fitted recording correction followed by a
position-only refit reproduces both positions to substantially below one metre.
The stored exact-refit clock is zero because its satellite states already
include the recording-specific corrections.

The RF audit found that all historical input RF centres match the repository's
published pilot-band centres. A bandwidth-dependent tuner-centre discrepancy
therefore does not explain the earlier historical result. This check does not
establish absolute oscillator calibration or audit all modern wideband exports.

## Reproduction and remaining validation

Run `tools/replay_wide_session_clocks.py --run /tmp/leo-wide-randomized-polish
--evidence /tmp/leo-wide-randomized-evidence --output NEW_OUTPUT.json` with
`PYTHONPATH=src:tools` and the scientific dependencies documented in the parent
report. It refuses to overwrite an output. The [inference JSON](2026_09_20_fresh_wide_position/session-clock-inference.json)
includes parent/state digests, clock values, both cohorts, and exact refits.
The existing synthetic cohort replay test passes, including recovery of
separate clock groups and invariance to evaluation-data corruption.

Before treating this as the completed positioning result, test satellite/session
stability and the active clock bounds using physically supported timing limits.
Do not choose bounds or observations based on distance to the reference.
