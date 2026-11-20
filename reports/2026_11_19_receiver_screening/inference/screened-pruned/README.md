# Screened discovery and the pruned aligned v5 finish

The integrated worker reproduced both aligned Armijo position arms on both authenticated confirmation recordings. All four coordinates, conditional RF residuals and frequency objectives agree exactly. The worker removed six optimizer calls per recording and reduced residual evaluations from 789 to 759 and from 687 to 663. Both runs completed within 146 seconds on their pinned CPU. [Detailed results](comparison.json) · [Prediction seal](prediction-lock.json)

The integrated worker reuses the established shared association context during ranked discovery, screens the three original candidate assignments at two orbit-phase updates each, and finishes the winner at five. The existing aligned Armijo worker owns the numerical solver and phase seed alignment. Its pruned finish checks residual eligibility and family support before launching expensive late work. The worker starts at stored native detector factors and produces both calibration arms through final reassociation. [Frozen protocol](PROTOCOL.md) · [Pinned source closure](source-lock.json)

```mermaid
flowchart LR
    A[Authenticated native factors and causal TLE] --> B[Share repeated discovery work]
    B --> C[Screen three assignments after two phase rounds]
    C --> D[Finish the winner at five phase rounds]
    D --> E[Aligned Armijo and eligibility-pruned finish]
    E --> F[Final position and RF for both calibration arms]
```

DS26-0175 and DS29-0357 are the two earlier hash-selected pruned-finish confirmations. Both had complete aligned Armijo receipts on an identical normalized scientific request. The verification removed the per-run output directory and resolved the native-factor path before comparing the full numerical requests. All eight original v5 role receipts independently matched their signed archive request digest, native detector digest, track configuration and causal snapshots. These are integrated replays at one established installation. The original roles retain their existing omissions and evaluation boundaries. [Request and archive proof](plan.json)

The candidate uses one numerical thread each on CPUs 0 and 7. The earlier aligned runs use the same stored-factor-to-final-position boundary on their earlier pinned cores. Their wall, CPU and peak process memory describe the actual executions. The different cores and host sessions limit direct timing attribution. The fit counts and residual evaluations provide the matched work comparison. Original v5 role controls supply their archived positions and published RF presentation residuals. The complete candidate and aligned workers also supply their conditional RF metrics, which describe a different residual statistic. [Sealed candidate outputs](prediction-lock.json)

## Measured work and resources

| Recording | Optimizer calls aligned → integrated | Residual evaluations aligned → integrated | Whole CPU aligned → integrated (s) | Whole wall aligned → integrated (s) | Peak waited child RSS aligned → integrated (KiB) |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0175 | 110 → 104 | 789 → 759 | 238.24 → 129.45 | 272.06 → 138.45 | 1,641,176 → 1,414,700 |
| DS29-0357 | 100 → 94 | 687 → 663 | 255.04 → 137.42 | 314.61 → 145.66 | 1,583,820 → 1,490,636 |

Each integrated run fit two screening rounds for each of three candidates and three continuation rounds for the winner. The original aligned selection completes five rounds for each of the three candidates. Rank zero won both screens without fallback. Discovery reused 12 associations and eight center projections per recording. The finish reduced the paired family-influence omission work from 32 to 28 operations and from 44 to 30. Both runs still examined all three residual targets. Both offered the cavity and found no qualifying new family or admissible reassociation. The largest waited child RSS includes the numerical worker and is a process maximum. [Work counters and downstream decisions](comparison.json)

| Recording | Calibration | Shared final latitude | Shared final longitude | Shared conditional RF RMS (Hz) | Horizontal error (km) |
| --- | --- | ---: | ---: | ---: | ---: |
| DS26-0175 | `c=0` | 37.832419295879525 | −122.49344249368443 | 68.8977873725131 | 1.969985 |
| DS26-0175 | fitted | 37.832468874708255 | −122.49334683445572 | 68.89805430263044 | 1.961935 |
| DS29-0357 | `c=0` | 37.85135978591224 | −122.48170784154681 | 64.81664412892236 | 0.438032 |
| DS29-0357 | fitted | 37.85174869877145 | −122.48213433423291 | 64.87691266287534 | 0.436675 |

Compared with the four original v5 roles, the largest displacement was 5.95 m on DS26-0175 and 30.07 m on DS29-0357. The original archive retains its own presentation RF RMS, and the table above reports conditional RF separately. Both integrated decisions retained 2,783 associated observations on DS26-0175 and 4,025 on DS29-0357 in each arm. The standard variant and measured scientific dependencies stayed sealed throughout the run. The supervisor source was preserved before a post-run import-format change and the scorer verifies those measured bytes. [Four-role comparisons](comparison.json) · [Figure evidence](figure-lock.json)
