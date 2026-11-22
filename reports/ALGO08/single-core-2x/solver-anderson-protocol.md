# Predeclared native precision-update acceleration

## Method

Use the released native solver on the already captured corrected DS30-0008 and southern containing witnesses. Start every call at the original cold Gamma rates. Keep the full observation likelihood, covariance, conditioning checks, original precision tolerance of `1e-5`, and 256-update limit. Each accelerated trial fits a depth-three Anderson combination in log-rate coordinates using four ordinary mappings. Reject a normal-equation Cholesky pivot at or below `1e-10` times the largest Gram diagonal, extrapolation with coefficient absolute sum above eight, proposals below either Gamma rate floor, and candidates more than four ordinary log-rate steps from the latest ordinary successor.

Evaluate the ordinary successor before testing a proposal. The proposal must reduce the measured maximum log-rate residual at least 20% compared with that actual ordinary successor. Rejected proposals resume the exact ordinary continuation. Clear history after every proposal. Retry the original cold solver if the accelerated call fails a numerical check or exhausts its update budget. The method reads no location, truth, owner labels or capture identity.

## Admission before any complete solve

Use five alternating saved-kernel evaluations after warmup. Every witness must preserve the original kernel decision and the likelihood normalization and effective observations exactly. Compare the finite-budget stock output, even when it reaches the iteration cap. Different update counts are expected. Every quantity must be finite and satisfy its fixed differential limit.

| Quantity | Maximum change |
|---|---:|
| Complete negative twice ELBO, quadratic, log volume, each Gamma cost | `1e-5` absolute per value |
| Conditional residual frequency | `1e-3` Hz absolute per row |
| Normalized residual vector | `1e-5` absolute per row |
| Nuisance coefficient and each returned precision | `1e-5` scaled per entry, denominator `max(1, abs(stock))` |

The 256-update physical witness must save at least 35% median CPU, and each supported southern call may use at most 15% more CPU. Failed gates end this variant after the kernel experiment. A complete saved comparison is eligible only after these checks. It would use the existing uninstrumented controls, and require identical status and reason, both reported arms and noise-fit metrics, every owner, numerical grid and optimizer path, and exact self-replay under the stock evidence gates. No raw or held-out inputs enter the experiment.
