# Lag-structure timing proposals and restricted ARM GLRT search

The restricted search plus separately measured proposal costs takes **7.377 CPU
seconds per 120 ms dual-RX dwell** on one PLUTO+ ARM core at 2.5 MS/s, versus
25.085 seconds for the preceding full timing search: **3.40x faster**. This is
still 102.5x the 72 ms analysis budget for 40% headroom. It is a research
prototype, not a real-time detector or a production replacement.

## Method

For every 20 ms receiver-window, fold sample-lag products at lags 1, 3 and 5
over physical pilot frame offsets. Correlate each centered folded sequence
against the corresponding template lag structure. Add a centered pilot-power
correlation. Combine the four features by a fixed sum of percentile ranks.
Take four positive local maxima with five-sample circular exclusion, then
search their clipped +/-4-sample timing neighborhoods. All 11 original coarse
CFO lanes and the downstream fine FFT and selective boundary fallback remain.
At 2.5 MS/s this searches at most 36 timing cells instead of 3,333.

Proposals use current-window IQ, sample rate and the edge template. Original
candidate coordinates are evaluation labels only. No receiver or window is
skipped. Each dual-RX 120 ms dwell contains 22 overlapping 20 ms windows.
The four supported rates are 2.5, 5, 7.5 and 10 MS/s.

## Actual GLRT recovery

These are completed IQ-to-GLRT searches, not timing-region coverage. Hits
are original candidate entries with margin >=0.025. Recovery uses the frozen
maximum-cardinality one-to-one matcher in the same receiver/window, within
two timing samples and 8 kHz tracking CFO. Duplicate original entries stay in
the denominator. Recovery within these tolerances does not imply identical
candidate lists or bitwise-identical scores.

| Cohort | Dwells | 20 ms windows run | Original hits recovered | Originally positive windows recovered | Unmatched new positive entries |
|---|---:|---:|---:|---:|---:|
| DS7 mixed rates | 704 | 15,488 | 19,400/19,581 (99.08%) | 6,944/7,007 | 18,328 |
| DS8 mixed-rate subset | 32 | 704 | 779/785 (99.24%) | 309/311 | 880 |
| DS9 mixed-rate subset | 32 | 704 | 902/908 (99.34%) | 372/376 | 973 |
| ARM timing subset, DS7 2.5 MS/s | 4 | 88 | 119/119 (100%) | 49/49 | 139 |

The 704-dwell DS7 cohort is the existing benchmark subset, not all DS7.
DS8 and DS9 transfer tests each select four evenly spaced metadata entries per
rate/edge group. Their smaller scope must not be confused with the earlier
260/420-dwell full-search validation.

| DS7 rate | Windows run | Original hits recovered | Unmatched new positive entries |
|---|---:|---:|---:|
| 2.5 MS/s | 3,344 | 4,551/4,573 | 4,386 |
| 5 MS/s | 4,752 | 5,420/5,466 | 4,932 |
| 7.5 MS/s | 4,048 | 5,137/5,186 | 4,758 |
| 10 MS/s | 3,344 | 4,292/4,356 | 4,252 |

Restricting the search changes candidate competition and produces many extra
positive entries. These are neither recovered baseline hits nor established
false alarms. Their scientific interpretation remains unresolved. DS7 loses
181 original hits, versus five for the preceding full timing search with
boundary fallback. Thus this method improves speed while giving up some
recovery and output equivalence; it is not the preferred quality reference.

DS7 ran 123,904 candidate entries and 18,990 fallback re-evaluations, totaling
142,894 GLRT kernel calls. The ARM subset ran 704 candidate entries and 130
fallbacks, totaling 834 calls. Window counts and kernel-call counts differ.

## ARM runtime

Physical PLUTO+ 192.168.1.15, saved CI16 input resident in RAM, analysis pinned
to CPU0. Proposal timings use three executions of each of four DS7 dwells;
restricted search uses one execution per dwell. Plans, templates and inputs
are prepared before timing. No radio capture or concurrent producer ran in
this experiment. The total below adds independently timed stages, rather
than measuring a fused pipeline's wall time.

| Stage | Mean CPU ms per dual-RX dwell |
|---|---:|
| Native combined-top-four proposal | 988.433 |
| Restricted coarse search | 416.494 |
| Acquisition, including fine FFT | 3,821.640 |
| Boundary conditioning | 1,454.243 |
| GLRT scoring | 571.766 |
| Restricted search total, including other overhead | 6,388.459 |
| Proposal plus restricted search | **7,376.891** |
| Previous full timing search with boundary fallback | 25,084.860 |

Fine FFT alone accounts for 3,817.394 ms inside acquisition; do not add it a
second time. Coarse search fell from 19,771.048 to 416.494 ms, about 47.5x.
The proposal alone still exceeds the real-time budget. Its fold, correlation
and ranking costs are 277.493, 406.394 and 302.565 ms respectively. The earlier
native proposal that returned every diagnostic rank list cost 1,085.166 ms;
the combined-only mode returns the same selected four peaks for 988.433 ms.

The newer direct-CI16 explicit-arithmetic final scorer is not integrated here.
Its separate supplied-coordinate benchmark cannot be multiplied into these
measured end-to-end speedups. Fine frequency refinement is now the largest
measured search cost, so further coarse-only optimization cannot achieve the
goal by itself.

## Validation and artifacts

- `regional704-audit.json`, `regional-ds8-audit.json`,
  `regional-ds9-audit.json` and `regional-arm-audit.json` contain actual-hit
  audits, counts and source/result bindings from the frozen boundary scorer.
- `regional-control-parity.json`: enabling every timing epoch reproduced all
  5,632 candidate objects of the full-search host control on 32 DS7 dwells.
- `regional-host-arm-parity.json`: 704 candidate entries on the four ARM
  dwells match host epochs and fallback choices; maximum final-score
  difference 3.886e-16 and CFO difference 5.821e-11 Hz.
- `arm-combined-v2/summary.json`: all 264 repeated ARM proposal windows match
  the Python combined top-four rankings. `arm-comparison.json` contains the
  separately timed stage sums and speedup calculations.
- `builds/` and `regional-builds/` retain source snapshots, compiler commands,
  compiler diagnostics and binary hashes. For regional builds use
  `regional-build.json`; copied baseline receipts describe the predecessor.
- `input-bindings.json` records the oracle, templates, evaluation harness and
  staged input-manifest hashes. `PROTOCOL.md` records the initial proposal
  coverage experiment; this report describes the subsequent actual search.
- `test_proposal.py` and `test_evaluate.py` exercise four-rate synthetic lag
  shifts, phase behavior, zero input, peak exclusion and non-wrapping coverage.

The initial proposal-only DS7 experiment covered 19,391/19,581 original hit
timings with four +/-2-sample regions. That is not the actual recovery above:
the final search uses +/-4-sample neighborhoods and performs CFO refinement,
candidate competition and final GLRT. Raw lag-correlation phase was a poor
CFO predictor, so this prototype retains all original coarse CFO lanes.

Reproduction entry points are `evaluate.py` and `transfer.py` for proposal
evaluation, `build.py` / `run_arm.py --combined-only` for native proposals,
and `build_regional.py`, `run_regional.py`, `run_regional_arm.py` for actual
restricted searches. Use fresh output directories and their recorded input
bindings; preserve the measured artifacts.
