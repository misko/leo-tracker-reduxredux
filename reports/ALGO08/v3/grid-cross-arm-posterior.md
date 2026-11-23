# Exact cross-calibration reuse ceiling in the dense curved grid

Deleting the more expensive native posterior export at every matched location would save at most **1.000 CPU seconds** on the genuine dense short DS30-0008 grid. Giving away that arm's entire bound adapter, including validation and Python readout, raises the ceiling to **1.200 seconds**. Both arms combined spent **1.931 seconds** inside the native exports. The two-second target is beyond this boundary even before accounting for their different scientific inputs. The experiment stopped after the one saved-grid audit. [Frozen protocol](grid-cross-arm-posterior-protocol.md) · [Per-point clocks and operand counts](measurements/grid-cross-arm-posterior.json.gz)

| Timed boundary | Both arms CPU s | More expensive native or curved peer per location CPU s | Fresh unmatched endpoint CPU s |
|---|---:|---:|---:|
| Complete curved callback | 4.220 | 2.168 | 0.0201 |
| Installed native bound adapter | 2.329 | 1.200 | 0.00905 |
| Checked native export inside the adapter | 1.931 | 1.000 | 0.00710 |
| Argument validation inside the adapter | 0.185 | 0.100 | 0.00086 |

The observer measured the original installed calls. At each of 177 locations with two fresh evaluations, the ceiling grants the entire cost of whichever arm was more expensive at the stated boundary. Each arm's own endpoint reused its existing calculation, leaving one fresh export of the other arm at each endpoint. Those unmatched exports have no same-coordinate donor. The clocks are inclusive and nested. The wider 2.168-second curved allowance would also discard receiver-specific orbit/design assembly, conditional RF residuals, and curved readout. Those are different computations for the two arms. The table grants free lookups and copying and includes work whose inputs disagree. [Original posterior export](../../../tools/pipeline_eval/variants/algo08_posterior_handoff.py) · [Original design assembly](../../../tools/pipeline_eval/variants/algo08_curved_design.py)

## What actually matches

The original `c = 0` and fitted models retained the same **3,661 curved observations in 82 noise groups**, with identical owner assignments, aliases, support, times and native group order. They also shared noise scales, group powers, initial Gamma shapes and common prior index assignments. Their final phase references differ by up to **0.07537 s**. Eleven of 38 family references agree, and none of those equal references is used by a retained curved observation.

The following counts hold at every one of the 177 co-evaluated locations.

| Operand or dependency | Exact matching count |
|---|---:|
| Complete response rows | 0 / 3,661 |
| Rows whose entire common design matches | 0 / 3,661 |
| Matching common design cells | 941,525 / 955,521 |
| Matching nonzero common design cells | 54,915 |
| Original exported factor widths, zero / fitted | 261 / 262 |
| Rows with a nonzero fitted RF column | 3,661 / 3,661 |
| Noise groups with a nonzero common receiver-intercept–`c` product | 82 / 82 |
| Pre-update Gram entries with identical common operands | 18,450 / 32,134 |
| Pre-update right-hand side entries with identical operands | 0 / 1,622 |
| Noise groups with all common active design columns identical | 0 / 82 |
| Original final noise precision slots with identical values | 0 / 82 |

Common hardware, smooth receiver and track-constant values leave an exact subset of fixed products. Most matching cells in the dense feature matrix are zeros. The installed sparse per-group contraction already skips inactive columns. Its pre-update Gram and right-hand side are computed once per call, before all robust updates. Float identity on normalized input columns gives 57.4% eligible pre-update Gram entries and zero complete right-hand side entries. The eligibility count prices every matching entry, including mirrored entries, and assumes nothing about its fraction of native CPU. A previous fixed-Gram comparison measured 0.261 → 0.246 seconds on a different dense input even after eliminating about four fifths of its tracked products. [Prior fixed Gram study](../single-core-2x/solver-fixed-gram.md)

The nominal first noise weights agree across arms, while the phase-dependent design, measured responses and fitted-column couplings change the first posterior. The Gamma updates use each arm's conditional residual energy and posterior covariance. Every one of the 14,514 final active weight comparisons changed. Reusing a fixed principal block before weighting cannot make an arm's conditional factor, inverse checks, residual energy, or determinant interchangeable. A different joint algorithm could exploit that structure at changed arithmetic. This audit establishes the ceiling for direct reuse of the measured exact posterior or its sufficient arrays. Earlier cross-arm projection and robust warm-start experiments price distinct boundaries. [Cross-arm projection audit](../single-core-2x/solver-grid-cross-arm.md) · [Warm starting robust fits](../single-core-2x/solver-robust-updates.md) · [Current Gamma fit experiment](profiled-gamma-live.md)

The saved audit matched the 179-point ordered grid, numerical path, 4,367 owner and role rows per arm, both endpoints and RF RMS values, the original signed route and 25-probe geographic decision. Each endpoint replay error was zero. No inference path, optimization kernel, or location was changed. Four component tests passed. [Runner](grid_cross_arm_posterior_trial.py) · [Component tests](../../../tests/pipeline_eval/test_grid_cross_arm_posterior.py)

## Reproduce

Run the authenticated saved audit in a fresh directory with the original installed graph and fused projector. The original `ceiling.json` SHA-256 is `72438e15f670644c795c15d6024d9619a9da3d07d40334e4257eb11db1b08085`. The receipt pins the archived same-input numerical control and records all 177 exact paired comparisons.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
out=$(mktemp -d /var/tmp/leo-grid-cross-arm-posterior.XXXXXXXX)
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$PWD/reports/ALGO08/v3:$payload:$PWD:$release/src:$release" \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs reports/ALGO08/v3/grid_cross_arm_posterior_trial.py "$out/trial"
```
