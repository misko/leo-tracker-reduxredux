# Certified rejection of unpublishable salvage supports

On the saved short physical input, a two-endpoint bound eliminated **317 of 736** fine salvage profiles. Running the existing cheap gates before the polynomial noise screen eliminated every noise screen in this case. Fine salvage CPU fell from **0.114 to 0.048 seconds**. Both calibration positions, salvage alternatives, owner hashes and the full grid reproduced exactly.

## Where an objective bound applies

For one diagonal-noise support and one phase, let `rᵢ` be measured minus predicted frequency, `σᵢ` be fixed observation noise, and `P` be the native frequency period. Stock selects an integer from the unweighted mean of the entire support. It then minimizes the weighted squared residual with one Gaussian constant `b` of width `B = 1000 Hz`. The score includes the full-support normalization `N = log1p(B² Σᵢ 1/σᵢ²)` and the phase penalty `φ²/9`. [Original curve profile](../../../src/leo/analysis/research/retained_track_likelihood.py)

On any two indices `i, j`, dropping all other squares and allowing an unrestricted common offset leaves the lower bound `L = (rᵢ−rⱼ)² / (σᵢ²+σⱼ²) + N + φ²/9`. The shared native alias cancels in the difference. An unrestricted weighted centered sum over a subset gives the same type of bound with additional points. A strict lower-bound separation from an exactly scored incumbent can discard a losing phase in real arithmetic. A binary64 implementation would need to round the bound outward and keep every unresolved tie in the original order. The default coarse `argsort` also requires an exhaustive tie fallback because moving other values can change its equal-key order.

Re-running stock alias selection on a prefix does not give that lower bound. With raw differences `P/2 + [100, −120, 300] Hz` and fixed scales `[40, 300, 400] Hz`, the two-point prefix selects alias zero and costs 12921.769. The full support selects alias minus one and costs 12878.144, despite including another nonnegative square and more bias information. In broad discovery, the exact score and calibrated eligibility are also separate consumers. Some association outputs consume the total number of feasible candidates. Beating a cost incumbent alone does not establish that a losing candidate can be removed from those counts. [Discovery score consumer](../../../src/leo/analysis/localization_v3/scan.py) · [Counterexample tests](../../../tests/pipeline_eval/test_algo08_salvage_bound.py)

## What the prototype can reject exactly

An accepted phase also needs `|b| ≤ 3000 Hz` and `|rᵢ + kP − b| ≤ 6σᵢ` at every selected timestamp before the original candidate can be emitted. Its real-arithmetic score is therefore at most `36n + 9 + N + φ²/9`. A stronger inexpensive test follows directly from the two endpoint residual limits. Their difference cancels the same alias and bias, so any passing phase needs `|rᵢ−rⱼ| ≤ 6(σᵢ+σⱼ)`. If every phase either has an already below-horizon endpoint or violates that bound, the complete support produces no alternative. The experiment expands the residual magnitude limits with `nextafter` to allow for the original rounded division, alias addition and bias subtraction. It compares the resulting upper bound with an outward-rounded lower bound on the raw endpoint difference. Unsupported arithmetic and unresolved phases go through the original full loop.

Within each unresolved support, the frozen loop selects the minimum penalized cost over all visible phases before checking its gates. Filtering a single ineligible phase can promote a higher-cost phase the frozen loop would never test. One constructed pair gives costs 53.84 and 99.67, with maximum standardized residuals 6.417 and 2.750. The frozen loop picks the first and rejects the support. The prototype only skips a complete support or skips a noise screen when the original winner already fails an independent existing gate. It preserves the phase order and the final stable sort by descending support size and ascending cost. [Original fine salvage](../../../tools/pipeline_eval/variants/v5_tiled_salvage.py) · [Prototype](../../../tools/pipeline_eval/variants/algo08_salvage_bound.py)

## Bounded measurement

The saved DS30-0016 detector receipt was replayed through the complete solver and grid with causal parsing and coarse salvage statistics enabled in all modes. Each run used the same supplied region and archive and one low-priority pinned CPU. The benchmark contains one inspected salvage fragment. Every inspected support in that fragment failed a cheap existing gate. The component tests additionally compare accepted alternatives and exact ties.

| Mode | Fine supports considered | Full phase profiles | Noise screens | Fine CPU (s) | Complete solve and grid CPU (s) |
|---|---:|---:|---:|---:|---:|
| Control | 736 | 736 | 736 | 0.114 | 4.745 |
| Defer noise screen | 736 | 736 | 0 | 0.060 | 4.563 |
| Defer screen and reject impossible supports | 736 | 419 | 0 | 0.048 | 4.596 |

The 11 ms incremental fine-stage gain from the bound is smaller than the observed whole-solve timing variation. All modes published the same 109 owners per arm and the same 179 grid points. The `c = 0` position had 1.644 km error and 109.375 Hz solver RMS. The fitted-`c` position had 1.662 km error and 109.479 Hz RMS. [Trial runner](solver_salvage_bound_trial.py) · [Physical reference](../location-audit/README.md)

The prior DS30-0374 profile puts the complete coarse salvage scoring boundary at 0.067 seconds after its existing exact-statistics change. Fine salvage covers 2.492 profiled seconds, of which 0.621 is phase profiling and 1.253 is the polynomial noise screen. These are upper bounds on work removable from their respective measured boundaries before charging a pruning check. The full coarse search and preexisting discovery work remain necessary for this implementation. The measurements do not support a material whole-solver speedup from this bound. [Existing salvage timings](solver.md) · [Earlier discovery timings](solver-discovery.md)
