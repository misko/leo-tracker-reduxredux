# Split joint position and phase factors by track and satellite family

The first component test compares a sparse two-level Schur solve with a dense solve on the same regional linearization. It uses the selected physical models from saved DS30-0374 detections and the previously published north-far simulation, with matched `c = 0` and fitted `c` arms. It tests blocks at the selected point, region center and a corner, including family omission and one Gamma noise-precision update. The component never supplies the published position or owners. The stock solver still returns its north-far false fixes.

## Inputs, parameters, and reuse

| Input or result | Depends on | Reusable across |
|---|---|---|
| Validated TLE records and time interpolation stencils | Causal cutoff, snapshot identities, track sample times, available orbit epochs | Both arms and regional points within the same snapshot/time support. Geometry still depends on the offered site and phase. |
| Track responses and fixed noise | Native CFO, immutable observation and receiver/RF identifiers, resolved integer alias, selected point mask, point-noise model | Site changes until subtracting the geometry and prior mean. Owner, alias, mask or scale changes invalidate affected track responses and sufficient statistics. |
| Radio columns | Time, lane, channel frequency, hardware and smooth basis. The extra RF coefficient appears only in fitted `c`. | All tracks in the corresponding arm at a fixed observation set. Share common columns between arms before projection. |
| Local site and orbital columns | Offered east/north point, current satellite phase reference, selected TLE and modeled uncertainty. A satellite mode has support only in its own family. | Track projection at a fixed regional linearization. Changes in site, phase reference, active orbit modes or association require rebuilding the affected geometry-dependent products. |
| Noise-normalized per-track contractions | Responses and columns from the same linearization, fixed per-point noise, and active rows | Variational precision updates within that linearization. A change in a scalar track weight does not require recomputing the contractions. |
| Track and family elimination factors | Track contractions, per-track robust precision and power, and diagonal nuisance prior precision | Fixed-weight prediction and leave-family-out downdates. Changing a track weight, power or family prior refactors that family and invalidates the shared radio/site factor. |
| Shared posterior and each next Gamma update | All contributing family factors and shared priors | A frozen posterior evaluation only. A single refactor may change every family's conditional moments through the shared receiver/site block. A robust leave-out iteration must update surviving families' weights before claiming the robust optimum. |

At a fixed linearization, whiten each track by its pointwise noise and form three quantities once, `AᵀA`, `Aᵀy` and `yᵀy`. `A` contains the shared site and radio columns, that track's satellite-specific phase and physical uncertainty columns, and its private constant. Each weight multiplies one track's contributions. Eliminate its constant by a scalar Schur update. Eliminate that family's satellite columns after aggregating its tracks. Factor the resulting shared block, then recover means and marginal covariance blocks in reverse order. The stock native method already eliminates private columns. The proposed extra factorization exploits the separation among satellites that share no rows.

The component returns the normalized log determinant, coefficient means, covariance diagonal, and each track's normalized residual energy and posterior variance contraction. The log determinant and covariance terms matter to the variational update. The track-statistic energy formula can suffer cancellation and needs the earlier direct-row numerical guard in a production backend. Frozen-weight family omission uses a downdate of the shared block and leaves the omitted columns at their prior moments. A changed phase-precision or track-noise estimate requires a new factorization. Predictive linear rows can consume the curved posterior through its shared covariance, without entering the calibration system. Predictive covariance across distinct families still requires the shared block and the corresponding transfer factors. [Grouped energy experiment](solver-statistics.md) · [Sparse factorization](../../../tools/pipeline_eval/variants/algo08_family_schur.py)

## Differential boundary

Extract the selected curved likelihood, its original calibration layout and frozen likelihood powers. For this local experiment add two shared east/north derivative columns from 1 m central differences of the physical prediction and put the same weak, region-width-scaled prior on those two columns in both matrix solvers. The stock estimator still uses its original box constraint. Treat the regional derivatives and reference phases as fixed during each Gaussian solve. Compare all returned moments to a separately assembled dense Cholesky solve. Also compare a frozen-weight omission of the family with the most active rows. The omission is a matrix test with matched input layout. It does not assert equivalence to a fully refitted cavity decision.

| Input | Curved observations | Original track slots | Families | Dense width, `c = 0` / fitted | Shared width, `c = 0` / fitted | Family modes at most | Rows omitted in downdate |
|---|---:|---:|---:|---:|---:|---:|---:|
| DS30-0374 | 2,494 | 66 | 27 | 167 / 168 | 32 / 33 | 4 | 332 |
| North far | 228 | 15 | 8 | 76 / 77 | 32 / 33 | 4 | 38 |

| Input and arm | Coefficient | Marginal variance | Normalized log determinant | Group residual energy | Group variance contraction | Next Gamma precision |
|---|---:|---:|---:|---:|---:|---:|
| DS30-0374, `c = 0` | 2.20e−9 | 8.11e−12 | 2.06e−11 | 3.42e−8 | 7.83e−12 | 6.39e−10 |
| DS30-0374, fitted `c` | 2.93e−9 | 1.36e−11 | 2.16e−11 | 5.48e−8 | 1.17e−11 | 5.65e−10 |
| North far, `c = 0` | 9.91e−9 | 3.56e−9 | 2.67e−10 | 3.28e−7 | 6.96e−10 | 2.27e−9 |
| North far, fitted `c` | 1.79e−8 | 2.74e−9 | 3.00e−10 | 2.39e−8 | 3.96e−11 | 3.98e−9 |

The second table gives maximum absolute dense-versus-sparse discrepancies across the three positions and tested weight or omission conditions. The Gamma update column measures agreement before reweighting. Two component tests also passed, including respecifying the prior precision and rejecting an off-family design term. The north-far endpoints and frequency RMS reproduced the published boundary fits on the filtered curved-input differential. Their geographic errors remain 52.455 km with zero calibration and 52.491 km with fitted calibration. [Saved geographic scores](../regional-release/blind-scores.csv)

The next component can use affine site columns inside each regional patch. The track normal blocks are then quadratic polynomials of east and north, so a patch needs one set of contractions and each trial evaluates small coefficient blocks. Orbit-state range and a bound on displacement give a measurable geometric remainder. A joint trial still needs an acceptance check against the exact nonlinear marginal objective, and a phase update requires a freshly validated patch. All-catalogue nomination must account for every candidate through the original score or a provable bound, including when a threshold or shortlist comparison overlaps the numerical interval. The present measurement covers local Gaussian agreement with stock-selected inputs. [Trial runner](solver_schur_trial.py) · [Component tests](../../../tests/pipeline_eval/test_algo08_family_schur.py)
