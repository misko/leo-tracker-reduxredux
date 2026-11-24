# Compiled factorization budget inside the current signed finish

The entire curved likelihood adapter, including all validation, group products, factors, robust updates and readout, used **0.450 CPU s on saved dense DS30-0008 and 0.321 CPU s on hard DS30-0402**. Even a zero-cost replacement of that whole adapter would miss the **0.500 CPU s** screen. A faster weighted factorization could save only a part of that interval. The budget comes from the exact original signed replay of each case. No new factorization or solver replay was needed. [Archive accounting](measurements/signed-factor-roof.json) · [Original signed measurements](signed-state-ceiling.md)

| Scope in the original signed replay | Dense 0008 | Hard 0402 |
|---|---:|---:|
| Curved likelihood calls, including two summary readouts | 80 | 72 |
| Entire curved adapter CPU | 0.450 s | 0.321 s |
| Entire adapter after deducting the already-studied summary repeats | 0.440 s | 0.312 s |
| Complete separate predictive-covariance calls / CPU | 78 / 0.459 s | 70 / 0.322 s |
| Enclosing instrumented signed pair / remainder if all curved adapter work were free | 3.654 / 3.205 s | 2.865 / 2.544 s |

The enclosing clocks include instrumentation. The bound grants all time inside the observed curved call and gives the replacement free validation and fallback. The original paired acceptance, all 4,367 and 4,821 owner rows respectively, both objectives and both RF values matched the sealed publications. Dense RF RMS was **140.960889 / 140.949491 Hz** and hard RF RMS **100.672203 / 100.576460 Hz**, fixed zero first. The restored dense and hard endpoint errors stayed **0.915 / 0.854 km** and **0.864 / 0.860 km** in the archived controls. [Dense original finish](mixed-named-finish-0008.md) · [Hard original finish](named-survivor-fit-0402.md)

## Operations in the compiled kernel

The released native code forms its sparse per-track Gram and response contractions once for each actual position and phase. In each Gamma update it eliminates each private one- or two-column block, factors the shared Schur system, checks its condition, solves for the coefficients, and takes the inverse of the shared factor. That inverse is used in the cross covariance, complete conditioning guard, marginal variances and next robust rates. The final pass computes the original residuals and the normalized log determinant. Replacing the separate triangular mean solve with a multiply by the computed inverse leaves cubic factor and inverse work intact and still takes a quadratic operation for the mean. Its floating-point behavior would need independent checking. [Released C source](../../../src/leo/analysis/localization_v4/native_bound.c)

| Earlier genuine native profiles | Capped 0008 position sample | 0402 cold finalists |
|---|---:|---:|
| Actual calls / robust updates | 1 / 256 | 200 / 5,256 |
| `dpotrf`, `dpocon`, `dpotrs`, `dpotri` and surrounding readout | 39.887 ms | 662.620 ms |
| Initial group Gram and current block assembly | 8.038 ms | 214.266 ms |
| Primal norms and private Schur elimination | 12.997 ms | 246.513 ms |
| Cross covariance and complete conditioning | 15.810 ms | 267.158 ms |
| Mean and residual energy | 23.710 ms | 546.595 ms |
| Variance and rate updates | 6.261 ms | 118.742 ms |

The dense dump is an actual 4,522-row, 255-column position model with 111 track groups and 134 shared columns. Across 257 factors, all 256 changes were full rank over the exact binary64 inputs, even though prior precisions stayed fixed. The hard observations are actual cold-finalist traces with a byte-equivalent instrumented C kernel. They retain phase timings and dimensions rather than replayable signed fit operand arrays. These are different scopes from the current signed pair. They establish the operation mix without using their stage proportions as current signed timing. [Dense saved native sample](../single-core-2x/solver-wide-private-blocks.md) · [Exact update ranks](../single-core-2x/solver-anderson.md#exact-schur-reuse-audit) · [Hard native trace](cold-kernel-price.md)

Two-level family Schur already used the real observation support to eliminate groups of up to four satellite-specific columns. The earlier native run maintained the same owner sets and scored RF RMS, with movement below 0.3 mm. Its fixed-state comparison checked the coefficient, covariance diagonal, residual energy, next Gamma rate and normalized log determinant against dense Cholesky. The existing triangular conditioning certificate separately skipped 3,197 of 4,098 ordinary dense estimates for **81.5 ms** in its broader cumulative scope. The wider-private implementation addresses unsupported layouts in an earlier route. Profiled Gamma changes how many updates run, with only **84 ms** saved inside the older dense named signed native scope and no measured saved dense speedup on the later cumulative composition. The static design, group Gram and phase reuse trials leave no distinct, sufficiently large measured block inside the current adapter. [Family factor](../single-core-2x/solver-native-family.md) · [Moment and log determinant check](../single-core-2x/solver-schur.md) · [Conditioning](conditioned-factor.md) · [Wider layouts](wide-private-0402.md) · [Profiled Gamma](profiled-gamma.md) · [Current cumulative transfer](profiled-gamma-live.md)

## The separate predictive Gram

The signed event objective reassembles a dense, weighted curved precision for the predictive residual after the native curved posterior has already been solved. If \(D\) is the original diagonal scale vector written as a matrix, the native and reported precisions satisfy \(H_{\text{report}} = D^{-1}H_{\text{native}}D^{-1}\) in exact arithmetic. Exporting the weighted block matrix in the original column order and retaining the original Cholesky basis could remove a redundant weighted Gram while preserving the mathematical residual coordinates. Floating-point Gram order and conditioning checks would still matter. The installed grid export uses a permuted factor and rotates the residual vector. Its squared norm checked the same up to rounding, while a signed nonlinear optimizer consumes the residual vector and its finite differences. The grid evidence alone cannot qualify that reuse in the signed fit. [Existing checked grid export](../single-core-2x/solver-posterior-handoff.md) · [Released signed predictive attachment](../../../src/leo/analysis/localization_v3/event_position.py:179)

The separate Gram was outside the live curved adapter clock. The earlier instrumented dense signed replay left **0.688 CPU s** after charging curved evaluation, prepared predictive geometry and predictive covariance. That unitemized time covers the Gram plus other work. Removing the entire Gram would need to save **6.41 ms per dense call or 7.14 ms per hard call** to clear the screen. An earlier DS30-0155 grid measured its same direct Gram at **3.95 ms per call**. Granting the whole measured cost at that rate would give **0.308 s dense and 0.276 s hard** at the signed call counts. These are cross-scope scale estimates. They do not isolate a current signed Gram clock and are not ceilings for that separate port. No new numerical kernel was warranted by these receipts. [Earlier dense timing components](named-phase-reuse.md) · [Direct Gram comparison](../single-core-2x/solver-posterior-handoff.md)

Run `python3 -B reports/ALGO08/v3/signed_factor_roof.py` to reproduce the calculation from the tracked archives and released source digest. It needs no solver environment or detector data. No scheduler, BLAS setting, scientific threshold, source release or output contract changed. [Auditor](signed_factor_roof.py) · [Tests](../../../tests/pipeline_eval/test_signed_factor_roof.py)
