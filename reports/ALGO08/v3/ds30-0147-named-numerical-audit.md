# Exact numerical reuse inside the DS30-0147 named fallback

The verified field pair took 121.950 s on installed ALGO08v3 and 127.697 s on the charted 20/8-ms route. The latter spent 59.334 s wall / 59.094 CPU s inside the ordinary named fallback. Its constrained-gate counters were empty. The two ranks did repeat five nominal geometry calls, but the receipts provide no exclusive clock for those calls and no saved operands for a larger exact reuse claim. There was insufficient evidence to add a cache or change solver policy.

| Recorded scope | Wall s | CPU s |
| --- | ---: | ---: |
| Complete charted solve | 79.192 | 78.460 |
| Lean proposal before fallback | 16.472 | 16.206 |
| Ordinary named fallback, including grid | 59.334 | 59.094 |
| Ordinary rank, inside fallback | 5.950 | 5.919 |
| Standard 179-point grid, inside fallback | 5.368 | 5.350 |
| Fallback outside rank and grid | 48.016 | 47.825 |

The last row is a subtraction of two measured disjoint scopes from the fallback. It includes other scientific and evidence work. The saved interface exposes no separate clock for conservative recovery, history fitting, mandatory track support, signed refits or family-cavity proposals in that remainder. The publication stores the adopted owners and optimizer path. It does not store original rejected fit states, phase references, row operands or call order. A repeated coordinate, `c` calibration label, owner list or final RF score cannot establish equality of the original objective inputs.

## Verified repetition and its limit

The speculative two-centre rank returned six nodes and the ordinary rank returned seven. The fallback correctly excluded both the speculative rank and its finalist prefix. Both ranks operated on the prepared `previous` state. The ordinary `v5_core.scan_context` constructs fresh `ScanLikelihood` copies from the same prepared bank and tracks. The two-centre rewrite starts after the first centre statistics and changes the seed candidates. The nominal centre and corner projections use fixed observer coordinates. `discovery.explore` uses the selected smooth receiver state when forming the later corner statistics. Its phase proposals, signed aliases, ranking and finalists still need ordinary evaluation. [Checkpoint implementation](nomination_handoff.py) · [Prior zero-centre attempt](zero-centre-reuse-south.md).

| Archived cost or count | Two-centre rank | Ordinary rank |
| --- | ---: | ---: |
| Complete rank CPU s | 5.344 | 5.919 |
| Statistics CPU s, inside rank | 0.711 | 0.804 |
| Original nominal projection calls / satellite-time cells | 5 / 30,962,370 | 5 / 30,962,370 |
| Existing centre projection reuses within rank | 4 | 8 |
| Nominal geometry track terms built | 600 | 600 |
| Existing centre track-term reuses within rank | 480 | 960 |

Each nominal view has 1,587 catalogue rows by 3,902 distinct time slots and three binary64 planes. Caching only the centre output would retain 148,619,376 bytes across the lean attempt. Carrying its already prepared track terms as well would retain up to 261,093,240 bytes at that boundary. Keeping all five nominal views would retain 743,096,880 output bytes before cache metadata or any additional terms. These are array extents, not measured RSS, memory traffic or savings. The strongest direct ceiling is the 5.919 CPU-second ordinary rank, which also pays the required new seeds, shifted tracks, bounds, scores, and ordering. The whole statistics stopwatch bounds its own share at 0.804 CPU s and includes state-dependent corner work that must be rerun. A different dense packet measured all five original nominal projections at 0.548 CPU s. It provides scale only. [Prepared rank scope](compact-rank-scope-audit.md) · [Comparable dense clock](cold-track-row-reuse.md).

A smaller option would retain only nominal block indexes. The combined witness records 1,200 index builds, reconciling as two five-view ranks × 120 curved tracks. Reuse could eliminate at most 600 builds while all 3,120 actual compact likelihood queries still require their own observed values, shifted rows, inclusion certificates and diagnostics. An exact key requires the pinned native observer projection and checked geometry, binary64 observer coordinates, sampled track columns and RF scale. Verified identity of those operands would authorize reusing the original index arrays only. The receipt does not preserve the operand bytes or an isolated index-build stopwatch. The previous dense observer spent 0.396 CPU s for its 560 builds **and** 1,792 bound queries. That is an inclusive historical boundary for a different workload. It cannot price the DS30-0147 build subset or what reading the new key would cost. [Block implementation and measured boundaries](catalogue-block-bound.md).

## Work already shared or unresolved

- The charted context installs `stock_exact_gate_0402.gate_binding`, equivalent to the portable prepared constrained arithmetic. With empty counters, neither that feature nor the optional first-arm veto reaches any paid constrained fit on this packet. The route’s earlier lean repair and the ordinary cavity’s constrained gate have different call paths. [Earlier gate audit](field-installed-packet-saved.md#constrained-rescue-arm-order).
- The standard grid already prepares two fixed phase views and uses 356 checked calculations and 708 native projections. The references or native input values needed to count exact cross-arm matches are absent. A prior dense comparison found their common owner identities alone insufficient, with different projected features and final precisions. [Existing grid state reuse](grid-phase-state-reuse.md) · [Prior cross-arm audit](grid-cross-arm-posterior.md).
- Earlier signed fitting and secant tests already priced persistent layouts, short-run objective caches, fixed-state geometry and paired derivative calls. The dense signed diagnostic found zero full-objective hits in 78 calls and nine distinct references across ten refreshes. The physically tested paired derivative and predictive geometry port saved 23.5 ms before its 64.8 ms setup on a different matched slice. These observations constrain proposed duplicates. They give no hit count or speed estimate for 0147’s unobserved optimizer operations. [Signed phase reuse](named-phase-reuse.md) · [Paired secant comparison](paired-secant-geometry.md).

## Evidence

This audit reads the sealed generation-one case at `/srv/postgres-nvme/leo-ds30-evaluation-20261124/cases/DS30-0147` and the named/charted pinned source. The sources were compared to the publication hashes. No solver, raw recording, physical catalogue, or shared benchmark lease was used. The observed clocks and counts apply only to this archived original offer.

| Existing document | SHA-256 |
| --- | --- |
| `pair.json` | `e4e6b32aa6e6c1c1a1e67a2515651431c8d4f51db53178224d65db7356010252` |
| Installed `result.json` | `0e6d01763f43045c970c9e1f3506f750ef73cb2451f8e6203dc29979661bb9ee` |
| Successor `result.json` | `40535af864b91ee71ef1046e3c32b1a2569e9b08ac3bdde161402128a1dc226d` |
| Successor `exact-named-raw-witness.json` | `e3277a09631eb3b8af95dcb02d06878750d939727e970955baec6101f7693837` |
| Successor `legacy-original-acquisition.json` | `90c26d20c9af1204dd988e0d99503b709747d4ce339370b26b8c982b74cd62d7` |
