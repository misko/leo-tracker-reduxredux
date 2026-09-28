# Post-review lane-continuity correction

This correction supersedes the four-window means in `CORRECTION.md` and
`profile-results-v3.json`. Visits 5, 8, and 11 are channel 3 at 11.44 GHz.
Visit 12 is channel 2 at 11.19 GHz. A raw acquisition-CFO line cannot be
transferred between those lanes without a previously frozen normalization,
alias, and emitter-continuity rule. No such rule was frozen. Visit 12 remains
in the sealed per-window measurement rows, but its train-line prediction is
classified as `inapplicable` in `lane-eligibility-audit.json`.

The only eligible temporal comparisons are visits 5/8 training and visit 11
held, separately for each receiver. They bind to baseline tracks
`sha256:775d3aa...` for receiver 0 and `sha256:96d04708...` for receiver 1.
Both tracks are channel 3 at 11.44 GHz. Their masks at visits 5/8/11 are
`true,true,false`. The exported canonical 11.2 GHz frequencies equal
`(raw acquisition CFO - alias_index × 227272.72727272726) × 11.2/11.44`
within `1.1e-10 Hz`; alias indexes are 0 for receiver 0 and 3 for receiver 1.

Eligible held profiled coherence at visit 11 is:

| receiver | baseline | ordinary profile | robust profile | differential phase |
| --- | ---: | ---: | ---: | ---: |
| 0 | 0.13431 | 0.15063 | 0.15134 | 0.02984 |
| 1 | 0.10302 | 0.10410 | 0.10459 | 0.02673 |

These are one held visit per receiver, selected before this review but filtered
after the methodological issue was discovered. They are diagnostic temporal
self-consistency values, not a pristine holdout, frequency accuracy, or
precision result. The negative-control gate remains unmet. No extractor or
downstream geographic method is promoted.

No additional IQ was read. Wave2 cumulative use remains 153,600,000 bytes and
20.40 measured analyzer seconds.
