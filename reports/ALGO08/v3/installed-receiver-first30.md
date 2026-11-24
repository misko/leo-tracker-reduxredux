# Receiver-only speed target for installed ALGO08v3 on the first 30 field pairs

Doubling the entire installed launch-to-native-write interval would speed up the complete job by **1.487× at the paired median and 1.483× by summed wall time**. It clears neither 2× gate. Making that whole interval free would clear both. With the original downstream work held fixed per recording, the minimum common prefix acceleration is **4.294×** and must cut 1,817.205 seconds to **423.151 seconds**. The timestamp covers startup, reading, input verification, decoding, detection and the native write. Accelerating just the receiver implementation can save only its share of this interval. [Frozen scope](installed-receiver-first30-protocol.md) · [Per-record evidence and both gate calculations](measurements/installed-receiver-first30.json.gz)

| Prefix scenario with downstream wall unchanged | Installed-model summed wall | Paired median time ratio | Summed time ratio |
| --- | ---: | ---: | ---: |
| Observed installed elapsed | 2,788.109 s | 1.00000 | 1.00000 |
| Launch-to-native prefix 2× faster | 1,879.506 s | 0.67272 | 0.67412 |
| Launch-to-native prefix 4.294× faster | 1,394.054 s | 0.49786 | 0.50000 |
| Entire launch-to-native prefix free | 970.903 s | 0.34544 | 0.34823 |

This is the same-input, same-solver and same-PNG sensitivity. The actual mixed-receiver charted successor uses different detections. It took 1,696.681 wall and 1,571.591 CPU seconds, with wall ratios of 0.58202 median and 0.60854 summed. Neither those clocks nor the earlier three charted/full saved solver clocks are used as a substitute for the installed downstream floor. The current result is close to the older release panel's 4.31× requirement, and the first-30 receipts expose which downstream intervals explain it. [Earlier 100-case boundary](release-stage-budget.md) · [Separate hybrid treatment](hybrid-20ms-receiver-budget.md)

## Where the observed downstream time remained

| Disjoint wall interval | Seconds | Timestamp coverage |
| --- | ---: | --- |
| Launch through native data write | 1,817.205 | 30/30 |
| Native write to inventory write | 2.272 | 30/30 |
| Inventory write to terminal write | 858.724 | 29/30 |
| Inventory write to solver-failure exit | 15.256 | One actual case |
| Terminal write to worker exit | 80.472 | 29/30 |
| Independent published-product verification | 14.179 | 29 charged verifiers |
| **Verified installed total** | **2,788.109** | **30 original outcomes** |

A pinned released scanner writes detections before checking and writing inventory, then solves and writes the terminal before rendering or withholding. The immutable writer flushes the temporary file, then fsyncs and links it. Its timestamp measures the data write, with any remaining durability cost retained in the following span. Nearly **90% of the post-native wall floor** sits in inventory-to-terminal or inventory-to-failed-exit. That interval contains the numerical search and evidence before the terminal, plus boundary work. Terminal-to-exit captures rendering, publication and other final worker activity. The file markers do not isolate CPU for any of those substages.

Installed had 26 fixes, three withholds, and one solver failure. All 30 native and inventory files are directly hash-bound to the selected original attempts. The installed DS30-0397 failed after entering the solver and had no terminal. Its original 90.017 s exit includes 15.313 s after the native write. The recorded 0.084 s failure diagnostic lies outside that charged stopwatch and remains separately recorded. Completed fixes alone need 4.608× uniform prefix acceleration, with a 954.694 s downstream wall floor. The three small withholds and the failure remain in the primary timing population. All 30 individual cases cross half-time under the optimistic free-prefix bound.

## CPU capacity and effective throughput

Installed consumed **2,444.828 CPU seconds**. The first-30 retained receipts have **zero direct timers of complete installed acquisition or exclusive installed detector callbacks**. From one-core child occupancy on each side of the native write, with 10 ms slack, the allowed aggregate pre-write CPU spans **1,474.284–1,816.390 s**. The common verifier's separately measured CPU is charged once after exit where included. The lookahead receipt times 8.809 process CPU seconds around storage advice in 29 cases. It overlaps the prefix and supplies neither acquisition's timer nor an extra removable stage.

| Optimistic substitution | Free floor, paired median / summed ratio | Acceleration of the eligible span required for both gates |
| --- | ---: | ---: |
| Scale pre-write CPU, compare total CPU | 0.26850–0.38927 / 0.25705–0.39698 | **3.160–5.853×** |
| Scale pre-write CPU and retain all original off-CPU wall time | 0.34535–0.45817 / 0.34852–0.47122 | **4.301–18.376×** |

The higher required rates assume the smaller permitted pre-write CPU allocation. The model gives credit for all pre-write CPU savings as elapsed and leaves original waiting costs fixed. That wide range is uncertainty about CPU placement, with additional uncertainty about the optimizable receiver share inside the prefix.

The sealed roster accounts for **201.226 GB** of original compressed input. Observed effective throughput through the native write is **110.73 MB/s**. With the same retained downstream cost, a uniform **475.54 MB/s** through that boundary clears both gates. The summed target binds, while the median alone needs 465.20 MB/s. This is effective processed bytes per elapsed second, including any overlapping read, verification and compute. It is a target for the complete prefix, independent of the device's bandwidth specification.

For scale, the separate resident DS30-0016 experiment measured full exact-detector acquisition at **5.661 s wall / 5.659 s CPU**, with **3.184 CPU s** in 1,426 directly timed full-detector lane calls. DS30-0016 is outside this cohort. On the first 30, a CPU-only saving with waits held would need to average at least **4.639 ms across each of 300,522 admitted lanes** to meet the summed wall gate. Applying the donor's 2.233 ms callback rate uniformly and erasing that modeled work completely leaves wall ratios of 0.75902 median and 0.75930 summed. That sensitivity supplies no same-cohort native timing coverage. It illustrates how much work beyond the callback would still need to change at the observed donor rate. [Direct full-detector donor](installed-receiver-control.md)

Protocol `930dfafa6`, reducer as run `4b3a58a35`. The expanded report digest is `83d9031a863179c0f5ca5b4d678e8ca534ce7ae72c90b1bb96c9dc4cf9f5d298` and the compressed artifact is `164da2b6c62ee9e6b60b4918ce937d8d37475808b53d8e5f3269be30c70a7153`. The audit read retained JSON and file timestamps at low priority. It opened zero original waveforms, TLE bodies or PNG payloads and ran no acquisition, solve or benchmark lease. Three component tests passed. [Reducer](installed_receiver_first30.py) · [Tests](../../../tests/pipeline_eval/test_installed_receiver_first30.py)
