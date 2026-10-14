# Original native C: candidate-union qualification

Both DS21-035 and DS21-029 passed qualification using all twelve saved native initializers (six from each discovery run). This establishes that the preservation experiment can retain the original receiver calibration and satellite predictions. It does not establish improved localization: no optimization or reference-position evaluation was performed.

The model remains original native C, CH1–8, fitted c, without added receiver clocks or drift. Each initializer retains its original receiver alias lift and its own 25 km search disk. The union contains 55 satellites for 035 and 44 for 029. All twelve seeds per case are feasible without the original fitter adjusting their starting values.

| Case | Minimum union objective, original-discovery seeds | Minimum union objective, broader-discovery seeds | Maximum common prediction/derivative discrepancy | Elapsed |
|---|---:|---:|---:|---:|
| DS21-035 | 42917.443158 | 45169.729334 | 9.57e-10 | 35.24 s |
| DS21-029 | 41451.435701 | 39732.284180 | 7.42e-10 | 39.23 s |

These are unoptimized seed scores under the same union model within each case; they do not select or discard starts. Original-discovery seeds score better at initialization for 035, whereas broader-discovery seeds score better for 029. Neither observation predicts which optimized position will be accurate. Source-bank and union-bank objectives must not be ranked against one another because candidate priors and timing dimensions change.

Native receiver corrections close exactly (0 Hz discrepancy), common-candidate visibility masks match exactly, and native evidence, observation identities, calibration layout, ephemeris arrays, and physical timing constraints were checked. Each case used 24 objective evaluations and 24 explicit orbit predictions, with zero optimizer calls; objective-internal predictions are additional work. Source and output bindings were sealed and independently rehashed after completion.

Evidence:

- DS21-035: `local/model-c-union-qualification-035-v1/qualification.json`, SHA256 `6ebc0755696f3cc6ecc25997690bfc9f58214e9f8c6317baaa6909ccad8748a9`.
- DS21-029: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-union-qualification-029-v1/qualification.json`, SHA256 `4efd885777ca51116212514219f1971d2e529e1ddb20a4ee657162a6a7402288`.
- Frozen implementation: `tools/model_c_union_transport.py` and `tools/ds21_model_c_union_qualification.py`, through commit `df1a45d66`.

The next experiment fits all twelve starts per case under this common union model with the unchanged solver and original per-fit budget. Six broader-discovery fits can be shared between the six-start and twelve-start selectors, but their total search costs differ; this is a preservation experiment, not a matched-total-budget improvement claim. All fits must be sealed before position accuracy is evaluated.
