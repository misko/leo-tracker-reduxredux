# A035/A053: matched numerical endpoint controls change training selection

**Both original SLSQP repeats and positive-Hessian Newton finishing repair eligibility of the previously rejected lower-objective common-start q states.** Newton reaches stronger KKT, but has no exclusive position benefit. The repaired states win the unchanged q training objective. Consequently the current A053 winner is **1.343357 km**, not the earlier 0.256462 km endpoint; A035 improves from 9.004813 to **7.223109 km**. This is additional endpoint work, not an equal-total-cost claim about the original search.

**This current training selector supersedes the earlier A053 sub-kilometer headline.** The earlier endpoint and its original version remain valid; convergence attrition had excluded the lower-objective, less accurate state. Repairing eligibility exposes acceptance-induced optimism in the previous selected accuracy. It is not achievement of the localization target.

The eight controls use two cases × two exact saved complete endpoints (rejected common and accepted training winner) × two numerical methods. Each pair shares geography, nuisance/q state, fixed learned high shifts, bank, objective, priors and original 25/50 km disk. No reference selects an endpoint. Prior rejected attempts and accepted incumbents remain intact.

The new core `09f61fe69` reuses the immutable pure `tangent_gradient_finish.finish` port. Diagnostic/controller source is `2e6560efa`; runtime freeze adapter is `bb73e1f4d`. Twenty component tests and Ruff pass. The first freeze failed before any numerical call because audit-binding dictionaries were passed to a manifest path interface. Its partial source archives and durable failure receipt are preserved. A new namespace/v2 runtime projects the bound paths correctly; numerical code is unchanged.

Actual same-endpoint/recorded-port qualification passed **12 objectives, zero fits**, in 5.209 seconds, including original strict classification and identical density/gradient/posterior replay. Each numerical call has **20 seconds and 600 actual objective evaluations**, including Hessian probes and terminal replay; the SLSQP repeat retains its 600-iteration upper bound as well. This is a distinct stricter callback cap from the earlier 600-iteration protocols. Independent outcome audits are explicitly additional evaluations.

All eight numerical units completed, all strict, in **28.982 seconds** with four single-thread workers. Each unit has 90/105/110 second bounds. The global outcomes and own-objective selectors sealed before reference scoring: `7e0f6002ed537c67e1b7a2e726426e62c09b1679e9b7e9c92d12315d0f924c6d`.

| Case / original endpoint | Method | Actual solve objectives | Seconds | Strict KKT | Configured error km |
|---|---|---:|---:|---:|---:|
| 035 rejected common | SLSQP repeat | 13 | 0.302 | 0.000746589 | **7.223102** |
| 035 rejected common | PD Newton | 255 | 5.285 | **9.96e−8** | **7.223109** |
| 035 accepted old winner | SLSQP repeat | 2 | 0.061 | 0.000097955 | 9.004813 |
| 035 accepted old winner | PD certificate, no step needed | 258 | 5.425 | 0.000097955 | 9.004813 |
| 053 rejected common | SLSQP repeat | 29 | 0.420 | 0.000756834 | **1.343352** |
| 053 rejected common | PD Newton | 277 | 3.970 | **2.12e−8** | **1.343357** |
| 053 accepted old winner | SLSQP repeat | 13 | 0.193 | 0.000389571 | 0.256462 |
| 053 accepted old winner | PD certificate, no step needed | 278 | 4.032 | 0.000389571 | 0.256462 |

Solve counts total **1125 actual objectives** across eight calls. Qualification costs 12, independent endpoint audits 8, and post-seal scoring 8 additional objectives. There was no original held-data access, new candidate, geography proposal, threshold relaxation or regularization.

## Numerical evidence

The Newton method uses exact tangents for active affine timing/box constraints and declines active curved disks. Tangent dimensions are 126/128 for 035 common/old winner and 137/138 for 053 common/old winner. Full projected KKT, including active-bound multipliers, remains the original acceptance rule.

All four actual tangent Hessians are positive under the inherited relative test. Minimum eigenvalues are **0.226053 / 0.21369** for 035 and **0.211658 / 0.22097** for 053. Complete eigenvalue arrays, Cholesky diagonals, antisymmetry, active constraint IDs, and tangent-normal residuals are preserved in the numeric receipt; no pivot regularization or eigenvalue floor was applied.

At the rejected common states, one coupled Newton step changes the objective by approximately **−4.53e−9** (035) and **−3.56e−9** (053), roughly 1243/979 objective ULPs. That is much larger than the earlier *single-coordinate* predicted improvements of 5–8 ULPs: coupling matters. The scaled steps have norms 8.03e−5 and 1.30e−4; geographic changes are only millimeters. No objective-increase allowance was needed. Both endpoints satisfy the unchanged independent full KKT check afterward.

The much cheaper original SLSQP endpoint repeats also pass. The evidence therefore supports incomplete numerical termination, not a uniquely necessary Newton algorithm. Neither control demonstrates that the earlier original-seed search would finish within the same total budget; these calls start from saved endpoints and add cost.

## Selection and localization consequences

For each numerical method, strict new outcomes compete by their own unchanged q objective with the retained original strict incumbent. The common state wins in both cases:

| Case | Repaired common objective | Previously eligible winner objective | Current PD-selector error | Previous eligible-selector error |
|---|---:|---:|---:|---:|
| 035 | 28882.674102 | 30174.189041 | **7.223109 km** | 9.004813 km |
| 053 | 19314.770184 | 19370.784820 | **1.343357 km** | **0.256462 km** |

The earlier A053 sub-kilometer endpoint remains a real strict accepted result, but reporting it as the current training winner after this numerical repair would select a version by accuracy. The model prefers the less accurate common state by 56.014636 objective units. A035 also remains worse than its unchanged legacy 6.289664 km result. Better stationarity is scientifically necessary but does not guarantee better geography.

The earlier randomized conditional-development CV already warned about A053 q generalization: opposite-fold conditional NLL **worsened by 377.047164** at the fixed current-full geography. That warning remains part of the evidence even when the older selected position looked favorable. It does not authorize choosing a model or endpoint retroactively by reference error; no q cohort promotion follows from either version.

The preceding conditional low/high fits start from the *older* q winners. Their table remains valid for that version and must not be paired with these new full selectors. The next authorized four conditional views will start from the prespecified PD method's newly selected common states, retain all original banks/frames/shifts/disks and strict rules, and seal before new accuracy evaluation. They remain full-derived conditional views, not independent half-only A pipelines. No cohort promotion is justified by these two development cases.

[Complete endpoints, curvature diagnostics, frequency scores and provenance](model_a_propensity_polish_results.json). Output: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-a-propensity-polish-control-035053-v2`.
