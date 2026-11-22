# Conditional residual scans with original continuation

On short physical DS30-0016 the conditional schedule skips **554 of 1,426 residual requests**, keeps all 15 final residual selections, and drops one final primary selection. Both positions, owner maps and the full numerical grid reproduce. The southern simulation has no residual factor and all three schedules produce the same selected detections.

The replay keeps every admitted lane visit and every verified raw-scan factor. It requests residual discovery on admitted opportunities 1, 4, 7 and so on per `(receiver, channel, actual RF)`. It also requests residual discovery at every opportunity through eight device seconds after any verified residual it observes, including residuals the continuation declines. The choice uses lane metadata and prior observed factors and is made before the current factor callback. Every visit, including an empty one, advances the released twelve-entry continuation history. The controls request two scans at every opportunity or keep only raw-scan factors, each with an independent complete continuation history. [Schedule](../../../tools/pipeline_eval/variants/experimental/residual_schedule.py) · [Released continuation](../../../tools/pipeline_eval/variants/carrier_continuation.py)

The packed receiver's factor rank identifies the original scout, while the returned pair is ordered by margin. The physical ledger includes both original orderings. A residual can be the sole surviving factor if the raw scout confirmed for cancellation and the original-I/Q verifier later rejects its candidate. The two saved ledgers contain zero such rows. A component test confirms that a measured rank-one-only row can seed the activity horizon and pass the continuation, while a skipped rank-one-only row supplies an empty history entry. [Pinned receiver](../../../native/algo08v2/tools/pipeline_eval/variants/two_carrier_receiver.c) · [Tests](../../../tests/pipeline_eval/test_residual_schedule.py)

The runner verifies the exact saved detection bytes and recording authority. The two-scan replay then reproduces the complete ordered selected-probe document before reading any solver results. Alternative selections contain only originally verified factors. The offline result's identity binds the ledger, schedule and selected probes. The capture clocks, admitted windows, lane metadata, causal archive and region stay fixed for the matched solve. [Ledger capture](receiver_factor_ledger.py) · [Trial runner](residual_schedule_trial.py)

The saved per-lane CPU clocks cover the original native call as a whole. They include its raw scout and may include cancellation, residual discovery and both verifications. Summing those clocks on skipped requests gives an upper bound on the CPU that could be removed by suppressing only residual discovery on those lanes. The raw work remains necessary. A lane with an originally verified factor confirms that the original code reached cancellation and the residual scout. An empty factor row leaves that question open. The experiment did not run a native single-scan split or measure its CPU. [Clock collection](receiver_factor_ledger.py)

## Factor and selection comparison

| Ledger and arm | Residual requests / lanes | Observed raw / residual | Selected raw / residual | Lost / gained / changed selections | Upper bound on avoided native CPU (s) |
|---|---:|---:|---:|---:|---:|
| DS30-0016, two scans | 1,426 / 1,426 | 552 / 255 | 425 / 15 | 0 / 0 / 0 | 0 |
| DS30-0016, raw only | 0 / 1,426 | 552 / 0 | 410 / 0 | 31 / 1 / 4 | 4.631 |
| DS30-0016, conditional | 872 / 1,426 | 552 / 245 | 424 / 15 | 1 / 0 / 0 | 1.565 |
| South, two scans | 2,400 / 2,400 | 531 / 0 | 456 / 0 | 0 / 0 / 0 | 0 |
| South, raw only | 0 / 2,400 | 531 / 0 | 456 / 0 | 0 / 0 / 0 | 6.357 |
| South, conditional | 800 / 2,400 | 531 / 0 | 456 / 0 | 0 / 0 / 0 | 4.243 |

The 872 physical conditional requests comprise 480 sentinels and 392 activity extensions. Of the 554 suppressed requests, 163 had confirmed residual-scout work in the original call. The corresponding southern count is 354 of 1,600. The full original native clocks total 4.631 and 6.357 CPU seconds. These ceilings charge the combined call and exclude scheduler overhead and any change in fitting.

DS30-0016 lost one selected primary at visit 68, receiver 1. Both modes see the same single raw factor there. It received three continuation votes in the full history and two with the conditional donors. For the raw-only control, twenty previously selected primary rows and eleven selected residual rows lost their selection. Four selected residuals changed to the measured primary and one other primary gained a selection. [Full replay and solver receipts](measurements/residual-schedule.json.gz)

## Complete fitting on the physical selection

Each physical arm ran the same compact solver from selected factors through both calibration arms and the 179-point grid. Solve and grid CPU was 4.692 seconds with two scans, 4.576 seconds with only the raw scan, and 4.766 seconds with conditional residual discovery. The conditional case preserves both owner hashes, solver RMS values, objective replay, all numerical grid values and the recorded path. All three physical arms return both fixes. [Physical scoring reference](../location-audit/README.md)

| Physical arm | Published owners per calibration | `c = 0` error (km) | Fitted `c` error (km) | Solver RMS, zero / fitted (Hz) |
|---|---:|---:|---:|---:|
| Two scans | 109 | 1.644 | 1.662 | 109.375 / 109.479 |
| Raw only | 107 | 1.910 | 1.903 | 113.260 / 113.333 |
| Conditional | 109 | 1.644 | 1.662 | 109.375 / 109.479 |

All southern modes produce byte-identical solver inputs. The existing matched publication from those same detections has errors of 0.826 and 1.109 km and solver RMS of 6.503 and 6.392 Hz for zero and fitted calibration. The unchanged inputs make another fit redundant. The geographic comparison covers one physical recording and one public simulation. [Southern qualification](shared-publication.md)
