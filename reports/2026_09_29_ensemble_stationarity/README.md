# The N8 ensemble advantage partly depends on per-scan location mixing

Requiring one location to explain all five targets reduces the N8 ensemble's
advantage substantially, but does not eliminate it. The shared-location
mixture still beats the fixed N24 position in each dataset under the inherited
q020 scoring model. This clarifies the earlier comparison without changing
any RF likelihoods, fitted positions, prior weights or target selection.

| Dataset | Shared-location N8 minus N24 | Per-scan N8 minus N24 | Extra gain from per-scan mixing |
|---|---:|---:|---:|
| DS7 | +50.270 | +187.062 | +136.792 |
| DS8 | +5.885 | +148.135 | +142.250 |
| DS9 | +32.307 | +109.797 | +77.489 |
| Total | +88.462 | +444.993 | +356.531 |

Values are natural-log predictive-score differences, not metres. About 80.1%
of the earlier aggregate advantage disappears when one component must be
shared across all five targets. This percentage describes this score comparison,
not a fraction of physical error explained or an accuracy improvement.

## Two different predictive questions

Let L[s,k] be the already timing-integrated density of target scan s at source
N8 position k. Each dataset has three fixed positions with equal prior weight.

```
One uncertain stationary location:
    log(sum_k product_s L[s,k] / 3)

Location mixed independently per scan:
    sum_s log(sum_k L[s,k] / 3)
```

The first expression has one latent location-component index across the
five targets. The second independently mixes that index per scan. Timing
offsets remain independent between scans in both expressions. The fixed N24
position is scored as sum_s log L[s,N24]. No target location is optimized.

Earlier reports explicitly used sums of per-scan marginal predictive scores.
Those scores remain valid for that stated comparison. They do not equal the
joint density of all targets at one uncertain stationary location. The two
mixtures answer different questions; neither is universally larger. Tests
include a case in which a shared mixture wins because all scans agree.

For a stationary-location validation set, future comparisons should report
the shared-location joint score as well as per-scan marginal scores. Per-scan
mixtures may also serve as discrepancy models, but should not be described as
calibrated uncertainty about one fixed position without further evidence.

## Target disagreement

The leading component indices, in timestamp order, are:

| Dataset | Per-target leading component indices | Shared posterior leading component |
|---|---|---:|
| DS7 | 0, 1, 2, 1, 2 | 1 |
| DS8 | 1, 0, 2, 0, 1 | 1 |
| DS9 | 0, 2, 2, 1, 2 | 2 |

Indices identify the three previously fitted N8 *locations*, not satellites,
receiver IDs or physical handovers. The shared posterior concentrates almost
entirely on the listed component. Under the independently mixed posterior,
the probability that all five component indices happen to agree is about
4.83e−62, 2.06e−64 and 2.74e−36 respectively. These extreme model-conditional
values demonstrate disagreement under this likelihood; they do not prove
receiver motion or establish calibrated physical probabilities.

The residual +88.462 shared-mixture advantage shows that per-scan mixing alone
does not explain the earlier preference over N24. A location model can still
score better than the N24 point under the same stationary assumption. The
candidate banks, measurement likelihood and uncertainty model therefore still
need scrutiny. Do not select a new operating location from these target
posteriors and report it as independently validated accuracy.

## Verification and limits

The [protocol](PROTOCOL.md) was written before this recalculation. The fifteen
source result files and manifest were checked against their original evidence
seal; session identities, source exclusion, fixed position order and numerical
qualification were verified. No new RF data were loaded and no model was fitted.
The [results](results.json) include every component's summed score, posterior
weights, per-scan weights, both integration resolutions and provenance hashes.

Repeating all comparisons with stored 32-node audit scores changes results by
at most 0.008413 log units (DS7), 0.001123 (DS8), and 0.001482 (DS9). Signs and
conclusions are unchanged. Three tests check explicit mixture enumeration,
the possibility of shared-mixture advantage, permutation invariance and
large-negative-log numerical stability. All passed, as did Ruff.

This is a post-hoc semantics diagnostic on explored targets. The location
support is only three source-fit points, banks are site-conditioned, timing
priors are uncalibrated, and the geographic reference remains exposed and
unsurveyed. No geographic accuracy gain is claimed. Prior reports and their
published score definitions remain unchanged.

```bash
python3 -m unittest discover -s reports/2026_09_29_ensemble_stationarity -v
python3 reports/2026_09_29_ensemble_stationarity/study.py
```

The numerical result uses exclusive creation. Reproduce in a fresh archived-run
context. These are local research artifacts; no production or RF changes.
