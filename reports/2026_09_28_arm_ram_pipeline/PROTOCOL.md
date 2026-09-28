# Single-core ARM analysis with a concurrent RAM producer

Target: PLUTO+ 192.168.1.15, two Cortex-A9 cores, approximately 495 MiB total RAM. No RF configuration, new RF collection, firmware changes, service affinity changes, or SD formatting are part of this experiment.

## Measurement and scope

CPU0 runs one persistent native detector worker; CPU1 copies saved CI16 into a bounded RAM ring in 10 ms chunks. The worker consumes the actual produced slot, not a separate saved-file pointer. All sources, templates, buffers and output-record storage are loaded/allocated and prefaulted before timing. Scientific result records are emitted after timing. The benchmark never substitutes a cached detector result for execution.

Use the previous DS7 experiment's 28 hash-bound dual-RX 120 ms visits: 16 at 2.5 MS/s and four at each higher native rate. All selected targets are upper edge. Compare two unchanged native implementations, original D and previously qualified goal40mag, first in isolation and then with the paced RAM producer. Their ARM scientific workload ranks six windows and confirms one per receiver; it is not the full server eleven-window/eight-candidate GLRT detector. Results must therefore distinguish native-profile output parity from the user's 80%/90% recovery requirement for individual full-search GLRT detections. The latter remains unestablished by this pipeline experiment.

Run two pacing policies: continuous 120 ms capture starts and DS7 source-counter-derived start offsets. The latter repeats a finite observed block, using its mean observed gap at the synthetic block seam; report this continuation explicitly. Do not use the older network-publication arrival trace, which delivers bursts shorter than a physical 120 ms dwell. A slot becomes ready only after its full 120 ms simulated capture, so latency from capture start and latency from buffer readiness are distinct.

## Buffer ownership and overload

The main queue has three slots, with explicit FREE/FILLING/READY/CONSUMING states or an equivalent locked protocol. This allows a capture slot, a processing slot, and one additional queued dwell. The producer must not overwrite a filling, queued or consuming slot, and must not wait for the consumer in a way that slows the external arrival schedule. When no slot is free, record a dropped dwell and continue the same paced memory writes into a dedicated discard buffer. Prefault this buffer too. Drops are not successful analysis and remain in the expected-job denominator.

Record source job/case identity, scheduled capture start, actual copy timing, readiness, service start/end, consumer thread CPU time, producer thread CPU time, queue delay, response time, peak occupancy, dropped jobs, missed producer timing, peak RSS, and per-core `/proc/stat` deltas. CPU0 headroom during ingestion is computed over the producer interval, separately from final queue drain. CPU time from nested legacy process-wide diagnostics must not be mistaken for consumer-only CPU during concurrent execution.

The replay models paced CPU writes and RAM contention. It does not reproduce hardware DMA, interrupts, IIO driver behavior, or real capture processing. Passing it is not real-capture qualification. Synthetic writes may create different memory traffic from DMA; neither an upper nor lower bound is assumed.

## Bounded phases and gates

Start with host ring-ownership/overflow tests and sanitizer runs at every native rate. Then run short ARM phases, sequentially with no simultaneous hardware benchmark or SD transfer. Prioritize 2.5 MS/s; retain examples at 5/7.5/10 MS/s and expose overload at the higher rates. Each target process has a 120-second hard bound and at most 500 jobs. Use unique host/target output paths and preserve incomplete or failed receipts.

Require producer/consumer accounting to close, no corruption, and exact native-profile scientific repeatability between isolated and produced-slot analysis (excluding timers). Compare D versus goal40mag using the existing native scientific gates, with all losses and additions reported. Report CPU costs and latency distributions, actual dropped-work rates, queue growth and measured headroom. A 40% headroom claim additionally requires no dropped jobs and a bounded queue under the stated arrival policy. It is not implied by a fast isolated service-time mean.
