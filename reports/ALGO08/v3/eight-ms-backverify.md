# Cost ceiling for graph-targeted aperture rechecks

**Stop at saved evidence.** Exhaustive leave-one-out scoring cost **4.361 CPU s on North** and **1.630 CPU s on DS30-0016**, against raw mixed-native savings of **0.335 s** and **0.239 s**. The weak-margin and high-influence selectors each missed one of the two North observations that changed the addition-only graph. Both observations appear in the actual 8 ms graph. Rechecking either waveform or fitting another position would leave those coverage and cost results unresolved. [Frozen protocol](eight-ms-backverify-protocol.md) · [Complete candidate and storage receipts](measurements/eight-ms-backverify.json.gz)

## What the 8 ms graph exposes

The audit rebuilt the actual 8 ms prepared graph exactly for both recordings. It considered each nonanchor graph member once. In a lane-only rebuild it removed that member and counted other rows that changed assignment or co-membership, excluding direct loss of the removed row. Curvature flips were recorded separately. An influence of eight follows the installed minimum track size. The weak band follows the earlier verifier’s exact-minus-roll threshold of 0.050. The ranking used only influence, measured margin and visit order. Pivotal IDs were checked after every rule was fixed and ranked. [Earlier verifier rule](stereo-retry-protocol.md) · [Graph intervention identifying the pivotal factors](eight-ms-graph-subset.md)

| Case | Actual prepared rows | Eligible nonanchors | Weak margin | Influence ≥8 other rows | Weak and high | Cost for all leave-one-out scores |
|---|---:|---:|---:|---:|---:|---:|
| North containing | 504 | 441 | 1 | 103 | 1 | 4.361 CPU s |
| DS30-0016 | 301 | 253 | 0 | 19 | 0 | 1.630 CPU s |

North’s first pivotal factor had margin 0.0441, changed 44 other memberships and ranked first. It was the sole weak-band member. The second had margin 0.0663 and changed zero other assignments, groupings or curvatures when removed from the actual 8 ms graph. It ranked 104th and missed the weak, high, union and intersection rules. Its established influence belongs to the addition-only graph on 12 ms support. Its influence on the actual 8 ms final estimate was unmeasured. The physical negative-control pivotal is absent from the actual 8 ms graph. [Per-member rank, effects and rule coverage](measurements/eight-ms-backverify.json.gz)

## Restart and storage prices

The same-recording mean native restart prices were 1.049/1.904 ms per lane for 12/20 ms on North and 0.984/2.298 ms on physical. The table excludes selector CPU so it also shows the budget given a free shortlist. Native estimates apply measured population means to the selected lanes. The receipt counts the exact signed storage members and bytes to reopen for the selected visits. Actual second-pass read, decode, authentication and subset-specific native times were unmeasured.

| Case and rule | Antenna calls / stereo visits | Members | Requested stereo buffers (MB) | Compressed / decoded readback (GB) | Signed indexes (MB) | Estimated native 12 / 20 ms CPU (s) |
|---|---:|---:|---:|---:|---:|---:|
| North weak or intersection | 1 / 1 | 1 of 19 | 1.6 | 0.084 / 0.102 | 0.039 | 0.001 / 0.002 |
| North high or union | 103 / 71 | 13 of 19 | 113.6 | 1.095 / 1.331 | 0.505 | 0.108 / 0.196 |
| North CPU-only ranked cap | 319 / 213 | 19 of 19 | 340.8 | 1.579 / 1.920 | 0.730 | 0.335 / 0.607 |
| DS30-0016 weak or intersection | 0 / 0 | 0 of 13 | 0 | 0 / 0 | 0 | 0 / 0 |
| DS30-0016 high or union | 19 / 19 | 8 of 13 | 30.4 | 0.629 / 0.819 | 1.386 | 0.019 / 0.044 |
| DS30-0016 CPU-only ranked cap | 242 / 209 | 13 of 13 | 334.4 | 0.992 / 1.293 | 2.187 | 0.238 / 0.556 |

With the North high-influence rule, the 12 ms restart estimate leaves 0.227 s of the native savings. Spending that entire remainder on readback would require about **4.82 GB/s of compressed input and 5.87 GB/s decoded**. The physical high-influence rule would require 2.85 and 3.72 GB/s respectively. No time remains for another graph rebuild, solve or publication in those rates. The CPU-only ranked caps cover both North observations and reopen the entire recording in each case, even with selection treated as free. The corresponding observed 8 ms acquisition outside native search consumed 3.799 CPU s on North and 1.732 CPU s on physical. That stage includes more work than member readback and provides same-input context. [Raw clocks and receiver breakdown](eight-ms-physical.md) · [Exact bytes and throughput calculations](measurements/eight-ms-backverify.json.gz)

Avoiding archival readback by buffering every first-look positive nonanchor stereo visit through graph preparation would retain **1.475 GB on North** and **0.547 GB on physical**, before any other workspace. The final subset is determined only after graph construction. A margin-only buffer can be smaller and leaves the higher-margin North factor uncovered. Under free buffering and rechecks, the measured exhaustive selector alone still costs 13.0× or 6.8× the savings. The data did not establish a cheap route to both North observations. [Buffering and restart ceilings](measurements/eight-ms-backverify.json.gz)

Run `eight_ms_backverify.py CASE CROSSOVER_OUTPUT RECEIPT` on the sealed graph outputs under the same CPU 2, `gauss.lock`, `nice -n15`, `ionice -c2 -n7` and one-thread controls. Use the archive-readable account and the installed payload ahead of the checkout. The program reads signed indexes and manifests. Forty-eight focused and adjacent tests passed. [Audit](eight_ms_backverify.py) · [Tests](../../../tests/pipeline_eval/test_eight_ms_backverify.py)
