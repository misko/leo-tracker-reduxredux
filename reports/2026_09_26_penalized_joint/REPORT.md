# DS5 deterministic association-regularization follow-up

This follow-up evaluates a simpler deterministic version of the joint model on all 42 DS5 scans. It uses the empirical historical TLE timing prior, a 0.1-second timing grid over the retained support, deterministic multi-start coordinate ascent, and an explicit cost for changing a track away from its original satellite ID. Candidate sets remain independent by location. There is no geographic search, cross-location proposal sharing, new RF collection, or production change.

The predeclared primary change penalty is `log(12) = 2.4849` nats, corresponding to 12:1 prior odds for retaining the original ID versus any one alternative. Zero and 5 nats are sensitivity controls. The penalty affects assignment selection only; the held-out predictive score does not include the penalty.

All 42 scans / 1,739 tracks completed with no failures. The zero-penalty arm exactly reproduces the prior deterministic empirical-joint NLL for every site and scan (maximum difference 0). Four focused tests pass.

Lower NLL is better. A negative known-minus-alternative gap favors the known receiver location.

| Assignment change penalty | Known preferred to Sacramento | Mean / median gap | Known preferred to Reno | Mean / median gap |
|---:|---:|---:|---:|---:|
| 0 nats | 27/42 | -0.0451 / -0.0335 | 30/42 | -0.0619 / -0.0436 |
| log(12) nats, primary | 28/42 | -0.0443 / -0.0285 | 26/42 | -0.0537 / -0.0254 |
| 5 nats, sensitivity | 28/42 | -0.0466 / -0.0298 | 30/42 | -0.0620 / -0.0372 |

The primary 12:1 retention prior is not a robust improvement: it gains one Sacramento comparison but loses four Reno comparisons. The stronger 5-nat sensitivity restores the Reno count and retains the one-count Sacramento gain, but it was not the predeclared primary model and therefore cannot be selected from this dataset as a validated improvement.

The penalty reduces reassignment but does not merely freeze the model:

| Penalty | Mean changed tracks, reference | Sacramento | Reno |
|---:|---:|---:|---:|
| 0 | 7.69 | 8.95 | 9.38 |
| log(12) | 4.64 | 5.71 | 7.00 |
| 5 | 4.02 | 5.02 | 5.86 |

For the six DS5 cases whose Reno estimate is at least 100 km wrong, known beats Reno in 5/6 scans at zero penalty, 4/6 with the primary penalty, and 4/6 with 5 nats. Thus association-retention regularization does not solve the severe-error subset.

Conclusion: keep zero-penalty deterministic joint fitting as the simple reproducible reference, but do not claim that an ID-change penalty recovers performance across DS5. The full probabilistic joint+clock experiment improves the Sacramento count and severe Reno failures, but its chain disagreement remains too large for deployment. The next model change should target calibrated assignment marginalization and posterior exploration rather than tune a global retention penalty on DS5 outcomes.

Artifacts:

- `aggregate.json`: verified aggregate counts and strata.
- `results.json`: complete per-scan outputs and selection receipts.
- `results_v2_shard_*.json`: four successful source shards.
- `run.py`, `joint_selection.py`: evaluation harness and deterministic selector.
- `test_joint_selection.py`, `test_aggregate.py`: focused tests.

