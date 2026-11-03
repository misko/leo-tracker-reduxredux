# Read-only diagnosis of the frozen first implementation

The low result (9/62 represented references on ARM observations; 13/62 on server observations) is primarily missing local hypotheses, with secondary fragmentation and some over-linking. This diagnosis uses the frozen outputs and shared comparator only; no configuration or implementation was changed.

| Diagnostic | ARM observations | Server observations |
|---|---:|---:|
| Input-supported reference segments | 52 | 63 |
| Any consistent output fragment | 20 | 22 |
| Fragment union reaches 80% reference coverage | 11 | 15 |
| References represented by one complete output (excluding ref10) | 9 | 13 |
| Supported references with no consistent fragment | 32 | 41 |
| References represented by multiple consistent fragments | 16 | 17 |
| Unique candidates used / candidates input | 1,130 / 9,728 | 1,116 / 10,066 |

Fragmentation exists, but it cannot explain most misses. Unioning all consistent fragments improves the ARM ceiling only from 9 to 11 and the server ceiling from 13 to 15. The dominant observation is that 32 supported ARM references and 41 server references have no consistent output fragment at all.

The clearest implementation-level cause is deterministic fragment-cap starvation. Both real runs report exactly 8,192 retained fragments: eight lanes times the hard limit of 1,024 fragments per lane. The code visits windows chronologically and stops retaining fragments after that per-lane limit, so early, often redundant hypotheses consume the entire budget and later windows cannot enter linking. Within each window, seeds must start in the window's first source group and are enumerated in fixed candidate order; the 128-seed limit can therefore spend its budget on aliases or clutter before other viable anchors. This is not a global top-seed scan, but it still creates order-dependent local starvation.

Greedy linking then amplifies the retained-set bias. Each fragment is attached to the compatible chain with the greatest accumulated score, with no competing branch or dynamic-programming alternative. Multiple consistent fragments for 16 ARM and 17 server references show failed continuation choices. Conversely, several accepted matches have low overall purity (3 of 9 ARM matches and 4 of 13 server matches below 0.8), while every accepted match has at least 0.8 in-span purity. That pattern points mainly to chains extending across adjacent chronological segments, rather than pervasive within-span crossing swaps. The shared comparator reports no complete split or merge evidence, so these are partial/endpoint effects rather than qualified complete merges.

The result therefore tests this particular capped, first-group-anchored, greedy implementation. It does not reject local tracklets plus chronological linking as an approach. A fairer implementation would need order-independent bounded hypothesis selection and branching linkage, but those are conclusions for a later experiment, not tuning applied to this frozen run.
