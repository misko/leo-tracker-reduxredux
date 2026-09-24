# DS1 tau-zero baseline provenance

## Reuse decision

All 20 DS1 cases map to an existing sealed tau-zero baseline arm for each prior, except the two full-TEST arms. The full TEST group is an explicit sealed failure because session 48 lacks counter-continuity authority. It must remain unavailable; an executor must not silently use 63 scans.

The existing inferences contain the complete geographic search trace and the selected point. They are suitable blind seeds because the search used randomized TRAIN rows only, fitted one constant CFO per track from those rows, selected the ordinary visible candidate by TRAIN RMS, used occupied-second weights and the 800 Hz cap, and did not fit a time shift. The first-TRAIN artifacts explicitly record `timing_s: 0.0`; the second-TRAIN, validation, and TEST baseline programs call the same `long_training_search/search.py::score_point` directly with cached tau-zero states. Their inferences state that held rows and reference coordinates were not used for fitting.

## Exact arm mapping

Coordinates below are copied from each sealed arm's `search.selected`. Preserve full JSON precision when loading them; the displayed decimals are for review.

| DS1 case | sealed inference below `reports/` | Sacramento lat, lon | Reno lat, lon |
|---|---|---|---|
| train_20260921_00_1 | 2026_09_23_long_training_search/results/inference.json | 37.666759312, -122.080186027 | 37.666400723, -122.085841613 |
| train_20260921_00_6 | 2026_09_23_long_training_search_multi/results/inference.json | 37.901880219, -122.395937882 | 37.902306009, -122.396012201 |
| train_20260921_00_16 | 2026_09_23_long_training_search_multi/results/inference.json | 37.891427279, -122.384680350 | 37.891972268, -122.386739853 |
| train_20260921_00_all | 2026_09_23_long_training_full8h_position/results/inference.json | 37.847398800, -122.399716693 | 37.847788223, -122.398527280 |
| train_20260921_16_1 | 2026_09_23_long_second8h_training_baseline/results/inference.json | 37.762759570, -122.440889319 | 37.764279822, -122.440015656 |
| train_20260921_16_6 | same | 37.801647019, -122.410267662 | 37.801847727, -122.410238870 |
| train_20260921_16_16 | same | 37.817224221, -122.439367879 | 37.816992127, -122.439691167 |
| train_20260921_16_all | same | 37.845450527, -122.424160821 | 37.845482112, -122.422919358 |
| validation_20260922_08_1 | 2026_09_23_frozen_validation/baseline/inference.json | 37.855681888, -122.462110429 | 37.856908458, -122.461158738 |
| validation_20260922_08_6 | same | 37.859518982, -122.422114427 | 37.859575629, -122.421199332 |
| validation_20260922_08_16 | same | 37.919729328, -122.358305057 | 37.920700964, -122.358803873 |
| validation_20260922_08_all | same | 37.854179032, -122.430945449 | 37.854108014, -122.429904144 |
| validation_20260921_08_1 | 2026_09_23_frozen_validation/baseline/inference.json | 38.135745941, -122.363099972 | 38.136719996, -122.361939243 |
| validation_20260921_08_6 | same | 37.852546313, -122.415352408 | 37.852704604, -122.414277752 |
| validation_20260921_08_16 | same | 37.868370975, -122.413326164 | 37.868553426, -122.412618644 |
| validation_20260921_08_all | same | 37.864770365, -122.424405861 | 37.864791546, -122.423611768 |
| test_20260922_00_1 | 2026_09_23_final_test_global_epoch/baseline/inference.json | 37.901759131, -122.411519007 | 41.893097418, -115.967473905 |
| test_20260922_00_6 | same | 37.907149290, -122.396002767 | 37.905816859, -122.396136954 |
| test_20260922_00_16 | same | 37.878874042, -122.417908677 | 37.878985573, -122.417443289 |
| test_20260922_00_all | same, sealed failure | unavailable | unavailable |

The unusual one-scan TEST Reno selection is what the sealed blind search produced. It is not a transcription error and must not be replaced using reference knowledge.

## Deterministic selectors for `fixed_cone_execution`

- `train_20260921_00_1`: top-level `searches`, keyed by `prior`.
- `train_20260921_00_{6,16}`: `views` entry keyed by `scan_count`, then `searches` keyed by `prior`.
- `train_20260921_00_all`: top-level `searches`, keyed by `prior`.
- `train_20260921_16_*`: `arms`, keyed by `(scan_count, prior)`, then `search`.
- Validation: `arms`, keyed by `(group ISO UTC, scan_count, prior)`, then `search`.
- TEST: the same selector. For scan count 64, the arm has `failure` and no `search`; fail closed.

For every available arm, use `search.selected.latitude_deg`, `search.selected.longitude_deg`, and the same `search.trace` if the full sealed trace is required. Do not select `coarse_control_selected`, a later timing inference, or an evaluated results file.

## Session-order verification

The audit compared every case in `2026_09_24_ds1/dataset.json` with its source inference:

- first TRAIN 1 uses the single inference `session_id`; 6 and 16 exactly equal each `views[].session_ids`; 72 exactly equals the full inference `session_ids`;
- second TRAIN uses the exact prefix of the top-level 79-element `session_ids` for 1/6/16/all;
- validation uses the exact prefix of the matching `groups[].session_ids` for both ISO UTC groups;
- TEST uses the exact prefix of its sole `groups[].session_ids`; the 64-member inventory, including the failed session at position 48, remains intact.

All 20 comparisons preserve order and count. The DS1 dataset SHA-256 is `9ca01caa544babf0c427871daeb08fb2b5a06598bae58e84002980c6742f715d`.

## Seals

| Artifact | SHA-256 |
|---|---|
| first TRAIN, 1 | `e22b77a70a9b46a6d27807abd4f2ab632d3faed0b0fb520a9056ccbc95d7c2a4` |
| first TRAIN, 6/16 | `f75847e0d1bc6e10c02319d9840f754c72bbaee78b6ee35bb1c2573f4193d68b` |
| first TRAIN, all 72 | `4c7e299d3e62ef5106b42df38e0f97d7f40e586763823dfc0aeb33c52a85f78b` |
| second TRAIN, all views | `d47344aa374996cd3587476fbd8f4ed7e64a22e2039be768a3523dfb62e71646` |
| validation, both groups/all views | `61d04af0cc8d95adaec8e81ac8a0c9d8db49497b09a73b6aa7d064c7e4ade8b7` |
| TEST, all views/failure | `df7467db9a912a1005f1877ab604a3bd2ad6d1f1b523719c34d9d53f22cf54e5` |

Each artifact also binds its executed search/baseline source and cache receipts internally. A consumer should verify both the file digest above and those transitive bindings before reuse.
