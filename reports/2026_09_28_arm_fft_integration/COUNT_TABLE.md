# FFT host704 exact-20-ms counts

The FFT `host704-v1` run completed all 11 overlapping 20-ms windows for each
receiver of every selected dual-receiver dwell (22 windows per dwell).  Its
paired audit found complete candidate-object equality with the conditioned-CZT
baseline, so recovered positive windows and individual positive candidate hits
equal the baseline totals below.

| Rate (MS/s) | Exact 20-ms windows run | Baseline positive 20-ms windows | Recovered positive 20-ms windows | Baseline individual candidate hits | Recovered candidate hits |
|---:|---:|---:|---:|---:|---:|
| 2.5 | 3,344 | 1,682 | 1,682 | 4,573 | 4,573 |
| 5 | 4,752 | 1,874 | 1,874 | 5,466 | 5,466 |
| 7.5 | 4,048 | 1,933 | 1,933 | 5,186 | 5,186 |
| 10 | 3,344 | 1,518 | 1,518 | 4,356 | 4,356 |
| **Total** | **15,488** | **7,007** | **7,007** | **19,581** | **19,581** |

Positive means final `margin >= 0.025`.  A candidate hit is an individual
positive entry, rather than a deduplicated transmitter.  The 704 selected
dwells are unique `(session_id, visit_index)` pairs from 88 recordings (eight
per recording).  They cover 0.361% of the 194,934 published DS7 dwells; this
is a broad recording-level sample, not a full-DS7 run.

Sources: `host704-v1/manifest.json` (704 complete selected dwells, 88 unique
sessions), `host704-v1/summary.json`, the direct-original-baseline
`host704-v1/independent-summary.json`, `paired-audit.json`, and the DS7 cohort
protocol at `reports/2026_09_28_ds7_large_arm/PROTOCOL.md`.  The independent
summary directly reports these recovered window and hit counts against the
older original baseline.  It also records the inherited four low-margin
ordered candidates in one 7.5-MS/s window; there is no positive-gate crossing,
so it does not change any count in this table.
