# C019 matched budget diagnostic

Increasing the per-fit allowance from 20 to 60 seconds changed strict convergence from **0/4 to 4/4**, but did not resolve localization on the tested starts. Actual accepted fit durations were 28.4–44.3 seconds. The eight-call four-worker wave completed in 115.824 seconds; all outcomes sealed before the configured-reference comparison.

The four starts were selected by minimum returned training objective within each native model's original-start and coarse-start groups. Both models selected original ordinal 0 and coarse ordinal 16. Both budget arms restarted from the same **original qualified initializers**, not the failed endpoints. Candidate bank, observations, priors, calibration, fitted c, geographic domains and strict KKT threshold remained unchanged. These four starts do not represent the full 44-call coverage inventory.

| Model | Start group | 20 s strict | 60 s strict | 60 s actual duration | 60 s KKT | Configured distance km | Selected within model at 60 s |
|---|---|---|---|---:|---:|---:|---|
| Original native | Original, ordinal 0 | Fail | Pass | 28.414 s | 0.0008714 | 142.976656 | Yes |
| Original native | Coarse, ordinal 16 | Fail | Pass | 44.321 s | 0.0005476 | 203.272227 | No |
| Native common clock | Original, ordinal 0 | Fail | Pass | 35.526 s | 0.0003851 | 143.256619 | Yes |
| Native common clock | Coarse, ordinal 16 | Fail | Pass | 31.484 s | 0.0000408 | 183.521429 | No |

The selected original-native objective was 42270.495787; the alternative coarse objective was 42897.090867. The selected common-clock objective was 41854.253146; its coarse alternative was 43552.669008. Selectors compare objectives only within a model and budget. No failed 20-second endpoint receives a localization estimate.

The prior 20-second wider-search experiment cannot be interpreted as rejecting coverage or clock modeling. The matched diagnostic demonstrates a convergence-budget limitation for these starts. Conversely, convergence does not imply a correct location: both selected positions remain far from the configured reference. That reference remains unconfirmed, and this report does not establish verified accuracy.

Next: complete the same original 44-start inventory with a 60-second allowance, retaining these four exact 60-second calls and attempting only the other forty. All initial states and selection groups are already frozen in the original coverage protocol. Retain six-original-start and all-twenty-two-start selectors separately within each model, and seal the complete inventory before reference reporting. Do not select additional starts or alter the model using these geographic errors.

Budget driver source `9ceba17bb` passed three component tests and Ruff; post-seal evaluator `3f7cf6ad7` passed two tests and Ruff. Initial-state qualification performed four objective calls, zero fits, in 46.620 seconds with zero initializer adjustment. Scientific output: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c019-coverage-budget-v1`. Post-seal report: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c019-coverage-budget-comparison-v1`. Original failed calls remain immutable and no cohort histogram was changed.
