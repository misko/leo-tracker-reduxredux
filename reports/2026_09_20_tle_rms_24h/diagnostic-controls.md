# Polynomial and wrong-time comparisons as diagnostics

Matcher version 5 retains the polynomial and ±500-second comparison scores, but neither comparison contributes an association rejection. The nominal catalogue gates remain, including time-shift-boundary and rank-stability diagnostics. The algorithm version is included in the configuration digest. Historical published products are not modified by this source change.

This counterfactual uses the frozen September 19–20, 05:00 UTC snapshot, with unchanged candidate rankings and numeric scores. It removes polynomial and wrong-time reasons from each comparison independently. A representative track clears if at least one of its comparisons has no remaining reasons.

## Tracks with best held-out RMS <60 Hz and runner-up RMS >300 Hz

| Gate policy | Pass | Fail | No direct representative comparison |
|---|---:|---:|---:|
| Original published results | 6 | 88 | 38 |
| Polynomial diagnostic-only | 45 | 49 | 38 |
| Polynomial and wrong-time diagnostic-only | **66** | **28** | **38** |

Thus making wrong-time controls diagnostic-only clears another **21 tracks**. The 28 remaining failures contain 25 time-shift-boundary failures and eight catalogue leader/rank-instability failures; five tracks have both. The two rank-instability reason strings describe the same eight tracks and must not be added together.

These are individual-track RMS thresholds, not session medians. The 38 other tracks lack their own representative comparison; their absence from the pass/fail columns is not a scientific rejection.

Across **all 279 attempted comparison groups** in the 24-hour snapshot, without these RMS thresholds, 196 would clear and 83 would retain nominal-catalogue rejection reasons. Group hypotheses are not independent satellites.

[Per-track evidence](diagnostic-controls-impact.json) contains the remaining reasons, RMS values and per-comparison reason sets. These are frozen-score counterfactual counts, not a claim of completed production deployment/backfill or independently confirmed satellite identity.

The regression test gives both shifted-time winners and the polynomial an overwhelmingly favorable evaluation likelihood. Their scores remain in the result but do not create rejection reasons. The nominal catalogue and scanner service tests remain in the targeted suite.
