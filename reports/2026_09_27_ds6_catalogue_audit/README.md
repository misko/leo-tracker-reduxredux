# Full-catalogue coverage at DS6 baseline winners

The three completed scans with the lowest anchor shortlist mass were selected
before this audit, without using geographic error. At each frozen position and
timing, every catalogue candidate was propagated at the exact observation
epochs in bounded chunks. Candidates above the horizon at any training epoch
were scored under the identical Student-t4 100 Hz training-offset model.

| Scan suffix | Minimum retained mass at winner | Missing training-best candidates | Total full-catalogue training-score gain |
|---|---:|---:|---:|
| 60d9d1e77c14da0a | 0.9768305 | 0 | 0.0234425 |
| aa9770c66396e928 | 0.9899798 | 0 | 0.0100707 |
| 5eaaa2a8f8c995b3 | 0.9990680 | 0 | 0.0009324 |

This makes catalogue pruning an unlikely explanation for the large residual
errors **at these particular estimates**. It does not prove catalogue coverage
at every geographic location, rule out another optimum, or establish physical
satellite identity. No location was refitted and no ground-reference coordinate
was loaded. The candidate probabilities are conditional on the existing model.

All original baseline track IDs appear exactly once in each audit. The tests
check retained probability against known mixtures, log-shift invariance, frozen
source/input hashes, coverage of all baseline tracks, and the identity between
lost probability and training log-score change.

The fixed-model full-DS6 baseline continues separately. Short observed track
durations motivate a later test of linking consistent same-source fragments,
but that proposal has not been implemented or validated by this audit. No raw
IQ was replayed, no RF was captured, and no production service was changed.
