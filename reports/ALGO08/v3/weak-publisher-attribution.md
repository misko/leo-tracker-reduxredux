# What the weak saved publisher spends outside fitting and rendering

First imports and one independent decode of each published PNG account for
**0.988 of 1.066 CPU s** outside the solve and renderer in the profiled
positive DS30-0016 publication. The rest of the measured or unassigned work
totals **78.23 ms CPU**. Even treating all of it as free misses the frozen
0.100 s duplicate-work gate. No array or verification reuse candidate ran.

| Exclusive saved decision/publication scope | CPU ms | Elapsed ms | Calls |
|---|---:|---:|---:|
| First imports, including nested work | 773.867 | 774.377 | 44 |
| Independent PNG decode and RGBA conversion | 213.673 | 213.698 | 8 |
| Traced SHA-256, including image pixel hashes | 35.288 | 35.281 | 588 |
| JSON encoding and decoding | 11.847 | 11.857 | 39 |
| Graph eligibility and curvature bounds | 7.525 | 7.529 | 1 |
| Scan report view | 1.239 | 1.239 | 1 |
| Observed file reads | 2.238 | 2.235 | 96 |
| Transaction writes excluding child scopes | 2.253 | 2.253 | 5 |
| Fsync | 0.029 | 0.028 | 22 |
| PNG, manifest and path/grid checks excluding traced children | 4.973 | 4.972 | 28 |
| Research artifact receipt | 0.130 | 0.129 | 1 |
| Profiler setup and unassigned | 12.708 | 13.391 | — |
| **Total outside solve/render** | **1,065.770** | **1,066.992** | |

Times under the 2.074 s solve and 0.485 s renderer remain in those
buckets, including graph building and any nested imports and validation.
Graph eligibility materializes the winners once before the main solve.
Even deleting the entire 7.525 ms interval would miss the gate. The scan
report view is built once. Each of eight official PNGs is read and decoded
once, covering 2,913,411 encoded bytes. Existing verified media reuse
served eight evidence requests from those checks with zero fallback. Two
reads of the native document carry 1,079,732 bytes and take 0.122 ms
combined. The manifest was read 11 times (26,433 ASCII bytes). All
manifest validation, reads and access sum to 1.369 ms exclusive of JSON.
Grid and path are checked after writing as well as before commit. Their
validators, reads and sidecar access total 1.174 ms excluding JSON and hashes.

The largest import roots were `tools.algo08_position` (338.905 ms),
`tools.algo08_scan` (221.306 ms), `lighter_joint_estimator` (62.206 ms),
`isolated_salvage` (60.169 ms) and `leo.storage.short_window` (35.480 ms).
These are inclusive first-load subtrees with previously loaded modules
excluded. The older 20/12 ms saved import-deferral experiment reported a
0.099 s whole-process improvement. [Earlier import study](active-imports.md)

The process exited in **4.086 wall / 4.079 CPU s**, versus the sealed
**4.166 / 4.136 s** control, with unequal page-in (12 major faults and 312
filesystem input blocks versus 67 and 3,712). The new remainder was 49 ms
smaller in elapsed and 24 ms smaller in CPU than the original subtraction.
The independent nested timers and the instrumented partition differ by
less than 0.087 ms at the remainder boundary. No speedup is credited to
the observer.

The same 808-visit ledger produced the same 506 factors. The accepted
named survivor finish, both positions and RF residuals (134.021/133.740 Hz),
both ordered 115-owner rosters, 24 regional probes, numerical path and
179 grid points matched. All eight PNGs matched in encoded bytes, decoded
pixels and dimensions. No waveform call ran.

## Reproduction

The [protocol](weak-publisher-attribution-protocol.md) is at `72eeb2de5`;
the measured [observer](weak_publisher_attribution.py) is at `538d5599b`.
Launch under the usual low-priority Gauss CPU2 lock using a fresh tmpfs
root. The out-of-process `seal` command runs as its owner. Two component
tests passed. The [receipt](measurements/weak-publisher-attribution.json.gz)
includes both clocks, the scientific verification and exact partition.
