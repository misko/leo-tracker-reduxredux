# The complementary visit fold gives mixed strict CFO agreement

The frozen half-shrink rule gained **nine strict matches** across the complementary fold of DS30-0019 and DS30-0274. DS30-0019 lost two and DS30-0274 gained 11. The earlier odd fold gained 18 and six on the same recordings. The even-fold gain was **0.21% of the 4,270 original candidate-positive lanes**. Both loose counts stayed unchanged. [Frozen protocol](held-cfo-complement-protocol.md) · [Candidate-only forecast seal](measurements/held-cfo-complement-plan.json.gz) · [Scored receipt](measurements/held-cfo-complement-score.json)

Both radios at cycle positions 2, 4 and 6 were removed before the released Graph. Visit numbering restarted per original pilot edge, channel and actual RF. Every full anchor and the original odd visits remained measured in training. The two measured, same-lane brackets had to share an unambiguous Graph piece and signed alias and satisfy the published spacing, slope and arrival checks. After the forecasts were fixed, the rule shifted each eligible short winner halfway toward the forecast within one nominal signed bin, **443.892 Hz**, and kept the measured arrival. The SHA-bound stage and scorer are unchanged from the published rule. [Released stage](held-cfo-features.md) · [Earlier odd-fold scoring](held-short-cfo-shrink.md)

| Recording | Forecasts / moved / with installed reference | Strict with original → shrunk CFO | Restored / spoiled | Loose before and after | Closer / farther among moved with reference |
|---|---:|---:|---:|---:|---:|
| DS30-0019 | 282 / 254 / 249 | 237 → 235 | 3 / 5 | 243 / 249 | 135 / 114 |
| DS30-0274 | 433 / 396 / 384 | 360 → 371 | 14 / 3 | 376 / 384 | 225 / 159 |
| Pooled | 715 / 650 / 633 | 597 → 606 | 17 / 8 | 619 / 633 | 360 / 273 |

Strict means ±250 signed Hz and ±2 samples, and loose means ±2,250 Hz and ±6 samples. Both are evaluated against the same installed winner on the original hardware window. There were 22 forecasts on empty targets and 43 on targets over one bin away. Another 17 moved candidates lacked an installed winner, so they have no error measurement. On **all 3,516 paired even-fold winners**, including 2,883 untouched, the strict count was **2,934 → 2,943** and the loose count stayed **3,147**. All 754 candidate-only and 661 installed-only opportunities remain visible.

| Recording | All even lanes | Both winners | Candidate only | Installed only | Both empty | All paired strict before → after |
|---|---:|---:|---:|---:|---:|---:|
| DS30-0019 | 4,480 | 1,478 | 366 | 238 | 2,398 | 1,245 → 1,243 |
| DS30-0274 | 5,072 | 2,038 | 388 | 423 | 2,223 | 1,689 → 1,700 |

| Moved with installed reference | Signed bias before → after (Hz) | RMS (Hz) | MAE (Hz) | Absolute p95 (Hz) | Max absolute (Hz) |
|---|---:|---:|---:|---:|---:|
| DS30-0019 | 2,603.88 → 2,598.61 | 21,262.20 → 21,259.54 | 2,887.86 → 2,882.01 | 243.53 → 259.80 | 245,531.53 → 245,477.86 |
| DS30-0274 | −1,189.90 → −1,190.74 | 12,152.75 → 12,160.76 | 1,577.70 → 1,563.00 | 264.38 → 193.55 | 142,251.68 → 142,467.69 |
| Pooled | 302.44 → 299.86 | 16,353.18 → 16,355.43 | 2,093.07 → 2,081.85 | 264.09 → 225.43 | 245,531.53 → 245,477.86 |

The even and odd targets are disjoint and partition the original nonanchor calls. The 564 and 866 distinct even-fold donors are disjoint from their targets and edits. No earlier odd-fold edits entered either Graph. All **1,502 and 1,696** full anchor lanes remained intact, including 654 and 891 measured anchor winners. The applied row comparison verified only the selected signed CFO values changed. All original detector calls remain charged.

The two folds use different opportunity classes on the same two roof recordings. The reversal on 0019 and the unchanged loose counts limit the inference to small near-threshold changes in saved receiver agreement. The reference measures the first 8 ms as part of its 20 ms window. It supplies no independent geographical assessment. The assay used two metadata Graph preparations on CPU3 and no waveform, orbit, receiver, or position jobs.

Reproduce with `python -m reports.ALGO08.v3.held_cfo_complement SNAPSHOT` on the retained native fixtures and first-30 ledger pinned by the source. Seal the compressed predictions, then add `--score PLAN.gz SHA256` to open the installed references. The compressed candidate seal is `14ebdc472a275269cfe4f27dbaaa6034c3c7b5a918c911887656f4f201664572`, committed at `51f08d318` before scoring. Nine focused tests passed.
