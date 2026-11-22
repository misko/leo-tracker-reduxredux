# Share the broad orbital projections across held families

On DS30-0374 the shared projection removed **3.997 million of 12.262 million** sky cells and reduced the cavity nomination from **3.785 to 3.070 CPU seconds**. Full saved-detection-to-grid CPU moved from **28.700 to 28.240 seconds**. All held masks, coarse terms, fine nominations, final owners and both calibration positions matched the control.

Each held family uses the same fixed receiver trial point, causal sky and three per-satellite phase vectors for broad nomination. Its observation times can overlap the held times of other families. The prototype inspects the original active mask and predictive entries, builds an exact union of the requested timestamps, and reuses the stock Doppler and elevation fields at the shared times. It puts columns back in each family's original order and layout before calling the original correlated score. The cache key includes the sky inventory bound for this nomination, receiver point, and exact timestamp and phase values. The prior row-tiling experiment projected each held family's dates separately. Here time tiles bound the temporary interpolation work while the union removes repeated orbital calculations across families. [Prior row tiling](../../../tools/pipeline_eval/variants/v5_nomination_memory.py) · [Shared projection](../../../tools/pipeline_eval/variants/algo08_cavity_projection.py)

The table stores up to 128 MiB of projected columns. If the union exceeds that limit, it shares just the repeated columns when they fit, and otherwise runs the stock projection. One immutable sky snapshot supplies the original interpolator. Every catalogue row, held-family exclusion, five-step nuisance fit, correlated Gaussian nomination, stable order and shortlisted fine prediction remains in the original code. Fine predictions have their own updated satellite phases. Sharing their broad-phase state would change that likelihood. The component tests check both memory routes, exact float values and signed-zero timestamp identity across two geographies, and the full holdout eligibility used to build the union. [Component tests](../../../tests/pipeline_eval/test_algo08_cavity_projection.py)

The earlier DS30-0374 profile attributed 1.179 seconds to building the 20 excluded family models and another 1.510 seconds to 160 shortlisted candidate predictions. An exact Gram downdate at the first common phase expansion would leave most of that schedule intact. Subsequent phase references and robust weights depend on the actual data surviving each family's exclusion. The comparison targets the repeated broad geometry and preserves that numerical schedule. [Held-family model](../../../src/leo/analysis/localization_v3/family_cavity.py)

Runs start at the same verified saved detections and use the same offered region, causal archive, current exact parser and salvage optimizations, and one pinned low-priority CPU. The audit hashes every coarse candidate's score, alias and phase statistic, each held/excluded observation mask, and the full fine nomination output. The separate selected packet check covers both calibration arms, owner hashes, endpoint score replay and the complete grid. [Trial runner](solver_cavity_projection_trial.py)

| Saved input | Held timestamps, requested / distinct | Sky cells, control → shared | Projection CPU (s) | Nomination CPU (s) | Solve and grid CPU (s) |
|---|---:|---:|---:|---:|---:|
| DS30-0374 | 2,905 / 1,958 | 12,262,005 → 8,264,718 | 1.705 → 1.027 | 3.785 → 3.070 | 28.700 → 28.240 |
| North far | 228 / 114 | 1,073,196 → 536,598 | 0.167 → 0.086 | 0.666 → 0.586 | 11.588 → 11.498 |

The physical candidate ran first and the alternate-region control ran first. These are single pairs. The retained fields occupied 126.1 MiB during physical nomination and 8.2 MiB on north far. The process peaks moved from about 991.2 to 995.1 MiB and 939.0 to 938.9 MiB, respectively.

| Saved input and arm | Published owners in both runs | Horizontal error in both runs (km) | Solver RF RMS in both runs (Hz) |
|---|---:|---:|---:|
| DS30-0374, `c = 0` | 2,905 | 1.855 | 101.536 |
| DS30-0374, fitted `c` | 2,905 | 1.935 | 101.520 |
| North far, `c = 0` | 228 | 52.455 | 37.951 |
| North far, fitted `c` | 228 | 52.491 | 37.533 |

All three cavity hashes matched on both inputs, including ordered fine predictions. The physical solver reproduced all 179 grid evaluations and north far reproduced all 137. The north-far solver made its original cavity offer and published the same two false fixes. The earlier physical scoring reference and the separately held simulation reference were used after the solves. [Physical reference](../location-audit/README.md) · [Simulation scores](../regional-release/blind-scores.csv)

Eliminating the entire measured 3.785-second nomination would bound the physical saved-detection solve and grid speedup at 1.15×. The shared projection delivered 1.02× in that comparison while retaining the original evidence.
