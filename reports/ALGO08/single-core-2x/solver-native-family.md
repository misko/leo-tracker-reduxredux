# Native family elimination inside the variational solver

This experiment runs the sparse family factorization inside the same native likelihood used by ALGO08v2 for initial search, conservative refits, cavity scoring and the diagnostic grid. It preserves the original observation and candidate inventories, trial positions, robust updates, outer search and both RF calibration arms. The comparison control uses causal archive reuse and coarse salvage statistics on each input. [Previous solver experiment](solver.md) · [Fixed-linearization Schur differential](solver-schur.md)

The native kernel saved about **1.1 CPU seconds** on each saved input. DS30-0374's saved-detection-to-grid CPU time moved from **29.50 to 29.15 seconds**, and north-far's moved from **11.75 to 11.91 seconds**. That leaves the case for any substantial whole-solver speedup unresolved.

## Native boundary

The deployed backend first eliminates columns supported by a single track. The experimental version measures a second elimination that identifies independent components among the remaining shared columns using their actual nonzero support. It accepts a trailing partition only when no track couples its independent components and each component has at most four columns. The rule uses the design support and its natural column order. Catalogue entries, coordinates, and evaluation truth play no role in its selection. Layout eligibility is cached by the existing design-support key.

For every eligible variational solve, eliminate each local component, factor the remaining shared matrix, and reconstruct the full symmetric covariance. The existing native full-Gram condition check, private-track covariance reconstruction, residual scan, normal-Gamma update and stopping criterion consume that covariance. A failed sparse factor or unsupported structural layout runs the qualified dense-shared code. The floating-point elimination order changes, so equivalence to the baseline is tested via both decisions and numerical deltas. The kernel timer wraps the C likelihood call in both methods and includes all of its covariance and robust updates. The saved-detection-to-grid timer also includes orbit preparation and Python. No raw I/Q or PNG was regenerated. [Timed trial](solver_native_family_trial.py) · [Native code](../../../tools/pipeline_eval/variants/algo08_native_family.h)

## Paired results

Both trials used the existing release runtime, one low-priority core, the same causal archive and region, and the same saved detections. DS30 ran control first. North-far ran candidate first. North-far wall time varied sharply with shared-host contention, so kernel and complete-solver process CPU are the primary evidence.

| Saved input | Native C CPU seconds | Complete solve and grid CPU seconds | Sparse updates | Mean shared matrix width before → after |
|---|---:|---:|---:|---:|
| DS30-0374 | 4.799 → 3.740 | 29.505 → 29.150 | 26,471 | 84.38 → 30.27 |
| North far | 4.339 → 3.225 | 11.749 → 11.906 | 101,302 | 55.45 → 30.33 |

All eligible native updates used the second elimination. The DS30 case took the qualified Python fallback for 100 unsupported calls in both runs. It kept 2,905 owners and the same cavity decision in both arms. North-far kept 228 owners and the same cavity offer, and both arms again published false fixes on the boundary. Coordinate shifts and RF RMS changes were very small. The geographic error of those two north-far fixes still rounds to 52.455 km and 52.491 km. [Saved geographic scores](../regional-release/blind-scores.csv)

| Saved input and arm | Endpoint movement (mm) | Baseline RF RMS (Hz) | Absolute RMS change (Hz) | Maximum common grid score change |
|---|---:|---:|---:|---:|
| DS30-0374, `c = 0` | 0.119 | 101.53591276 | 9.59e−9 | 4.03e−6 |
| DS30-0374, fitted `c` | 0.069 | 101.51980285 | 7.83e−9 | 2.60e−6 |
| North far, `c = 0` | 0.283 | 37.95118710 | 3.94e−7 | 2.98e−7 |
| North far, fitted `c` | 0.256 | 37.53327599 | 7.35e−8 | 2.56e−7 |

Grid differences use the 81 identical coarse points. Endpoint-centered points moved by the numerical coordinate change. The component test also verifies the complete native likelihood with and without an extra calibration column, as well as the fallback on a design with fully coupled support.

On DS30, the cube of the factor dimensions summed over updates fell by about 95%. Measured C CPU fell by 22%, which includes the formation of native group normal blocks, covariance reconstruction and conditional track updates. The entire timed C operation cost 4.80 seconds in the control. Eliminating it would cap the effect of this boundary at 1.19× for the full saved-detection solve. A 10–15-second saving needs fewer full model rebuilds and geometry evaluations across the optimizer, cavity and grid, in addition to faster linear algebra.
