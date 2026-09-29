# ARM GLRT performance: implementation and evidence index

## Current research baseline — 2026-09-29

The [subsecond-goal checkpoint](../../reports/2026_09_29_arm_subsecond/REPORT.md)
measures a faster tradeoff at **2.010 seconds/dwell**, including separately timed
proposals: **19,249/19,581** standard hits retained, 151 fewer than the previous
19,400-hit result.
Search alone is 1.280 seconds; all 15,488 windows still run. Unmatched positives
increase to 21,555. This combines two-frame fine estimation, full-frame moment
conditioning without near-max rechecks, fixed CI16 scaling, radius-2 proposals,
exact final-result reuse and NEON/radix proposals. **The subsecond goal remains
open**; this is neither a fused nor concurrent-capture measurement.

The earlier measured extension, [compiler/local-arithmetic tuning](../../reports/2026_09_29_arm_low_precision/REPORT.md),
reduces raw-FP32 search to **4.468 seconds/dwell**, 8.1% less CPU than the fresh
4.863-second reference. It retains **19,400/19,581** standard hits on 704 DS7
dwells and changes no candidate positive decisions. Including separately timed
proposals gives **5.319 seconds/dwell**. The corrected `limited-complex-v2`
build passed physical-ARM tests; its relaxed exceptional complex semantics are
qualified only for the tested finite-data workload. This is the fastest measured
research extension, not production integration. Q15 integer FFTs and scalar/NEON
packed spectrum caches were slower. Strict raw FP32 remains the reference below.

Selected by the user: **raw FP32 fine FFTs without the fine-FFT FP64 fallback**,
combined with FP32 lag proposals, restricted timing search and lazy FFT reuse.
The final GLRT remains FP64. The separate residual-boundary conditioned
fallback remains enabled; this decision does not remove that mechanism.

- **ARM search:** 4.860 CPU seconds per 120 ms dual-RX dwell at 2.5 MS/s,
  mean of two runs on four saved dwells, CPU0 of PLUTO+ .15.
- **Search plus separately timed proposals:** 5.711 seconds/dwell. This is
  a stage sum, not a fused pipeline or concurrent-capture measurement.
- **Standard detections recovered:** 19,400/19,581 (99.08%) across 704 DS7
  dwells, including 4,551/4,573 at 2.5 MS/s. All 15,488 windows are evaluated.
  The 18,328 unmatched positive entries remain a quality limitation.
- **Status:** research only, not deployed or real time. The target remains
  72 ms/dwell for 40% headroom on one analysis core.

Start with the [current experiment and exact counts](../../reports/2026_09_29_arm_fine_precision/REPORT.md),
[selected implementation/build instructions](../../reports/2026_09_29_arm_fine_precision/README.md),
and [machine-readable ARM timings](../../reports/2026_09_29_arm_fine_precision/arm-aggregate.json).
Use [the comparison table](arm-glrt-comparison.md) for alternatives and their
standard-pipeline hit counts. Detailed dated reports remain immutable evidence.

## Progress milestones

All times below are CPU seconds per 120 ms dual-RX dwell at 2.5 MS/s.
Larger-cohort recovery is evaluated separately from the small ARM timing set.

| Milestone | ARM time | Standard hits recovered, 704 DS7 dwells |
|---|---:|---:|
| Exact refinement reuse | 33.167 s | 19,581/19,581 |
| Boundary-conditioned fallback | 25.085 s | 19,576/19,581 |
| Lag proposals and restricted timing search | 7.377 s, stage sum | 19,400/19,581 |
| Add lazy fine-FFT reuse | 6.449 s, stage sum | 19,400/19,581 |
| Add FP32 proposals | 6.313 s, stage sum | 19,400/19,581 |
| **Add raw FP32 fine FFTs — selected** | **5.711 s, stage sum** | **19,400/19,581** |
| Compiler/local-arithmetic extension, qualified finite inputs | **5.319 s, stage sum** | **19,400/19,581** |
| Full-frame moment conditioned screen, exact near-max rechecks | 4.567 s, stage sum | 19,400/19,581 |
| Two-frame estimation, moment screen, radius 2, exact final reuse | **2.010 s, stage sum** | **19,249/19,581** |

