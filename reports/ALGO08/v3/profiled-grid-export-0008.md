# Checked posterior export on one physical DS30-0008 likelihood

The profiled export passed every frozen numerical gate on the only enrolled physical operand. It took **13 precision updates instead of 39** and returned a checked factor with **0.010952 Hz** maximum conditional residual difference. The operand is from the fitted-`c` arm. It supplies a native kernel transfer for one physical likelihood. The current field path and its standard map were outside the comparison. [Frozen protocol](profiled-grid-export-0008-protocol.md) · [Numerical and timing receipt](measurements/profiled-grid-export-0008.json)

The original all-full archived DS30-0008 `history_position` capture holds **3,574 × 243** normalized design values. The signed RF coefficient is inserted as hardware column 8 in the pinned fitted-arm source. In the fixed-zero source, column 8 is the first smooth feature for radio 1 and structurally zero on radio 2. In the immutable sample, column 8 is nonzero on **all 1,594 radio-2 rows**. The remaining **1,980 rows** belong to radio 1. Column width alone was not used for the arm classification. The capture preserved one such history likelihood, with no enrolled fixed-zero counterpart. [Input and runtime pins](profiled_grid_export_0008.py) · [Original capture and unexported comparison](profiled-gamma.md)

| Frozen check | Observed absolute change | Gate |
| --- | ---: | ---: |
| Curved negative twice ELBO | 1.965e−9 | 1e−5 |
| Maximum conditional residual | 0.010952 Hz | 0.02 Hz |
| Constructed predictive slice loss | 0.000297313 | 0.01 |

Both factors independently reproduced their permuted precision matrices at the frozen elementwise tolerances. Their respective maximum absolute reconstruction errors were 1.431e−6 and 4.768e−7 on the matrix's scale. All **68** rows of the deterministic every-53rd-row slice came from the authentic input. The slice uses the fixed validation construction from the simulation study, including its latent member-count proxy. It tests the factor used in a predictive integration. It has no associated map location, native predictive owner roster or geographic interpretation. [Checker](profiled_grid_export_check.py) · [Earlier simulation result](profiled-grid-export.md)

## Paid callback timing

The first **55 s** watch saw no official export updates and made zero shared-lock attempts. A separately authorized watch admitted one timed child on a fresh DS30-0277 storage deferral. The child authenticated the same saved proof and binaries. It ran stock, proof, proof, stock with one initially warmed provider on CPU 2, nice 15, idle I/O and a single numerical thread. Both candidate calls activated the same checked factor, with zero native replays or Python fallbacks. No waveform, orbit archive, separate sample, map or solver ran. [Admission and per-call receipts](measurements/profiled-grid-export-0008.json)

| Warm callback boundary | Stock median | Profiled median | CPU reduction |
| --- | ---: | ---: | ---: |
| Checked capture CPU | 12.477 ms | 4.845 ms | 61.2% |
| Enclosing bound CPU | 13.635 ms | 6.028 ms | 55.8% |
| Enclosing bound wall | 13.636 ms | 6.028 ms | — |

The checked capture includes the native export and Python bridge. The enclosing bound also includes the original argument validation and readout. Neither clock includes the constructed predictive score or a grid. The capture reductions were **7.792 and 7.473 ms** in the two orders. Preparation, authentication and cache priming took **47.394 ms CPU**. Proof-context binding separately cost **0.189–0.255 ms CPU**. The full command took **1.213 s elapsed / 1.072 s CPU** through exit, with **73 major faults and 74,088 input blocks** process-wide. The enrolled numerical array was fully resident in tmpfs. The process counters include startup and runtime reads without file attribution. The older **13.247 → 5.558 ms** values measured a separate likelihood kernel without factor export. [Earlier unexported witness](measurements/profiled-gamma-witnesses.json)

To verify the same operand, use the pinned one-thread release Python and repository import path, then run `-B -m reports.ALGO08.v3.profiled_grid_export_0008`. The one-shot timing entry accepts the resulting JSON and its digest via `--physical-0008` during an eligible shared-slot deferral. Seven focused tests passed, including the arm classification and rejection of a deferral for another official case. [Admission entry](profiled_grid_export_admission.py) · [Tests](../../../tests/pipeline_eval/test_exact_shared_solver.py)
