# Exploratory coarse-only candidate-gate frontier

This is an offline, **training-only** exploration on the same frozen 704-dwell
Wave4 cohort used to inspect its candidates. It is not a holdout result and is
not a runtime, timing, or ARM qualification. Every policy uses only fields
already available before fine refinement: `coarse_score`, the emitted
coarse-rank index, rate, and the coarse epoch/bin identity. Quality is measured
after filtering candidate objects with the frozen one-to-one matcher against
the standard baseline.

The useful exploratory frontier is a per-rate absolute score gate:

| Rate (Hz) | score threshold | emitted candidates | removed | recovered hits |
| ---: | ---: | ---: | ---: | ---: |
| 2,500,000 | 0.150 | 26,752 | 0 | 4,515 |
| 5,000,000 | 0.150 | 38,016 | 0 | 5,360 |
| 7,500,000 | 0.175 | 24,991 | 7,393 | 5,100 |
| 10,000,000 | 0.152 | 17,402 | 9,350 | 4,251 |
| **total** | — | **107,161** | **16,743** | **19,226 / 19,581** |

The original candidate inventory and fine-precision call count were 123,904.
If implemented before fine refinement, this policy would issue exactly 107,161
candidate-level fine calls, a reduction of 13.5%. Every emitted candidate also
reaches the final-GLRT path, so 107,161 is its pre-cache GLRT-call opportunity.
The frozen runner counted 120,197 actual GLRT executions, 19,078 GLRT cache
hits, and 15,371 boundary-fallback candidates. Those cache and fallback totals
cannot be projected exactly from filtered rows because the cache keys and
fallback decisions change with the remaining candidates; this report does not
turn the candidate reduction into a claimed physical call or time reduction.

For comparison, a global 0.152 threshold also retained all 19,226 recovered
hits but emitted 114,554 candidates. Raising it to 0.153 removed 11,780 but
lost one recovered hit. Rank caps, score/max ratios, and the tested rank-plus-
absolute combinations did not provide a better same-cohort full-recovery
frontier: the closest rank-plus threshold case emitted 91,093 candidates but
recovered 19,194 hits.

The apparent 7.5 MHz gain depends on selecting 0.175 after viewing this cohort.
It needs a separately frozen holdout and a native replay before it can be
considered for implementation. No classifier was built, no sealed source was
changed, and no ARM job was run.

## 2.5 MHz targeted extension

The initial 0.150--0.175 range removed no 2.5 MHz candidates, so it did not
justify a 2.5 MHz speed expectation. A small rate-only extension found a
separate coarse-score band at 0.30. The table gives the most aggressive tested
0.001-grid point within each allowed recovered-hit loss; all other rates remain
ungated in this calculation.

| allowed 2.5 MHz recovered-hit loss | threshold | emitted | removed | actual loss |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 0.300 | 16,681 | 10,071 | 0 |
| 5 | 0.305 | 10,226 | 16,526 | 5 |
| 10 | 0.312 | 6,030 | 20,722 | 9 |
| 20 | 0.313 | 5,687 | 21,065 | 11 |

At 0.314 the loss jumps to 30, so this bounded grid found no more aggressive
point within twenty losses. Thus 2.5 MHz does have an exploratory coarse-only
candidate-reduction opportunity; the prior no-op was only the too-low threshold
range, not evidence that rate gating helps only higher rates. These values are
still selected on the same 2.5 MHz data and require holdout plus native replay.

Evidence and reproduction:

- `analyze.py` loads Wave4 `host704/rows.jsonl`, retains every window, and
  filters only its candidate arrays.
- `results.json` records every evaluated policy, candidate inventory, exact
  frozen matcher output, source hashes, and the compact Pareto frontier.
- `rate2500_frontier.py` and `rate2500-results.json` record the narrow 2.5 MHz
  extension; it does not rescan other rates.
- `test_analysis.py` uses real frozen candidate rows to verify that filtering
  uses coarse fields, changes the dynamic candidate inventory, preserves the
  original candidate objects, and sends that inventory to the frozen matcher
  without fabricating scientific scores.
- Inputs are Wave4 `host704/{manifest,rows}.jsonl`, the frozen standard
  baseline, and `independent_summary.py`; their SHA-256 hashes are in
  `results.json`.
