# Wave 8: closing the remaining dense-workload runtime gap

## Completed larger ARM qualification

The selected approximate combination reduces **mean ARM CPU time by 51.35%**
on the same 152 saved 2.5 MS/s dual-RX dwells, from **915.499 to 445.353 ms**
(2.06×). Both runs execute all **3,344 receiver/windows**, use PLUTO+ CPU0,
and include input preparation, proposals, and search. The control is a fresh
run of the Wave5 binary and preserves its previous candidate objects exactly.
File reads, initialization, output serialization, and simultaneous capture are
excluded. This remains a static-IQ research result, not deployed real-time ARM
performance.

| Matched physical ARM152 method | Mean ms/dwell | P95 ms/dwell | Original hits recovered | Unmatched positive entries |
|---|---:|---:|---:|---:|
| Fresh Wave5 control | 915.499 | 1,217.145 | 4,506/4,573 (98.53%) | 1,079 |
| Reduced proposals/reuse/radius-one + exact ranking + gate 0.314 + PGO | **445.353** | **705.910** | **4,211/4,573 (92.08%)** | **599** |

The speed target is met for the mean, with an explicit quality tradeoff: 295
fewer original hits are recovered in aggregate. Unmatched entries are not
independently labeled false positives. Recovery uses same-receiver/window,
maximum-cardinality one-to-one matching at margin >=0.025, epoch tolerance
two samples, and CFO tolerance 8 kHz against the frozen original detector.
This is not bit-for-bit scorer equivalence or validation against current
production fractional-refinement outputs.

The 148 dwells excluding all four PGO training contexts still improve from
914.237 to 444.971 ms (**51.33%**). The 116 excluding both training and the
earlier heldout32 timing panel improve from 913.448 to 443.699 ms (**51.43%**).
These exclusions concern compiler training and timing panels; DS7 was still
used for search/gate selection. All 152 candidate dwells finish below one
second, but none meets the 120 ms real-time budget. No simultaneous-capture
headroom is established. The smaller non-PGO ARM4 gate check recovered 107/119
(89.92%), so the 90% recovery result is an aggregate-panel claim, not a
per-dwell or universal guarantee.

Evidence: `wave8-results.json` binds both complete cohorts, scientific audits,
and paired context subsets. Each cohort includes `cpu-distribution.json`;
`arm_wave8_gate_pgo` contains source/build receipts, five archived PGO profiles,
and twelve passed physical ARM unit checks. Host scientific transfer results
and all four supported rates are reported below separately from ARM timing.

The 50% runtime-reduction target retains the original dense workload: all
22 receiver/windows per saved 120 ms dual-RX dwell on one Cortex-A9 core.
The matched Wave5 means are 917.633 ms on heldout32 and 915.434 ms on the
larger 152-dwell primary-rate panel. Their half-runtime targets are 458.816
and 457.717 ms respectively. A smaller probe schedule is not used to meet
this target.

This workload differs from the deployed main adaptive analysis, which uses
one 20 ms window per receiver per 120 ms dwell. The frozen scientific oracle
here uses 10 ms stride and eight acquisition candidates, and predates the
deployed fractional refinement. Reported standard-hit recovery therefore
means recovery against that frozen reference, not a validation of every
current production output. See the deployed adaptive GLRT audit.

The matched heldout32 progression uses the same 32 saved 2.5 MS/s dwells and
921 frozen standard individual hits throughout:

| Method | ARM CPU ms/dwell | Reduction from Wave5 | Recovered hits | Method scope |
|---|---:|---:|---:|---|
| Wave5 matched control | 917.633 | — | 904/921 | Optimized ARM timing control |
| Wave6 combined PGO | 776.473 | 15.38% | 904/921 | Exact versus preceding ARM output |
| Wave7 histogram PGO | 758.592 | 17.33% | 904/921 | Exact versus Wave6 combined PGO |
| Wave7 frontier PGO | 473.795 | 48.37% | 854/921 | Approximate search frontier |
| Wave8 rank PGO | 470.056 | 48.78% | 854/921 | Exact versus frontier PGO |
| Wave8 gate 0.314 PGO | **449.206** | **51.05%** | **849/921** | Additional gate approximation |

