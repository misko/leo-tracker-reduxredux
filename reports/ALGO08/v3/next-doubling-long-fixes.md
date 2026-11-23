# A single-core budget for long recordings that return a position

The next doubling is relative to named ALGO08v3, from original signed I/Q through process exit and all eight figures on a fix. Short-case diagnostics found useful correctness changes. The first four recordings in the timing roster each contain 6,770–6,773 visits, so seconds saved on long successful fixes determine whether the work transfers. [Frozen roster](roster-savings.md) · [Qualification criteria](single-core-target.md)

The newest physical check selected DS30-0340 by visit count before inspecting its outcome. It was the sole recording in the 512–767 visit band, with 555 issued visits. The combined candidate and named v3 both finished acquisition, then failed during the solver's leave-one-family-out calibration with the same nonempty-observation-mask exception. Both exited with code 1 and neither produced a terminal decision or figures. Elapsed to error was 6.784 s for the candidate and 8.690 s for v3. This pair supplies a regression fixture and counts as one failure for each build. A timing comparison for successful analysis or a position-error comparison requires a completed result. Both launches had the original input resident after one separate 8.624 s conditioning pass.

## How much original input must the receiver handle?

The historical stage ledger includes 55 recordings, 52 fixes with separate clocks, and 46 of those fixes with at least 6,000 issued visits. For each of the 46, give the solver, figures and exit a hypothetical fixed elapsed allowance. Subtract that allowance from half the original raw elapsed, then divide the recording's own compressed megabytes by the remaining seconds. This gives the effective rate from process launch to signed detections needed to halve that individual recording. The rate includes opening, reading, decompression, authorization checks and signal detection. [Per-recording stage clocks, input sizes and visit counts](measurements/acquisition-throughput.json)

| Hypothetical elapsed after detections | Median time left for acquisition | Median required acquisition rate | Upper quartile of required rates |
|---:|---:|---:|---:|
| 18 s | 37.5 s | 221 MB/s | 283 MB/s |
| 22 s | 33.5 s | 248 MB/s | 328 MB/s |
| 24 s | 31.5 s | 263 MB/s | 357 MB/s |
| 26 s | 29.5 s | 281 MB/s | 390 MB/s |

Every recording has a positive acquisition allowance in these four rows. Rates use decimal MB. The upper quartile uses Python's exclusive sample quartiles. Each column is summarized separately, and these per-recording targets are stricter than requiring half time in the aggregate. The 20/12 ms mixed receiver previously achieved 292 MB/s on a fully resident short physical recording. On a long dense recording its 32.403 acquisition CPU seconds imply at most 252.5 MB/s on that path with zero wait. The acquisition boundary in those measurements is slightly narrower than launch to sealed detections. [Measured receiver throughput](warm-recording-budget.md)

## Why speeding up cold reads alone misses the total-time gate

For the 55 historical clocks, halve the detections-to-decision time on each of the 52 fixes, keep publication costs, and charge the full elapsed of the three unsplit recordings. Scale launch-to-detections elapsed according to starting compressed-page residency. Of the 52 fixes, 31 started below 20% cache residency. The scenarios assume the stated reductions are achievable. [Historical clocks](measurements/acquisition-throughput.json) · [Earlier uniform-stage model](second-doubling-frontier.md)

| Hypothetical acquisition saving | Median candidate/v3 | Total candidate/v3 |
|---|---:|---:|
| 55% only on the 31 cold fixes | 0.483 | 0.614 |
| 55% on cold fixes, 30% on other fixes | 0.483 | 0.550 |
| 55% on every fix | 0.480 | 0.497 |

The same median can accompany substantially different server time. Both ratios must reach 0.500. On the observed 52 fixes, acquisition, solving and publication accounted for 67.1%, 30.1% and 2.8% of the original summed wall time.

## Experiments in order of priority

| Priority | Direction | Smallest decision-making experiment |
|---:|---|---|
| 1 | Combine fast satellite discovery with the original final fit on the accepted observations. | On an independent long saved packet, measure search, fallback, final fit and eight-image publication together. Check satellite assignments, both calibration arms and the position errors. The same-input 0402 and 0169 clocks improved by 43.91 s and 6.07 s respectively. [Transfer measurements](original-final-fit-transfer.md) |
| 2 | Make the initial 12 ms detection supply the pilot correlations for the 20 ms frequency refinement. | Compute the new frequency from the shared prefix plus disjoint trailing frames. Account for the carrier adjustment between the two measurements. Compare with the independent full calculation around acceptance thresholds, and charge every recomputation. The current refinement improved held frequency RMS from 87.70 to 53.28 Hz but adds work on every selected positive. [Frequency estimator](short-cfo-refine.md) · [Measured verifier costs](short-cfo-exact-cost.md) |
| 3 | Reduce verified input CPU and exposed storage wait together. | On the same two signed members, time source read, decompression, both payload digest scopes and DSP through the final seal, in reversed order. Try a native streaming decode-to-consumer loop with bounded output blocks. Existing decoder upgrades and buffer reuse showed mixed total-time results. Require a complete traversal gain on resident input before a cold check. [CPU attribution](dense-ingress-attribution.md) · [Physical cold variation](physical-stage-envelope.md) |
| 4 | Spend extended measurements on observations that distinguish rival satellite assignments. | Replay saved short/full frequency substitutions one group at a time on a dense packet. Price a selection rule that uses disagreement between live assignments and occasionally samples unclaimed time spans for new signals. Give it the same number of retries as uniform selection and measure the cost of the fallback. A peak-shape rule alone barely beat uniform on weak clips. [Equal-budget comparison](peak-shape-retry.md) |
| 5 | Reduce dense full-catalogue scoring cost while retaining every visible satellite. | Change the evaluation order to share geometry and bounds among nearby hypotheses. Preserve ties, keep ambiguous candidates, and compare full ranking, later ownership and positions. Restricting the catalogue to earlier geographic winners lost 79 observations per arm even though the dense top three matched. [Cold scoring costs](cold-exact-budget.md) · [Reduced-catalogue failure](proof-global-rank.md) |
| 6 | Replace per-sample trigonometry with short oscillator recurrences anchored at exact phase. | Price it across primary verification, real cancellation factors and extended frequency estimation. Recompute close decisions with the original verifier and charge those calls. The original refinement spent 333 microseconds per positive in rotation and tap preparation, only part of which is avoidable. [Native profile](short-cfo-exact-cost.md) |
| 7 | Give future recordings independently authenticated short prefixes and extensions. | Price one capture write plus one complete first analysis. On legacy DS30 one converted member avoided 35% of input bytes under the mixed schedule but needed eight analyses to recover conversion cost. Keep prospective recording economics separate from legacy release gates. [Measured conversion and break-even](seekable-member.md) |

A threshold tuned on one roof could save work by discarding signals needed elsewhere. Freeze selection before checking a separate location, run both fixed-zero and fitted calibration, and compare worsening as well as improvements on common fixes. Include a containing offer and a nearby omitted offer. Both named v3 and a saved solver have falsely published on the southern 100 m omission. [Geographic control](named-south-transfer.md)
