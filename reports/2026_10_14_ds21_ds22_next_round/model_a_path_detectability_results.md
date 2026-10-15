# A029/A071: shared and band detectability transfer

The final-stage detectability extension does not repair either unresolved case. DS21-029 improves substantially but remains about 40 km wrong; DS21-071 remains about 58 km wrong. These are conditional development results from two selected difficult cases, not a cohort update or a model promotion.

| Case | Published coverage A, km | Shared q, km | Band-contrast q, km | Strict endpoints, shared / contrast |
|---|---:|---:|---:|---:|
| DS21-029 | 116.682586 | 76.468687 | 39.987144 | 4/6 / 6/6 |
| DS21-071 | 57.398154 | 56.179103 | 57.799904 | 6/6 / 5/6 |

Every selector uses its own model's training objective. No endpoint, path, model, or width was selected by position error. The published coverage baseline is versioned separately from this pilot; historical A/B endpoints were initializers, not grandfathered q incumbents.

## Controlled inventory and accounting

All six strict original coverage A-final complete states in each case received both arms. Every path retained its own frozen high-minus-low receiver offsets, added the corresponding 50 kHz Gaussian prior exactly once, and preserved its bank, observation rows, RF frame, common-clock state and prior, fitted c, original 25 km disk, and original global 250 km prior. Banks contain 25 candidates for 029 and 39 for 071. All q tails started at exactly zero; no states or folds from 035/053 were imported.

Both arms use the previously qualified conditional density and compact smooth visibility with numerical width 1e-5. Shared q has one satellite propensity vector; contrast q has separate effective low/high vectors with the original coupled shared/contrast prior. The contrast fitter preserves its non-diagonal prior metadata. This is an explicit A final-stage sensitivity: learned RF shifts remain frozen and path-specific. It does not establish a common jointly optimized calibration model across the six paths.

The actual zero-fit qualification passed all 654 wrapper evaluations: 271 for 029 in 4.222 s and 383 for 071 in 9.918 s. It also made 172 explicit geometry calls and 1,148 implicit orbital predictions. Shared/contrast zero-tail objective agreement was at most 7.28e-12; the largest scaled finite-difference errors were 8.52e-6 and 1.15e-5. All twelve zero-q source states had no soft transition pairs. FD probes changed no hard visibility memberships or soft supports; 3/17 interpolation-cell changes were recorded. The nonzero-q mixed directional probes also passed. These are derivative and transport checks, not position evidence.

The 24 fits consumed 10,318 actual objective evaluations, including independent audits. Each had a 20 s / 2,000 actual-evaluation / 600-iteration limit, with one audit evaluation reserved inside that limit. Four single-thread workers ran finite case waves; all outer processes returned successfully. Maximum numerical time was 16.953 s. Whole-unit limits were 120 s, with external TERM at 135 s and KILL at 140 s. No time or evaluation-budget failure occurred, and no call was retried. Fifteen owned component tests and Ruff passed before source freeze (`ed3855713`; qualifier `4aac70b92`).

Both complete twelve-unit matrices and their training selectors were sealed before the configured development reference was accessed. No held measurements were read or predictive scores computed. The reference remains configured rather than independently confirmed.

## Selected training endpoints

| Case / arm | Path | J | NLL | Total prior | Scaled KKT | Source-to-final movement, km | Radius used / allowed, km |
|---|---:|---:|---:|---:|---:|---:|---:|
| 029 shared | 0 | 30740.225007 | 30274.125381 | 466.099626 | 0.000156 | 0.601200 | 13.011789 / 25 |
| 029 contrast | 5 | 29219.967781 | 28916.260685 | 303.707096 | 0.000126 | 1.361749 | 25.000000 / 25 |
| 071 shared | 2 | 32339.537682 | 31979.476567 | 360.061115 | 0.000899 | 1.425367 | 18.698936 / 25 |
| 071 contrast | 2 | 32138.752903 | 31764.693840 | 374.059063 | 0.000790 | 1.587451 | 21.132645 / 25 |

Relative to each selected path's own zero-q initial objective, J improved by 787.742, 3127.259, 1136.970, and 1337.755 respectively. The fitted q prior costs are 16.837, 17.523, 14.104, and 29.663. Better in-sample frequency fit does not establish better localization. Shared versus contrast objective values are not a model-selection or generalization criterion, and legacy versus conditional objective changes also include the changed density normalization.

Three endpoints failed the unchanged 0.001 KKT gate:

| Case / arm / path | J | KKT | Relation to its accepted selector |
|---|---:|---:|---|
| 029 shared 4 | 29662.427099 | 0.001290 | Lower J than selected shared path 0 |
| 029 shared 5 | 30521.387170 | 0.005868 | Lower J than selected shared path 0 |
| 071 contrast 5 | 33248.701202 | 0.001293 | Higher J than selected contrast path 2 |

Thus the 029 shared result is affected by convergence attrition. The 029 contrast selector has all six strict endpoints available. Both 071 selectors also have all available lower-J endpoints admitted; its single rejected contrast endpoint cannot explain the selected wrong basin. No rejected endpoint was silently polished or promoted.

The modest within-path movements distinguish these results from wholesale geography loss during this final continuation: the main outcomes include changed across-path selection and retained starting basins. The 029 contrast winner reaches its local disk boundary; this observation alone does not prove useful outward descent. The 071 winners are interior. Neither result establishes that candidate coverage, calibration, or detectability is the unique cause.

## Next discriminating checks, without new fits

For 029, replay the accepted contrast winner's radial/tangential gradient and 1/10/100 m outward finite differences, retaining the original global prior and explicitly checking visibility support changes. An expanded-domain continuation is justified only if this training-only audit establishes feasible outward descent.

For 071, audit the genuine saved B incumbent's complete correction and prior before adding any source. Its receiver contrasts generally differ from each A path's frozen contrasts, so it cannot be silently represented in those fixed-contrast models. A seventh source-defined path can instead freeze its own B contrast, invert the exact centered-to-raw intercept transformation, and preserve its own disk. This would be declared extra search inventory; a future cohort recipe must apply that inventory consistently. No such new fit is included here.

These checks target domain restriction versus omitted genuine calibration/basin state. This pilot provides no held-out validation for q, and earlier negative A035 contrast CV remains evidence against broad promotion.

## Receipts

All namespaces are beneath `/srv/bulk/leo-research-ds21-ds22/2026_10_14`:

- Qualifiers: `model-a-path-detectability-qualification-{029,071}-v1`.
- Scientific matrices: `model-a-path-detectability-control-{029,071}-v1`.
- Finite waves: `model-a-path-detectability-control-{029,071}-wave-v1`.
- Post-seal position join: `model-a-path-detectability-control-pair-evaluation-v1/development-errors.json`.

Scientific seal hashes: 029 `5d57c848ed09390d447dec4989bab0f660d9eac20b9ccc824a816daf11bcf955`; 071 `aa887fd812cd0f7de71386bfe7b371faa75291914fdfc493af13f796f269d0b8`.

The adjacent JSON binds protocols, terminals, qualification results, seals, saved baseline exports, and the post-seal join. The CSV preserves scores, NLL, priors, KKT, movement, limits, counts, and terminal hashes for all 24 calls, including all three rejections. No original cohort plot or selector was changed.
