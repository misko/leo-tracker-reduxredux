# DS1 historical coverage audit

This audit repairs provenance visibility only. It does not turn historical multi-case development results into qualified DS1 rankings.

| Method | Iteration | Coverage | Sealed evidence | Selector | Case summary |
| --- | ---: | --- | --- | --- | --- |
| baseline-doppler | None | sealed_method_matched_evaluation | reports/2026_09_24_ds1_train_full/post-seal-evaluation/one-hour-post-seal-evaluation.json | baseline | 8 cases; 1-scan: 24.386 km, 6-scan: 13.109 km |
| causal-per-norad-orbit-rate | None | sealed_method_matched_evaluation | reports/2026_09_24_ds1_train_full/post-seal-evaluation/one-hour-post-seal-evaluation.json | causal_per_norad_orbit_rate | 8 cases; 1-scan: 24.386 km, 6-scan: 13.109 km |
| fixed-hard-cone-orientation | None | still_unavailable | — | — | — cases; — |
| global-time | None | sealed_method_matched_evaluation | reports/2026_09_24_ds1_train_full/post-seal-evaluation/one-hour-post-seal-evaluation.json | global_time | 8 cases; 1-scan: 18.262 km, 6-scan: 6.009 km |
| global-time-plus-per-norad-orbit-rate | None | sealed_method_matched_evaluation | reports/2026_09_24_ds1_train_full/post-seal-evaluation/one-hour-post-seal-evaluation.json | global_time_plus_per_norad_orbit_rate | 8 cases; 1-scan: 18.262 km, 6-scan: 6.009 km |
| i01-unknown-history | 1 | still_unavailable | — | — | — cases; — |
| i02-regularized-per-scan-time | 2 | sealed_method_matched_evaluation | reports/2026_09_24_ds1_iteration2/post-seal-evaluation/iteration2-post-seal-evaluation.json | per_scan_time | 8 cases; 1-scan: 18.362 km, 6-scan: 3.995 km |
| i02-shared-global-time | 2 | sealed_method_matched_evaluation | reports/2026_09_24_ds1_iteration2/post-seal-evaluation/iteration2-post-seal-evaluation.json | global_time | 8 cases; 1-scan: 18.362 km, 6-scan: 3.912 km |
| i03-global-time-plus-orbit-rate-screen | 3 | still_unavailable | — | — | — cases; — |
| i04-seed-union-exact-selection | 4 | still_unavailable | — | — | — cases; — |
| i05-common-grid-timing-refinement | 5 | still_unavailable | — | — | — cases; — |
| i06-matched-cap300-cap800 | 6 | still_unavailable | — | — | — cases; — |
| i06b-legacy-session-scale | 6 | still_unavailable | — | — | — cases; — |
| i07-ar1-student-t-rerank | 7 | still_unavailable | — | — | — cases; — |
| i07-independent-gaussian-rerank | 7 | still_unavailable | — | — | — cases; — |
| i08-equal-weight-joint-multiscan | 8 | still_unavailable | — | — | — cases; — |
| i09-symmetric-joint-refinement | 9 | still_unavailable | — | — | — cases; — |
| i10-three-level-shared-refinement | 10 | still_unavailable | — | — | — cases; — |
| i11-fine-symmetric-confirmation | 11 | still_unavailable | — | — | — cases; — |
| i12-consistent-cap800 | 12 | still_unavailable | — | — | — cases; — |
| i12-expanded-exact-rate-only | 12 | still_unavailable | — | — | — cases; — |
| i12-regularized-session-scale | 12 | still_unavailable | — | — | — cases; — |
| i12-shared-norad-rate | 12 | still_unavailable | — | — | — cases; — |
| i22-randomized-time-predictive | 22 | still_unavailable | — | — | — cases; — |
| i23-widened-rate | 23 | still_unavailable | — | — | — cases; — |
| i24-crossfit-rate | 24 | still_unavailable | — | — | — cases; — |
| i25-source-admission | 25 | still_unavailable | — | — | — cases; — |
| i26-quartic-rate-marginal | 26 | still_unavailable | — | — | — cases; — |
| i30-fixed-topk-soft-preflight | 30 | still_unavailable | — | — | — cases; — |
| i31-exact-state-soft-preflight | 31 | still_unavailable | — | — | — cases; — |
| independent-per-track-time | None | sealed_method_matched_evaluation | reports/2026_09_24_ds1_train_full/post-seal-evaluation/one-hour-post-seal-evaluation.json | independent_per_track_time | 8 cases; 1-scan: 12.052 km, 6-scan: 11.598 km |
| learned-pointing-cone-quantiles | None | still_unavailable | — | — | — cases; — |
| local-fitted-full-fov-cone-position | None | still_unavailable | — | — | — cases; — |
| regularized-per-scan-time | None | sealed_method_matched_evaluation | reports/2026_09_24_ds1_train_full/post-seal-evaluation/one-hour-post-seal-evaluation.json | per_scan_time | 8 cases; 1-scan: 18.262 km, 6-scan: 6.009 km |
| soft-association | None | sealed_method_matched_evaluation | reports/2026_09_24_ds1_train_full/post-seal-evaluation/one-hour-post-seal-evaluation.json | soft_association | 8 cases; 1-scan: 11.598 km, 6-scan: 11.598 km |
| soft-association-plus-global-time | None | sealed_method_matched_evaluation | reports/2026_09_24_ds1_train_full/post-seal-evaluation/one-hour-post-seal-evaluation.json | soft_association_plus_global_time | 8 cases; 1-scan: 10.145 km, 6-scan: 6.009 km |
| staged-full-fov-cone-sweep | None | still_unavailable | — | — | — cases; — |

## Limits

- A sealed multi-case development evaluation is evidence of DS1 method coverage, not a DS1 qualification.
- No selected best case or synthetic aggregate is used as a DS1-versus-DS3 ranking value.
- Rows without an exact sealed method selector remain unavailable.