Tested alternatives are retained in reports: guarded FP32 fine FFTs cost
5.802 seconds including proposals with unchanged measured recovery; batches
of four/sixteen FP64 FFTs were slower. First/last-window interpolation missed
the recovery target. These are not part of the selected baseline.

## Motivation

Make the PLUTO+ GLRT optimizations easy to find, reproduce, and extend without
reconstructing the investigation from dated report directories or chat history.
The priority workload is 2.5 MS/s on one ARM core, with support for 5, 7.5 and
10 MS/s and eventual simultaneous capture to RAM.

## Problem

The experiments mix exact numerical optimizations, approximate search methods,
host recovery checks and ARM timing. They also use different baselines and
subsets. A speedup or confirmation count alone does not establish preservation
of individual GLRT hits, production integration, or real-time capacity.

## Solution

The near-standard-output quality reference remains **fine-direct GLRT with
selective boundary-conditioned fallback**. Start with its
[implementation README](../../reports/2026_09_28_arm_boundary_fallback/README.md)
and the [DS8/DS9 validation report](../../reports/2026_09_28_arm_ds89_validation/REPORT.md).
It retains every window and eight candidate entries, skips normalized
verification, and restores conditioned frequency refinement only when the
initial GLRT residual lies within 1 kHz of either principal-interval boundary.

This is a **research implementation, not a deployed server or radio analysis
mode**. Its 99.985% original-hit recovery on the DS8/DS9 sample is approximate;
candidate ordering and all scientific fields are not identical to baseline.
The latest exact alternative is the
[refinement-cache V2 implementation](../../reports/2026_09_28_arm_refinement_cache/REPORT.md).

## Method

This synthesis was checked on 2026-09-29 against the sealed DS7 and DS8/DS9
reports, source/build receipts, individual-hit audits and CPU0 ARM measurements
linked below. Dated reports remain the authority for exact binaries, cohorts
and numerical claims. Update this index as new evidence changes the preferred
method; preserve the sealed reports.

## Measured result to use

Use the [standard-pipeline comparison table](arm-glrt-comparison.md) for
method-by-method individual-hit recovery. Its denominator is always the
standard GLRT pipeline, with cohort and scoring-only limitations explicit.

**Two workloads must remain distinct.** The reduced native detector already
kept up with saved-IQ concurrent RAM replay at **69.24 ms per 120 ms dual-RX
dwell**, confirming one selected window per receiver. That result does not
establish full-search individual-hit recovery or real RF capture headroom.
See the [RAM replay report](../../reports/2026_09_28_arm_ram_pipeline/REPORT.md).
Its separate [704-dwell DS7 recovery measurement](../../reports/2026_09_28_ds7_large_arm/REPORT.md)
recovered only **499/19,581 original individual hits (2.55%)**, including
**126/4,573 (2.76%) at 2.5 MS/s**. It executed 1,408 selected GLRT windows
versus 15,488 in the original search. That physical-ARM quality run used
same-window, one-to-one matching within 2 microseconds and 8 kHz; it did not
include concurrent capture. The 69.24 ms result therefore does not meet the
full-search hit-preservation requirement.
The exhaustive high-recovery method below remains around 25 seconds/dwell.

The [oracle-seeded scoring budget documented in the scorer report](../../reports/2026_09_29_arm_scoring_kernel/REPORT.md)
isolates another barrier: even free perfect proposals cost about 119 ms/dwell
for input preparation plus positive-only scoring with the current kernel.
Sharing converted windows reduced input preparation from 150.5 to 36.8 ms,
with original score parity. These are diagnostic costs, not a deployable
119 ms detector or a new recovery result.

