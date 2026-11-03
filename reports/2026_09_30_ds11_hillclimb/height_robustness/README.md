# DS11 hypothetical height robustness

All 12 fits qualified; all six scan/scenario cells have a training-selected
solution. Each child completed within 11.42 seconds. Four component tests passed
(two selection-policy tests here and two existing fixed-height model tests).

| Original scan index | Hypothetical ellipsoidal height | Displacement from refitted zero height | Changed training MAP track associations |
|---|---:|---:|---:|
| 0 | -50 m | 183.263 m | 0 / 62 |
| 0 | +50 m | 183.519 m | 0 / 62 |
| 16 | -50 m | 30.321 m | 0 / 58 |
| 16 | +50 m | 29.208 m | 0 / 58 |

Displacement uses the existing east/north parameter coordinates. These are
position movements, not position errors or improvements. No geographic error
evaluator was loaded, no scenario was ranked against ground truth, and no
antenna height was chosen. MAP indices refer to unchanged per-track candidate
banks, so index equality compares the same satellite candidate within each
track. Label stability does not establish correct labels or unchanged soft
association probabilities.

The nonlinear refits confirm that height uncertainty can matter horizontally,
especially for scan 0. They found no MAP association switches at these stress
points. This is evidence about two diagnostic scans, not a bound on all DS11
scans or on every height between the stress points. Height remains an uncertain
calibration input; this result is not a replacement positioning model.

The user supplied Apple Compass 56 ft plus approximately 10 ft to the antenna:
66 ft = 20.1168 m on the phone's elevation reference. A repeat read-only USGS
EPQS query at the stored station coordinates returned 54.571628571 metres and
179.04078188087962 feet with the respective requested units. Thus the earlier
terrain number was not a metres/feet parsing error. Terrain, phone accuracy,
exact datum, and measurement location remain distinct uncertainties; no datum
conversion or measured antenna height is inferred here.

Reproduce with the pinned release Python and single-thread BLAS settings:
`python -m unittest discover -s <this-directory> -p 'test_*.py'`, followed by
`run.py prepare`, `run.py batch`, and `run.py summarize` in a fresh output
directory. Existing results deliberately reject overwrite. Protocol and inputs
were hashed before fitting. Original causal orbit banks and production defaults
remain unchanged. No new RF was collected.
