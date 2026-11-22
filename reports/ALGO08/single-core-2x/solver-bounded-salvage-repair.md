# One paired repair after salvage gate failures

The collapsed solver with one paired repair cut the DS30-0374 solve and grid from **28.445 to 21.877 CPU seconds**. Both repaired arms retained every stock observation and satellite assignment, plus two additional curved rows. The physical error changed from 1.855 to 1.848 km with zero calibration and from 1.935 to 1.928 km with fitted calibration. The southern simulation retained its exact owner map through the existing no-salvage path. [Paired measurements](measurements/collapsed-repair.json)

## Repair policy

The previous one-pass salvage candidate restored the missing curved identities and nominated the full predictive set on DS30-0374. Several tracks failed the subsequent paired fit, so the candidate fell back to the curved-only incumbent. The stock curved-only history loop already drops incompatible masks and retries, but it does not repair this combined curved and predictive proposal. [Earlier add-back](solver-salvage-addback.md) · [Stock history gates](../../../src/leo/analysis/localization_v3/history_policy.py)

The new candidate runs the same nomination and initial paired fit. If that pair fails, it removes the union of tracks marked incompatible across both arms, including both curved rows and predictive entries. The remaining aliases and identities carry into one paired refit. The repair recomputes the causal phase means and the family confidence and powers using its shared active mask. If a surviving curve lacks the original orbital-mode owner requirement, or a predictive entry loses its curved family or required receiver band, the candidate keeps the incumbent. It takes the same fallback on a failed repaired pair. Every accepted repair passes the original curved and predictive stock gates, including the paired phase-settlement test when predictive entries remain. The common masks and five-refresh budgets match between the calibration arms. Recording identity and position references are absent from the policy. [Implementation](../../../tools/pipeline_eval/variants/algo08_collapsed_repair.py) · [Collapsed solver](solver-collapsed.md)

## Matched saved replay

Each comparison starts on identical detector bytes with a common causal archive, regional offer, and exact standard selected packet. Both control and candidate use causal parser reuse and the existing salvage statistics. They ran as fresh processes on one low-priority pinned CPU with one numerical thread. The physical control ran first and the southern repair ran first. All runs evaluated the complete **179-point** grid and reproduced their selected endpoint objective with zero discrepancy. The timings stop at the completed grid. [Runner and owner audit](solver_linear_trial.py)

| Input and method | Solve and grid CPU (s) | Owners per arm | Satellites per arm | `c = 0` error (km) | Fitted `c` error (km) | Solver RMS `c = 0` / fitted (Hz) |
|---|---:|---:|---:|---:|---:|---:|
| DS30-0374, stock solver | 28.445 | 2,905 | 20 | 1.855 | 1.935 | 101.536 / 101.520 |
| DS30-0374, one-pass fallback | 18.874 | 2,379 | 18 | 2.287 | 2.350 | 101.415 / 101.378 |
| DS30-0374, paired repair | 21.877 | 2,907 | 20 | 1.848 | 1.928 | 101.496 / 101.482 |
| DS30-0374, endpoint screening | 21.198 | 2,882 | 19 | 1.793 | 1.884 | 101.174 / 101.219 |
| South containing, stock solver | 6.579 | 266 | 7 | 0.826 | 1.109 | 6.503 / 6.392 |
| South containing, paired repair route | 5.084 | 266 | 7 | 0.296 | 0.607 | 6.470 / 6.373 |
| South containing, endpoint screening route | 4.973 | 266 | 7 | 0.296 | 0.607 | 6.470 / 6.373 |

The physical first pair repeated the previous six zero-calibration and four fitted-calibration failures on the new matched detector receipt. The union removed six curved fragments and 160 active rows. No predictive entry failed. The repaired pair accepted all 411 predictive rows and 2,496 curved rows in each arm. The 2,907 owners included all 2,905 stock observation identities, with the same satellite and role at each shared point. Two additional curved observations came from one enlarged trim. The repaired endpoints moved 21 m and 9 m from the corresponding stock endpoints. Support and prior preparation consumed 0.640 CPU seconds and the full repair consumed 1.401 seconds. DS30's recording-specific reference was used only after fitting. [Physical reference audit](../../2026_11_21_ds30_full/reference-audit.json)

South containing had no masked curved rows and offered no predictive entries. Both experimental schedules therefore took the same existing collapsed path and reproduced one another's arms, exact owner map, optimizer paths, and numerical grid. All 266 stock identities retained their satellite and role. The case checks the path on a second location, with a containing offer. The repair itself was exercised on the physical input. [Public simulation scoring key](../regional-release/scoring-key.json)

## Cheaper screening at the incumbent endpoints

This variation evaluates the original curved and predictive gates once at each already-qualified incumbent endpoint. It uses the same recovered proposal, relinearizes surviving families from each arm's incumbent phase reference, and uses the causal mean for a new family. The frozen-position failures determine the same type of paired removal before one stock refit. This avoids optimizing the first joint proposal. The two exact endpoint gate evaluations took 0.112 CPU seconds. [Screening implementation](../../../tools/pipeline_eval/variants/algo08_collapsed_repair.py)

It passed the final stock gates on DS30-0374, keeping all 411 predictions and the same two additional curved points as the repair. It dropped a further 25-point stock curve that passed after the complete joint fit, losing one satellite from the final set. Both horizontal errors were lower on this recording. Those errors and the frequency residual improvement measure different effects on a smaller observation set. Screening saved 0.679 CPU seconds relative to the repair in this pair. Measured elapsed time was 25.015 versus 22.431 seconds for the repair. The selected post-fit repair for the next saved-case comparison preserves the otherwise-qualified curve. [Per-arm owner differences and timing](measurements/collapsed-repair.json)

## Reproduce

The copied solver source is experiment commit `ba830dcc3`. Run the `control`, `salvage`, `repair`, and `prefit` modes as appropriate. The component suite checks the exact paired removal, coupled support refresh, phase settlement and fallback, and the independent fixed endpoint screens. [Tests](../../../tests/pipeline_eval/test_algo08_collapsed_repair.py) · [Input pins](measurements/collapsed-repair.json)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock /tmp/leo-algo08v2-2x-bench/gauss.lock nice -n 15 ionice -c 2 -n 7 taskset -c 2 \
  env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONPATH="$PWD:$release/src:$release" "$release/venv/bin/python" -B \
  reports/ALGO08/single-core-2x/solver_linear_trial.py \
  "$mode" "$saved_detections" "$tle_archive" "$release/assets" "$offer" "$detector_digest"
```
