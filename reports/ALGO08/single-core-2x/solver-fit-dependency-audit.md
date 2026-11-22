# Optimizer and publication dependencies on the dense saved solve

The archived DS30-0008 solve spent **0.33 ms** serializing the position path. The **11.876 CPU seconds** attributed to curvature refreshes are part of the original optimizer's step and stopping decisions. All of the selected packet, including exact grid evaluations, took **7.486 CPU seconds**. A path or grid shortcut therefore has no measured route to an 8-second exact saving. [Profile readout](measurements/solver-fit-dependency-audit.json)

## Accepted steps and curvature

Each `bounded_secant` call builds two finite-difference residual columns when it needs a new Jacobian. The trust trial uses those columns in the box-constrained step and predicted decrease. A small step computed with the existing secant Jacobian triggers a fresh comparison before the fit can terminate. The observed 188 refreshes made 376 residual probes across 84 optimizer calls. The solver records the initial value and appends an accepted step only after the original objective at the proposed position improves. `recorded_fit_path` extracts the positions and validates the endpoints from that existing history. It never invokes a residual, likelihood or optimizer. [Optimizer](../../../tools/pipeline_eval/variants/compact_cavity_optimizer.py) · [Path](../../../src/leo/presentation/position_path.py)

| Saved path with deployed margins | Fixed-zero points by phase round | Fitted points by phase round | Fixed-zero / fitted moves |
|---|---|---|---:|
| DS30-0008 | 10, 5, 2, 1, 1 | 10, 5, 2, 1, 1 | 14 / 14 |
| DS30-0374 | 4, 5, 1, 1, 1 | 5, 5, 1, 1, 1 | 7 / 8 |
| Public southern containing | 8, 2, 1, 1, 1 | 6, 2, 1, 1, 1 | 8 / 6 |

The 10 recorded points in the first dense round include its starting point. Each of the last two rounds needed zero accepted moves and still had its own phase reference and stopping check. The selected packet reconstructs the objective from the retained model and validates its selected position. Its sampler uses the accepted endpoints and offered box for the grid. It deduplicates the exact coordinates and evaluates both arms at all retained grid positions. The other recorded steps serve the path figure independently. The dense grid accounted for **6.893 of 7.486** packet seconds. Existing endpoint and full-call studies already measured replay at the same complete model inputs, with at most 2.776 gross seconds of dense matches in the tested 64 MiB layout. [Packet assembly](../../../tools/algo08_position.py) · [Sampler](../../../src/leo/analysis/position_grid.py) · [Complete-call reuse](solver-exact-likelihood-reuse.md) · [Known grid requirements](solver-grid-kernel.md)

## Orbital projection budget

The dense profile assigns **2.267 inclusive CPU seconds** to all 1,466 curved phase projections, including preparation of the phase states on layout changes, observer calculations and both phase differences. Its separate predictive geometry took **1.064 seconds** and its complete orbital mode-bank construction **0.489 seconds**. Their combined cost is a generous **3.820-second ceiling** for sharing those routines. On the portable southern control the same three costs are **1.900, 0.413 and 0.199 seconds**. The profile and the public southern path in the table use different southern simulations. [Dense profile](restored-scout-0008-solver-profile.md) · [Portable southern profile](screened-stock-profile.md)

The existing geometry cache already holds the exact center and perturbed states at a fixed phase reference. Relative direction and range still depend on the trial observer. Each calibration arm can select its own phase reference and robust posterior. The prior fused nominal and mode projection saved 0.181 seconds on DS30-0155 in the relevant geometry routines. The previous exact cross-arm grid audit measured a generous 0.137-second ceiling on DS30-0374. A new sharing pass in these boundaries cannot cover the dense target even at their full profile cost. [Phase cache](../../../src/leo/analysis/localization_v3/marginal.py) · [Fused projection](solver-fused-phase-projection.md) · [Cross-arm audit](solver-grid-cross-arm.md)

## Held-family calibration and remaining native work

The dense cavity nomination used **6.627 CPU seconds**, including **3.207 seconds** in `family_data`. A held family retains its own mask and five phase updates at the original trial point. Within that family's loop the scan, owner layout, mask, arm, history weights, means and priors stay fixed. Only the phase reference changes between constructions. The final `calculate` uses the same instance, position and reference as the last `state` call, since assigning the new reference at the end of the loop only changes a local variable. A reusable model with a properly updated phase reference and a retained last posterior could avoid some of that work while preserving all five state updates, the original covariance and the full broad sky assessment. The first quantitative ceiling includes every model construction and the last posterior read. It is **1.245 seconds** on DS30-0008 and **0.235 seconds** on the portable southern simulation. Retaining the necessary first construction in each family reduces the opportunity further. The separate shared broad-sky projection already targets the downstream nomination call. [Held-family calibration](../../../src/leo/analysis/localization_v3/family_cavity.py) · [Broad projection](solver-cavity-projection.md)

| Cavity calibration subcall | DS30-0008 calls / inclusive CPU | Portable southern calls / inclusive CPU |
|---|---:|---:|
| Construct fixed-owner model | 130 / 0.998 s | 50 / 0.182 s |
| Compute phase update from bound | 130 / 1.702 s | 50 / 0.393 s |
| Read last model's posterior | 26 / 0.247 s | 10 / 0.052 s |

The dense likelihood still has the higher budget. Native execution used 14.099 profiled seconds and the dense Python fallback 5.120 inclusive seconds. The previously measured 256-update native witness spent 23.710 ms evaluating means and residuals and 15.810 ms evaluating cross-covariances and conditioning. Packing those operands for vector operations across independent rows or columns could keep each original reduction order. Removing both entire boundaries at the witness's cost per update, across the known dense 18,750-update family, would account for about 2.9 seconds. The extrapolation applies to that family of shapes. Within the witness's 39.887 ms of LAPACK the exact Schur-factor audit found zero reusable factors and full-rank changes at every update. Earlier timing of the wider fallback and complete-call cache yielded no repeatable whole-solver gain at the 8-second scale. [Native phases and fallback timings](solver-wide-private-blocks.md) · [Schur audit](solver-anderson.md#exact-schur-reuse-audit)

This audit used the archived profiles and restored-margin terminals only. [Readout script](solver_fit_dependency_audit.py) · [Component tests](../../../tests/pipeline_eval/test_solver_fit_dependency_audit.py)

```sh
python3 reports/ALGO08/single-core-2x/solver_fit_dependency_audit.py \
  /tmp/leo-algo08v2-2x-bench "$new_receipt"
```
