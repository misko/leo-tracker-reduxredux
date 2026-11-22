# Share canonical records through causal orbit preparation

The tables saved **0.42 CPU seconds on DS30-0016** and **0.49 seconds on the northern far offer** from saved detections through the completed grid. Temporal history, priors, both calibration decisions, owner hashes and every grid value matched the control.

The earlier scan-scoped parser already reuses validated SGP4 records across overlapping archive snapshots. A saved DS30-0374 profile of that variant still recorded 60,501 canonical TLE exports in 2.388 profiled seconds and 77 parses in 0.973 seconds from the repeated prior-bank path. The original and genuine-previous banks independently assemble and verify their prior receipts, and changes in selected labels repeatedly traverse that path. Forecast calibration ran once, in 0.297 seconds. [Earlier exact preparation experiment](solver.md)

The experiment keeps the canonical line pair returned by the stock exporter for each unique validated SGP4 record. The table lives through nominal, previous and phase-history preparation and is released before the forecast and fitting. The stock policies still choose each archived version and preserve its distinct collection time, epoch, provider and snapshot digest. They each read from the original read-only archive adapter with its existing byte verification. Canonical lines can be shared across those records because the formatting depends on the orbital element fields, while retrieval metadata belongs to the source record.

An independent table retains parsed catalogues keyed by the exact composed previous TLE text for the duration of the solve. The original receipt hash still runs before a prior bank uses a cached catalogue. Matching catalogue bytes can be shared across stock prior contexts, while different bytes get separate entries. Regional screening, both previous orbit policies, alignment, covariance priors, forecast and solver arithmetic continue through the original functions. The two tables are bounded to 65,536 canonical pairs and four prior texts. The accelerated SGP4 array copies its element input, so cached records are available for repeat bulk propagation. Nonaccelerated SGP4 uses the stock path. [Implementation](../../../tools/pipeline_eval/variants/algo08_causal_table.py) · [Component tests](../../../tests/pipeline_eval/test_algo08_causal_table.py)

Each process starts at verified saved detections and runs through the full selected packet grid with fixed-zero and fitted RF calibration. All modes use one low-priority CPU and the existing causal parser and salvage-statistics implementation. The runner captures nominal and historical input values before solving, then hashes them after timing. The audit checks temporal history and source receipts, final positions, owner hashes and all grid values. [Trial runner](solver_orbit_table_trial.py)

| Saved input and mode | Canonical exports | Prior catalogue parses | Preparation CPU (s) | Complete solve and grid CPU (s) |
|---|---:|---:|---:|---:|
| DS30-0016, control | 33,327 | 19 | 2.926 | 4.747 |
| DS30-0016, canonical lines | 11,915 | 19 | 2.608 | 4.360 |
| DS30-0016, composed priors | 33,327 | 2 | 2.785 | 4.487 |
| DS30-0016, both | 11,915 | 2 | 2.562 | 4.324 |
| North far, control | 40,794 | 54 | 3.190 | 11.412 |
| North far, both | 15,209 | 2 | 2.981 | 10.924 |

The inputs ran in table order on DS30 and in reverse on north far. Each cell is one run. The north-far canonical export work fell from 0.522 to 0.291 CPU seconds and its prior parse work from 0.286 to 0.010. The independent controls on the short physical recording also show some preparation timing variation outside the changed functions. Whole-solve comparisons include timing instrumentation.

| Saved input and arm | Horizontal error in both runs (km) | Solver RF RMS in both runs (Hz) | Published owners |
|---|---:|---:|---:|
| DS30-0016, `c = 0` | 1.644 | 109.375 | 109 |
| DS30-0016, fitted `c` | 1.662 | 109.479 | 109 |
| North far, `c = 0` | 52.455 | 37.951 | 228 |
| North far, fitted `c` | 52.491 | 37.533 | 228 |

The recorded positions and ownership reproduced the 179-point physical grid and 137-point simulated grid. Both north-far arms reproduced the stock false fixes. Every prepared source receipt and the full historical forecast matched. The component tests also check the archive read sequence, epoch/retrieval selection, and rejection of a changed prior text under its old digest. [Physical scoring reference](../location-audit/README.md) · [Simulation scoring reference](../regional-release/blind-scores.csv)

The DS30-0374 profile attributed 1.392 seconds to `previous_bank`, including the 0.973 seconds of parsing. Even free propagation and alignment within that path would save at most the remaining 0.419 profiled seconds. A reusable old orbit row must bind the actual old and nominal SGP4 records, UTC origin, and knot and phase evaluation inputs. Initial and genuine-previous policies can select different epochs for the same candidate. A previous-bank subset also changes the shared padding around the knot window. Forecast runs once per scan and took 0.26–0.33 CPU seconds in the two comparisons. Its adjacent version triples normally use different collection targets even when they share an element record. These timings bound the additional gain from reuse in preparation and prior alignment. [Original previous-bank calculation](../../../src/leo/analysis/localization_v3/orbit_modes.py) · [Forecast calculation](../../../src/leo/analysis/localization_v3/phase_prior.py)
