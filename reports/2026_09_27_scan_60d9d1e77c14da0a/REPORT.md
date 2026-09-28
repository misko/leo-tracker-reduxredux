# Held-out review: `scan-fw-60d9d1e77c14da0a`

The scan began at 2026-09-27 00:00:03 UTC and contains 58 tracks. It is chronologically after the DS5 model-development corpus. Candidate generation was repeated from this scan's training partition independently at each location; no DS5 candidates or cross-location candidates were reused.

## Locations

| Label | Latitude | Longitude | Distance from ground truth |
|---|---:|---:|---:|
| Ground truth | 37.849033 | -122.485654 | 0 km |
| Sacramento branch estimate | 37.847242 | -122.419735 | 5.791 km |
| Reno branch estimate | 42.724615 | -121.266843 | 551.891 km |

The branch names describe the search prior, not the physical city containing the final point. In particular, the “Sacramento” result is a near-ground-truth Bay Area point.

## Original published baseline

The following reproduces the scanner's published capped-RMS objective exactly:

| Position | Capped weighted RMS | Uncapped weighted RMS | Rank |
|---|---:|---:|---:|
| Sacramento | **283.961 Hz** | 475.389 Hz | 1 |
| Ground truth | 298.493 Hz | **468.329 Hz** | 2 |
| Reno | 423.118 Hz | 516.345 Hz | 3 |

This baseline uses `randomized-evaluation-rms-v1`: held-out RMS participates in satellite-ID selection. It is therefore optimistic and is shown separately from the clean training-only comparison below. It selects Sacramento, corresponding to 5.791 km error, and strongly rejects Reno.

## Clean predictive comparison

Both arms below select candidates using training observations only and use the same 100 Hz Gaussian one-second-block likelihood and historical TLE-age timing prior. Lower held-out predictive NLL per block is better.

| Position | Frozen-ID baseline | Exact soft assignment |
|---|---:|---:|
| Ground truth | 24.8440 | 8.1054 |
| Sacramento | 22.8058 | **7.9823** |
| Reno | **19.7271** | 8.2910 |
| Winner | **Reno** | **Sacramento** |

The frozen predictive baseline fails badly, selecting the position 551.9 km away. The soft model reverses this: ground truth beats Reno by 0.1856 NLL per held-out block, while Sacramento beats ground truth by 0.1231 per block. Thus the new model recovers the correct local region and eliminates the catastrophic Reno result, but it does **not** distinguish the exact ground-truth point from the nearby 5.8 km Sacramento-branch point correctly.

There are 879 held-out one-second blocks. They are dependent, so the aggregate score gap must not be converted into a calibrated location probability.

## What changed

The soft posterior's most likely identity differs from the frozen identity on 14/58 tracks at ground truth, 16/58 at Sacramento, and 31/58 at Reno. A handful of frozen associations create extremely poor held-out likelihoods. For example, at ground truth one frozen track contributes -8,547 log-score units, versus -429 after soft assignment. Marginalizing identities prevents those hard mistakes from dominating the entire scan.

Only 6/58 ground-truth tracks, 4/58 Sacramento tracks, and 10/58 Reno tracks have maximum soft-assignment probability below 0.8. The mean maximum assignment probabilities are 0.960, 0.970, and 0.934 respectively.

## Conclusion

This held-out example supports the new model's main purpose: it turns a catastrophic far-away predictive result into a near-ground-truth result without candidate sharing or evaluation-driven assignment. It does not yet resolve locations separated by roughly 6 km. The next useful test is additional post-DS5 scans, evaluated with this protocol frozen.

Artifacts: `results.json` contains complete per-track scores and assignment probabilities; `shortlist.json` records the independently generated candidates; `run.py` is the hash-pinned evaluator.