Here, “exact” means candidate parity with the preceding optimized ARM method.
It does not mean that method recovers every frozen-original hit. CPU means are
paired to this panel; they must not be mixed with ARM4 or host timings.

The exact histogram/key implementation now composes with the approximate
proposal8/half-grid/tracking/radius-one frontier and ARM-trained PGO. It takes
**470.056 ms/dwell** on heldout32 versus **473.795 ms** for that frontier
without the new ranker. Recovery remains **854/921** frozen standard hits.

The separately calibrated 2.5 MS/s coarse gate of 0.314 reduces that result to
**449.206 ms/dwell**, with 997 emitted candidates and **849/921** frozen
standard hits. This is 51.05% below the matched 917.633 ms Wave5 mean and 9.610
ms below its half-runtime target. It meets the dense heldout32 timing target,
with five fewer recovered hits than the ungated rank-PGO configuration. The
larger 152-dwell physical comparison above confirms the mean-time target with
a fresh control; this earlier 32-dwell result remains separately identified.

Before adding the gate, Host704 candidate parity is exact against the same
frontier: all 77,894 candidate objects in 15,488 windows are identical,
retaining 18,465/19,581 hits. Gate 0.314 was selected on this DS7 panel: it
retains 18,441/19,581 overall and 4,211/4,573 at 2.5 MS/s, above the fixed 90%
primary-rate floor. Separate 32-dwell gate transfer checks recover **745/785
on DS8** and **861/908 on DS9**. These are host scientific checks, not ARM
timings or whole-dataset claims. The PGO heldout32 contexts exclude the four
training contexts, but are also DS7 and are not unseen gate-validation data.

The Host704 gate audit by native rate is:

| Rate | Recovered frozen hits |
|---:|---:|
| 2.5 MS/s | 4,211/4,573 |
| 5 MS/s | 5,223/5,466 |
| 7.5 MS/s | 5,005/5,186 |
| 10 MS/s | 4,002/4,356 |

This table is a host scientific qualification across 704 DS7 dwells. It is
not physical timing evidence.

Whole FP32 final scoring on the non-PGO frontier takes **505.582 ms** on ARM4,
versus 506.355 ms for its matched control, retaining 108/119 hits. The total
saving is only 0.15%, despite a cheaper final-scoring stage, and is not an
established useful improvement. Host704 identity matching loses no further
hits. Its physical numerical unit passes; it remains approximate arithmetic.

Exact integer energy preparation and NEON bitwise widening are isolated in
`arm_wave8_integer_input`. The initial candidates preserve all prepared data
but regress on Cortex-A9: at 2.5 MS/s, the scalar integer version takes 62.425
ms versus 60.994 ms, and NEON widening takes 98.278 ms versus its 60.497 ms
control. Their microbenchmark results cover input preparation only and must not
be presented as full GLRT runtime.

Adaptive-Q int32 final dots were also rejected. The kernel executes without
fallback and preserves the frontier's Host704 hit identities, but the matched
ARM4 pipeline takes 521.845 ms versus 506.355 ms and final GLRT rises from
74.436 to 93.703 ms. Quantization and integer reductions cost more than the
FP64 dots they replace on Cortex-A9.

Raising the 2.5 MS/s coarse gate from 0.312 to 0.320, 0.325 or 0.330 was
rejected in the host qualification stage. Primary-rate recovery fell from
4,235/4,573 to 3,717, 3,117 and 2,611 respectively, below the 90% floor.
No physical ARM speed claim is made for those rejected thresholds. The smaller
0.314 gate is the measured configuration above. It is an additional
approximation and does not preserve every previously recovered hit.
