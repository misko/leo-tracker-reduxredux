# Compact cavity inference at 512 MiB

Releasing finished likelihoods let the compact v5 receiver publish on all four authenticated roof recordings under a 512 MiB Linux cgroup with zero swap. All eight position and RF results matched the unrestricted compact secant controls exactly. The earlier capped receiver published only DS26-0026. Collection and allocator trim alone recovered DS26-0146 and still exhausted the kernel cap on both DS29 recordings.

| Recording | Bounded cavity | GC and trim | Direct release, GC and trim | Direct CPU / wall |
| --- | --- | --- | --- | ---: |
| DS26-0026 | 395.2 MiB, published | Outside diagnostic roster | 424.5 MiB, published | 71.29 s / 74.27 s |
| DS26-0146 | 512 MiB, OOM | 504.0 MiB, published | 438.9 MiB, published | 73.97 s / 77.16 s |
| DS29-0174 | 512 MiB, OOM | 512 MiB, OOM | 438.2 MiB, published | 73.94 s / 75.47 s |
| DS29-0316 | 512 MiB, OOM | 512 MiB, OOM | 476.1 MiB, published | 83.17 s / 85.91 s |

Direct release drops the signed label-only construction before refits, detaches the last-use phase-model closures and their dense memo tables, and releases the nomination-only problem before cavity restoration. Numerical fits retain their five refreshes, hypotheses, priors and RF gates. Stage and one-second kernel samples show that explicit collection changed charge by less than 1 MiB at signed entry. Arena trim then returned 76–96 MiB there and 111–114 MiB at DS29-0316 cavity entry. The two remaining trim-only failures show that returning free allocator pages could not replace shorter object lifetimes. The direct candidate increased peak use on the already-passing DS26-0026. The release edits were tested together, so their individual contributions to peak use are unresolved.

In the direct replay, median geographic error was 0.946 km for zero c and 0.964 km for fitted c. The corresponding P95 values were 1.530 and 1.470 km. Median RF RMS was 83.811 and 83.801 Hz. Both arms used the same native observations, inputs and fit budgets. These are host measurements on four selected stored-GLRT roof captures, including three previous failures.

[Protocol](PROTOCOL.md) · [All results and kernel timings](scores.json) · [Direct prediction seal](direct-lock.json) · [Allocator-control seal](gc-trim-lock.json)
