# DS6 positioning investigation: consolidated results

This report publishes the completed CFO investigation and its supporting results. It complements the [DS6 index and phase investigation](../DS6_INDEX.md). It preserves unsuccessful experiments and numerical failures rather than presenting them as improvements.

## Verified accuracy

| Estimator | Dataset | Horizontal error to operator reference |
|---|---|---:|
| Corrected independent fits | All 43 scans | Mean 3333.239 m; median 2425.128 m; maximum 8502.146 m; **6/43 below 1 km** |
| Corrected combined static-site fit | All 43 scans | **754.938 m** |
| Same combined model, random subset A | 22 scans | **935.176 m** |
| Same combined model, random subset B | 21 scans | **637.095 m** |

The combined estimates passed all nine component checks, including independent full-profile gradient and exact-orbit audits. All six optimization starts converged inside their bounds. The subset positions are 625.825 m apart. Independent fits passed seven checks, with all 129 starts converged. [Independent results](../2026_09_27_ds6_full_stationary/README.md); [combined results](../2026_09_27_ds6_stationary_joint43/README.md).

Sub-kilometre combined-site accuracy is verified on DS6. Reliable independent-scan sub-kilometre accuracy remains unresolved. The operator reference is not surveyed and has no supplied altitude or uncertainty. All geographic errors are post-fit evaluation; the reference is excluded from fitting and training winner selection. Searches are conditional local searches with inherited candidate shortlists, not blind global localization. Repeated use of DS6 for development is not independent generalization evidence.

## Numerical corrections and scientific findings

- [Causal element freshness](../2026_09_27_ds6_element_freshness/README.md): corrected stale provider selection for the first five scans; all five geographic errors improved. The other 38 reused identical elements.
- [Original offset iteration audit](../2026_09_27_ds6_offset_convergence/README.md): exposed incomplete IRLS convergence. Its all-43 test intentionally exposes one unconverged case. This historical failure is retained; it is superseded by the [stationary solver](../2026_09_27_ds6_stationary_offsets/README.md) and [full stationary refit](../2026_09_27_ds6_full_stationary/README.md).
- [Full-catalogue audit under the corrected solver](../2026_09_27_ds6_stationary_catalogue/README.md): 172 tracks and 91,353 visible track/candidate combinations across three selected scans; no omitted training-best candidate. Minimum retained probability 97.7%. This checks fitted locations, not all geographic modes.
- [Shared-position prediction diagnostic](../2026_09_27_ds6_stationary_joint43/PREDICTION_DIAGNOSTIC.md): pooled subset positions worsen conditional held prediction in 39/43 scans, despite improved geography. Model mismatch remains.
- [Range-rate audit](../2026_09_27_ds6_range_rate_audit/README.md): state-velocity and finite-difference range Doppler differ by less than 0.45 Hz raw and 0.20 Hz after subtracting a track constant. Numerical step sensitivity remains explicit; this is not an orbit-accuracy certification.

## Completed changes not adopted

| Experiment | Result |
|---|---|
| [Host timing brackets](../2026_09_27_ds6_clock_bracket/README.md) | 36/43 unrestricted timing shifts fall outside host brackets. Constraining four development fits worsened held prediction in all four; none was below 1 km. Absolute host UTC accuracy is not independently established. |
| [Correlated CFO slope uncertainty](../2026_09_27_ds6_correlated_cfo/README.md) | Learned opposite-subset slope uncertainty improved prediction but worsened geographic error against its zero-slope control in all four scans; two hit bounds. |
| [Long-track selection](../2026_09_27_ds6_long_tracks/README.md) | Training spans >=30 seconds produced two better and two worse errors, none below 1 km; all-track held prediction worsened in all four. |
| [Satellite-specific slope transfer](../2026_09_27_ds6_satellite_slope_transfer/README.md) | 703 eligible tracks, but zero targets had sufficient repeated-satellite donor coverage. This was untestable under the frozen rule, not a neutral or successful correction. |
| [Height sensitivity](../2026_09_27_ds6_height_sensitivity/README.md) | Positive tested ellipsoidal heights worsened all four development errors. No antenna altitude was inferred or calibrated from ground truth. |
| [Track influence](../2026_09_27_ds6_track_influence/README.md) | No tested deletion brought a previously failing scan below 1 km. Omitted-track prediction worsened for all 24 deletions. |
| [Track noise scales](../2026_09_27_ds6_track_scale/README.md) | Improved held prediction, without resolving positioning errors. |
| [Curvature refits](../2026_09_27_ds6_curvature_refit/README.md) | More residual flexibility did not reliably improve geography. |

Additional historical drift, fragment linking, receiver/channel consistency, uncertainty, and catalogue experiments are included in the artifact inventory. Their own reports retain exact scope, warnings, and outcomes. Phase work already published on this branch's base remains indexed by DS6_INDEX.md; it has not demonstrated useful geographic improvement beyond CFO.

## Dataset, reproducibility, and publication

DS6 contains 43 roof recordings and 95,269 visits. The [inventory](../2026_09_27_ds6_roof/README.md) and [numerical export](../2026_09_27_ds6_cfo_dataset/README.md) bind membership and inputs. Randomized whole-visit partitions are preserved across receivers and tracks; combined A/B comparisons use a reproducible whole-scan split. Models use causal TLE data through read-only ports. No new RF collection or production deployment was performed for these experiments.

Each experiment includes source, frozen protocols, machine-readable results, tests, and report-specific hashes where available. publication.json records the newly archived paths and their hashes, report links, fresh test outputs, and checks of existing seals. Logs are retained for numerical warnings and provenance. Bytecode, caches, raw IQ, and external protected TLE data are not added to Git. Recomputing scientific results requires the original read-only stores; saved-result tests generally do not.

Fresh publication checks cover the current corrected estimator and the recent experiments separately to avoid legacy research-module name collisions. Historical artifacts are not rewritten to make old tests pass. The archived exploratory pair-ranking script is not evidence of a completed ranking or additional accuracy result.

Publication verification: **33 tests passed across eight report suites; all 31 existing checksum files for the archived report directories verified with no mismatches.** A separate live `ds6_long_phase_plots/replay.py` process was writing additional phase artifacts during publication. That in-progress directory is excluded from this completed-results snapshot and remains untouched for its owning task.
