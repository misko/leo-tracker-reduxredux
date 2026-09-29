# Fourth ARM optimization iteration

The subsecond objective remains unmet. This iteration concentrates on exact
preparation and vectorization changes around the current 1.709724-second fused
pipeline. The accepted change preserves its individual-hit recovery and every
candidate object; it does not restore the 174 hits separating that baseline
from the earlier 19,400-hit method.

Quality uses the frozen standard GLRT pipeline on 704 mixed-rate DS7 dwells
from 88 recordings: 15,488 receiver-specific 20 ms windows, 123,904 candidate
entries and 19,581 original positive detections. This is not all DS7. Native
host execution measures larger-cohort recovery; physical ARM timing uses four
saved 2.5 MS/s dual-RX dwells on CPU0 of PLUTO+ 192.168.1.15. The outer CPU timer
includes proposals, regions, conversion and search, excludes initial workspace
setup/file loading/capture, and retains all 22 windows per dwell. No RF ran.

| Method added to Wave3 | ARM outer CPU seconds/dwell | Standard hits recovered | Decision |
|---|---:|---:|---|
| Wave3 control, two-run mean | 1.709724 | 19,226/19,581 | Reference |
| Combined exact proposal changes, two-run mean | **1.686498** | **19,226/19,581** | Retain; goal still open |
| Precomputed proposal geometry | 1.692925 | 19,226/19,581 | Retain |
| Precomputed rank values + linear top-four v1 | 1.715771 | 19,226/19,581 | Slower |
| Above, check score before coordinate conversion (v2) | 1.708492 | 19,226/19,581 | Small ranking-stage saving |
| FP32 128/512-point final GLRT FFTs | 1.714276 | 19,226/19,581 | No overall gain |
| Four NEON lanes for moment orders | 1.737549 | 19,226/19,581 | Slower |
| Four NEON lanes for adjacent coarse epochs | 1.759823 | 19,226/19,581 | Slower |

Unless marked otherwise, isolated rows are single timing runs. All rows retain
21,505 unmatched positives on the larger host cohort. Recall is not complete
numerical equivalence to standard analysis or verified false-alarm behavior.
The proposal, moment-order and epoch-lane variants preserve every candidate
object relative to Wave3 on the full host cohort and the ARM panel. FP32 final
FFTs change numerical values even though aggregate hit counts match.

The combined exact proposal variant is in `../2026_09_29_arm_wave4_combined`.
It precomputes resampling indices/fractions, frame offsets, support counts and
the original FP32 rank fractions. Top-four selection uses four scans with the
same local-maximum, score/index tie-break and circular exclusion rules, testing
score before the relatively expensive coordinate conversion. Original support
division, interpolation, all proposal features and all search/scorer work stay
unchanged. All 123,904 larger-cohort candidate objects match Wave3 exactly.
Two physical-ARM runs measured 1.687046 and 1.685950 seconds/dwell, averaging
1.686498: 1.36% less CPU than Wave3. Both runs preserve all candidate objects
and recover 119/119 standard hits on the timing panel, with 155 unmatched
positives. The combined larger host run retains 19,226/19,581, including
4,515/4,573 at 2.5 MS/s. Runtime is still 14.05 times the 120 ms real-time
budget before concurrent capture; this does not satisfy the subsecond goal.

## Rejected fine-input prototype: correctness failure

`../2026_09_29_arm_fine_input_neon` reuses normalized coarse samples and energy
prefixes to prepare FP32 FFT input. Its measured 1.713365-second candidate was
already slower, but a dedicated terminal-frame ASan test subsequently found a
heap-buffer-overflow. The availability predicate permits the last active
symbol while the new loop reads the entire frame, including its zero-template
tail. The potential overread is 22/45/67/89 complex samples across the four
rates. The variant is quarantined; the earlier inherited test passes and hit
counts do not qualify it. It is excluded from the combined implementation.
The published failure reproducer requires unpacking that sealed source archive
into the experiment's `sources` directory before invoking its shell runner.

## Verification and next direction

Physical ARM component tests cover the accepted proposal changes, full-range
CI16, all four rates, exact resampling/folding parity, peak ties and wraparound.
Host/sanitizer tests pass; larger host candidate equality and standard-hit
audits are recorded separately. The rejected fine-input variant demonstrates
why cohort recall cannot replace boundary-case memory tests.

The remaining runtime is mostly search: fine estimation about 310 ms, coarse
search about 218 ms, conditioned screening about 193 ms and final GLRT about
297 ms. Proposal work is about 459 ms. The next useful experiments must remove
or amortize expensive search work; multiplying independent microbenchmark
speedups cannot establish the goal. Potential follow-ups include sample-lane
moment accumulation without the larger per-sample power table and a bounded
NEON implementation of the previously scalar decimated fine estimator. These
are unmeasured directions, not promised savings.

`collect_wave4.py` collects timing/audit evidence with hashes in
`wave4-results.json`; `publish_wave4.py` retains sealed source archives,
receipts and the rejected variant's failure reproducer.
