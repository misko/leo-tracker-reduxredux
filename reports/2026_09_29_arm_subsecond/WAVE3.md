# Third optimization iteration

The previous goal turn made measured progress and published an actual outer
CPU time of 1.865693 seconds per 120 ms dual-RX dwell. The objective remains
below one second on a single PLUTO+ ARM core while keeping individual-hit
recovery close to 19,400/19,581. No RF or concurrent capture is used.

This iteration tests rank-only proposal magnitudes, resampled omit-power
proposals, cached FP32 final matched-filter dots, and low-margin boundary
refinement gates. It retains all 22 windows and eight candidate entries per
window. All rates remain supported; ARM timing prioritizes 2.5 MS/s.

Quality uses actual host execution on the same 704 mixed-rate DS7 dwells and
sealed standard pipeline: 15,488 windows, 123,904 candidate entries, 19,581
original positive detections. This is not all DS7. ARM timing uses four saved
2.5 MS/s dwells on CPU0. Initial setup and capture are excluded. Fused outer
timing includes proposals, regions, CI16 conversion and search.

| Method | ARM outer CPU s/dwell | Standard hits recovered | Unmatched positives |
|---|---:|---:|---:|
| Published fused V4, two-run mean | 1.865693 | 19,225/19,581 | 21,418 |
| Squared-magnitude proposal ranking | 1.842725 | 19,225/19,581 | 21,418 |
| Resampled omit-power proposals | 1.805847 | 19,234/19,581 | 21,493 |
| Boundary-refinement minimum margin .025 | 1.838794 | 19,225/19,581 | 21,411 |
| Boundary-refinement minimum margin .1 | 1.788930 | 19,218/19,581 | 21,430 |
| Resampling + squared ranking + .1 boundary gate, two-run mean | **1.709724** | **19,226/19,581** | 21,505 |
| Resampled lag1 + lag5 proposals, original boundary rule | 1.652205 | 19,189/19,581 | 20,575 |
| Combined method plus compiler loop unrolling, two-run mean | 1.706445 | 19,226/19,581 | 21,505 |

Unless marked two-run mean, new timings are single runs. Rank-only proposals preserve every
candidate object on the full host cohort and ARM panel. Resampling changes
outputs and slightly increases both recovered and unmatched hit counts.
Unmatched positives are not independently classified as true or false signals.

Cached FP32 final dots are rejected for speed: search-only CPU is 1.276861
seconds versus 1.228289 for the corresponding NEON-moments FP64 scorer;
the GLRT stage rises from 303.758 to 354.545 ms. The final sealed build retains
19,249/19,581 standard hits with 21,555 unmatched positives on its four-feature
proposal cohort. This standalone search timing is not comparable to the fused
outer times without adding proposals and outer conversion.

The boundary-gate instrumented run preserves all original candidate fields
across 123,904 entries. Counterfactual replay and actual native execution agree
exactly: a .025 initial-margin gate skips 1,843 logical boundary refinements
and retains 19,225 hits; a .1 gate skips 4,000 and retains 19,218. These counts
do not imply proportional CPU savings because caches reuse some work.
Native ARM timings are in the table. Thresholds were explored on this cohort; there
is no independent transfer or generalization claim.

The combined method measured 1.709462 and 1.709985 seconds/dwell, 8.36% less
CPU than published fused V4. Both ARM runs recovered 119/119 standard hits on
the small panel, with 155 unmatched positives. Its larger host cohort recovers
4,515/4,573 hits at 2.5 MS/s. All 15,488 windows and 123,904 candidate entries
remain. This is a recall measurement, not exact numerical or false-alarm
equivalence. The subsecond goal remains unmet, and 1.710 seconds is still
14.25 times the 120 ms real-time budget before capture overhead.

Further bounded experiments:

- Two-lag proposals lower CPU further but lose 45 hits relative to the
  three-lag resampled method. Single-lag variants recover only 822–825/843
  on the small panel, below the predeclared 829-hit expansion gate; stopped.
- Adaptive one/two-frame fine FFTs avoid 6.42–9.87% of endpoint transforms
  but lose 36–41 hits relative to their 19,249-hit baseline. No ARM timing claim.
- A 24-tap FIR before a factor-five fine FFT is 2.05 times slower in the
  isolated host feasibility test. It was crosscompiled but not ARM-qualified.
- Exact cross-window frame reuse would cover only 0.0313% of visible final
  scorer frames, so no cache was implemented.
- Offline coarse-score threshold .15 removes 4,459 of 123,904 candidates
  without additional recovered-hit loss. Threshold .175 loses 1,904 hits.
  Native execution subsequently confirmed 119,445 emitted candidate entries
  and 19,226 recovered hits, with 21,380 unmatched positives. Its small ARM
  panel removes zero candidates and takes 1.707646 seconds; it therefore does
  not demonstrate pruning speed savings on ARM. All window rows remain.

The compiler-only follow-up adds `-funroll-loops` to the combined method and
preserves every candidate object across all 704 host dwells and both ARM runs.
Physical-ARM component tests pass. Outer CPU is 1.705877 and 1.707014 seconds,
mean 1.706445: only 0.19% below the combined baseline. This is too small to
claim a material gain from the four-dwell timing panel. Target text grows
1.54%. PGO is supported by the compiler but remains unmeasured; it needs ARM
training profiles and a separate held-out qualification run.

The fine FFT inputs are general complex sequences, so two-real-input FFT
packing is ineligible. Exact two-frame FFT batching was already tested and
slower. Earlier Q15 FFT and scalar/NEON packed-spectrum experiments were also
slower; see `../2026_09_29_arm_low_precision/REPORT.md`. Lower FLOP count or
smaller data alone does not establish lower CPU time on this target.

Evidence is collected with source hashes in `wave3-results.json` by
`collect_wave3.py`. Completed source receipts are included by
`publish_wave3.py`; active new experiments are excluded.
