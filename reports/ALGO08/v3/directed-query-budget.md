# Cost of checking the empty-lane proposals

Use all 30 original pairs from the existing receiver/solver timing study. Count each unique signed carrier proposal in the sealed development and held plans once. These proposals revisit empty lanes after the candidate completes its ordinary short scan. Charge their incremental cost in addition to both existing stages.

Before scoring, fix three engineering scenarios for native-callback and whole-solver wall time respectively: unchanged, 1.5× and 1.4×, and 1.75× and 1.4×. Keep every other recorded wall cost fixed. Compute the largest uniform incremental wall time per proposal that satisfies both the summed half-time target and the median paired half-time target. Also evaluate a fixed 0.84 ms per query for sensitivity. That assumed wall cost has not been measured on this stream of largely empty lanes. Zero or positive slack is a timing condition only. A real implementation must also preserve the positions and fix decisions.
