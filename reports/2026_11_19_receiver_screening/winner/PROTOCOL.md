# Screen initial v5 branches before all five refreshes

Run the stock-optimizer screening method and the secant screening method on the six previously selected v5 timing recordings. Use the original single 25 km roof tile, every archived native GLRT observation, the same causal catalogue and nuisance priors, and both calibration arms. The first two runs use DS26-0036 and DS29-0082. Use the following fixed schedule and a 480-second deadline for each worker.

| Recording | Logical CPU | Method order |
| --- | ---: | --- |
| DS26-0036 | 22 | stock optimizer, secant |
| DS26-0122 | 22 | secant, stock optimizer |
| DS26-0237 | 23 | stock optimizer, secant |
| DS29-0082 | 23 | secant, stock optimizer |
| DS29-0174 | 22 | stock optimizer, secant |
| DS29-0247 | 23 | secant, stock optimizer |

Freeze the implementation, numerical dependencies, recording inputs, catalogue, original truth-free request, supplied region, and archived control receipts before inference. Keep both candidate outputs for every scheduled recording, including timeout or withheld outcomes. Publish a content seal for the predictions before reading evaluation coordinates. Compare coverage, geographic error and shift from the four original v5 reference methods in each calibration arm. Tabulate conditional frequency RMS independently of geographic error. Use the published 50 m displacement and 1 Hz conditional RMS thresholds for a paired numerical comparison against the matching optimizer's five-refresh compact cavity endpoint. Show all six cases even when a gate fails.

Record the initial ranked branch indices, two-refresh scores, final winning rank, initial phase fits, and fallback for each successful run. A successful ordinary screening pass runs two refreshes on each of the three initial candidates and three more on the selected candidate, for nine fits versus fifteen for the compact five-refresh reference. The later paired conservative, history, signed and cavity paths retain their original refresh budgets. Use the frozen initial branch audit as the original optimizer's winning-rank comparison.

Report the paired initial selection CPU and entire initial stage wall time separately from the whole-worker CPU and wall. Compare fresh measurements from the same pinned CPU and order schedule. Add the previously sealed five-refresh compact projector and five-refresh secant worker as matching scientific controls. The projector was measured on the same logical CPUs in an earlier session and through an additional outer CLI worker. The archived secant runs used CPUs 20 and 21 and a different supervisor. Archived timings provide historical context with these scopes and host conditions. The archived initial stage records wall time. Fresh initial CPU is timed from v5 inference entry through the initial selection callback. Whole-worker timing includes projector compilation, launch, input preparation, and inference through the paired cavity decision.
