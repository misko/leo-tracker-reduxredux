# All six A paths: releasing contrasts does not beat the joint incumbents

**No new continuation improves the existing B joint winner on either case.**
All 24 fixed/free fits pass strict convergence. Releasing frozen receiver
contrasts lowers training J and NLL on every path, but does not repair the
unresolved A localization failures. The larger improvements obtained by
retaining historical B results are not new experimental gains.

| Case | Training-selected fresh fixed | Training-selected fresh free | Fixed → free fresh J | Fixed → free fresh NLL | Fixed → free fresh error km |
|---|---|---|---:|---:|---:|
| 029 | A4 | A4 | 34490.580765 → 34229.687319 | 34211.560896 → 33862.319801 | 116.682586 → 114.420846 |
| 071 | A2 | A2 | 36875.422356 → 36758.269054 | 36522.794355 → 36401.589534 | 57.398154 → 57.652048 |

| Case | Proper fixed-family selector | Proper free-family selector | Free incumbent J | Free incumbent error km |
|---|---|---|---:|---:|
| 029 | Fresh fixed A4, equivalent old A point | Retained historical B | 33977.015658 | 63.286893 |
| 071 | Fresh fixed A2, equivalent old A point | Retained historical B | 35276.749686 | 2.242587 |

The fresh free winners remain 252.671661 and 1481.519369 above the existing
joint incumbents in J. The original fixed selectors and practically identical
positions remain available. There is no best-by-distance seed or endpoint
selection. Both full matrices seal before any new configured-reference join.

## What changed

Every one of the six strict original coverage A final states in each case
receives two full fits. Fixed keeps its path's learned high-minus-low shift;
free releases that constraint in the **existing B folded-frequency model**.
Both begin with exactly the same physical native-row calibration, geography,
timing, common clock, c and priors after the qualified raw-to-centered intercept
transport. The fixed arm explicitly includes the frozen shift's 50 kHz prior
as a constant, matching the free arm's physical offset prior.

The observation density remains the original hard-visibility/uniform-candidate
likelihood. No q tail, smooth visibility, new candidates, search centers or
expanded disks enter. Banks remain 25 satellites on 029 and 39 on 071; all own
25 km local disks and the original 250 km global prior remain unchanged.
This is a sequential-initialization/constraint-release sensitivity, not a new
architecture. Historical A/B pipeline costs and existing starting inventories
differ; the equal new budgets do not establish an equal-total-cost comparison.

All six strict original A states remain eligible in the fixed selector after
adding their constant prior. The strictly replayed historical B training
minimum remains eligible in the exact same free family. Its higher-J original
siblings cannot improve that retained minimum. The twelve new free fits do
not supersede that incumbent on either case.

## Bounds, failures and source closure

- **24/24 strict**, 12/12 per case; no failure, missing outcome or retry.
- **5042 actual objective evaluations**: 3180 on 029 and 1862 on 071.
- Each fit retains 20 seconds, 2000 actual objective evaluations including one
  reserved independent endpoint audit, and 600 iterations. Maximum measured
  fit time is 5.781 s; the independent unit limits are 120/135/140 seconds.
- Four single-thread workers run separate finite case waves in 15.086/13.944 s.
- The earlier exact qualification uses 46 objective evaluations and zero fits;
  those costs are additional. Its native-row, likelihood, prior, gradient,
  domain and finite-difference closures are separately documented in
  [the qualification report](model_a_029_071_qualification_results.md).
- All calls have durable launch/call/result/termination receipts. Saved results
  precede the final source check, preserving evidence even if validation fails.
  Source and qualifier bytes remain frozen; component and actual numerical
  integration tests pass (5 control tests, 8 transport/qualification tests).

The 029 seal is `sha256:41fafe253a09c345d99d8e481d31ce0de3def1da49163df414b154d527f8700b`;
the 071 seal is `sha256:d89ee30e7fc698fca9adb4944154f796f9b66926ae9274fdef173afa7f1deb05`.
The paired evaluator verifies both complete twelve-unit matrices and their
own-family selectors before reference access. All 24 fresh outcomes, including
their configured distances, appear in
[CSV](model_a_all_path_contrast_outcomes.csv) and
[the bound numeric report](model_a_all_path_contrast_results.json).

## Mechanism and next question

The earlier large released-offset gradients correspond to real attainable
likelihood improvement. They do not establish that those constraints caused
the position error. The complete A states remain in basins that fail to reach
the already demonstrated lower joint objective, even after all six contrasts
are released. 071's existing B position lies in A's current search domains;
merely adding more geographic starts is therefore not the first explanation.
029 already had a negative original-solver fixed-union preservation pilot.

A separate next question is whether the satellite-detectability likelihood
qualified on 035/053 transfers to 029/071. It must retain every genuine current
A source and its full frozen calibration function, use zero-initialized q
parameters, and qualify shared-versus-band nesting and actual derivatives
before fitting. No case-specific 035/053 folds or configured-reference seeds
may enter. That is a different likelihood experiment, not an interpretation
of these completed fixed/free results.

The cohort curves remain unchanged. These are repeatedly exposed development
cases and distances to the existing configured station, without new physical
station confirmation. Frequency fit, strict convergence and position accuracy
remain separate outcomes. No result is promoted.
