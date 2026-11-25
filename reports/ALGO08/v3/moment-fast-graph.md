# Exact Graph acceleration for forming signed CFO edits

The complete published Graph port preserved the edit-formation outputs
on DS30-0280 and DS30-0212. The two preparation passes used **56.0%
less CPU on DS30-0280** and **50.2% less on DS30-0212**.
[Matched comparison](measurements/moment-fast-graph-full-comparison.json) ·
[Frozen follow-up protocol](moment-fast-graph-full-protocol.md)

The saved worker forms held-odd proposals and builds the unedited
Graph under a scoped restore of stock functions. That restore removes
vector edges, the per-lane polynomial cache and the compiled path
wrapper on the lane. The later Graph on the adjusted winners runs with
those three ports active. Its receipt on DS30-0280 recorded 199 native
path calls, and DS30-0212 recorded 85.
[Metadata and clock preflight](measurements/moment-fast-graph-full-preflight.json)

The first saved comparison enabled the vector edge and polynomial
ports on both preparation passes, with exact agreement on both
recordings. On DS30-0280 it reduced the combined CPU time from
2.526 to 1.934 seconds, saving 0.593 seconds. On DS30-0212 it reduced
the combined CPU time from 0.887 to 0.663 seconds, saving 0.224 seconds.
[Vector/cache trial](measurements/moment-fast-graph-comparison.json) ·
[Admission](measurements/moment-fast-graph-admission.json)

| Recording | Archived masked proposals | Archived unedited preparation | Archived edited preparation | Archived edited inner Graph |
|---|---:|---:|---:|---:|
| DS30-0280 | 0.846 / 0.849 s | 1.684 / 1.694 s | 0.757 / 0.757 s | 0.664 / 0.664 s |
| DS30-0212 | 0.311 / 0.311 s | 0.531 / 0.531 s | 0.267 / 0.268 s | 0.219 / 0.219 s |

Archived values show CPU and wall respectively. Masked proposal time
includes construction of the held-odd packet, Graph preparation and
the released eligibility and interpolation logic. Unedited preparation
includes winner extraction. Edited preparation adds the overlay to
extraction and Graph work. All clocks come from immutable nanosecond
fields at their original boundaries.
[Archived clock extraction](measurements/moment-fast-graph-preflight.json)

## Matched complete-port timings

| Recording and preparation scope | Stock CPU | Complete CPU | Stock wall | Complete wall |
|---|---:|---:|---:|---:|
| DS30-0280 masked proposals | 0.859 s | 0.386 s | 0.878 s | 0.398 s |
| DS30-0280 unedited Graph with extraction | 1.656 s | 0.719 s | 1.658 s | 0.727 s |
| **DS30-0280 sum** | **2.515 s** | **1.105 s** | **2.536 s** | **1.125 s** |
| DS30-0212 masked proposals | 0.340 s | 0.179 s | 0.342 s | 0.187 s |
| DS30-0212 unedited Graph with extraction | 0.547 s | 0.263 s | 0.547 s | 0.283 s |
| **DS30-0212 sum** | **0.886 s** | **0.442 s** | **0.890 s** | **0.469 s** |

The complete-port unedited inner Graph used 0.649 CPU seconds on
DS30-0280 and 0.219 on DS30-0212. The archived edited inner Graph used
0.664 and 0.219 respectively on those separate inputs and runs. Native
preparation work in the matched trial was as follows.

| Recording and pass | Winner extraction CPU | Packed lanes | Compiled paths | Packing CPU | Path search CPU |
|---|---:|---:|---:|---:|---:|
| DS30-0280 masked | 48.0 ms | 16 | 163 | 1.62 ms | 7.32 ms |
| DS30-0280 unedited | 69.5 ms | 16 | 199 | 2.54 ms | 17.04 ms |
| DS30-0212 masked | 33.4 ms | 16 | 71 | 1.14 ms | 2.62 ms |
| DS30-0212 unedited | 43.8 ms | 16 | 85 | 1.58 ms | 5.33 ms |

All complete-port passes used the compiled path with zero fallback. Packing and
search are already included in Graph time. The projection itself
cost 12.9 ms CPU on DS30-0280 and 4.6 ms on DS30-0212 in the complete
arm. The timing child exited in 5.567 wall seconds and 5.418 CPU
seconds, including preflight checks, both modes, the projection and
verification. The two experiments took distinct fresh DS30-0279
storage deferrals on the shared Gauss lease.
[Complete-port admission](measurements/moment-fast-graph-full-admission.json)

The two modes and the earlier vector/cache trial produced exact full
Graph fingerprints for the same inputs, including ordered membership,
polynomial pieces and numerical arrays. All 558 DS30-0280 and 153
DS30-0212 proposed signed edit records and projected values agreed.
The 378 and 73 applied changes reproduced the archived input and
overlay winner hashes. Maximum moment magnitude before and after the
projection was 224.28 → 6.78e-11 Hz on DS30-0280 and 277.25 →
2.87e-11 Hz on DS30-0212. The entire stored moment certificates,
including the per-track rounding checks, agreed across arms.

The comparison stops at saved Graph and edit formation. It ran with
zero receiver or position executions. Eleven focused tests passed.
[Complete-port runner](moment_fast_graph_full.py) ·
[Component tests](../../../tests/pipeline_eval/test_moment_fast_graph.py)
