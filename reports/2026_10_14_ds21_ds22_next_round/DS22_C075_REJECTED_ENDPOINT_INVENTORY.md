# C075 rejected expanded-bank endpoints do not reveal a lower-score incumbent

The complete44-result,87-satellite,60-second coverage experiment contains24 strictly accepted and20 rejected outcomes. This new inventory reconstructed the unchanged native models and constraint geometry without calling any objective, optimizer, or reference. All20 rejected outcomes have finite complete physical/nuisance states and satisfy their original feasibility constraints. None has a lower saved objective than its own model's accepted winner.

| Model | Rejected outcomes | Best rejected ordinal | Objective above accepted winner | Smallest recorded rejected KKT |
|---|---:|---:|---:|---:|
| No-clock native | 7 | 7 | 2302.777227 | 0.412357 (ordinal10) |
| Native common receiver clock | 13 | 0 | 696.813025 | 24.984094 (ordinal9) |

Both accepted winners are original ordinal2, at objectives39905.834144 and39447.108044 respectively. Every rejected call reports solver_success=false and approximately60 seconds of fitting. Recorded KKT values span0.412357–4999.846741, far above0.001. These are saved stationarity receipts, not newly recomputed gradients. There is no demonstrated lower-objective feasible competitor or near-threshold endpoint that would motivate another numerical polish analogous to C019.

Constraint reconstruction found a timing boundary at clock ordinal4, a local-disk boundary at clock ordinal5, and a timing boundary at no-clock ordinal13. The other17 rejected endpoints have no active timing, disk, physical-box, or nuisance-box constraint under the audit tolerances. No-clock13's generic fitter initializer would change its timing chart by8.998e-10; no initializer was applied and no fit was launched. All other reconstructed initializer deltas were zero.

The audit completed in42.76 seconds with zero objective evaluations and zero fits. Source `ce116e198`; native component test confirms the inventory cannot invoke the objective and rejects infeasible nuisance values; Ruff passed. Namespace `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c075-rejected-inventory-v1`, report digest `sha256:2d72a1f01ea9d5b35cb6a52241ce6fa37a5904849c50dd9278e9105da4a9cdbf`. All original fits remain unchanged.

This does not prove that further search cannot improve the objective. It removes the specific evidence of an already-saved lower-score rejected basin. The next bounded comparison is the missing same-bank half-view control, using two prespecified full-training source states per native model, rather than blindly repeating44 fits.
