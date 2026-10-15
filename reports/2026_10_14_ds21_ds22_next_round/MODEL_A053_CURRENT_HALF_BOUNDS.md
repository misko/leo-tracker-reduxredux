# A053 latest full selector versus accepted half-view bounds

The new 1.148233 km full selector does not demonstrate another half-view search shortfall. Replaying its complete state under each unchanged half objective gives a worse score than that half's accepted incumbent. This is a limited feasible-bound check, not a claim of global half-view optimality.

| Conditional view | New full state scored on this view | Accepted half objective | Difference |
| --- | ---: | ---: | ---: |
| CH1–4 | 12919.508371 | 12871.464237 | +48.044134 |
| CH5–8 | 6659.614037 | 6142.299734 | +517.314303 |

Five objective evaluations independently replayed the current full incumbent, both current half incumbents, and both masked evaluations of the full state. Source objective/NLL/KKT checks pass, and the full NLL and physical/nuisance gradients partition into the half likelihoods with the shared prior counted once. No localization fits or reference accesses occurred.

The current accepted comparison remains full/low/high **1.148233 / 1.659857 / 1.444907 km**, as reported by the preceding sealed experiments. The earlier low-view gap (a full state scoring better than the accepted low fit) has been repaired by the visibility-event starts. Further improvements still require scientific validation; this diagnostic alone does not justify additional identical half-view retries.

Source `96d882d59`; one test and Ruff pass. Evidence: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-a053-current-half-bounds-v1`. All source identities and the diagnostic result are sealed. No held observations or reference-selected states were used.
