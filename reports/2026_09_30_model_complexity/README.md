# Localization benefit versus model complexity

The shared-track-scale likelihood is the best-supported modest increase over the original independent Student-t baseline. The contrast likelihood with an explicit unassociated-trend component, q020, is a reasonable working research baseline, but its added geographic benefit is less firmly established. Correlation, curvature, nominal receiver geometry and learned track-variable noise weights do not currently justify becoming default localization components.

This assessment uses completed matched geographic experiments and stronger transfer checks, plus a new same-input objective runtime benchmark. It is not a fresh accuracy campaign. All metre values are distance to an exposed, unsurveyed reference. The configured center is already 809 m from that reference. No candidate establishes reliable sub-kilometre absolute accuracy.

## Model decisions

| Model or extension | Geographic evidence | Added complexity | Is it warranted? |
|---|---|---|---|
| Independent Student-t baseline | First-eight DS7/8/9: 2541 / 1424 / 1213 m; full DS7 677 m | Candidate mixture, profiled frequency offsets, one timing per scan | Keep as regression and scientific control |
| Shared track scale, no correlation | Same first-eight panels: 2287 / 1391 / 683 m; full DS7 527 m | Changes residual dependence; no added optimized position/timing dimensions; latent scale analytically integrated | Yes as a research estimator: modest complexity with matched improvements |
| Frequency contrasts | Held prediction improves 17/18; geographic distance improves 9/18 | Analytically eliminates arbitrary constant frequency; changes scored observation space | Yes for a clear frequency-invariant formulation; not a proven accuracy upgrade |
| q020 unassociated-trend mixture | Matched held gains 18/18; geographic wins 9/18; sub-km count unchanged at 3/18 | One fixed background mixture and analytic trend marginalization; no extra optimized timing/position dimensions | Provisionally yes: useful model of unassociated tracks, modest cost; retain simpler comparator |
| Temporal correlation | First-eight 2955 / 819 / 1647 m; later DS9 N8 median worsens 876 → 2059 m | Covariance matrices, correlation assumptions and cached linear algebra | No geographic default: predictive improvement does not reliably improve position |
| Shared curvature | N24 388 / 390 / 107 → 341 / 373 / 135 m | Candidate grouping and numerical integration over shared curvature | No: outside-scan wins only 6/15; extra structure not justified by transfer |
| Receiver/candidate slopes | Receiver slopes first-eight 2302 / 1551 / 1750 m; later whole-scan predictive total worsens | Additional residual flexibility; potential absorption of position information | No default; use only with independent physical constraints |
| Nominal receiver cones or tilt | 40-degree N8 medians 2061 / 1779 / 747 m; no consistent DS7–9 sub-km result | Physical pointing/mapping assumptions, beam response and candidate reweighting | Not yet: calibration burden exceeds demonstrated localization benefit |
| RX-derived variable noise weights | DS10 1092 → 1078 m but held score worsens; direct calibration loses constant control | Paired-track support, feature calibration, donor transfer and density normalization | No: reject despite a slightly smaller reference distance |
| Sequence-informed phase/rate corrections | Some waveform gains; no demonstrated geographic improvement | Waveform estimation, support gates and extra clock/dynamics assumptions | Keep separate research branch until stronger transfer passes |

Shared scale and q020 are not the same model. The full-dataset shared-scale results (DS7/8/9: 527 / 736 / 229 m) and q020 selected N24 results (388 / 390 / 107 m) use different populations and cannot establish q020 superiority. With a uniform chronological N24 selection, q020 yields 454 / 1877 / 341 / 1092 m on DS7/8/9/10. Selecting the best dataset-specific model or subset after examining reference distance is not justified.

## Computational cost

The benchmark evaluates five existing implementations on identical first-eight DS7/DS8/DS9 inputs and the same frozen point within each dataset. Each has ten explicitly optimized coordinates: two horizontal coordinates and eight recording offsets. Integrated latent variables and profiled frequency offsets still contribute computational/statistical complexity despite not increasing this count.

For each implementation, construction is timed separately, then one warm-up and five objective-plus-gradient evaluations are performed. Repeated values and gradients must agree to 1e-9. The independent Student-t arm uses its existing batched offset profiler. All arms use one BLAS thread. Input loading, orbit-bank generation, optimizer iterations and multistart selection are excluded. Results are current-code microbenchmarks, not end-to-end fit times or large-dataset scaling claims. Different model scores are not ranked directly because likelihood definitions differ.

