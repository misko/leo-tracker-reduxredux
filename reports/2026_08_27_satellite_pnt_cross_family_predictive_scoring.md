# Satellite PNT paired cross-family predictive scoring

Status: opened-development leave-one-background-pair-out diagnostic; no threshold, posterior odds, satellite identity, correction, or positioning claim.

The catalogue model is the frozen true causal-TLE curve at `tau=0` plus one training-only CFO offset. The primary radio model is a training-only line. Both are scored once on the same usable odd-Qin future rows.

| Case | Truth | Future rows | Raw catalogue/radio RMS (Hz) | LOO radio−catalogue NLL | LOO preference | Correct |
|---|---|---:|---:|---:|---|---|
| `hard-null-062228:catalogue-orbit` | catalogue-orbit | 597 | 54.897376/61.931641 | 13.673579 | catalogue-orbit | true |
| `hard-null-062228:radio-polynomial` | radio-polynomial | 599 | 57.468643/57.654514 | -1.385489 | radio-polynomial | true |
| `hard-null-105640:catalogue-orbit` | catalogue-orbit | 598 | 57.731176/63.028892 | 6.564770 | catalogue-orbit | true |
| `hard-null-105640:radio-polynomial` | radio-polynomial | 599 | 54.351956/55.387975 | 0.852353 | catalogue-orbit | false |
| `hard-null-111222:catalogue-orbit` | catalogue-orbit | 600 | 56.748485/56.824525 | -0.543347 | radio-polynomial | false |
| `hard-null-111222:radio-polynomial` | radio-polynomial | 599 | 53.592385/53.583351 | 0.562231 | catalogue-orbit | false |

The leave-one-pair-out family preference matches 3/6 truth arms (50.0%).

Only three independent background pairs are available, below the frozen 19-pair finite-rank floor. The result diagnoses current discrimination and covariance scale; it does not calibrate a decision threshold or normalize full-catalogue multiplicity.
