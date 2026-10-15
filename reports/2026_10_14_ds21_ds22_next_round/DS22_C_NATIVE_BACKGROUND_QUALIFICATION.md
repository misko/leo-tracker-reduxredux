# Native C background: both actual-data qualifications pass, no fits yet

The source-frozen native sample-rate background wrapper passed **192 full-objective evaluations and zero optimizer calls** on DS22 C053/C075. This qualifies numerical identity, normalization and derivatives; it establishes no predictive improvement or position benefit.

| Qualification | C053 | C075 |
|---|---:|---:|
| Original no-clock native candidates | 44 | 87 |
| Native sample-rate circle | 2.5 MHz | 2.5 MHz |
| Full objective evaluations | 96 | 96 |
| Wall seconds, including preparation/audits | 39.534 | 50.599 |
| Maximum raw source value/gradient discrepancy | 2.47e-12 | 7.28e-12 |
| Maximum conditional-uniform value/gradient discrepancy | 1.14e-13 | 4.55e-13 |
| Maximum empirical directional FD absolute discrepancy | 0.000151222 | 0.000197211 |
| Frozen training-fold window counts | 1818 / 1648 | 1520 / 1635 |

Both complete units exited successfully within internal120/external135/140-second limits. All 36 finite-difference directions per case passed the prespecified absolute0.001 plus relative0.0001 tolerance, without a changed hard visibility pattern. Each objective used one native orbit prediction; there were no extra explicit predictor calls. Counts describe full objective evaluations, not nested pure arithmetic helper invocations.

Uniform density exactly nests the original raw native objective, all physical/nuisance gradients and satellite posteriors. The conditional uniform wrapper also nests the existing native conditional core. Empirical-background posterior accounting and unchanged physical/nuisance prior contributions close. The estimator normalizes **within each lane's own-fold training-window mass**, allocating total weight one across existing waveform-weighted alternatives; it does not count alternatives as extra windows. Missing/unseen lanes remain uniform. Both native models retain their original groups, integer receiver lifts, branch evidence, timestamps and no-clock layout.

The 2.5 MHz density is not B's approximately227 kHz alias density: there is no unintended eleven-fold change in uniform odds. The full-origin C053 conditional support mass is one to numerical precision; C075 includes a minimum0.982484948 in one fold, which is explicitly retained in both matched conditional arms. The unchanged support-mass algebra is independently tested against `model_c_visibility_mass.support_mass`, with full, partial and absent signal support. Component quadrature integrates both nonuniform background and signal mixture over a **common circular translation of fixed branch offsets**. This is not a generative likelihood for the detector set, branch availability or waveform evidence. The empirical reference includes real signals and is not verified clutter.

The three source states were prespecified full/LOW/HIGH training-selected complete states: exact transported original C053 half functions on its44-bank full frame, and corresponding C07587-bank no-clock half views. Histogram estimation used only each own fold, with saved randomized whole20s mapping, seed20261014 and no redraw. Discovery, bank, frame and source states remain full-derived; future opposite-fold results would therefore be conditional development evidence. No reference, original held or locked observations were read.

Implementation/source commit **7e512af7b**: `native_empirical_background.py`, `native_background_objective.py`, and `ds22_native_background_qualification.py`. Nine component/runner tests and Ruff passed before freezing. Recursive AST import closure binds316 local imported sources, including imported child modules and relative imports, combined with the original authorities for totals472/488 source files. Additional pure support-mass/permutation tests leave these frozen sources and original qualification receipts unchanged.

Runtime root `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-native-background-qualification-v1`:

| Binding SHA256 | C053 | C075 |
|---|---|---|
| Protocol | c5ffd699de15fa45a5c17c13f37236dee61b82badc4581c71c4072ead38663dd | 42bd883de5ff391cf862b33319c3c28cdc8dfe69004de9f71a0dc04a782483c5 |
| Result | 03e4749ef78b576d71dab51cb71995302a33813b4c9ccff2314239e368163f61 | d81a333d41e135ad3be2d38dcc4822430f525567863ee44937df1956d3a96749 |
| Termination | 117e401cc738e6023f18f1736531f6e23c960497a6905611b9d3b637a408e71f | 844ef8edb00d45674d9225ec47ec200a5509f551934d4ebb83cfc7ff72d7b6c7 |

A separately reviewed matched predictive experiment is required before any localization claim. No new optimizer cycle on the old C053 basin was launched.