The follow-up [FP64 scorer experiment](../../reports/2026_09_29_arm_scoring_kernel/REPORT.md)
reduces that oracle-positive diagnostic to **46.7 ms/dwell** by using local
real/imaginary arithmetic and reading CI16 directly. All 123,904 original
candidate scores on the 704-dwell DS7 subset match within tolerance, including
all 19,581 positive entries. These are supplied-coordinate checks: candidate
discovery is excluded and the complete real-time objective remains unmet.

The [lag-structure restricted-search experiment](../../reports/2026_09_29_arm_lag_discovery/REPORT.md)
reduces the measured ARM cost to **7.377 seconds/dwell**, including separately
timed proposals: **3.40x faster** than the full timing search. It recovers
**19,400/19,581** original hits on the 704-dwell mixed-rate DS7 subset, but
also produces 18,328 unmatched positive entries and loses more original hits
than the quality reference below. This research method remains far from the
72 ms budget and is not a production replacement. Fine frequency refinement
now dominates search runtime; no concurrent capture was measured in this run.

| Cohort | 20 ms windows evaluated | Original individual hits recovered | Role |
|---|---:|---:|---|
| DS7: 704 dwells, 88 recordings | 15,488 | 19,576/19,581 (99.9745%) | Development data used to choose the fallback threshold |
| DS8: 260 dwells, 65 recordings | 5,720 | 7,281/7,282 (99.9863%) | Later recordings, frozen method |
| DS9: 420 dwells, 105 recordings | 9,240 | 12,215/12,217 (99.9836%) | Later recordings, frozen method |

DS8/DS9 together recover **4,550/4,550 original hits at 2.5 MS/s**. All four
rates were evaluated on the host. These samples span every recording identity
in their inventories but do not cover every dwell. They are from the same site.

| ARM 2.5 MS/s subset | Exact-cache CPU s/dwell | Boundary-fallback CPU s/dwell | Speedup | Original hits recovered |
|---|---:|---:|---:|---:|
| DS8: four dual-RX dwells | 33.3161 | 24.7851 | 1.34x | 53/53 |
| DS9: four dual-RX dwells | 32.9876 | 24.9560 | 1.32x | 136/136 |

Timing uses one PLUTO+ ARM core, saved IQ processed from RAM, and no simultaneous
capture. A dwell is 120 ms with eleven overlapping 20 ms windows per receiver,
10 ms stride, and two receivers. **Approximately 25 CPU seconds/dwell is not
real time**: a 40% headroom target allows only 72 ms CPU per continuously
arriving dwell, before accounting for other work on that core.

Recovery means maximum-cardinality one-to-one matching of original positive
candidate hits within the same receiver/window, with margin >=0.025, epoch
distance <=2 samples and tracking CFO distance <=8 kHz. It does not mean unique
transmitters or visit-level confirmations. DS8/DS9 retain matched hits in
7,124/7,126 originally positive windows, lose three near-threshold hits, and
produce two unmatched new positives; independent truth labels are unavailable.

## Implementation and experiment map

