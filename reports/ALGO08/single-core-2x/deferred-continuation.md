# Run the two-scan detector only when a continuation can use its result

The published detector selects a carrier only if it receives three votes from earlier measurements. A vote comes from the same receiver, channel and actual RF, within eight seconds and the last twelve valid visits. The supporting times must span at least 0.4 s back from the current measurement. A visit too early to produce a selected carrier may still be needed as evidence for a later one.

The prototype leaves that visit's two-scan measurement pending. It retains the original I/Q and computes the measurement if a later carrier can use it. If the visit ages out of the twelve slots or eight-second horizon, its samples can be released. If the memory budget fills first, the oldest pending visit is measured. A known empty visit occupies the same history slot as in the deployed receiver. The method uses waveform evidence and hardware time independently on each RF lane. [Selection rule](../../../tools/pipeline_eval/variants/carrier_continuation.py) · [Delayed measurement](../../../tools/pipeline_eval/variants/experimental/deferred_continuation.py)

For a measured current carrier the planner treats every unmeasured predecessor as a possible vote. With a known predecessor it uses the deployed maximum slope and frequency tolerance to enclose every possible vote. If none of the current carriers can reach three votes even in that optimistic count, the result is empty. Conversely, three measured votes already suffice for a single current carrier because additional past measurements can only add support. For ambiguous cases the planner calls the original selection rule with the complete relevant history. The tests include a weak second carrier defeating the stronger first carrier, expiry, memory pressure and mixed RF lanes. [Component tests](../../../tests/pipeline_eval/test_deferred_continuation.py)

## Evidence from sealed I/Q

The instrumented stock receiver captured both verified factors before continuation and timed each actual C call. Replaying ordinary continuation on the ledger reproduced every published probe on both inputs. The delayed planner received a measurement only when it invoked that lane's callback. It reproduced all 440 selected measurements on DS30-0016 and all 456 on the southern simulation.

| Recording | Pending-lane budget | Native calls avoided / possible | Measured CPU of avoided calls | Share of native CPU |
|---|---:|---:|---:|---:|
| DS30-0016 | 16 | 53 / 1,426 | 0.104 s | 2.3% |
| DS30-0016 | 192 | 69 / 1,426 | 0.138 s | 3.0% |
| Southern simulation | 16 | 16 / 2,400 | 0.029 s | 0.5% |
| Southern simulation | 192 | 1,073 / 2,400 | 2.038 s | 32.1% |

With the larger budget, actual occupancy peaked at 44 and 48 pending lane measurements respectively. The raw prototype uses one 64-lane limit for both locations and reproduced those counts. Each immutable stereo window is 1.6 MB and can serve two pending lanes. The observed peak window counts were 22 and 26, equivalent to 35.2 and 41.6 MB of retained sample data. The CPU estimates above charge the original measurements and exclude actual raw-window retention, delayed memory access and publication. A limited budget forces early evaluation and largely removes the southern benefit. [16-slot replay](measurements/deferred-16.json) · [64-slot replay](measurements/deferred-64.json) · [192-slot replay](measurements/deferred-192.json) · [Replay and equivalence check](deferred_continuation_trial.py) · [Complete raw publications](moments-publication.md)

On DS30-0016 the complete native calls on all **unpublished** lanes together cost only **2.19 s**. Even an oracle skipping every one of those calls for free would leave the latest 15.56 s of pipeline CPU above half of the 24.18 s baseline on this input. The southern simulation has 3.94 s of native work on unpublished lanes. Resource estimates from either location alone would misstate the opportunity elsewhere. [Full physical publication](measurements/DS30-0016-tables.json)
