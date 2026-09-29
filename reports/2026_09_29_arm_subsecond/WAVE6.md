# Wave 6: ARM packing, reuse, and compiler experiments

The strongest measured combination adds ARM-trained PGO to the exact reuse
changes: **917.633 → 776.473 ms/dwell (15.38% lower)** on a disjoint 32-dwell
test panel. All 1,201 candidates and **904/921 standard hits** are conserved.
The 50% target is not reached. The broader result below qualifies the exact
reuse combination without PGO on 152 dwells; do not conflate the two panels.

The combined exact prototype reduces mean CPU time from **915.434 to
814.874 ms per 120 ms dual-receiver dwell**, a **10.98% reduction** across
the same 152 saved 2.5 MS/s DS7 dwells. Every candidate is identical to the
previous ARM result. All **3,344 overlapping receiver/windows** run and
**4,506/4,573 standard individual hits (98.53%)** are recovered, unchanged.
The additional 50% runtime goal remains unmet. Radio capture is disabled.

Median CPU time is 798.271 ms, nearest-rank p95 1,129.109 ms, and maximum
1,323.799 ms. 126/152 dwells finish below one second; none fits 120 ms.
This is the selected DS7 2.5 MS/s benchmark subset, not all DS7 recordings.

All 88 overlapping 20 ms receiver/windows are processed. The timing includes
proposal generation, input preparation, and search. Initial workspace setup,
file loading, and output formatting are excluded. Dwell-input variants charge
their complete new preprocessing, including its allocations, to the outer CPU
timer; their internal search-stage sum alone understates runtime.

| ARM approach, independently applied to Wave5 v2 | Mean CPU ms/dwell | Runtime reduction | Standard individual hits recovered, ARM4 |
|---|---:|---:|---:|
| Wave5 final v2 control | 960.455 | — | 119/119 |
| Three-pass stable radix ranking | 943.901 | 1.72% | 119/119 |
| Share CI16 loads across lag1/3/5 folding | 908.417 | 5.42% | 119/119 |
| Prepare overlapping-window input once per dwell | 937.072 | 2.43% | 119/119 |
| NEON four-bin complex products and magnitudes | 954.435 | 0.63% | 119/119 |
| Compiler `-fipa-pta` | 961.855 | −0.15% | 119/119 |
| Compiler `-falign-functions=32` | 958.755 | 0.18% | 119/119 |
| Combined radix + shared folding + dwell input | **863.029** | **10.14%** | **119/119** |
| Half-size proposal FFT, approximate | 799.021 | 16.81% | 115/119 |
| Precompute dwell lag products, scalar | 1007.331 | −4.88% | 119/119 |
| Precompute dwell lag products, NEON | 946.907 | 1.41% | 119/119 |
| Proposal-only `-ffast-math`, non-exact | 947.167 | 1.38% | 119/119 |

The combined build excludes the separate NEON product/magnitude experiment.
Tiny differences below one percent are not established wins without repeat
timing. Independent savings must not be summed to claim a combined result.

The product cache is slower than shared-load folding (908.417 ms), including
with NEON preparation and folding, and needs another 14.4 MB at 2.5 MS/s.
It is rejected for the preferred combination. The fast-math proposal build
preserves host standard-hit identities (zero lost/gained) but changes 12
candidate objects across five host windows; its small ARM4 saving does not
justify including it in the exact combination.

True ARM-trained **profile-guided optimization (PGO)** was tested separately
from these four-dwell comparisons. Four training dwells were excluded from a
deterministic 32-dwell evaluation panel. The Wave5 control averages **917.633
ms/dwell** on that panel; PGO averages **874.445 ms**, a **4.71% reduction**.
All 1,201 candidates remain identical, with **904/921 standard hits** recovered.
Six component suites pass on ARM. The recorded profile archive allows the
compiler inputs to be inspected; instrumented training timings are not used
as performance evidence.

PGO also composes with the exact changes. On those same 32 held-out dwells:

| Method | Mean CPU ms/dwell | Standard hits recovered |
|---|---:|---:|
| Wave5 control | 917.633 | 904/921 |
| Exact reuse/ranking/folding combination | 816.561 | 904/921 |
| Wave5 with ARM-trained PGO | 874.445 | 904/921 |
| Exact combination with ARM-trained PGO | **776.473** | **904/921** |

The last step saves another **4.91%** versus the exact combination on this
panel, for **15.38%** versus Wave5. Nine component suites pass on ARM. The
PGO combination has not yet received the full 152-dwell or DS8/DS9 target
evaluation. Its exact sources, training profiles, build, units and held-out
comparison are preserved in `arm_wave6_combined_pgo`.

On the mixed-rate **704-dwell DS7 host panel**, the exact combined prototype
preserves all **86,439 emitted candidates in 15,488 receiver/windows** bit for
bit against Wave5 v2. It recovers **19,217/19,581 standard individual GLRT hits
(98.14%)**, the same as that control. This is host scientific qualification,
separate from the physical ARM timing above. It is not a claim that
every standard pipeline hit is preserved or that all of DS7 was evaluated.
The independent DS8/DS9 host panels also preserve every candidate against
Wave5, retaining 773/785 and 886/908 standard hits respectively.

The half-size proposal FFT is a tradeoff, not an exact optimization. Its
704-dwell host result is **19,161/19,581**: 65 previously recovered standard
hits are lost and 9 are gained. It remains separate from the preferred pipeline.

The exact gains primarily reduce repeated loads, conversions, and ranking
passes. SIMD executes independent arithmetic in parallel; it does not by itself
reduce mathematical FLOPs. Actual lower-precision FFT experiments from the
earlier low-precision report were slower on this Cortex-A9 and are not revived
as claimed improvements here. FP64 final scoring remains unchanged.

Reproduce the table with `collect_wave6.py`; `wave6-results.json` binds each
row to its immutable build receipt, output hash, cohort, and standard-hit audit.
Sources, component tests, build recipes, and evidence live in the corresponding
`reports/2026_09_29_arm_wave6_*` directories. All four input rates remain covered
by component tests and mixed-rate host qualification. Physical timing in this
table is specifically 2.5 MS/s on PLUTO+ CPU0 at 192.168.1.15.

The next priority is a structural reduction in repeated search work. The
bounded compiler/packing matrix yielded useful savings but provides no evidence
for a further 50% reduction, or for real-time capture plus analysis on this core.
