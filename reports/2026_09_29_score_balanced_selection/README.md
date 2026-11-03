# Score-balanced subsets reproduce the 24-scan locations with eight scans

The fixed selector produces an eight-scan subset in each dataset whose refit
lies within 4.5–20.6 metres of the existing N24 fit. All three reference errors
are below 1 km, and excluded-scan total scores slightly exceed N24. This is a
successful source-data compression result, not independent eight-scan acquisition
or blind validation of absolute accuracy.

| Dataset | Balanced-eight median error | Geometry-only eight error | Score-balanced eight error | N24 error | Shift from N24 |
|---|---:|---:|---:|---:|---:|
| DS7 | 1,416.6 m | 1,831.6 m | **390.8 m** | 387.5 m | 4.5 m |
| DS8 | 1,422.8 m | 987.6 m | **403.4 m** | 389.8 m | 20.6 m |
| DS9 | 1,042.8 m | 395.8 m | **97.6 m** | 107.2 m | 9.6 m |

The first column summarizes three sets per dataset; the other columns are
single fits. All reference errors use the inherited exposed, unsurveyed
reference. The selected scans span 10.25, 8.01 and 12.02 hours, respectively;
these are not consecutive eight-scan results. All 24 source scans and their
existing fitted location are used in selecting the eight.

## Fixed rule and matched fitting

The [protocol](PROTOCOL.md) preceded execution. Enumerate all 735,471 eight-scan
subsets per dataset. Among those with positive definite summed observed
geographic curvature, maximize:

```
log det(sum geometry information + ridge I)
    − summed_gradient' × inverse(summed_curvature) × summed_gradient.
```

Each scan's gradient and curvature come from its training likelihood at the
N24 source fit, after locally profiling its timing offset. The geometry term
comes from the preceding training-only information diagnostic. The penalty is
twice the local quadratic source-score gain from moving away from N24. Its
coefficient is fixed at one; there is no sweep, reference-based tuning or
target-based selection. This is a subset-selection heuristic, not a likelihood,
calibrated bias test or claim that N24 is ground truth.

Use the preceding information-selection driver's same original q020 model,
three cold and three training-only timing-grid starts, optimizer qualification,
and five frozen outside-pool target evaluations. The new wrapper substitutes
only the selector and output directory; the reused source is hash-bound. The
chosen endpoint maximizes qualified training likelihood. N24 is not supplied
as an optimization warm start, although it explicitly supplies the selection
expansion point.

| Dataset | Selected pool indices (zero based) | Early / middle / late | Disagreement penalty | Predicted local shift |
|---|---|---:|---:|---:|
| DS7 | 0, 4, 11, 14, 16, 18, 22, 23 | 2 / 2 / 4 | 0.001133 | 4.52 m |
| DS8 | 0, 1, 3, 4, 7, 11, 17, 23 | 5 / 1 / 2 | 0.072960 | 20.60 m |
| DS9 | 5, 6, 9, 11, 12, 13, 14, 23 | 2 / 5 / 1 | 0.009639 | 9.64 m |

Exact selected session IDs appear in each dataset output. Selection remains
temporally uneven: the rule balances score derivatives, not window counts.

## Excluded-scan prediction

| Dataset | Versus mean balanced-eight score | Versus geometry-only eight | Versus N24 | Versus equal per-scan N8 mixture |
|---|---:|---:|---:|---:|
| DS7 | +93.752 | +174.008 | +0.269 | −186.793 |
| DS8 | +128.830 | −13.460 | +1.814 | −146.321 |
| DS9 | +89.591 | −38.946 | +0.734 | −109.063 |

Numbers are sums of log-score differences over five excluded scans, with one
shared timing offset integrated per scan. All positions use the same original
q020 scoring rule. The score-balanced fits do not dominate every individual
balanced control: each dataset has one such control with a higher total target
score. They also remain below the per-scan mixture of all three balanced
locations. That mixture averages location hypotheses separately for each scan
and is not a single shared stationary-location fit.

The +2.816 total advantage over N24 is small. The principal supported result
is preservation of the source solution with a reduced subset, not superior
prediction. Targets have been examined repeatedly in this research and are
not a fresh blind test. No significance or population reliability claim is made.

## Verification

All 18 starts and all 15 target integrals qualify. Maximum optimizer gradient
audit error is 5.55e−6. Maximum 16/32-order timing-integration difference is
0.003976 log units; no refinement is needed. Halving the geometry derivative
steps preserves the selected subset in all datasets. Every upstream per-scan
observed-Hessian audit qualifies.

All 735,471 subsets are examined per dataset. Positive-curvature counts are
735,471 for DS7, 735,205 for DS8 and 735,206 for DS9; rejected subsets remain
accounted for. Two synthetic tests check score cancellation, batch-independent
selection and rejection of nonpositive curvature. An independent scalar
enumeration audit on 20 random cases matches every chosen subset and objective
within 4.45e−16. All workers exit zero in 74–90 seconds, under 300-second caps.
Source bindings and Ruff checks pass.

## Decision and remaining work

Retain score-balanced selection as a working research method for compressing
these scouted datasets. It resolves the large source-location shifts caused by
geometry-only selection on this panel without altering the Doppler model.
It does not reduce the amount of data required to discover the pooled solution.
The selection inherits the pooled model's bias and site-conditioned candidates.

To establish practical sub-km performance, the next evaluation must distinguish
preservation of an already good full-pool fit from independent estimation with
limited data. Useful next tests include fixed smaller scouting prefixes with
later scans reserved for evaluation, and applying the frozen rule to previously
unused temporal groups. Independent surveyed position and historical timing
authority remain necessary for an absolute accuracy claim.

See [summary](summary.json), [selector](score_selector.py), [runner](run.py),
[scalar audit](scalar_selector_audit.json), and per-dataset outputs with all
starts and target results. No new RF, production edits or publication occurred.
Artifacts are local. Reproduce using `batch.py prepare`, `batch.py run` and
`summarize.py` under a NumPy/SciPy interpreter in a fresh output context.
