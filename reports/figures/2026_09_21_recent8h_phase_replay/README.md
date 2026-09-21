# Recent-track bounded saved-IQ phase replay

This report replays four phase-blind tracks selected by the frozen inventory
window `2026-09-21T06:34:16Z` through `2026-09-21T14:34:16Z`. Session
`scan-hop-6adcb067e2dbce43` is intentionally excluded because it is analyzed in
the separate primary-track work. For each remaining session, twelve visit
indices were selected deterministically and evenly from the exact shared-visit
inventory. Only those immutable saved-IQ visits were read.

The existing `report_adaptive_dual_rx_raw_coherence.py` research tool trained a
broadband RX1-minus-RX0 frequency on the first 60 ms, checked it on the held
second 60 ms, and then re-correlated both receivers with one CFO branch and
sample reference. The first, middle, and last selected visits in every session
also received the bounded delay search. All twelve delay-search controls chose
zero samples. Published phase products were not modified.

## Long-track results

The corrected pair for each visit was matched to the original long-track RX0
and RX1 observation IDs by its exact tracking-CFO fields. All 48 visits matched.

| Session | Lane | Visits | Median absolute train/held CFO difference (Hz) | Median trained/held coherence | Median wrong-time coherence | Median resultant | Median phase SE (deg) | Median exact/control floor |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `scan-hop-e46d3aba244cf641` | 2 upper | 12 | 12.301 | 0.0890 | 0.00306 | 0.9450 | 5.275 | 30.19 |
| `scan-hop-6ca90c84541ebe31` | 4 lower | 12 | 23.669 | 0.0396 | 0.00216 | 0.9042 | 5.934 | 24.27 |
| `scan-hop-b158f63a64278e61` | 4 lower | 12 | 17.566 | 0.0645 | 0.00341 | 0.9455 | 4.722 | 47.07 |
| `scan-hop-34c0b0e1ae062f97` | 4 lower | 12 | 21.870 | 0.0344 | 0.00332 | 0.9530 | 4.325 | 29.95 |

The wrapped phase values span much of the circle and are not unwrapped into a
geometric trajectory here. The raw JSON retains per-visit phase, frequency,
standard errors, pilot controls, and legacy diagnostics.

## Second-source finding

Forty-seven visits contain one phase-blind dual-receiver pair. Visit 678 of
`scan-hop-34c0b0e1ae062f97` contains two pairs on channel 4 lower. The two
corrected RX0 tracking CFOs are 455071.85 Hz and 339691.36 Hz, and the tool
reports an alias-aware separation of 111892.24 Hz. Both pairs have resultant
length above 0.95 and exact-to-control power-ratio floors above 13.7.

This visit is a candidate for a real same-visit matched-pilot double-difference
follow-up. The `double_differences` field in the raw tool output uses the legacy
asynchronous-centroid calculation. It is retained only as a diagnostic and is
not interpreted as geometric phase evidence.

## Files

- `summary.json` binds each chosen corrected pair to the original track
  observation IDs and records the selection, controls, and medians.
- Each `*.raw-coherence.json` is the complete immutable research result from
  the generic replay tool.
- Each matching PNG renders that tool result for inspection.