Medians below summarize the three per-dataset medians, each based on five repeated calls.

| Implementation | Objective plus gradient | Relative to q020 | Construction |
|---|---:|---:|---:|
| Independent Student-t, batched offset profiler | 2054.71 ms | 14.02× | 3.69 ms |
| Shared track scale, no correlation | 173.89 ms | 1.19× | 12.46 ms |
| Shared track scale, 10 s correlation | 173.30 ms | 1.18× | 16.71 ms |
| Frequency contrasts | 147.24 ms | 1.00× | 0.67 ms |
| q020 contrast plus background | 146.60 ms | 1.00× | 9.03 ms |

Contrast and q020 costs are effectively tied in this small benchmark; their sub-millisecond difference should not be treated as a performance advantage. Shared scale is about 11.8 times faster per call than the independent implementation here. A richer model need not cost more: analytic profiling/marginalization can be cheaper than iterative independent-error offset fitting. These ratios do not predict total optimizer speedups.

Measured values are preserved in [benchmark.json](benchmark.json) with source/input hashes; [benchmark.py](benchmark.py) reproduces the bounded test in a fresh output context. The covariance implementation constructs dense matrices even for zero decay, so the present shared-scale implementation need not be the fastest mathematically possible version.

Historical first-eight full-fit process times were similar for shared scale and correlation: 7.52–11.27 s versus 8.01–12.93 s over six starts each, including process/setup overhead. Correlation is rejected primarily for scientific reliability, not because those historical fits were slow. Do not extrapolate these timings to the full corpus.

## Complexity outside the likelihood

| Choice | Benefit and cost | Recommendation |
|---|---|---|
| Pool scans across time | Often larger benefit than extra residual parameters, but increases data and latency; selection changes outcomes | Warranted when latency allows; use a frozen selection rule and report coverage |
| Multistart plus training-only timing checks | Detects alternative modes and numerical failures; costs repeated evaluations | Warranted as an optimization safeguard, not an accuracy claim |
| Score-balanced compression | N8 retains N24 position within 5–21 m, but requires scouting/fitting all 24 and enumerating 735471 subsets | Only for an explicit downstream compression need; not default acquisition strategy |
| Geometry-only scan selection | DS7 1832 m on selected N8 despite 24-scan scouting | Not justified as the default selector |
| Simple causal receiver-response model | Better than signed response geometry in 4/6 records; no location result | Useful inexpensive research control; not a localization replacement |

## Recommended working stack

Keep shared-scale zero-correlation as the simpler geographic comparator. Use q020 contrasts as the working research implementation, with frozen scan membership, qualified multistart selection and training-only timing checks. Avoid stacking correlation, curvature, free candidate slopes, nominal cone weights or learned RX noise weights onto it without a matched transfer win. Spend the next effort on independent timing/pose/reference evidence and trustworthy candidate identity, where missing constraints are measured limitations.

The current evidence supports a lean research stack, not a deployment claim. No fresh geographic evaluation was launched merely to repeat already-completed comparisons, and no model was selected using the smallest exposed-reference distance.

Sources: [matched shared-scale/correlation study](../2026_09_28_covariance_position/README.md), [resource receipts](../2026_09_28_covariance_position/resource-summary.json), [full DS7](../2026_09_28_ds7_full_shared/README.md), [full comparison](../2026_09_29_approach_summary/README.md), [contrasts](../2026_09_29_frequency_contrast/README.md), [q020](../2026_09_29_unassociated_trend/README.md), [correlated contrasts](../2026_09_29_correlated_contrast/README.md), [curvature](../2026_09_29_curvature_n24/README.md), [rank selection](../2026_09_29_rank24_control/README.md), [slope transfer](../2026_09_29_scan_holdout/README.md), [cone sweep](../2026_09_29_rx_cone_position/README.md), [RX weights](../2026_09_30_ds10_scale_weighting/README.md), [direct calibration](../2026_09_30_contrast_scale_calibration/README.md), [compression](../2026_09_29_score_balanced_selection/README.md), [checkpoint](../2026_09_29_subkm_methods_checkpoint/README.md), [causal response](../2026_09_30_rx_causal_response/README.md).
