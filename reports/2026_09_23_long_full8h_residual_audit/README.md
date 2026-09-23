# Full-8h TRAIN residual concentration audit

This read-only diagnostic replays the fixed candidate IDs at each sealed
full-72 TRAIN coordinate, recomputes the CFO-centered training residual for
each track, and verifies the exact sealed duration-weighted capped objective.
It does not fit a location, alter candidates, run a new search, use position
truth, or open validation or test data.

Both fixed views reproduce their sealed objective exactly: 295.369273408 Hz
for Sacramento and 295.374344591 Hz for Reno (absolute difference 0 Hz). The
audit covers all 3,587 tracks and 60,760 duration-weight seconds. The
duration-weighted 10th/50th/90th track spans are 11.61/22.63/37.56 s.

| Measure | Sacramento | Reno |
| --- | ---: | ---: |
| slope 10th / 50th / 90th percentile (Hz/s) | -46.79 / -3.47 / 34.54 | -46.81 / -3.46 / 34.51 |
| capped loss share: top 1 / 10 / 100 tracks | 0.66% / 5.03% / 33.32% | 0.66% / 5.03% / 33.31% |
| capped loss share: top 1 / 10 scans | 3.58% / 28.84% | 3.58% / 28.81% |
| distinct selected candidate IDs | 1,400 | 1,400 |
| candidate IDs supported in two scans | 48 | 47 |

No selected candidate appears in more than two scans. The per-scan
duration-weighted slope-sign coherence has 10th/50th/90th percentiles of
0.472/0.609/0.710 (Sacramento) and 0.472/0.610/0.710 (Reno). Every scan has
at least one eligible overlapping track pair; the median within-scan
pairwise covariance of integer-second TRAIN CFO-centered residual means is
2,016 Hz² and 2,047 Hz² respectively. The plot
`results/residual_concentration.png` shows the top-loss track RMS values and
the distribution of scan weighted slopes.

The compact evidence contract has no public per-track receiver field, so this
report deliberately records receiver mapping as unknown and does not invent a
receiver stratification. Pair covariance uses only overlapping integer-second
bins and is descriptive. Slope coherence, recurrence, and residual covariance
can help distinguish patterns worth modelling, but do not establish receiver
drift, orbit error, causality, or calibrated covariance.

`results/results.json` records every scan summary, the top 20 loss tracks,
candidate support histogram, source bindings, and the exact parity check.
Its SHA-256 is in `results/results.sha256`.

Reproduce to a fresh directory:

```bash
.venv/bin/python reports/2026_09_23_long_full8h_residual_audit/audit.py \
  --results reports/2026_09_23_long_training_full8h_position/results \
  --manifest reports/2026_09_23_long_training_cache_full8h/manifest.json \
  --cache-root /tmp/leo-long-training-cache-full8h \
  --single-tool reports/2026_09_23_long_training_search/search.py \
  --fast-loader reports/2026_09_23_long_training_fast_score/loader.py \
  --output /tmp/long-full8h-residual-audit
```

Ruff and the held-mutation regression test passed for `audit.py`. The helper
fails closed if the inference seal, frozen session list, sealed helper source,
any cache receipt or NPZ hash, fixed candidate IDs, per-track sealed RMS
values, or aggregate fixed objective differ. It replays the fixed assignments;
it does not rerun candidate selection.

`results_superseded_unmasked/` and `audit_superseded_unmasked_source.txt`
preserve the initial unpublished attempt. That attempt included held rows in
the covariance input and is superseded. The current results use TRAIN rows
only for both residual slopes and covariance.
