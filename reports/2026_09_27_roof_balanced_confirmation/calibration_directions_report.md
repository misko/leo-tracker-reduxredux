# Robust calibration direction reconstruction

The frozen robust Student-t top-three identities and weights were projected at the known sites of the same six calibration scans. The extraction covers exactly 344 topology-retained tracks and 6,378 reception observations. It used no development/confirmation location, distance error, search result, or refit.

All cache, input-manifest, analysis-manifest, evidence, snapshot, source-link, topology-audit, known-site association, and frozen-parameter bindings passed. The parameter artifact binds to the exact fixed-point extraction and values (`scale_hz=130.0352477522671`, `df=1.5307006392659719`). Across 16,155 shared old/new candidate-observation comparisons, independently reconstructed tau-zero east/up components agree to a maximum absolute difference of `8.88e-16`; this rules out an observable propagation-time or coordinate-convention change in the comparison.

## Feature movement

Under the model-relevant track-equal summary, mean east/up movement is 0.02963 overall. It is 0.43052 for the 20 MAP-changed tracks and 0.004883 for the 324 MAP-unchanged tracks. Under occupied-second weighting those values are 0.02628, 0.42172, and 0.003136, respectively.

For the descriptive observation-equal view, the mean absolute east change is 0.02554 overall, 0.41499 for the 358 rows on MAP-changed tracks, and 0.002377 for the 6,020 rows on MAP-unchanged tracks. Dense tracks receive more influence in this view, so it is not a replacement for track-equal calibration weighting.

The result confirms that the association inconsistency produces substantial direction-feature movement primarily in the small MAP-changing subset. It supports a later calibration-only mixture refit, but this extraction performs no refit and makes no geographic-performance claim.

`calibration_directions_data.json` preserves, for every reception row, each old and robust candidate ID, weight, east/up component, both weighted means, exact observation ID/time/index, track weight, and movement. `calibration_directions_summary.json` contains the exact hashes and aggregation definitions.
