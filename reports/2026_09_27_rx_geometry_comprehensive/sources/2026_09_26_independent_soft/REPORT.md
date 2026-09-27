# Deterministic soft association across all DS5

## Result

All 42 DS5 scans / 1,739 tracks completed with zero failures. The recommended simple model is deterministic soft satellite assignment with:

- site-specific training-only candidate sets (`top 3 + original`), never shared between candidate locations;
- uniform prior probability over the retained real satellite candidates;
- the historical TLE-age timing prior, integrated on the 0.1-second grid;
- one independent timing nuisance variable per track/candidate;
- a constant frequency offset integrated per track;
- 100 Hz Gaussian likelihood on held-out one-second blocks;
- no scan-clock term, no null candidate, no hard assignment, and no sampler.

For each track, the model computes the training posterior over candidate satellite and timing offset exactly, then averages the held-out predictive density over that posterior. Track predictive log densities are summed and divided by the held-out block count.

## All-DS5 comparison

Lower predictive NLL is better. “Known wins” means the known receiver location has lower NLL than the named existing estimate; it is not a geographic localization-success count.

| 100 Hz model | Known beats Sacramento | Known beats Reno | Known is best of all three |
|---|---:|---:|---:|
| Frozen IDs, no clock | 25/42 | 30/42 | 21/42 |
| Sampled joint IDs + clock | 31/42 | 28/42 | 25/42 |
| **Exact soft IDs, no clock/no null** | **30/42** | **30/42** | **24/42** |

The exact soft model recovers the frozen model's Reno performance while adding five Sacramento wins. Relative to the sampled joint+clock model, it loses one Sacramento comparison but gains two Reno comparisons and removes chain instability entirely.

Known-minus-estimate gaps for the exact soft model are negative on average and at the median:

| Comparison | Mean gap | Median gap |
|---|---:|---:|
| Sacramento | -0.1536 | -0.0328 |
| Reno | -0.1358 | -0.0397 |

Excluding the two development scans, known wins 28/40 against each estimate. The mean and median gap favor known at every sample rate (2.5, 5, 7.5, and 10 MHz). In the severe-error subsets, known wins 5/6 against Reno estimates at least 100 km wrong and 1/1 against the Sacramento case at least 100 km wrong.

## Sensitivities

At 100 Hz, adding/removing the scan clock and adding/removing the 10% broad null candidate changes no winning location in any of the 42 scans. This supports selecting the no-clock/no-null form for parsimony rather than outcome optimization.

The declared 200 Hz sensitivity gives 32/42 against Sacramento and 31/42 against Reno for the no-clock/no-null model. This direction is encouraging, but 200 Hz was not the predeclared primary noise setting and should not be promoted based on DS5 outcomes alone.

The posterior mean null probability in the primary clock/null arm is below 0.8% at every site on average, another indication that the broad null component is unnecessary here.

## Interpretation and limits

This is a stable, straightforward prototype, not a validated production localizer. It removes the MCMC convergence failure by making a deliberate approximation: TLE timing is independent by track, even when multiple tracks may belong to the same satellite. That sacrifices potentially useful shared-orbit information in exchange for exact, reproducible inference.

The improvement over frozen IDs is descriptive rather than statistically decisive. Against Sacramento, the soft model flips 11 frozen losses to wins and six frozen wins to losses (paired exact binomial p=0.33); against Reno the changes are six in each direction. DS5 was used during model development, the noise scale is not externally calibrated, the shortlist is finite, and the original train/evaluation blocks retain dependence. A future dataset is required for an unbiased confirmation.

No geographic search, cross-location proposal sharing, production mutation, or new RF collection was performed.

## Artifacts

- `core.py`: exact soft-assignment and timing marginalization.
- `run.py`: hash-pinned all-DS5 evaluation harness.
- `aggregate.py`: accounting, strata, and diagnostics.
- `results.json`: complete scan/site/track results.
- `aggregate.json`: verified summary tables.
- `results_shard_*.json`: four successful source shards.
- `test_core.py`, `test_aggregate.py`: numerical and accounting tests.

