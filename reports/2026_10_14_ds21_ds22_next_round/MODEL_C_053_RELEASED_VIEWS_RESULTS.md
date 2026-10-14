# C053 matched channel views after anchor-release improvement

The upper band improves when given the same newly selected full-band seed.
Consequently the previous comparison against older half fits overstated the
combined-band advantage: full still trails high by0.303118 km.

| View | Error (km) | Objective | NLL | Independent KKT |
|---|---:|---:|---:|---:|
| CH1–8 | 1.027646 | 22314.652881 | 22083.543077 | 0.000105388 |
| CH1–4 | 1.137860 | 15163.068227 | 14938.489513 | 0.000046362 |
| CH5–8 | 0.724527 | 6875.632928 | 6728.053311 | 0.000097834 |

All three fits are accepted. They receive exactly the same selected release
vector and nuisance parameters, original discovery centre,50 km radius,
20-second/600-iteration budget, full-derived candidate bank/frame and priors.
Only likelihood rows change. No initializer adjustment exceeds1e-12. Three
qualification objectives verify source replay and low/high NLL partition.
The full fit reproduces its source optimum. The reference is joined only after
all three calls and outcomes are sealed. Runtime23.675 seconds,3 new fits.

These remain conditional shared-discovery comparisons, not independent
half-band discovery. No cohort baseline changes. The next calibration-profile
test can use these newly available training-derived half positions; neither
position nor nuisance parameters should be chosen using reference error.

Driver `5b9afe0cd`, evaluator `1dd204628`;4 component tests and Ruff pass.
Namespace `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-released-views-053-v1`.
Terminal SHA256 `ad64036f0aef250a3595e5a70c5f598fe713830a5c98e1c8f89e6057c6aefd90`.
Seal SHA256 `45f00b813b0295dbb8fc58be29fe495d4ed0a2506ee51e62d4d6414c95f60faf`.
