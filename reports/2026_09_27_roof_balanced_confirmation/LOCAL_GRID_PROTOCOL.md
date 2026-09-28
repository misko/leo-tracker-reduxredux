# Equal-coordinate local-ranking diagnostic

This is post-confirmation development on all four second-cohort recordings, not a new outcome-blind validation. No outcome-based scan selection. Existing confirmation artifacts and models remain immutable.

For each independent prior, center a17×17 grid on that prior's own frozen Doppler-only selected east/north coordinate. Offsets are−4km through+4km inclusive at0.5km spacing in the original prior's coordinate chart. Clip only to the original prior disk. Include the center. Do not center on GPS/reference, a geometry winner, another prior's point, or an outcome-selected alternative.

Evaluate D and D+geometry on exactly the same grid coordinates with unchanged calibration, observations, zero timing, catalogue availability and per-location training-only shortlists. Select the best evaluated point under each score; ties by east then north. Retain a point-inventory digest, actual count, selected coordinates, scores, and boundary indicators. A boundary winner is not a converged local optimum.

Repeat reception-pair deduplication on the same grids as a sensitivity. Original D seeds must remain fixed in both variants; no reception-guided expansion. Identical coordinates isolate final local-score ranking from broad search coverage. Report both D coarse→D local and D local→joint local, avoiding attribution of all refinement gains to geometry.

Do not use these additional289-point local evaluations to claim equal cost with the old160-point standalone estimator. This is a diagnostic; the matched comparison is between scores over the same local coordinate inventory. Grid spacing alone does not measure physical resolution or uncertainty. Distance reporting remains separate from evaluation and requires all four completed artifacts per variant.

The local box can miss a displaced objective minimum or the reference. Report boundary and domain limitations. Any new location estimator developed from this diagnostic needs untouched validation, not relabeling this cohort.
