# DS1 iteration 7: fixed exact-residual likelihood ablation

## Result

Iteration 7 completed in 235.6 seconds with four workers.  It consumed exactly
the 56 qualified iteration-6 candidates (28 per prefix-6 TRAIN group), their
stored hard associations, and their stored exact-SGP4 per-NORAD rate maps.
It reconstructed the exact fixed-Earth residual sequences without refitting
an orbit rate, changing an association, or searching a coordinate or tau.

Two reference-free rankings were computed on the same exact residuals:

1. An independent Gaussian with a profiled global scale and per-track CFO.
2. A correlation-aware robust approximation of the prior formal model: fixed
   AR(1) `rho=0.65`, one-second correlation time, Student-t `df=4`, a
   profiled global scale, and robust per-track CFOs.

The Gaussian ranking retained the iteration-6 spatial winner in both groups.
The AR(1)+Student-t ranking changed both timing/location rows, including a
materially worse post-seal result for group `00`.

## Inference boundary and residual construction

Every candidate enters from `iteration6-results.json` with its qualified exact
replay gate, exact rate map, and exact hard associations.  For each selected
NORAD and receive time, iteration 7 calls the same exact SGP4 state replay
used by the gate: orbit phase is shifted by the persisted causal rate while
Earth rotation remains at receive time plus the candidate global tau.  The
residual is measured Doppler minus this exact prediction.

Rates are immutable inputs.  CFO and scale are likelihood nuisances only:
the independent model profiles a per-track mean CFO and one scale bounded to
`[5, 2000]` Hz.  The robust model profiles a per-track Student-t innovation
location with 12 bounded IRLS updates and one scale on the same interval.  Its
predeclared log-scale prior is centered at 250 Hz with width 1.5.  No
reference/truth field is accepted by the inference program; post-seal
coordinates are read only by `evaluate_iteration7_postseal.py` after results
are written.

## Sequence and track accounting

Each candidate retains its own frozen iteration-6 hard association; there is
no reassignment in either likelihood.  Track cardinality, receive-time rows,
and occupied-second accounting are identical across candidates in a group, so
both models use the same track accounting.  A sequence is one selected
hard-associated track sorted by its receive time.  The first point supplies
one unconditional innovation; every later point supplies one AR(1)-
standardized conditional innovation.  There is no time thinning and no claim
that those conditional innovations are independently sampled observations.

For likelihood aggregation, each track's mean innovation NLL is weighted by
the same occupied-second track weight as the earlier capped-loss objective,
then normalized by total occupied seconds.  This prevents long tracks from
silently changing the contribution rule between the two models.

| Group | Tracks/sequences | Observations and conditional innovations | Transitions | Occupied-second weight |
|---|---:|---:|---:|---:|
| `20260921_00` | 476 | 8,285 | 7,809 | 7,532 s |
| `20260921_16` | 298 | 9,686 | 9,388 | 5,426 s |

## TRAIN rankings

| Group | Model | Selected tau | Scale | NLL per weighted innovation | Post-seal error |
|---|---|---:|---:|---:|---:|
| `20260921_00` | Iteration-6 exact baseline | -1.00 s | — | — | 3.157 km |
| `20260921_00` | Independent Gaussian | -1.00 s | 167.15 Hz | 6.537833 | 3.157 km |
| `20260921_00` | AR(1)+Student-t | -1.25 s | 134.36 Hz | 5.505604 | 4.204 km |
| `20260921_16` | Iteration-6 exact baseline | -0.50 s | — | — | 0.423 km |
| `20260921_16` | Independent Gaussian | -0.25 s | 286.72 Hz | 7.077437 | 0.423 km |
| `20260921_16` | AR(1)+Student-t | -1.00 s | 161.21 Hz | 5.742068 | 0.423 km |

The group-`16` likelihood winners have the same iteration-6 spatial
coordinate at different retained taus, so their external position error is
unchanged.  For group `00`, the Gaussian score kept the iteration-6 row, while
the robust score preferred the retained iteration-4 coordinate/tau.  The top
two robust NLLs in `00` are very close (5.505604 and 5.505695), so this
particular robust rank reversal is not a large likelihood separation.

## What worked, what did not, and next

The refit-free construction worked: exact residual replay, both nuisance
profiles, and both rankings completed in under four minutes, and all 56 input
candidates already had qualifying exact replay gates.  Independent learned
scale was stable and retained the prior spatial selection in both groups.

The correlation-aware robust formulation did not improve this sealed
comparison.  Its group-`00` rank reversal increased external error by about
1.05 km, while group `16` changed only tau on the same spatial coordinate.
This is evidence against adopting the robust rank as a replacement objective
for this fixed candidate set, not a rejection of residual likelihoods in
general.

The next bounded diagnostic is to measure rank stability under a small
predeclared sensitivity grid around the historical AR(1) parameters on these
already reconstructed residuals.  It should report agreement and NLL gaps,
without changing rates, associations, coordinates, or using reference data to
choose settings.

## Artifacts and reproduction

- `iteration7-results.json`: reference-free exact residual likelihood
  inference, candidate ranks, nuisance fits, and sequence accounting.
- `iteration7-postseal/iteration7-postseal.json`, CSV, and PNG: external
  evaluation only.

```bash
.venv/bin/python -m pytest -q reports/2026_09_24_ds1_joint_rate_search/test_*.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv/bin/python reports/2026_09_24_ds1_joint_rate_search/iteration7_residual_likelihood.py \
  --workers 4 --output reports/2026_09_24_ds1_joint_rate_search/iteration7-results.json
.venv/bin/python reports/2026_09_24_ds1_joint_rate_search/evaluate_iteration7_postseal.py \
  --inference reports/2026_09_24_ds1_joint_rate_search/iteration7-results.json \
  --output-dir reports/2026_09_24_ds1_joint_rate_search/iteration7-postseal
```
