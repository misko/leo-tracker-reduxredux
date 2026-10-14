# C053 conditional view pilot stopped before any optimization

The six-fit all/low/high pilot v1 stopped during source-state qualification, before any optimizer call. Its strict no-projection check detected the original fitter's internal starting-point adjustment at the distant clock endpoint. The failed namespace is retained unchanged.

A bounded read-only domain inspection found identical behavior in all three likelihood views:

| Source endpoint | Minimum physical constraint | Maximum fitter start adjustment | Minimum nuisance-bound slack |
|---|---:|---:|---:|
| Distant/incumbent | +1.8474e-13 | 8.6644e-10 | 1662.448836 |
| Closer/shifted | −3.0411e-10 | 0 | 1340.548205 |

The shared original fitter clips coordinate bounds and rescales timing coordinates to its physical timing limits when constructing its start. Both saved endpoints pass its existing feasibility check. The additional pilot rule required adjustment below 1e-12 and therefore rejected the incumbent. No model-specific difference between all, low and high caused this stop. The postmortem domain inspection made no objective or optimizer calls.

The next version should explicitly derive one canonical starting vector per endpoint using the existing fitter, record every changed coordinate, and reuse that identical vector for all views. It must first demonstrate negligible objective/NLL changes and unchanged geographic/calibration coordinates, retain the original saved state and failed v1 receipt, and preserve the original convergence/feasibility thresholds. This is a disclosed initialization change, not a claim that v1 completed or an automatic retry.

V1 source `0ff584ff8`; evaluator `eef4927e4`. The native-model test verifies likelihood partition, six equal-budget calls, identical nuisance initialization, failure retention and no retry. A second test blocks reference access before all six outcomes seal; tests and Ruff passed. Actual v1 terminated after 10.325 seconds with `optimizer_calls: 0` and reason `No initializer projection allowed`.

Artifacts: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-clock-views-053-v1/`. No reference evaluation was run, and no half/full accuracy comparison is available from this attempt.
