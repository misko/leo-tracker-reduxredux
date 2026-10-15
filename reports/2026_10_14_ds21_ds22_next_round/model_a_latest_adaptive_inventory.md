# Latest adaptive-only dataset and completed CH1–4 comparisons

DS18 is the latest verified adaptive-only numbered dataset in the repository's dataset index. Its immutable membership contains 34 recordings acquired in the UTC window October 8, 2026, 14:36:56–23:08:51. Actual first/last starts are 14:46:05.979109 and 23:03:27.633583. DS17 contains 51 earlier adaptive recordings, from 01:33:48–14:36:56 that day. DS16 contains 63 recordings from an earlier 16-hour window; its familiar 48-recording evaluation is a subset. DS21 and DS22 are later mixed fast/adaptive mints and are excluded from this adaptive-only comparison.

Membership authority: `/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_08_ds18_post_ds17/local/manifest.json`, SHA-256 `894a6f4b7055e5f6bd602f94ce3acf7f722f204c68c2b521a06dfd6be35a7516`, with its sibling seal. The index is `/home/mouse9911/gits/leo-tracker-reduxredux/docs/research/datasets.md`. Admission did not filter by signal, localization, or analysis completion. The mint contains 33 published captures and one sealed firmware archive. Both receivers remain together.

Two complete saved algorithm versions are available; they must remain separate curves.

| Fixed version | Available / assigned | Median km | Mean km | Worst km |
|---|---:|---:|---:|---:|
| Published Hard60 V2, fitted c | 34 / 34 | 1.852194 | 4.422188 | 58.693871 |
| Iteration 107 B7 research baseline, fitted c | 34 / 34 | 1.122461 | 2.691656 | 53.400741 |

Published Hard60 V2 has 10/34 below 1 km and 1/34 below 0.5 km. Its posterior frequency RMS has mean 101.057 Hz and median 97.350 Hz. Every selected endpoint satisfies the original strict 0.001 stationarity threshold. All 34 have exactly acquired CH1–4 and 1,983–3,515 selected original GLRT windows. Public read-only `Hard60Store.status` and `artifact` validate the saved document and PNG; the public adaptive capture metadata port confirms each recording digest and acquired channel set. Configuration `sha256:d1524c45e6e702008221d941240e7a0ac26f13feac87fef73e83f04c9c0a80f6` has protocol `sacramento-hard60-v1`. The fitted RF coefficient ranges from −679.742 to 143.005 Hz/GHz. This is a separate production pipeline, with different search, calibration and likelihood from the fast A/B/C research curves.

The iteration 107 B7 snapshot is already complete and consumed development evidence. Its baseline and recovery-candidate selected vectors, clocks and objectives are exactly equal for every DS18 member; the exported curve uses the prespecified baseline, not a per-recording best version. The stored complete snapshot authenticates all 68 baseline/candidate scientific receipt files. This inventory reread and streamed all 9,982,024,792 receipt bytes and verified their hashes, its protocol hash, snapshot integrity map and exact mint membership. The later iteration 164 has only 13 DS18 result directories and is not a complete replacement.

Both versions evaluate against the saved configured receiver reference at latitude 37.84903264307456, longitude −122.4856541910174. The prior is centered at Sacramento, latitude 38.5816, longitude −121.4944, radius 250 km; it is not centered on that reference. Saved products state that known position was not used for inference and position-fix claims remain false. This review does not independently verify physical station continuity. DS18 has prior research exposure: 24 members were already consumed at minting and ten had no reviewed registry match. The latter are not unseen validation. Current reporting is descriptive consumed development, with no new locked split.

Ready-to-plot source-bound outputs:

- Published V2: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-a-ds18-published-v2-inventory-v2/inventory.json` and `inventory.csv`. Every row includes assigned identity, acquisition time, status, configured distance, selected windows, fitted c, frequency RMS, configuration/input/analysis digests and source-metadata bindings.
- B7 research: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-a-ds18-saved-comparison-v1/inventory.json` and `inventory.csv`.
- Original B7 snapshot: `/home/mouse9911/gits/leo-hard60-default/reports/2026_10_09_position_error_iter107/DS18_COMPLETE_SNAPSHOT.json`, with `ds18-complete-integrity.json` and `DS18_COMPLETE_SNAPSHOT.md`.

No optimizer, objective, orbit predictor, GLRT measurement, or IQ read was performed. Earlier metadata-only attempts remain preserved: V3 has no published DS18 products; the first V2 adapter could read products but failed a visit-schema field lookup. The corrected V2 adapter verifies all 34. These were reporting failures, not scientific fit failures. No mixed DS22 cohort is exported into the comparison plot.
