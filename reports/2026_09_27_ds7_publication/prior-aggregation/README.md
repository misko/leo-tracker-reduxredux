# DS7 error by dwell time and sample rate

Rows aggregate individual published selected-position errors; they are not pooled location fits.
Reno and Sacramento name search priors applied to the same recordings, not collection sites.
Dwell groups use `active_dwell_ms` (120, 240, or 360 ms), not `valid_visit_ms` (120 ms for all 88). Each recording has a nominal duration of 300 seconds.

Correction: the initial published table incorrectly grouped by `valid_visit_ms` and therefore collapsed the three active-dwell settings. This version uses the same frozen API snapshot and errors, regrouped by active dwell and sample rate. The overall 88-recording metrics are unchanged.

| Active dwell (ms) | Rate (MS/s) | N | Reno available | Reno median (km) | Reno mean (km) | Reno P90 (km) | Sac available | Sac median (km) | Sac mean (km) | Sac P90 (km) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 120 | 2.5 | 4 | 4/4 | 8.89 | 64.96 | 170.49 | 4/4 | 6.62 | 8.12 | 11.43 |
| 120 | 5 | 10 | 10/10 | 3.99 | 38.05 | 45.25 | 10/10 | 6.62 | 7.87 | 14.42 |
| 120 | 7.5 | 9 | 9/9 | 5.00 | 7.00 | 15.99 | 9/9 | 5.79 | 7.39 | 9.03 |
| 120 | 10 | 8 | 8/8 | 3.99 | 4.37 | 5.00 | 8/8 | 6.16 | 6.21 | 6.72 |
| 240 | 2.5 | 4 | 4/4 | 11.95 | 14.58 | 26.98 | 4/4 | 6.26 | 12.26 | 23.52 |
| 240 | 5 | 9 | 9/9 | 3.99 | 5.99 | 7.78 | 9/9 | 5.79 | 6.18 | 6.72 |
| 240 | 7.5 | 6 | 6/6 | 5.00 | 6.98 | 11.95 | 6/6 | 5.79 | 5.95 | 6.26 |
| 240 | 10 | 6 | 6/6 | 5.00 | 111.89 | 326.67 | 6/6 | 5.79 | 11.62 | 23.29 |
| 360 | 2.5 | 11 | 11/11 | 3.99 | 115.24 | 604.58 | 11/11 | 5.79 | 9.19 | 6.72 |
| 360 | 5 | 8 | 8/8 | 4.50 | 7.41 | 14.33 | 8/8 | 6.16 | 7.68 | 10.19 |
| 360 | 7.5 | 8 | 8/8 | 9.41 | 45.78 | 106.36 | 8/8 | 6.72 | 9.92 | 19.64 |
| 360 | 10 | 5 | 5/5 | 9.41 | 196.25 | 532.82 | 5/5 | 6.72 | 6.49 | 6.72 |
| All | All | 88 | 88/88 | 5.00 | 48.16 | 84.00 | 88/88 | 6.16 | 8.09 | 13.74 |

P90 uses linear interpolation on sorted per-recording errors; each recording has equal weight.
Missing outputs remain in the N denominator and are excluded from error summaries.

| Prior | Search complete / 88 | Below 1 km / 88 |
|---|---:|---:|
| Reno | 0/88 | 0/88 |
| Sacramento | 0/88 | 0/88 |

Recorded stopping reasons: `{"reno": ["point-budget-reached"], "sacramento": ["point-budget-reached"]}`.

These budget-limited prior searches are a different estimator from the report's 677 m full88 joint fit.
Availability means a published selected estimate exists; it does not imply exhaustive search or a qualified fix.
DS7 contains 31 recordings at 120 ms, 25 at 240 ms, and 32 at 360 ms active dwell. `valid_visit_ms` is a separate metadata field and is 120 ms throughout.
The evaluation-only reference is 37.84903264307456, -122.4856541910174 (unsurveyed).
This is descriptive single-site evidence, not a causal comparison of sample rates or dwell durations.

Snapshot UTC: 2026-09-27T23:29:37.901893+00:00. DS7 manifest SHA-256: `47007b1c18e8182f6a005dfd05c237cb3edb9bf85ae6376c99ccf29d54434109`.

[Per-recording CSV](individual.csv) · [Summary JSON](summary.json) · [Frozen API excerpts](snapshot.json)

API excerpts retain source document hashes, input bindings, search configuration, selected results and the evaluation reference; large numerical diagnostics are omitted. Original document hashes identify the full source documents, not the excerpts.

Regenerate offline with `python ../aggregate_priors.py` from this directory.