| Improvement or experiment | Where to look | Current interpretation |
|---|---|---|
| Selective boundary fallback | [C implementation](../../reports/2026_09_28_arm_boundary_fallback/full_search.c), [build tool](../../reports/2026_09_28_arm_boundary_fallback/build.py), [tests](../../reports/2026_09_28_arm_boundary_fallback/test_direct_glrt.c) | Near-standard-output quality reference; `boundary_fallback_required` and the final GLRT loop implement the decision and rerun |
| Frozen DS8/DS9 validation | [Protocol](../../reports/2026_09_28_arm_ds89_validation/PROTOCOL.md), [reproduction commands](../../reports/2026_09_28_arm_ds89_validation/EXECUTION.md), [host hit counts](../../reports/2026_09_28_arm_ds89_validation/host-hit-audit.json), [ARM comparison](../../reports/2026_09_28_arm_ds89_validation/arm-comparison.json) | Strongest transfer check for the current method; no retuning |
| Exact per-window refinement reuse | [Report and source directory](../../reports/2026_09_28_arm_refinement_cache/REPORT.md) | V2 uses exact grid/frequency keys and retains duplicate candidate entries; latest exact comparison baseline. V1 was rejected |
| Shared verification traversals | [Verification-fusion report](../../reports/2026_09_28_arm_verify_fusion/PERFORMANCE_REPORT.md) | Earlier exact optimization, preceding the exact cache and selective fallback |
| Conditioned frequency search and rotation reuse | [Conditioned-CZT report](../../reports/2026_09_28_arm_conditioned_czt/PERFORMANCE_REPORT.md), [screen-rotation report](../../reports/2026_09_28_arm_screen_rotation/PERFORMANCE_REPORT.md) | Earlier measured kernels; fallback still uses the established conditioned search |
| Direct GLRT without selective fallback | [Direct-GLRT report](../../reports/2026_09_28_arm_direct_glrt/REPORT.md) | Faster refinement exposed residual-frequency branch errors; superseded for the 90% target by boundary fallback |
| Sparse coarse proposals | [Sparse-proposal report](../../reports/2026_09_28_arm_sparse_proposal/REPORT.md) | Separate speed/recovery tradeoff, not combined with boundary fallback; do not multiply their speedups |
| Power-spectrum frequency proposals | [PSD prototype and results](../../reports/2026_09_29_arm_psd_proposal/REPORT.md) | Tested raw-PSD ranking loses too many hits; confidence gating retains only 81.51% at 2.5 MS/s in the native replay. Keep the unpruned boundary-fallback method |
| Full-search harness and original large DS7 reference | [Full-optimization report](../../reports/2026_09_28_arm_full_optimization/REPORT.md), [large-DS7 report](../../reports/2026_09_28_ds7_large_arm/REPORT.md) | Reusable window inventory, original scientific baseline and scoring provenance |

Use `builds/host-cohort-v1` and `builds/arm-v1` under the boundary-fallback
experiment to identify the validated binaries. The report's `SHA256SUMS.json`
and build receipts bind their sources and hashes. Temporary `/var/tmp` build
directories and the device SD card are working storage, not the durable index.

## Relationship to server analysis

The shared server path calls acquisition and then GLRT in
[`src/leo/scanner/detector.py`](../../src/leo/scanner/detector.py).
The boundary-fallback experiment is not wired into that path. Porting it should
use an explicit analysis mode and preserve published contracts; its ARM timing
ratio is not a server speedup estimate.

Earlier portable improvements already exist in the checked working tree:
heap-based coarse peak selection in
[`acquisition.py`](../../src/leo/analysis/starlink/acquisition.py) and immutable
template-geometry caching in
[`pilot_methods.py`](../../src/leo/analysis/starlink/pilot_methods.py).
Their [server benchmark](../../reports/2026_09_27_server_scan_speed/REPORT.md)
measured 4.31% less CPU for full 2.5 MS/s Standard analysis on five visits with
identical numerical outputs. This source status is not evidence of deployment.

## Continuing the work

Use a new dated report for each experiment. Keep the original baseline, hit
matcher and source/input hashes explicit; report per-rate recovery, positive
windows, unmatched new hits, actual GLRT calls and ARM CPU time separately.
Do not replace individual-hit recovery with confirmation recovery from the
older [server benchmark](ds7-glrt-benchmark.md) or
[progressive-search experiment](ds7-progressive-glrt.md).

The selected restricted search has shifted the bottleneck from coarse search
to fine FFTs and conditioned refinement. See the [runtime profile](../../reports/2026_09_29_arm_fine_precision/fine-stage-profile.json).
Further search reduction must earn its own hit-recovery evidence.
Concurrent capture-to-RAM qualification, higher-rate ARM
timings, server integration and the 40% real-time headroom goal remain open.
