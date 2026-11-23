# Exact short prefix and guarded full lanes through a staged seal

The hybrid used the exact original short detector with reused CFO prefix rows and the same guarded full anchor and cancellation detector as the oscillator arm. It reproduced each assigned source's lane factors and continuation. Its two receiver seals took **0.924 and 0.796 s**, longer than both archived independent and all-oscillator runs on the same staged member. Native CPU fell versus the independent arm and rose slightly versus the complete oscillator arm. [Protocol](hybrid-prefix-stage-protocol.md) · [Three-way receipt](measurements/hybrid-prefix-stage.json.gz)

## Disjoint CPU

The 64-visit DS30-0169 member has 51 admitted visits and 102 measured stereo lanes. The receiver ran 16 full calls and 86 short-primary calls. A uses the original independent 20 ms refinement, including its full lane load. B uses the 32-anchor oscillator for full, short and refine. C uses B's full anchor and cancellation library, with the original exact short verifier and guarded prefix gather. A/B came from the already frozen two reversed comparisons. C ran in two subsequent fresh processes under the same source-pinned worker. [Independent exact-gather versus prefix lane comparison](short-prefix-correlations.md)

| CPU within the measured receiver and policy | A, original independent (ms) | B, complete oscillator (ms) | C, exact prefix and oscillator anchors (ms) |
| --- | ---: | ---: | ---: |
| Full native call | 52.223 / 53.218 | 47.682 / 48.220 | 48.545 / 49.637 |
| Short primary | 93.679 / 93.292 | 87.070 / 87.025 | 96.387 / 96.222 |
| CFO refinement and rule | 35.549 / 36.388 | 19.621 / 19.654 | 12.513 / 12.397 |
| **Disjoint total** | **181.451 / 182.898** | **154.374 / 154.899** | **157.446 / 158.256** |

For C, the callback runs inside the native short invocation. Its **11.855 / 11.757 ms** is subtracted from the short-primary clock in this table and charged to refinement with the subsequent Python rule. Full, short-primary and refinement CPU each enter the total once. C's cheaper refinement does not recover the higher observed cost of its exact short primary compared with B.

| Elapsed, s | A | B | C |
| --- | ---: | ---: | ---: |
| Inside authenticated acquisition | 0.451 / 0.434 | 0.348 / 0.363 | 0.547 / 0.516 |
| Staged worker start through verified detector seal | 0.713 / 0.710 | 0.617 / 0.655 | 0.924 / 0.796 |
| Fresh process through exit | 0.819 / 0.817 | 0.717 / 0.767 | 1.072 / 0.920 |
| Process input blocks | 0 / 0 | 0 / 0 | 32,520 / 264 |

Software inputs and the recorded member were pinned, and waveform intake stayed on the existing tmpfs. The worker recorded **384 / 357 ms** of C acquisition CPU outside native and rule clocks, compared with **270 / 249 ms** for A and **192 / 208 ms** for B. This remainder includes ingress, verification, asset handling, observation and publication work. A/B are earlier runs, so their dependency residency and activity were unsynchronized with C. The clocks establish no C through-seal improvement and do not allocate that difference to any one part of the remainder. A controlled native comparison already isolated the benefit of prefix reuse against an independent exact *frame-support* gather. A in this report predates that gather change.

## Signed output and scope

Every C short native factor and emitted observation matched A exactly. Every C full native factor and continued observation matched B exactly. Both C launches sealed the same packet digest `fce718ac9c1ba8044058768788404db474f1f036a85eae8d66b13ec80a0eebb7` under a separate hybrid recipe. All arms authenticated the same decoded window identities, delivery clock and signed opportunities, with **66** native factors including **10** secondary cancellation residuals and **56** selected observations. The 45 C positives reused **360** exact frames on each pass, with zero prefix fallbacks. The full guarded path used one exact fallback in 21 fractional evaluations. The original CFO refinement decision counts agreed.

| Maximum absolute deviation | C versus independent A | C versus complete oscillator B |
| --- | ---: | ---: |
| Native exact or rolled score | 9.59 × 10⁻¹⁴ | 5.18 × 10⁻¹⁴ |
| Selected score or margin | 7.31 × 10⁻¹⁴ | 7.46 × 10⁻¹⁴ |
| Emitted signed CFO, Hz | 0 | 5.82 × 10⁻¹⁰ |

This single signed member ends at the actual detector seal. It supplies no full position, calibration-arm or geographic transfer measurement. The original waveform archive was not accessed. The first preflight stopped at a moving dependency source pin before opening the staged member. The retained runs use the sealed direct-kernel worker at `786346e32`; A and B were never reacquired. [Hybrid driver](hybrid_prefix_stage.py) · [Disjoint accounting and signed partition tests](../../../tests/pipeline_eval/test_hybrid_prefix_stage.py)
