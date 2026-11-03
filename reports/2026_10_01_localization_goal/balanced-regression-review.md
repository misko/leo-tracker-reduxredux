# Satellite-balanced score on the frozen64

The development-panel median improvement did not transfer to the complete regression. The unchanged rule improves 43 scans, but its accepted-case median is slightly worse than baseline and one endpoint fails numerical verification. No promotion is justified.

| Metric | Original baseline | Satellite-balanced |
| --- | ---: | ---: |
| Accepted | 64/64 | 63/64 |
| Median horizontal error | 2,059.90 m | 2,085.50 m |
| p90 horizontal error | 5,850.75 m | 5,264.11 m |
| Within 1,000 m | 10/64 | 13/64 |
| Within 3,000 m | 47/64 | 43/64 |

Candidate quantiles are conditional on the 63 accepted scans. On those same 63 scans, the baseline median/p90 are 2,062.17/5,898.55 m. Threshold counts retain all64, including the failed candidate. The balanced median warm runtime is 1.671 s, maximum 2.514 s, and median CPU 1.617 s. These exclude original acquisition and baseline fitting and are not cold runtime results.

![Frozen64 comparison](balanced-group-regression64-v1.png)

| Dataset | Candidate accepted | Baseline median | Balanced median | Baseline p90 | Balanced p90 |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS9 | 22/22 | 2,194.78 m | 2,511.14 m | 6,072.93 m | 5,998.28 m |
| DS10 | 21/21 | 1,945.94 m | 1,495.18 m | 7,733.56 m | 5,121.55 m |
| DS11 | 20/21 | 2,057.64 m | 2,029.25 m | 3,483.80 m | 3,403.28 m |

DS11's candidate quantiles exclude its failed endpoint; its baseline column includes all21. These dataset differences do not authorize choosing a method by dataset or tuning to reference errors.

## Diagnostic and evaluation sequence

The reference-free12scan information decomposition was completed before comparison with the saved geographic outcomes. Singleton groups gain information share in every scan, including both improvements and regressions. Changes in major inverse-curvature axes also have both signs in each outcome category. For example, DS10-F075 regresses even while its major axis shrinks from860 to742m, whereas DS9-F025 improves while its major axis grows from763 to896m. Thus neither a simple singleton-amplification explanation nor a geometry-loss explanation separates outcomes. Those axes are not calibrated confidence radii. Evidence: `balanced-geometry-v1.json` and its SHA seal.

Rather than tune a selector on that exposed panel, freeze the same coefficients N/(G*n_s), original hard labels, priors, fixed height and independent baseline initialization. Run only the remaining52scans, retaining the earlier12sealed results. At most2fitprocesses ran; each used25sinternal/30sexternal warm caps. No retries or RF collection. All52newprocesses returned locally stationary statuses, but statuses alone do not establish acceptance.

Independent evaluation recomputes source/input/height/assignment/weight bindings, support, objectives, metrics, monotonicity and finite-difference gradients before reading reference coordinates. DS11-F031 fails: maximum analytic-versus-numerical gradient difference1.0217 and numerical scaled decrement squared0.8841. Its saved solver status was `scaled_stationary`, so that status is not trusted. Error remains null; do not continue or relabel this run as accepted. Diagnose the discrepancy at the sealed endpoint, including finite-difference step dependence and any visibility discontinuity, before changing software.

The source freezes and receipts are in `balanced-group-regression-v1/` and the earlier two batch directories. Authoritative evaluation is `balanced-group-regression64-v1.json` with its SHA seal, assembled from the three sealed evaluations and the immutable baseline. The figure was visually inspected.

No fresh cold acquisition-and-fit benchmark, held-out candidate evaluation, or uncertainty calibration has been performed for this model. Both accuracy targets remain unmet. Keep the original baseline as the fully benchmarked reference and the balanced model as an informative but unpromoted alternative.
