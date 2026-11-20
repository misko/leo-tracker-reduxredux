# Prune ineligible work in the aligned v5 finish

Replay the complete aligned Armijo receiver and the pruned finish from stored native GLRT factors through the final paired position decision. Use the original causal catalogue, blind single 25 km tile, stored nuisance inputs, both calibration arms and the original numerical budgets. Position performance is scored only after the candidate output seals are written. Each worker has at most 480 seconds within a 1,200-second replay window after source lock. Keep every scheduled outcome, including failure or timeout.

The four known challenge recordings retain their authentic, matched aligned-finish predictions. They cover accepted residual addition with accepted reassociation, accepted residual addition without reassociation, rejected residual addition, and a scan with no qualified new family. The two independent normals were selected without position or RF scores. For each dataset, they have the smallest SHA-256 of `pruned-finish-normal-v1:<recording ID>` among the blind ordinary aligned-confirmation roster. Run both methods serially on the same CPU for each normal, with opposite order between the two cases.

| Scope | Case | CPU | Fresh worker order |
| --- | --- | ---: | --- |
| Known challenge | DS26-0066 | 20 | pruned |
| Known challenge | DS26-0287 | 20 | pruned |
| Known challenge | DS26-0002 | 22 | pruned |
| Known challenge | DS29-0082 | 22 | pruned |
| Independent normal | DS26-0175 | 20 | aligned, pruned |
| Independent normal | DS29-0357 | 22 | pruned, aligned |

Within each CPU lane, finish both known challenges before starting that lane's normal. Verify checksums for the implementation, kernel, frozen source and runner, native file, catalogue, and both the original and resolved blind requests. Compare the effective executed requests with only their scratch output locations normalized. Verify the four known predictions against their signed file receipt and matched scientific requests. Use the fresh controls for claims about stage CPU, wall time, and peak RSS. The earlier aligned timings provide separate historical context.

Report both geographic endpoints, published conditional Doppler RMS and final frequency objective, the checked residual addition and reassociation decisions, and associated observation counts. For fresh instrumented pairs, record the residual target count, actual coarse nomination and catalogue-propagation work, eligible final RF influence families, actual leave-one-out builds, and per-stage CPU and wall with peak RSS. Preserve unavailable archived conditional RMS values as unavailable. Require exact end-to-end numerical and decision parity on the observed controls before qualifying the pruned finish. Geographic error against the recorded reference remains distinct from the RF fit comparison.
