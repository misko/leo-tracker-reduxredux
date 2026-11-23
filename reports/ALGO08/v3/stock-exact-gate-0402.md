# Exact constrained gate preparation in named DS30-0402

The saved named publication used **64.041 CPU s** in its numerical solve with prepared gates, versus **68.774 s** in the archived stock replay. Both calibration positions and RF fits, the rank-one finalist, all **4,821 ordered owners per arm**, the 179-point grid and path, and all eight encoded and decoded PNGs reproduced. The **4.733 CPU s** difference is a single candidate-to-archived-control comparison on DS30-0402. [Frozen protocol](stock-exact-gate-0402-protocol.md) · [Verified publication receipt](measurements/stock-exact-gate-0402.json.gz)

## Original gate and proposal work

Inside the installed `family_cavity.constrained` call, the binding prepares the exact time-dependent variables used by `batch_noise_screen`. The screen keeps the original least-squares fit, residual reductions, six diagnostic fields and comparisons. The white profile binds the verified stock diagonal whitening matrix and its fixed contractions for 1,000 Hz curved and 300 Hz predictive bias priors. It keeps every original profile field, including Gaussian cost, the rounded alias and innovation vector. Its prepared state lasts one proposed configuration. Original admission and final gates use the stock functions. The source and callable-identity checks bind this trial to the named release. [Binding and runner](stock_exact_gate_0402.py) · [Exact screen unit sample](named-roster-0402.md)

| Candidate counter | Observed |
|---|---:|
| Constrained proposals / phase fits | 1 / 10 |
| Unique inner gate visits | 393 |
| Prepared polynomial screens / time preparations | 82,137 / 124 |
| White profiles / diagonal preparations | 48,732 / 124 |
| Whitening requests / cached white matrices built | 33,405 / 85 |
| Unsupported screen, profile or whitening fallbacks | 0 |

Preparing the 124 time bases took **2.290 ms CPU**. The full constrained call took **15.128 CPU s**, including **14.973 s** in the ten stock SLSQP fits with prepared gates. All three original cavity proposal summaries reproduced, including both arms' corrected losses, RF RMS, terminal phase changes, failed gate counts and rejected decisions. The old instrumented constrained call used **21.261 wall s**. That older subclock includes profiler overhead, so it does not isolate the gain inside the constrained stage. The instrumentation preserves total visits and terminal diagnostics. [Original named stage accounting](named-roster-0402.md)

## Saved publication and timings

| Boundary | Archived named | Exact gates | Difference |
|---|---:|---:|---:|
| Numerical solve CPU | 68.774 s | 64.041 s | −4.733 s |
| Numerical solve elapsed | 68.825 s | 64.084 s | −4.741 s |
| Through worker exit CPU | 73.254 s | 68.508 s | −4.745 s |
| Through worker exit elapsed | 73.351 s | 68.589 s | −4.763 s |

| Calibration | Archived and reproduced horizontal error | Reproduced RF RMS | Conditional / predictive owners |
|---|---:|---:|---:|
| `c = 0` | 0.863651 km | 100.672203 Hz | 4,150 / 671 |
| Fitted `c` | 0.860302 km | 100.576460 Hz | 4,150 / 671 |

The independent scorer checked the terminal digest, arm outputs, ordered owners, screened rank and scores, the scientific digests for the complete grid and path, their position-PNG bindings, and each image's dimensions and encoded and decoded hashes. The original saved acquisition handoff ran once with the signed 20 ms packet, original offer and 48-snapshot causal archive. The two saved processes ran on the same low-priority CPU 2 slot with one numerical thread in different sessions. Linux reported **15,488** input blocks for stock and **3,400** for the candidate. This comparison includes cache and session variation. The two gate preparations ran together, so the full timing does not attribute separate savings to them. [Archived stock comparison and scientific bindings](prospective-0402-solver.md)

The full candidate ran once from `aa6a0b01d`. The initial post-exit comparison rejected tuple-valued image dimensions against their equal archived JSON lists. The corrected scorer normalized the representations and verified the original completed output. Twenty focused and adjacent tests passed. The tests cover byte equality of every profile field at both bias widths, near alias rounding and noncontiguous layouts, fallback for correlated whitening, changed time supports, and binding restoration. [Component tests](../../../tests/pipeline_eval/test_stock_exact_gate_0402.py)

Run `stock_exact_gate_0402.py launch NEW_TMPFS_ROOT` with the pinned release interpreter, the original staged request and the shared Gauss lock. Then run `stock_exact_gate_0402.py evaluate NEW_TMPFS_ROOT NEW_RECEIPT.json` against the sealed archived named score and original gate observations. The completed worker and scored receipt remain under `/dev/shm/leo-v3-0402-exact-gate-run01` and `/dev/shm/leo-v3-0402-exact-gate-scored01.json`.
