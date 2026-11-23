# Same-core compressed lookahead and one decode arena

Whole-member prefetch and one reused Zstandard destination reduced complete scoped CPU by **3.8% and 4.9%** in two reversed cold pairs with the same genuine full-coverage short receiver. Sealed elapsed improved by 30% and 42%, with most of the difference after reader return. All four detection documents were byte-identical to the previous candidate. The best combined reader rate was **228.27 MB/s**. It was **177.40 MB/s** with the prefix's durable detection seal included.

The [corrected 55-file model](full-short-seal-scaling.md) charges the durable detection seal once per recording. At the best combined reader rate the favorable aggregate ratio is 0.491 with the optimistic seal and worker overhead excluded, 0.503 with the stressed seal, and at least 0.509 with measured worker overhead. The original through-seal extrapolation is retained below for comparison.

## Paired cold clocks

The [frozen test](full-short-arena-protocol.md) used just the three original DS30-0008 members, 192 stereo visits, 232.084 MB compressed and 307.200 MB decoded. Both arms paid 48 full and 336 short native lane calls. The released arm used its capped 16 MiB hints. The combined arm fetched the full second and third compressed members on the same CPU as the receiver and decoded each member into one reused arena.

| Pair and order | Ingress | Reader elapsed s | CPU through seal s | Elapsed through seal s | Effective compressed MB/s | Worker startup and exit s | Peak RSS MiB |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1, first | Released hints | 1.072 | 0.893 | 2.402 | 96.63 | 1.868 | 405.4 |
| 1, second | Full prefetch + arena | 1.180 | 0.859 | 1.683 | 137.89 | 1.814 | 497.7 |
| 2, first | Full prefetch + arena | 1.017 | 0.878 | 1.308 | 177.40 | 1.895 | 497.5 |
| 2, second | Released hints | 1.062 | 0.924 | 2.257 | 102.81 | 1.905 | 405.8 |

The speculative worker supplied both full members, 154.641 MB per run, with two hits and zero fallback. It confirmed affinity to CPU 2 in both reads. Worker thread CPU was 45.3 and 45.9 ms and is included in the complete CPU column. Prefetch demand wait was 325 ms in the first pair and 0.016 ms in the second. Process CPU while the native calls were active was 0.466–0.488 s for released hints and 0.493–0.522 s for the combined arm. Those spans can also contain prefetch thread CPU. The measurement isolates complete process CPU and thread prefetch CPU.

The per-inode eviction left all 56,663 compressed payload pages absent before each arm, and all were resident afterward. Process block reads were 232,091,648 bytes in both combined trials and 232,099,840 / 232,091,648 bytes in the two released trials. All four wrote 159,744 block bytes. The one-time authenticated private copy took 22.508 s elapsed and per-arm eviction took 0.7–4.4 ms, outside the measured acquisition. Between reader return and the immutable file's fsync, readback and digest verification, elapsed was 1.330 / 1.196 s for released hints and 0.503 / 0.292 s with prefetch and the arena. Reader elapsed moved by +108 ms and −45 ms. The hardware and filesystem variation in these pairs prevents attributing the larger sealed elapsed improvement to the new ingress.

## Exact ingress and buffer lifetime

The original compressed and JSONL index member checks, every window SHA-256, and all three computed decoded member SHA-256 values passed in every run. The experiment changes the decoder binding inside the original reader function and uses the same paired digest implementation. The sealed detector, analysis binding, clock rows, 195 selected signed factors and full documents were identical to the previous candidate at SHA-256 `fa087af8dad3a919cad433aa23a44341d974fe5b85cfd0bfdc600f86c3fc089b`. No new position or owner inference ran.

The borrowed output is private to the synchronous prefix runner. The native timing scout and margin verifier read the current CI16 pointer during each call and copy lane data into their own workspaces. Cancellation uses an owned residual and the Python callback returns scalar probe rows. The outer generators can retain inactive view objects while moving between chunks. The arena verifies each loan is a read-only view at the expected byte offset, guards the callback lifetime and checks no direct array reference escapes. Before reuse it requires all 64 callback loans and the full prior decoder scope to have closed. The original reader then checks the decoded member digest. Both trials recorded one 102.4 MB allocation, two reuses, three completed members and 192 released callback loans. Scope is specific to the pinned receiver and bounded runner. A deferred or external consumer requires the earlier ownership-safe reader path.

The speculative worker retains just one next compressed member and the normal reader holds its current compressed member. The one decoded arena adds 102.4 MB. Here complete process peak RSS rose by about 92 MiB, which includes Python, native workspaces and the prefetch worker.

## Original through-seal transfer to the 55 historical inventories

The calculation repeats each observed three-member rate over each full recorded inventory, scales its solver clock and retains the publication tail. Values are proposed / historical median individual and summed elapsed ratios. The sensitivity column adds measured subprocess overhead once per recording, outside the sealing scope.

| Solve scaling | Effective MB/s and path | Median / sum | With worker startup and exit |
| --- | --- | ---: | ---: |
| 23.482/60.966 | 96.63 released | 0.921 / 0.924 | 0.939 / 0.941 |
| 23.482/60.966 | 102.81 released | 0.871 / 0.879 | 0.889 / 0.896 |
| 23.482/60.966 | 137.89 combined | 0.679 / 0.699 | 0.695 / 0.715 |
| 23.482/60.966 | 177.40 combined | 0.562 / 0.581 | 0.578 / 0.599 |
| 11.680/21.383 | 96.63 released | 0.956 / 0.971 | 0.972 / 0.988 |
| 11.680/21.383 | 102.81 released | 0.911 / 0.925 | 0.927 / 0.943 |
| 11.680/21.383 | 137.89 combined | 0.731 / 0.745 | 0.747 / 0.762 |
| 11.680/21.383 | 177.40 combined | 0.614 / 0.628 | 0.631 / 0.645 |

Both 55-file targets require at least 209 / 221 MB/s in the first solver scenario and 245 / 258 MB/s in the second, with zero startup. Even the 31 historically cold files miss at the fastest observed combined rate in the favorable scenario, at 0.510 / 0.524 excluding startup. Median inventory size is 8,235 MB. The rates over these 232 MB prefixes supply a projection under historical clocks and no measured full-recording speed or geographic result.

Sixty-three targeted tests passed. Run the [existing prefix command](full-short-cold.md) with `--compare-ingress` on the runner and scorer. [Full receipt](measurements/full-short-arena.json.gz) · [Timing transfer](measurements/full-short-arena.json) · [One-arena adapter](full_short_arena.py) · [Component tests](../../../tests/pipeline_eval/test_full_short_arena.py).
