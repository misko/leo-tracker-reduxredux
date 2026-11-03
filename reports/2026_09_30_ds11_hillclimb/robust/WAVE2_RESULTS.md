# Robust-likelihood Wave 2 original32 result

Both frozen arms completed the 24 remaining original DS11 recordings. Combined
with their eight immutable `wave1_vectorized` results, each arm has 32/32
qualified fits and no numerical failures.

| Arm | Qualified | Wins | Median (m) | Mean (m) | P90 (m) | Max (m) | Sub-km | Follow-through gate |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Original IID | 32/32 | — | 2,759.38 | 3,784.91 | 7,708.23 | 8,540.08 | 2 | — |
| df8, scale 100 Hz | 32/32 | 21 | 3,088.71 | 3,710.66 | 7,336.05 | 8,187.09 | 6 | fail |
| df4, scale 200 Hz | 32/32 | 20 | 3,102.09 | 3,664.52 | 6,691.68 | 8,164.02 | 7 | fail |

Both challengers have majority paired wins and lower P90, mean, and maximum
error than original IID. Both fail the predeclared all-32 median condition:
df8 is 329.33 m worse and scale200 is 342.71 m worse. Neither arm is eligible,
so no Wave 2 winner is selected and the conditional additional-panel check is
not launched.

The strict raw-model audit independently reconstructs the complete 32-row,
screen, and replication partitions from bound receipts and results. It reports
32/32 model and baseline qualification for each arm, no failures, and the same
metrics. Its tradeoff assessment is therefore complete rather than
matched-subset only: df8 adds four sub-km results and lowers mean error by 74 m
and P90 by 372 m while worsening the median by 329 m; scale200 adds five sub-km
results and lowers mean error by 120 m and P90 by 1,017 m while worsening the
median by 343 m. These tail and mean benefits are not a median success.

This result preserves the original Wave 1 failure. The follow-through is an
exploratory post-screen analysis on the same exposed 32 recordings, not an
independent confirmation or a relaxation that retroactively promotes either
arm.
