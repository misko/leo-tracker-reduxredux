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

## Stability and timing-authority audit

The `--stability` option repeats the selected-cohort inference sixteen times,
removing each NORAD-modulo-eight group, then each recording-index-modulo-eight
group. All identities and the parent quality selection remain frozen, and each
fit starts at the same parent wide-search mode. These are sensitivity tests,
not independent geographic validations or confidence intervals.

| Removed group | Satellite-group error (m) | Recording-group error (m) |
|---|---:|---:|
| 0 | 935.8 | 1043.2 |
| 1 | 1147.8 | 999.7 |
| 2 | 1228.0 | 1019.1 |
| 3 | 1044.3 | 1013.2 |
| 4 | 1036.5 | 998.8 |
| 5 | 877.0 | 888.7 |
| 6 | 1024.7 | 986.2 |
| 7 | 879.7 | 966.2 |

Only three of eight satellite removals and five of eight recording removals
remain below one kilometre. All sixteen fits converge. The full-data result
is reproducible, but is close enough to the threshold that ordinary source
removal changes whether it passes. No removal is selected as the answer.

The original [recording inventory](figures/2026_09_07_eight_hour_scan_pnt/inventory.json)
contains host-bracketed device-counter timing for these scans. Full first-sample
bracket widths range from **0.866439 to 1.923855 ms**, median **1.3336045 ms**.
This bounds the recorded host/device transaction, not an independently surveyed
absolute UTC error. Nevertheless, the fitted tens-to-hundreds-of-milliseconds
corrections cannot be explained by these bracket widths. Their improvement may
represent absorbed TLE/orbit error or other model mismatch. It is not evidence
of a measured per-recording hardware clock defect, and does not justify changing
capture timestamps or relaxing firmware timing qualification.

[Full audit inference](2026_09_20_fresh_wide_position/session-clock-audit.json)
stores both baseline fits, exact-propagation checks, and all sixteen removals.
The grouped-clock synthetic test also verifies that corrupting evaluation CFO
by 1 MHz does not alter fitted positions or clock corrections.

The next model audit should separate independently bounded receiver timing from
satellite orbit uncertainty, rather than widening clock limits until the answer
is closer to the reference. No bound or observation is selected from reference
distance. The sub-kilometre goal remains under validation.

## Separate orbit-phase experiment

The existing `polish_regional_doppler.py` was run against the same final wide
grid, with all 484 retained episodes and recorded UTC fixed. Its alternative
shares one orbit-phase correction per NORAD/TLE snapshot (269 groups), with
the existing 0.5 s Gaussian prior and ±2 s bounds. It propagates the satellite
at the displaced orbit epoch while retaining Earth rotation at the recorded
UTC; it does not rewrite reception timestamps.

| Model | Position error | Source-balanced fitting RMS | Source-balanced evaluation RMS |
|---|---:|---:|---:|
| Fixed recorded UTC, no orbit correction | 1,715.7 m | 137.17 Hz | 178.12 Hz |
| Fixed recorded UTC, bounded orbit-phase corrections | 1,967.0 m | 121.57 Hz | 164.94 Hz |

Both converge. This solver uses source-balanced robust weights, so compare
these two rows to one another rather than directly interpreting their RMS
difference from the observation-weighted recording-clock experiment.
The lower residual does not translate into a better position. These results
do not support promoting this orbit-correction model as the solution.

Reproduce with `tools/polish_regional_doppler.py --run
/tmp/leo-wide-randomized-grid05 --evidence /tmp/leo-wide-randomized-evidence
--output NEW_OUTPUT.json`. The [complete orbit-phase result](2026_09_20_fresh_wide_position/orbit-phase-inference.json)
records the assignments, regularization, fitted corrections, and convergence.
Twenty regional-search, source-selection, and local-refinement tests pass.

The next transfer experiment repeats the full 9,000-mile search on the recent
48-hour RF-only export (211 recordings / 684 tracks), rather than inheriting
the earlier field-of-view-assisted identities. The historical 937–941 m result
must not be represented as a demonstrated result on that newer corpus.

## Independent Earth-rotation check

The frame converter documents its approximation of UT1 by UTC. We checked
the [IERS rapid-service file](https://datacenter.iers.org/products/eop/rapid/standard/finals2000A.all)
rather than fitting an Earth-rotation correction from the antenna reference.
The [audit excerpt](2026_09_20_fresh_wide_position/earth-rotation-audit.json)
retains the source hash, retrieval time, exact daily rows, uncertainty, and
observed/predicted flags.

| UTC date at midnight | UT1−UTC | Status |
|---|---:|---|
| September 7 | +0.0006878 s | Rapid observed |
| September 8 | +0.0002138 s | Rapid observed |
| September 18 | −0.0091919 s | Predicted |
| September 19 | −0.0097070 s | Predicted |
| September 20 | −0.0102799 s | Predicted |

One second of Earth rotation corresponds to approximately 465.1 m at the
equator, less at the receiver latitude. These offsets therefore correspond
to at most about 0.32 m on the historical day and 4.8 m on September 20.
They cannot explain the kilometre-scale residual displacement. This is a
rotation-scale bound, not an executed nonlinear position correction. No orbit
epoch, recording timestamp, or production frame-conversion code was changed.
The recently retrieved observed values are an offline audit, not a claim that
this particular file was available during the historical recording.
