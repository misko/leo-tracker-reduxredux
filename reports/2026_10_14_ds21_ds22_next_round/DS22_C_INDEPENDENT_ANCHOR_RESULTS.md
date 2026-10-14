# Independent half-band geographic anchors in the original full C model

The completed paired control gives a small training-selected improvement on DS22-003 and no change on DS22-001. It does not resolve the full-band discrepancy or establish the accuracy target. DS22 distances use the configured, still unconfirmed reference location.

Only geography was imported from independently fitted half-band models. All three anchors shared the original full-band winner's remaining physical parameters and receiver nuisance initialization. The full-band observations, candidate bank, objective, priors, fitted c, and per-call 20-second/600-iteration limits were unchanged. Each stationary fixed-position profile could proceed to a free-position release in a 25 km disk around that anchor. Selection used the minimum stationary release objective before reference access.

| Case | Original configured distance, km | Selected anchor | New configured distance, km | Original objective | New objective |
|---|---:|---|---:|---:|---:|
| DS22-001 | 21.266493 | Original full-band | 21.266493 | 41863.551059 | 41863.551059 |
| DS22-003 | 2.827544 | Independent lower-band | 2.709445 | 33448.986949 | 33431.507310 |

DS22-003's selected likelihood NLL fell from 33162.958700 to 33145.996294. This is a frequency-fit change, reported separately from the 0.118099 km configured-distance improvement. Its independent upper-band fit remains closer to the configured reference (1.663814 km).

There were nine actual optimizer calls across the pair: four on 001 and five on 003. Both alternative profiles on 001 failed convergence within their limits, so their releases were skipped. The 003 upper-anchor profile also failed the independent stationarity criterion (0.002957262 > 0.001), despite the solver returning success after 15.272 seconds and 488 evaluations. Its objective, 32749.329539, was lower than the accepted solutions, but it was not admitted or released. A zero-fit derivative audit is the next diagnostic; these failures do not prove that those geographic basins cannot help.

Both case seals existed before the paired evaluator read the configured reference. No held observations were used for fitting or selection. The independent upstream fits add computation; this is not an equal end-to-end-budget comparison. No incumbent or production model was replaced.

Evidence:

- Frozen control source: `d27809098`; paired evaluator: `66c86646e`.
- 003 qualification: 38.460902 seconds, zero optimizer calls; run: 71.066988 seconds, five calls.
- 003 terminal SHA256: `abb9dd04e96dc3a2510a15814d36c050fba5c6aab38a13fae79682699f035f9f`.
- 003 seal SHA256: `d9170ea21150a025890857563f52112ad50ff5c6412328ec64c7a5c36492f228`.
- Paired report: `local/ds22-c-independent-anchor-comparison-v1/report.json`.
- Earlier 001 receipts and limitations: `DS22_C_ANCHOR_001_PROGRESS.md`.
