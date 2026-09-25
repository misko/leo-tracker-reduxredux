# DS1 vs DS3 all-method report

Publication ready: **False**.

DS1 `unavailable` qualification means no sealed DS1 qualification record, not necessarily that no historical method result exists. `DS1_COVERAGE_AUDIT.md` lists sealed, exact-method multi-case evidence separately; it is not promoted into a ranking aggregate.

Required DS3 method arms are pending for: causal-per-norad-orbit-rate, i03-global-time-plus-orbit-rate-screen, i04-seed-union-exact-selection, i05-common-grid-timing-refinement, i06-matched-cap300-cap800, i07-ar1-student-t-rerank, i07-independent-gaussian-rerank, i18-timing-refresh, i19-rate-bound-audit, i20-session-predictive, i21-session-balanced-closure, i22-randomized-time-predictive, i23-widened-rate, i24-crossfit-rate, i25-source-admission, i27-phase-cache, i28-basin-search, i29-resolution-safe-search, soft-association.

| Method ID | Iteration | Class | DS1 qualification | DS3 | DS1 error km | DS3 qualified km | DS3 diagnostic km | Delta km | Comparability |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| baseline-doppler | None | position_method | unavailable | terminal_control | — | — | 4.231 | — | sealed DS3 control; qualification metadata unavailable |
| causal-per-norad-orbit-rate | None | position_method | unavailable | not_run | — | — | — | — | pending DS3 terminal result |
| fixed-hard-cone-orientation | None | position_method | unavailable | qualified | — | 239.344 | — | — | method-matched DS1/DS3 comparison |
| global-time | None | position_method | unavailable | terminal_control | — | — | 4.231 | — | sealed DS3 control; qualification metadata unavailable |
| global-time-plus-per-norad-orbit-rate | None | position_method | unavailable | terminal_control | — | — | 4.231 | — | sealed DS3 control; qualification metadata unavailable |
| i01-unknown-history | 1 | missing_history | unavailable | missing_historical_artifact | — | — | — | — | accounting/diagnostic only |
| i02-regularized-per-scan-time | 2 | position_method | unavailable | unqualified_boundary | — | — | 1.114 | — | terminal but unqualified; estimate is diagnostic only |
| i02-shared-global-time | 2 | position_method | unavailable | unqualified_boundary | — | — | 1.114 | — | terminal but unqualified; estimate is diagnostic only |
| i03-global-time-plus-orbit-rate-screen | 3 | position_method | unavailable | not_run | — | — | — | — | pending DS3 terminal result |
| i04-seed-union-exact-selection | 4 | position_method | unavailable | not_run | — | — | — | — | pending DS3 terminal result |
| i05-common-grid-timing-refinement | 5 | position_method | unavailable | not_run | — | — | — | — | pending DS3 terminal result |
| i06-matched-cap300-cap800 | 6 | position_method | unavailable | not_run | — | — | — | — | pending DS3 terminal result |
| i06b-legacy-session-scale | 6 | nonportable | unavailable | not_portable_legacy | — | — | — | — | accounting/diagnostic only |
| i07-ar1-student-t-rerank | 7 | diagnostic | unavailable | not_run | — | — | — | — | pending DS3 terminal result |
| i07-independent-gaussian-rerank | 7 | diagnostic | unavailable | not_run | — | — | — | — | pending DS3 terminal result |
| i08-equal-weight-joint-multiscan | 8 | position_method | unavailable | unqualified_numerical | — | — | 4.420 | — | terminal but unqualified; estimate is diagnostic only |
| i09-symmetric-joint-refinement | 9 | position_method | unavailable | unqualified_parent | — | — | 3.068 | — | terminal but unqualified; estimate is diagnostic only |
| i10-three-level-shared-refinement | 10 | position_method | unavailable | unqualified_parent | — | — | 2.819 | — | terminal but unqualified; estimate is diagnostic only |
| i11-fine-symmetric-confirmation | 11 | position_method | unavailable | unqualified_parent | — | — | 2.779 | — | terminal but unqualified; estimate is diagnostic only |
| i12-consistent-cap800 | 12 | position_method | unavailable | terminal_control | — | — | 4.031 | — | sealed DS3 control; qualification metadata unavailable |
| i12-expanded-exact-rate-only | 12 | position_method | unavailable | unqualified_boundary | — | — | 2.748 | — | terminal but unqualified; estimate is diagnostic only |
| i12-regularized-session-scale | 12 | position_method | unavailable | unqualified_convergence | — | — | 2.647 | — | terminal but unqualified; estimate is diagnostic only |
| i12-shared-norad-rate | 12 | diagnostic | unavailable | no_position_diagnostic | — | — | — | — | accounting/diagnostic only |
| i13-basin-closure | 13 | position_method | qualified | unqualified_boundary | 0.600 | — | 2.604 | — | terminal but unqualified; estimate is diagnostic only |
| i14-cap800-basin | 14 | position_method | unqualified | unqualified_boundary | 0.488 | — | 1.411 | — | terminal but unqualified; estimate is diagnostic only |
| i15-information-weighted | 15 | superseded | invalidated_by_later_audit | unqualified_boundary | 0.576 | — | 2.201 | — | terminal but unqualified; estimate is diagnostic only |
| i16-dynamic-association | 16 | position_method | unqualified | unqualified_boundary | 0.860 | — | 2.476 | — | terminal but unqualified; estimate is diagnostic only |
| i17-reacquire-then-freeze | 17 | position_method | qualified | unqualified_boundary | 0.663 | — | 2.585 | — | terminal but unqualified; estimate is diagnostic only |
| i18-timing-refresh | 18 | position_method | unqualified | not_run | 0.884 | — | — | — | pending DS3 terminal result |
| i19-rate-bound-audit | 19 | position_method | unqualified | not_run | 0.910 | — | — | — | pending DS3 terminal result |
| i20-session-predictive | 20 | position_method | unqualified | not_run | 0.267 | — | — | — | pending DS3 terminal result |
| i21-session-balanced-closure | 21 | position_method | unqualified | not_run | 0.714 | — | — | — | pending DS3 terminal result |
| i22-randomized-time-predictive | 22 | diagnostic | unavailable | not_run_diagnostic | — | — | — | — | pending DS3 terminal result |
| i23-widened-rate | 23 | diagnostic | unavailable | not_run_diagnostic | — | — | — | — | pending DS3 terminal result |
| i24-crossfit-rate | 24 | diagnostic | unavailable | not_run_diagnostic | — | — | — | — | pending DS3 terminal result |
| i25-source-admission | 25 | diagnostic | unavailable | not_run_diagnostic | — | — | — | — | pending DS3 terminal result |
| i26-quartic-rate-marginal | 26 | nonportable | unavailable | not_portable_legacy | — | — | — | — | accounting/diagnostic only |
| i27-phase-cache | 27 | position_method | unqualified | not_run | 1.113 | — | — | — | pending DS3 terminal result |
| i28-basin-search | 28 | position_method | unqualified | not_run | 1.706 | — | — | — | pending DS3 terminal result |
| i29-resolution-safe-search | 29 | position_method | unqualified | not_run_adapter_unavailable | — | — | — | — | pending DS3 terminal result |
| i30-fixed-topk-soft-preflight | 30 | preflight | unavailable | unqualified_preflight | — | — | — | — | terminal but unqualified; estimate is diagnostic only |
| i31-exact-state-soft-preflight | 31 | preflight | unavailable | unqualified_preflight | — | — | — | — | terminal but unqualified; estimate is diagnostic only |
| independent-per-track-time | None | position_method | unavailable | terminal_control | — | — | 4.231 | — | sealed DS3 control; qualification metadata unavailable |
| learned-pointing-cone-quantiles | None | diagnostic | unavailable | no_position_diagnostic | — | — | — | — | accounting/diagnostic only |
| local-fitted-full-fov-cone-position | None | position_method | unavailable | qualified | — | 250.181 | — | — | method-matched DS1/DS3 comparison |
| regularized-per-scan-time | None | position_method | unavailable | terminal_control | — | — | 4.231 | — | sealed DS3 control; qualification metadata unavailable |
| soft-association | None | position_method | unavailable | not_run | — | — | — | — | pending DS3 terminal result |
| soft-association-plus-global-time | None | position_method | unavailable | terminal_control | — | — | 4.231 | — | sealed DS3 control; qualification metadata unavailable |
| staged-full-fov-cone-sweep | None | diagnostic | unavailable | no_position_diagnostic | — | — | — | — | accounting/diagnostic only |

