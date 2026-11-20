# Two detector workers at the original recording clock

Use two complete five-minute recordings on opposite pilot edges, DS26-0237 and DS29-0082. Both have archived original and four-region results. Their earlier individual errors are known. The new inputs are the actual joint-run emissions. Decode the saved I/Q once into a separately measured source. Run the prepared original detector and the fast four-region detector concurrently on different pinned host cores. Each worker has one waiting visit and the same scheduled arrival zero. Keep every original hardware exclusion and clock. Record the time both antenna measurements leave each worker. The position handoff closes at the last scheduled arrival, including a hardware-invalid last arrival. Discard late completions from the geographic input.

Freeze five policies before the joint runs or their positions are inspected.

| Policy | Measurement admitted for each valid visit |
| --- | --- |
| Wide only | The actual four-region pair if it finished before the handoff closed. |
| Original only | The actual prepared original pair if it finished before the handoff closed. |
| Replace | Use the complete original stereo pair wherever it arrived by close. Otherwise use the available wide pair. An original rejection can remove a wide positive. |
| Fill | Preserve each positive wide antenna. An original positive can fill a negative wide antenna on the same physical visit. If only one detector returned, keep its authentic pair. |
| 20 ms per visit | Use the replacement rule across packets completed within 20 ms of their own scheduled arrival and by the final close. |

The exactly matched physical visit is the unit of substitution. Sample counters, RF and receiver metadata must agree. Keep every candidate from a selected physical antenna together. A missing detector reply has different status from a completed detector with zero passing candidates. Before every solve, bind both trace hashes and record coverage, positive probes, visit ages, late completions and the selected sources. Compare the two calibration arms on the same inputs, candidate roster, budgets and original offered 25 km square. Score geographical error and the conditional RF fit separately against the four archived v5 options. Withheld, failed and unavailable fits remain in each denominator. The measured acquisition interval and downstream position time are separate boundaries.

A development check uses the preceding two independently timed DS29-0082 FIFO traces and the same final cutoff. Their replay timestamps can be aligned to the recording clock. That comparison models how the separate runs would combine. Only the new joint runs measure concurrent acquisition. Results on the preexisting traces cannot change the above rules. The separate fixed one-in-twelve study uses recorded detector factors and tests transfer across recordings. All roof recordings share one physical location.
