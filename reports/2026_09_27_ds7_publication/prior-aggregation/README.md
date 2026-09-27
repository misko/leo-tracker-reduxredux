# DS7 error by dwell time and sample rate

Rows aggregate individual published selected-position errors; they are not pooled location fits.
Reno and Sacramento name search priors applied to the same recordings, not collection sites.
Dwell is valid per-visit time, not the nominal 300-second recording duration.

| Dwell (ms) | Rate (MS/s) | N | Reno available | Reno median (km) | Reno mean (km) | Reno P90 (km) | Sac available | Sac median (km) | Sac mean (km) | Sac P90 (km) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 120 | 2.5 | 19 | 19/19 | 5.00 | 83.46 | 311.38 | 19/19 | 6.53 | 9.61 | 16.90 |
| 120 | 5 | 27 | 27/27 | 3.99 | 18.28 | 15.84 | 27/27 | 6.53 | 7.25 | 9.80 |
| 120 | 7.5 | 23 | 23/23 | 5.00 | 20.48 | 18.32 | 23/23 | 5.79 | 7.89 | 15.97 |
| 120 | 10 | 19 | 19/19 | 5.00 | 88.82 | 270.87 | 19/19 | 6.53 | 7.99 | 8.06 |
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
All 88 recordings have a 120 ms valid dwell and nominal duration of 300 s; dwell-duration effects cannot be estimated here.
The evaluation-only reference is 37.84903264307456, -122.4856541910174 (unsurveyed).
This is descriptive single-site evidence, not a causal comparison of sample rates or dwell durations.

Snapshot UTC: 2026-09-27T23:29:37.901893+00:00. DS7 manifest SHA-256: `47007b1c18e8182f6a005dfd05c237cb3edb9bf85ae6376c99ccf29d54434109`.

[Per-recording CSV](individual.csv) · [Summary JSON](summary.json) · [Frozen API excerpts](snapshot.json)

API excerpts retain source document hashes, input bindings, search configuration, selected results and the evaluation reference; large numerical diagnostics are omitted. Original document hashes identify the full source documents, not the excerpts.

Regenerate offline with `python ../aggregate_priors.py` from this directory.
