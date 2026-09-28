# Independent 8/12-c128 cohort audit

This audit independently parsed the completed host `rows.jsonl` rather than
reusing the cohort's hit-audit totals. It checked the 704 manifest/context hash
pairing, all 22 receiver/probe windows per dwell, eight emitted candidates per
window, finite scored fields, and `glrt_complete == 1` for all 123,904 emitted
candidates. It then performed a fresh maximum-cardinality bipartite match for
each same-window candidate set. An edge exists only when the original positive
and native positive differ by at most two epoch samples and 8 kHz tracking CFO.
The margin gate is 0.025.

| Scope | Dwells | Windows | Baseline positive hits | Recovered hits | Recovery | Native positive hits | Unmatched native positives | Newly positive baseline-negative windows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Full 8/12-c128 | 704 | 15,488 | 19,581 | 18,404 | 93.989% | 19,248 | 844 | 151 |
| Held out after excluding the selected 64 | 640 | 14,080 | 17,912 | 16,883 | 94.255% | 17,631 | 748 | 134 |

The full result reproduces the reported 18,404/19,581 and the held-out result
reproduces 16,883/17,912. At 2.5 MS/s, full-cohort recovery is 4,347/4,573
(95.058%); held-out recovery is 3,893/4,088 (95.230%). Per-rate details and
input hashes are in [COHORT_AUDIT.json](COHORT_AUDIT.json).

`unmatched_native_positive_hits` is the difference between native positive
hypotheses and one-to-one recovered baseline positives. It is an association
result under the stated gates, not a false-positive count. The 151 full-cohort
and 134 held-out newly-positive windows likewise identify baseline-negative
windows with at least one native positive candidate; they do not establish
scientific truth without separate adjudication.

The 704 result includes the 64 dwells used to select the 8/12 budget. The
640-dwell subset removes exactly the `host64-812-c128-v1` manifest selection;
it remains a held-out subset of the same DS7 corpus.

## Separate 4/12-c128 host result

The same independent parsing and matching checks were also applied to the
completed 4/12-c128 host cohort. This is a separate method result, not an ARM
measurement.

| Scope | Dwells | Baseline positive hits | Recovered hits | Recovery | Native positive hits | Unmatched native positives | Newly positive baseline-negative windows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Full 4/12-c128 | 704 | 19,581 | 15,545 | 79.388% | 17,120 | 1,575 | 171 |
| Held out after excluding its selected 64 | 640 | 17,912 | 14,298 | 79.824% | 15,689 | 1,391 | 156 |

Both scopes contain 22 windows per dwell and eight completed-GLRT candidates
per window. The same association caveat applies: unmatched native positives
and newly positive baseline-negative windows are not false-positive counts.
