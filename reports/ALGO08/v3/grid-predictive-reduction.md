# Integrating predictive curve biases on the dense publication grid

The reduced predictive kernel saved **0.431 CPU seconds** across all 356 fresh calls on the dense DS30-0008 publication grid. The incumbent used **1.790 s** and the reduced kernel **1.358 s** on the same checked native posteriors. Both complete 179-point grids kept the original sampled minima, and their scores differed by at most **7.28 × 10⁻¹²**. Both renders produced eight identical decoded PNGs. The reduction leaves the dense solver above its 24-second CPU target. [Frozen protocol](grid-predictive-reduction-protocol.md) · [Per-node, preservation and rendering receipt](measurements/grid-predictive-reduction.json.gz)

## Where the 6.45 seconds go

The pinned full-catalogue signed solve spent **6.452 CPU seconds** in standard evidence. Its three disjoint grid handoff timers attribute **3.594 s** to geometry, robust curved calculation and native posterior export, **1.809 s** to predictive integration and **0.021 s** to the checked handoff or precision checks. The residual **1.028 s** covers the remaining geometric and assembly work, including predictions and the path outside the timed grain. These numbers exclude PNG rendering. The earlier dense path serialization cost 0.33 ms. The exact cross-arm projection bound on DS30-0374 was 0.137 s, with different final phase references and robust weights. Existing endpoint and compact geometry work makes those poor places to look for another multi-second saving. [Same-packet signed route](full-family-amortized.md) · [Archived path and output dependencies](../single-core-2x/solver-fit-dependency-audit.md) · [Cross-arm grid bound](../single-core-2x/solver-grid-cross-arm.md)

## Exact reductions within predictive integration

The existing handoff obtains a checked curved-posterior Cholesky factor in private-then-shared order. For each predictive row, it solves a triangular system and combines the whitened uncertainty with one new independent 300 Hz prior bias per predictive curve. The original dense predictive factorization therefore includes both the uncertainty columns and the separate curve-bias columns. The new kernel keeps that same covariance and drops a leading part of the triangular solve only where it verifies that the corresponding right-hand-side rows are exactly zero. A lower-triangular factor gives an exactly zero solution on that leading block. The remaining lower-right system supplies identical uncertainty coordinates in exact arithmetic. The dense posterior widths were 242 and 243. Only eight leading columns qualified in each arm. [Existing posterior handoff](../single-core-2x/solver-posterior-handoff.md)

The bias columns do not need to enter the dense Gram factor. On a curve, divide observations and design by each independent noise standard deviation. Its bias then contributes a rank-one covariance `I + v vᵀ` with elements `vᵢ = 300 / σᵢ`. Its symmetric inverse square root is `I − v vᵀ / [r(r+1)]`, where `r = √(1 + vᵀv)`. Apply it to that curve's new residuals and uncertainty rows, and add `log(1 + vᵀv)` to the log determinant. After integrating the 59 curve biases this way, the remaining Gaussian over the reduced posterior columns uses the same normalization and evaluates the quadratic from the residual and ridge penalty. The test keeps all 908 predictive rows. These transformations leave the exact marginal objective invariant. They run only on the diagnostic grid, where the required output is a scalar. They leave optimizer residual vectors, endpoints and predictive assignments outside the grid unmodified. [Reduced kernel](grid_predictive_reduction.py)

## Same-node comparison

One saved full-catalogue signed solve computed each checked curved posterior once. It ran both predictive kernels on every fresh node with alternating order, retaining the original cached endpoint values at the other two arm-locations. It publishes the reduced likelihood values in the experimental grid with unchanged coordinates and recovers the original stock grid from the directly observed original scores. The stock grid SHA-256 matches the archived one exactly, along with both original arm results, path, 4,440 owners per arm, roles, qualification and zero endpoint objective-replay differences. All grid evaluations were complete. The candidate changed five fixed-zero scores and one fitted score, each by at most 7.28 × 10⁻¹². The two sampled minimizing indices stayed at 0 and 1, respectively.

| Predictive or grid boundary | CPU s |
|---|---:|
| Incumbent predictive kernel, direct | 1.790 |
| Reduced predictive kernel, direct | 1.358 |
| Reduced whitening, curve-bias integration and remaining Gaussian | 0.588 / 0.315 / 0.454 |
| Common grid work and probe overhead | 4.158 |
| Reconstructed grid with incumbent kernel | 5.948 |
| Reconstructed grid with reduced kernel | 5.517 |

The last two rows subtract the other kernel's directly timed work from one dual-kernel grid and still include common observation overhead. The **7.2%** grid saving and the **0.431 s** difference describe this saved packet. Both versions rendered all eight required PNGs through the same standard renderer off-clock. The encoded and decoded RGBA hashes match for all plots, including the position grid. Both renders used the unchanged supplied region without evaluation coordinates.

## Whole-solve and input implications

The original full-catalogue solver used **28.680 CPU s**. Transferring the directly measured saving would leave **28.249 s**. Even removing the entire archived 1.809 s predictive kernel would leave **26.870 s**, still above 24 s. Removing all 6.452 s of standard evidence is a separate upper ceiling that would leave 22.228 s and would also remove required grid work. The dominant remaining measured grid cost is producing the distinct robust curved posterior on each arm and point. Existing exact reuse found no duplicate export calls in the earlier dense grid. [Complete-call reuse audit](../single-core-2x/solver-exact-likelihood-reuse.md)

For the historical warm dense raw path, half of the 113.02 s publication clock leaves 56.51 s. Using the archived 3.34 s terminal-to-exit allowance and transferring the reduced saved CPU one-for-one into elapsed time leaves about **24.92 s** for verified acquisition, versus **52.70 s** originally. That is a cross-run budget, not a new elapsed measurement. The measured grid change is too small to close the gap by itself. [Historical dense stage clocks](first-55/stage-clocks.csv)

## Reproduce

Run one saved dense solve with the installed v3 tools and the pinned causal archive. The two PNG renders are outside the measured solve and require no raw recording access. Eight focused unit tests passed.

```bash
bench=/tmp/leo-algo08v2-2x-bench
tree=/home/mouse9911/gits/leo-tracker-reduxredux
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
here="$PWD/reports/ALGO08/v3"
lock() {
  flock -x "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 timeout --signal=INT 65s \
    env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="$here:$payload:$release/src:$release:$PWD" "$@"
}
lock "$release/venv/bin/python" -BPs "$here/grid_predictive_reduction_trial.py" "$new_output"
lock "$tree/.venv/bin/python" -BPs -m pytest -q tests/pipeline_eval/test_grid_predictive_reduction.py \
  tests/pipeline_eval/test_algo08_posterior_handoff.py
```
