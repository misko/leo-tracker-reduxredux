# Cost of checking the empty-lane proposals

Use all 30 original pairs from the existing receiver/solver timing study. Count each unique signed carrier proposal in the sealed development and held plans once. These proposals revisit empty lanes after the candidate completes its ordinary short scan. Charge their incremental cost in addition to both existing stages.

Before scoring, fix three engineering scenarios for native-callback and whole-solver wall time respectively: unchanged, 1.5× and 1.4×, and 1.75× and 1.4×. Keep every other recorded wall cost fixed. Compute the largest uniform incremental wall time per proposal that satisfies both the summed half-time target and the median paired half-time target. Also evaluate a fixed 0.84 ms per query for sensitivity. That assumed wall cost has not been measured on this stream of largely empty lanes. Zero or positive slack is a timing condition only. A real implementation must also preserve the positions and fix decisions.

The first 30 recordings produced 64,639 proposals, including three recordings with zero proposals. Trying every proposal at 0.84 ms adds 54.3 seconds across the panel.

| Native / solver rate | Seconds left before summed half-time limit, before adding checks | Maximum additional wall time per proposal for both gates | Summed / median paired speedup at 0.84 ms per proposal |
|---|---:|---:|---:|
| Current measured stages | −302.63 s | Already misses target | 1.592× / 1.665× |
| 1.5× / 1.4× modeled | 0.57 s | 8.8 µs | 1.926× / 1.977× |
| 1.75× / 1.4× modeled | 46.00 s | 711.7 µs | 1.988× / 2.043× |

The summed gate binds in both modeled scenarios. Under the 1.5× / 1.4× assumption, 0.57 seconds would pay for at most 678 verifications at 0.84 ms each across all 30 recordings, even if selecting the proposals took zero time. A filter that reduces the count needs measured selectivity, recovery and selection cost before a full-panel trial. These calculations apply to this DS30 subset and price wall time only.

Reproduce with `python -m reports.ALGO08.v3.directed_query_budget` from the repository root.