## Diagnostic unqualified estimates

These errors are post-seal diagnostics only. They are excluded from qualified-method ranking.

| Method ID | Iteration | Terminal status | Diagnostic error km |
| --- | ---: | --- | ---: |
| baseline-doppler | None | terminal_control | 4.231 |
| global-time | None | terminal_control | 4.231 |
| global-time-plus-per-norad-orbit-rate | None | terminal_control | 4.231 |
| i02-regularized-per-scan-time | 2 | unqualified_boundary | 1.114 |
| i02-shared-global-time | 2 | unqualified_boundary | 1.114 |
| i08-equal-weight-joint-multiscan | 8 | unqualified_numerical | 4.420 |
| i09-symmetric-joint-refinement | 9 | unqualified_parent | 3.068 |
| i10-three-level-shared-refinement | 10 | unqualified_parent | 2.819 |
| i11-fine-symmetric-confirmation | 11 | unqualified_parent | 2.779 |
| i12-consistent-cap800 | 12 | terminal_control | 4.031 |
| i12-expanded-exact-rate-only | 12 | unqualified_boundary | 2.748 |
| i12-regularized-session-scale | 12 | unqualified_convergence | 2.647 |
| i13-basin-closure | 13 | unqualified_boundary | 2.604 |
| i14-cap800-basin | 14 | unqualified_boundary | 1.411 |
| i15-information-weighted | 15 | unqualified_boundary | 2.201 |
| i16-dynamic-association | 16 | unqualified_boundary | 2.476 |
| i17-reacquire-then-freeze | 17 | unqualified_boundary | 2.585 |
| independent-per-track-time | None | terminal_control | 4.231 |
| regularized-per-scan-time | None | terminal_control | 4.231 |
| soft-association-plus-global-time | None | terminal_control | 4.231 |

## DS1 diagnostic estimates

These historical errors are retained for audit but are excluded from rankings.

| Method ID | Iteration | DS1 qualification | Diagnostic error km | Reason |
| --- | ---: | --- | ---: | --- |
| i14-cap800-basin | 14 | unqualified | 0.488 | sealed inference is incomplete |
| i15-information-weighted | 15 | invalidated_by_later_audit | 0.576 | widened-rate basin remained on the northwest boundary and is unqualified |
| i16-dynamic-association | 16 | unqualified | 0.860 | sealed qualification reports qualified=false |
| i18-timing-refresh | 18 | unqualified | 0.884 | sealed geographic_interior gate failed |
| i19-rate-bound-audit | 19 | unqualified | 0.910 | sealed qualification reports qualified=false |
| i20-session-predictive | 20 | unqualified | 0.267 | sealed geographic_interior gate failed |
| i21-session-balanced-closure | 21 | unqualified | 0.714 | sealed interior_closure gate failed |
| i27-phase-cache | 27 | unqualified | 1.113 | sealed gate failed: all_leave_one_session_center_reranks, center_winner |
| i28-basin-search | 28 | unqualified | 1.706 | transverse bracket failed |
